// Tarjeta "Mapa de clientes" de la pantalla Pedidos (reparto y admin): el mapa de la zona (arranca en San Juan y se
// encuadra solo sobre los clientes) con un pin por cada cliente que tiene la ubicación cargada y, aparte, el pin del
// celular de la cuenta de reparto, que se actualiza solo mientras el mapa está abierto.
//
//   - Al tocar un pin de cliente: nombre, dirección, localidad, cuántos pedidos tiene por entregar, "Cómo llegar" y,
//     si tiene un pedido por entregar, "Ver pedido" (abre el detalle en la lista de arriba).
//   - Pin ámbar = cliente con pedidos por entregar; azul = el resto; verde con pulso = el reparto (gris si hace más de
//     2 minutos que no llega su posición).
//
// El mapa lo dibuja Leaflet (vendor/leaflet/, copiado al repo) sobre mosaicos de OpenStreetMap: sin claves. Los
// mosaicos necesitan señal; sin ella el mapa queda gris pero el resto de la pantalla anda igual. Los datos vienen de
// GET /mapa/clientes (una vez al abrir) y GET /mapa/reparto (cada 15 s mientras está abierto). La posición del
// reparto la manda su celular (seguimiento.js).
(() => {
  const $ = (id) => document.getElementById(id);
  const pantalla = $("pantalla-gestion");
  const btnMapa = $("btn-mapa");
  const zona = $("mapa-zona");
  const contenedor = $("mapa-clientes");
  const elEstado = $("mapa-estado");
  const elAviso = $("mapa-aviso");
  const elCuenta = $("cuenta-mapa");

  const SAN_JUAN = [-31.5375, -68.5364];
  const ZOOM_INICIAL = 12;
  const ZOOM_MAX_AL_ENCUADRAR = 15;
  const INTERVALO_REPARTO_MS = 15000;
  const REPARTO_VIEJO_SEG = 120; // más que esto sin posición nueva: se ve gris, "hace X"

  let mapa = null;
  let capaClientes = null;
  let capaReparto = null;
  let clientes = []; // los que tienen ubicación (GET /mapa/clientes)
  let pedidos = []; // lo que falta entregar (lo avisa gestion.js)
  let abierto = false;
  let encuadrado = false; // el mapa se encuadra sobre los clientes una sola vez; después lo maneja quien lo mira
  let temporizador = null;

  // ── piezas ───────────────────────────────────────────────────────────────
  function el(tag, clase, texto) {
    const nodo = document.createElement(tag);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
  }

  function icono(clase) {
    return L.divIcon({ className: `pin ${clase}`, html: "<span></span>", iconSize: [20, 20], iconAnchor: [10, 10], popupAnchor: [0, -12] });
  }

  function hace(seg) {
    if (seg < 5) return "ahora";
    if (seg < 90) return `hace ${seg} s`;
    const min = Math.round(seg / 60);
    return `hace ${min} min`;
  }

  // Los pedidos por entregar de cada cliente, en el orden de la lista.
  function pedidosPorCliente() {
    const por = new Map();
    for (const p of pedidos) {
      if (!por.has(p.id_cliente)) por.set(p.id_cliente, []);
      por.get(p.id_cliente).push(p);
    }
    return por;
  }

  function popupDe(c, suyos) {
    const caja = el("div", "popup-cliente");
    caja.appendChild(el("strong", null, c.nombre || `Cliente ${c.id}`));
    const donde = [c.direccion, c.localidad].filter(Boolean).join(" · ");
    if (donde) caja.appendChild(el("span", null, donde));
    if (suyos.length > 0) {
      caja.appendChild(el("span", "popup-pedidos", `${suyos.length} ${suyos.length === 1 ? "pedido por entregar" : "pedidos por entregar"}`));
    }
    const acciones = el("div", "popup-acciones");
    const enlace = el("a", null, "Cómo llegar");
    enlace.href = `https://www.google.com/maps/search/?api=1&query=${c.lat},${c.lng}`;
    enlace.target = "_blank";
    enlace.rel = "noopener noreferrer";
    acciones.appendChild(enlace);
    if (suyos.length > 0) {
      const ver = el("button", null, "Ver pedido");
      ver.type = "button";
      ver.addEventListener("click", () => {
        mapa.closePopup();
        document.dispatchEvent(new CustomEvent("mana:abrir-pedido", { detail: suyos[0].id_pedido }));
      });
      acciones.appendChild(ver);
    }
    caja.appendChild(acciones);
    return caja;
  }

  function avisar(texto) {
    elAviso.textContent = texto || "";
    elAviso.hidden = !texto;
  }

  // Clientes con pedidos por entregar a los que todavía les falta la ubicación: no están en el mapa y conviene decirlo.
  function avisoDeFaltantes() {
    const sin = new Set(pedidos.filter((p) => p.ubicacion_lat == null && !p.ubicacion_maps).map((p) => p.id_cliente));
    if (sin.size === 0) return "";
    return sin.size === 1
      ? "1 cliente con pedidos por entregar todavía no tiene ubicación: no sale en el mapa. El reparto la guarda al llegar."
      : `${sin.size} clientes con pedidos por entregar todavía no tienen ubicación: no salen en el mapa. El reparto la guarda al llegar.`;
  }

  // ── dibujo ───────────────────────────────────────────────────────────────
  function dibujarClientes() {
    if (!mapa) return;
    capaClientes.clearLayers();
    const por = pedidosPorCliente();
    const puntos = [];
    for (const c of clientes) {
      const suyos = por.get(c.id) || [];
      const pin = L.marker([c.lat, c.lng], { icon: icono(suyos.length > 0 ? "pin-pedido" : "pin-cliente"), title: c.nombre || "" });
      pin.bindPopup(() => popupDe(c, pedidosPorCliente().get(c.id) || []));
      pin.addTo(capaClientes);
      puntos.push([c.lat, c.lng]);
    }
    elCuenta.textContent = String(clientes.length);
    if (puntos.length > 0 && !encuadrado) {
      mapa.fitBounds(puntos, { padding: [32, 32], maxZoom: ZOOM_MAX_AL_ENCUADRAR });
      encuadrado = true;
    }
    if (clientes.length === 0) avisar("Todavía no hay clientes con la ubicación cargada. Se cargan desde la PC o con el celular del reparto, estando en el lugar.");
    else avisar(avisoDeFaltantes());
  }

  function dibujarReparto(posiciones) {
    if (!mapa) return;
    capaReparto.clearLayers();
    if (posiciones.length === 0) {
      elEstado.textContent = "Reparto: sin ubicación (el celular no tiene la app abierta).";
      elEstado.classList.add("mapa-estado-viejo");
      return;
    }
    const partes = [];
    let alguno = false;
    for (const p of posiciones) {
      const viejo = p.hace_seg > REPARTO_VIEJO_SEG;
      if (!viejo) alguno = true;
      const pin = L.marker([p.lat, p.lng], { icon: icono(viejo ? "pin-reparto pin-reparto-viejo" : "pin-reparto"), title: p.nombre || "Reparto", zIndexOffset: 1000 });
      pin.bindTooltip(`${p.nombre || "Reparto"} · ${hace(p.hace_seg)}`, { direction: "top", offset: [0, -10] });
      pin.addTo(capaReparto);
      partes.push(`${p.nombre || "Reparto"}: ${hace(p.hace_seg)}`);
    }
    elEstado.textContent = `Reparto · ${partes.join(" · ")}`;
    elEstado.classList.toggle("mapa-estado-viejo", !alguno);
  }

  // ── datos ────────────────────────────────────────────────────────────────
  async function cargarClientes() {
    try {
      clientes = await Api.llamar("/mapa/clientes");
      dibujarClientes();
    } catch (e) {
      avisar(typeof e.status === "number" ? e.message : "Sin conexión: no se pudieron traer los clientes del mapa.");
    }
  }

  async function cargarReparto() {
    try {
      dibujarReparto(await Api.llamar("/mapa/reparto"));
    } catch (e) {
      elEstado.textContent = typeof e.status === "number" ? e.message : "Sin conexión: no se sabe dónde está el reparto.";
      elEstado.classList.add("mapa-estado-viejo");
    }
  }

  function crearMapa() {
    if (mapa) return;
    mapa = L.map(contenedor, { zoomControl: true }).setView(SAN_JUAN, ZOOM_INICIAL);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(mapa);
    capaClientes = L.layerGroup().addTo(mapa);
    capaReparto = L.layerGroup().addTo(mapa);
  }

  // ── abrir y cerrar la tarjeta ────────────────────────────────────────────
  function abrir() {
    if (typeof L === "undefined") {
      avisar("No se pudo cargar el mapa. Cerrá la app y volvé a abrirla.");
      return;
    }
    abierto = true;
    zona.hidden = false;
    btnMapa.textContent = "Ocultar mapa";
    btnMapa.setAttribute("aria-expanded", "true");
    crearMapa();
    setTimeout(() => mapa.invalidateSize(), 0); // el contenedor recién se hizo visible: Leaflet tiene que medirlo
    cargarClientes();
    cargarReparto();
    clearInterval(temporizador);
    temporizador = setInterval(() => {
      if (abierto && !document.hidden && !pantalla.hidden) cargarReparto();
    }, INTERVALO_REPARTO_MS);
  }

  function cerrar() {
    abierto = false;
    zona.hidden = true;
    btnMapa.textContent = "Ver mapa";
    btnMapa.setAttribute("aria-expanded", "false");
    clearInterval(temporizador);
    temporizador = null;
  }

  function limpiar() {
    cerrar();
    clientes = [];
    pedidos = [];
    encuadrado = false;
    elCuenta.textContent = "0";
    elEstado.textContent = "";
    avisar("");
    if (mapa) {
      capaClientes.clearLayers();
      capaReparto.clearLayers();
    }
  }

  btnMapa.addEventListener("click", () => (abierto ? cerrar() : abrir()));

  // gestion.js avisa cada vez que cambia la lista de pedidos: los pines cambian de color y el aviso de faltantes se
  // recalcula sin pedir nada a la red.
  document.addEventListener("mana:pedidos-actualizados", (ev) => {
    pedidos = ev.detail || [];
    if (!abierto) return;
    dibujarClientes();
    // Alguien guardó la ubicación de un cliente que tiene un pedido: todavía no está en el mapa, se vuelve a pedir.
    const conocidos = new Set(clientes.map((c) => c.id));
    if (pedidos.some((p) => p.ubicacion_lat != null && !conocidos.has(p.id_cliente))) cargarClientes();
  });
  document.addEventListener("visibilitychange", () => {
    if (abierto && !document.hidden && !pantalla.hidden) cargarReparto();
  });
  document.addEventListener("mana:sesion-cerrada", limpiar);
})();
