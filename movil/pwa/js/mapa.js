// Tarjeta "Mapa de clientes" de la pantalla Pedidos (reparto y admin): el mapa de la zona (arranca en San Juan y se
// encuadra solo sobre los clientes) con un pin por cada cliente que tiene la ubicación cargada y, aparte, el pin del
// celular de la cuenta de reparto, que se actualiza solo mientras el mapa está abierto.
//
//   - Al tocar un pin de cliente: nombre, dirección, localidad, cuántos pedidos tiene por entregar, "Cómo llegar" y,
//     si tiene un pedido por entregar, "Ver pedido" (abre el detalle en la lista de arriba).
//   - Pin ámbar = cliente con pedidos pendientes o programados; rojo = con algún pedido EN CAMINO (si tiene de los dos,
//     gana el en camino: es lo que está pasando ahora); azul = el resto; verde con pulso = el reparto (gris si hace más
//     de 2 minutos que no llega su posición).
//
//   - "Armar ruta": con los clientes que tienen pedidos EN CAMINO el servidor calcula en qué orden conviene visitarlos
//     (por las calles y respetando sus sentidos, saliendo de donde está el reparto: POST /mapa/ruta). Se dibuja el
//     recorrido con las paradas numeradas, se lista con el tramo de cada una y se puede abrir en Google Maps para ir
//     con la voz. Si cambian los pedidos en camino (se entregó uno, salió otro) se recalcula sola.
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
  const btnRuta = $("btn-ruta");
  const elRutaAvisos = $("ruta-avisos");
  const panelRuta = $("ruta-panel");
  const elRutaResumen = $("ruta-resumen");
  const elRutaSalida = $("ruta-salida");
  const elRutaParadas = $("ruta-paradas");
  const enlaceGoogle = $("ruta-google");
  const btnQuitarRuta = $("btn-quitar-ruta");

  const SAN_JUAN = [-31.5375, -68.5364];
  const ZOOM_INICIAL = 12;
  const ZOOM_MAX_AL_ENCUADRAR = 15;
  const INTERVALO_REPARTO_MS = 15000;
  const REPARTO_VIEJO_SEG = 120; // más que esto sin posición nueva: se ve gris, "hace X"
  const GOOGLE_MAX_PARADAS = 10; // un enlace de Google Maps admite el destino y hasta 9 paradas intermedias
  const PAUSA_RECALCULO_MS = 1500; // espera a que se asiente la lista antes de recalcular la ruta

  let mapa = null;
  let capaClientes = null;
  let capaRuta = null;
  let capaReparto = null;
  let ruta = null; // la ruta que se está mostrando (respuesta de POST /mapa/ruta), o null
  let rutaFirma = ""; // los pedidos en camino con los que se armó: si cambian, la ruta se recalcula
  let calculando = false;
  let temporizadorRuta = null;
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

  // El color del pin de un cliente según sus pedidos: en camino > pendientes o programados > ninguno.
  const enCamino = (pedidosDelCliente) => pedidosDelCliente.filter((p) => p.estado === "en camino");

  function clasePin(suyos) {
    if (enCamino(suyos).length > 0) return "pin-camino";
    return suyos.length > 0 ? "pin-pedido" : "pin-cliente";
  }

  function popupDe(c, suyos) {
    const caja = el("div", "popup-cliente");
    caja.appendChild(el("strong", null, c.nombre || `Cliente ${c.id}`));
    const donde = [c.direccion, c.localidad].filter(Boolean).join(" · ");
    if (donde) caja.appendChild(el("span", null, donde));
    const camino = enCamino(suyos).length;
    const porEntregar = suyos.length - camino; // pendientes o programados
    if (camino > 0) caja.appendChild(el("span", "popup-camino", `${camino} ${camino === 1 ? "pedido en camino" : "pedidos en camino"}`));
    if (porEntregar > 0) caja.appendChild(el("span", "popup-pedidos", `${porEntregar} ${porEntregar === 1 ? "pedido pendiente o programado" : "pedidos pendientes o programados"}`));
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
        // Si tiene uno en camino, es el que se abre primero: es el que está pasando ahora.
        const elegido = enCamino(suyos)[0] || suyos[0];
        document.dispatchEvent(new CustomEvent("mana:abrir-pedido", { detail: elegido.id_pedido }));
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
      const pin = L.marker([c.lat, c.lng], { icon: icono(clasePin(suyos)), title: c.nombre || "" });
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

  // ── la ruta ──────────────────────────────────────────────────────────────
  const km = (metros) => (metros < 1000 ? `${metros} m` : `${(metros / 1000).toLocaleString("es-AR", { maximumFractionDigits: 1 })} km`);

  function minutos(seg) {
    const min = Math.max(1, Math.round(seg / 60));
    return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${min % 60} min`;
  }

  // Los pedidos en camino con los que se arma la ruta (y si su cliente tiene ubicación): si esto cambia, la ruta que
  // se está mostrando ya no es la de ahora.
  const firmaEnCamino = () =>
    enCamino(pedidos)
      .map((p) => `${p.id_pedido}${p.ubicacion_lat == null ? "?" : ""}`)
      .sort()
      .join(",");

  function avisosRuta(textos) {
    elRutaAvisos.replaceChildren(...textos.map((t) => el("p", "mapa-aviso", t)));
    elRutaAvisos.hidden = textos.length === 0;
  }

  function actualizarBotonRuta() {
    btnRuta.hidden = !(abierto && enCamino(pedidos).length > 0);
    if (calculando) return;
    btnRuta.disabled = false;
    btnRuta.textContent = ruta ? "Recalcular ruta" : "Armar ruta de los pedidos en camino";
  }

  // A Google Maps: las paradas en el orden calculado (Google respeta el orden que se le da). El celular del reparto
  // sale de donde está (Google usa "tu ubicación"); a un admin se le pone la salida con la que se calculó.
  function enlaceDeGoogle(r) {
    const usadas = r.paradas.slice(0, GOOGLE_MAX_PARADAS);
    const punto = (p) => `${p.lat},${p.lng}`;
    const params = new URLSearchParams({ api: "1", travelmode: "driving", destination: punto(usadas[usadas.length - 1]) });
    if (usadas.length > 1) params.set("waypoints", usadas.slice(0, -1).map(punto).join("|"));
    if (Api.rol() !== "reparto" && r.origen) params.set("origin", `${r.origen.lat},${r.origen.lng}`);
    return `https://www.google.com/maps/dir/?${params.toString()}`;
  }

  function itemParada(p, hayTramo) {
    const li = el("li");
    li.appendChild(el("span", "ruta-num", String(p.orden)));
    const dato = el("div", "ruta-dato");
    dato.appendChild(el("strong", null, p.cliente || `Cliente ${p.id_cliente}`));
    if (p.direccion) dato.appendChild(el("span", null, p.direccion));
    if (hayTramo) dato.appendChild(el("span", "ruta-tramo", `${km(p.metros)} · ${minutos(p.segundos)} desde ${p.orden === 1 ? "el reparto" : "la parada anterior"}`));
    li.appendChild(dato);
    const ver = el("button", "ruta-ver", "Ver pedido");
    ver.type = "button";
    ver.setAttribute("aria-label", `Ver el pedido de ${p.cliente || "este cliente"}`);
    ver.addEventListener("click", () => document.dispatchEvent(new CustomEvent("mana:abrir-pedido", { detail: p.pedidos[0] })));
    li.appendChild(ver);
    return li;
  }

  function dibujarRuta(r, encuadrar) {
    capaRuta.clearLayers();
    const avisos = [];
    if (r.paradas.length === 0) {
      ruta = null;
      panelRuta.hidden = true;
      avisos.push(r.sin_ubicacion.length > 0 ? "Ningún pedido en camino tiene la ubicación del cliente cargada: no se puede armar la ruta." : "No hay pedidos en camino.");
    }
    if (r.sin_ubicacion.length > 0) {
      const nombres = r.sin_ubicacion.map((c) => c.cliente || `Cliente ${c.id_cliente}`).join(", ");
      avisos.push(`Sin ubicación guardada, no entran en la ruta: ${nombres}. El reparto la guarda al llegar.`);
    }
    if (r.paradas.length > 0) {
      if (r.aproximada) avisos.push("No se pudo consultar las calles: la ruta es aproximada (en línea recta) y puede no respetar los sentidos de las calles.");
      else if (!r.trazado_por_calles) avisos.push("El orden respeta las calles, pero no se pudo dibujar el recorrido: la línea une las paradas en recta.");
      if (r.paradas.length > GOOGLE_MAX_PARADAS) avisos.push(`Google Maps admite ${GOOGLE_MAX_PARADAS} paradas por enlace: el botón abre las primeras ${GOOGLE_MAX_PARADAS}.`);
    }
    avisosRuta(avisos);
    if (r.paradas.length === 0) return;

    if (r.trazado.length >= 2) {
      // una línea blanca más ancha debajo, para que se lea sobre cualquier mapa
      L.polyline(r.trazado, { color: "#fff", weight: 9, opacity: 0.9, lineCap: "round", lineJoin: "round", interactive: false }).addTo(capaRuta);
      L.polyline(r.trazado, { color: "#1b2fb5", weight: 5, opacity: 0.9, lineCap: "round", lineJoin: "round", dashArray: r.trazado_por_calles ? null : "8 10", interactive: false }).addTo(capaRuta);
    }
    for (const p of r.paradas) {
      const cliente = { id: p.id_cliente, nombre: p.cliente, direccion: p.direccion, localidad: null, lat: p.lat, lng: p.lng };
      const icono = L.divIcon({ className: "pin pin-parada", html: `<span>${p.orden}</span>`, iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -15] });
      const pin = L.marker([p.lat, p.lng], { icon: icono, title: `${p.orden}. ${p.cliente || ""}`, zIndexOffset: 500 });
      pin.bindPopup(() => popupDe(cliente, pedidosPorCliente().get(p.id_cliente) || []));
      pin.addTo(capaRuta);
    }
    if (encuadrar) mapa.fitBounds(r.trazado.length >= 2 ? r.trazado : r.paradas.map((p) => [p.lat, p.lng]), { padding: [32, 32], maxZoom: 16 });

    const n = r.paradas.length;
    const resumen = [`${n} ${n === 1 ? "parada" : "paradas"}`];
    if (r.metros > 0) resumen.push(km(r.metros), `~${minutos(r.segundos)} de manejo`);
    elRutaResumen.textContent = resumen.join(" · ");
    elRutaSalida.textContent = r.origen
      ? `Sale desde la posición del reparto (${hace(r.origen.hace_seg)}).`
      : "No hay una posición reciente del reparto: la ruta arranca por la parada que más conviene.";
    elRutaParadas.replaceChildren(...r.paradas.map((p, i) => itemParada(p, !(i === 0 && !r.origen))));
    enlaceGoogle.href = enlaceDeGoogle(r);
    panelRuta.hidden = false;
  }

  function quitarRuta() {
    clearTimeout(temporizadorRuta);
    temporizadorRuta = null;
    ruta = null;
    rutaFirma = "";
    if (capaRuta) capaRuta.clearLayers();
    panelRuta.hidden = true;
    avisosRuta([]);
    actualizarBotonRuta();
  }

  async function armarRuta(encuadrar = true) {
    if (calculando || !abierto) return;
    calculando = true;
    btnRuta.disabled = true;
    btnRuta.textContent = "Calculando la ruta…";
    const firma = firmaEnCamino();
    try {
      const r = await Api.llamar("/mapa/ruta", { method: "POST" });
      if (!abierto) return; // la tarjeta se cerró mientras se calculaba
      ruta = r.paradas.length > 0 ? r : null;
      rutaFirma = firma;
      dibujarRuta(r, encuadrar);
    } catch (e) {
      // Una ruta vieja no se deja a la vista: ya no es confiable. El botón queda para reintentar.
      quitarRuta();
      avisosRuta([typeof e.status === "number" ? e.message : "Sin conexión: no se pudo armar la ruta."]);
    } finally {
      calculando = false;
      revisarRuta();
    }
  }

  // Si cambiaron los pedidos en camino desde que se armó la ruta, se rehace (sin mover el mapa de quien lo está mirando).
  function revisarRuta() {
    actualizarBotonRuta();
    if (!ruta || !abierto || calculando) return;
    if (enCamino(pedidos).length === 0) {
      quitarRuta();
      return;
    }
    if (firmaEnCamino() === rutaFirma) return;
    clearTimeout(temporizadorRuta);
    temporizadorRuta = setTimeout(() => armarRuta(false), PAUSA_RECALCULO_MS);
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
    capaRuta = L.layerGroup().addTo(mapa);
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
    revisarRuta(); // muestra el botón de la ruta y, si ya había una armada y cambiaron los pedidos, la rehace
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
    clearTimeout(temporizadorRuta);
    temporizadorRuta = null;
    actualizarBotonRuta();
  }

  function limpiar() {
    cerrar();
    clientes = [];
    pedidos = [];
    encuadrado = false;
    elCuenta.textContent = "0";
    elEstado.textContent = "";
    avisar("");
    quitarRuta();
    if (mapa) {
      capaClientes.clearLayers();
      capaReparto.clearLayers();
    }
  }

  btnMapa.addEventListener("click", () => (abierto ? cerrar() : abrir()));
  btnRuta.addEventListener("click", () => armarRuta(true));
  btnQuitarRuta.addEventListener("click", quitarRuta);

  // gestion.js avisa cada vez que cambia la lista de pedidos: los pines cambian de color y el aviso de faltantes se
  // recalcula sin pedir nada a la red.
  document.addEventListener("mana:pedidos-actualizados", (ev) => {
    pedidos = ev.detail || [];
    if (!abierto) return;
    dibujarClientes();
    revisarRuta();
    // Alguien guardó la ubicación de un cliente que tiene un pedido: todavía no está en el mapa, se vuelve a pedir.
    const conocidos = new Set(clientes.map((c) => c.id));
    if (pedidos.some((p) => p.ubicacion_lat != null && !conocidos.has(p.id_cliente))) cargarClientes();
  });
  document.addEventListener("visibilitychange", () => {
    if (abierto && !document.hidden && !pantalla.hidden) cargarReparto();
  });
  document.addEventListener("mana:sesion-cerrada", limpiar);
})();
