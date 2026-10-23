// Pantalla del perfil de reparto: lista de pedidos programados / en camino (GET
// /reparto/pedidos), con dirección, teléfono, mapita y "Cómo llegar", y el botón
// "Marcar entregado" (POST /reparto/pedidos/{id}/entregar). La entrega es idempotente
// en el servidor: si ya estaba entregado responde OK, así que reintentar es seguro.
// También guarda la ubicación de un cliente con el GPS del celular, estando en el lugar
// (POST /reparto/clientes/{id}/ubicacion): solo si todavía no tiene una cargada.
// Necesita conexión (la cola sin señal para el reparto es un paso aparte).
(() => {
  const pantalla = document.getElementById("pantalla-reparto");
  const titulo = document.getElementById("titulo-entregas");
  const elLista = document.getElementById("lista-reparto");
  const elVacio = document.getElementById("reparto-vacio");
  const elError = document.getElementById("error-reparto");
  const elOk = document.getElementById("mensaje-reparto");
  const btnActualizar = document.getElementById("btn-actualizar-reparto");

  const INTERVALO_MS = 60000;
  const PRECISION_MAX_M = 50; // peor que esto, se avisa antes de guardar
  const ESTADOS = { programado: "Programado", "en camino": "En camino" };

  let pedidos = [];
  let hayLista = false; // se pudo traer la lista al menos una vez en esta sesión
  let cargando = false;
  let firmaLista = ""; // para no redibujar (y cerrar los productos abiertos) si no cambió nada

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function aIso(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function mostrarError(texto) {
    elError.textContent = texto;
    elError.hidden = false;
  }

  function mostrarOk(texto) {
    elOk.textContent = texto;
    elOk.hidden = false;
  }

  function ocultarMensajes() {
    elError.hidden = true;
    elOk.hidden = true;
  }

  // Agrupa por día de entrega: lo atrasado primero, después hoy, mañana y los días que siguen.
  function grupoDe(fechaIso) {
    const hoy = new Date();
    const hoyIso = aIso(hoy);
    const manana = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() + 1);
    if (!fechaIso) return { orden: "3", etiqueta: "Sin fecha" };
    if (fechaIso < hoyIso) return { orden: "0", etiqueta: "Atrasadas" };
    if (fechaIso === hoyIso) return { orden: "1", etiqueta: "Hoy" };
    if (fechaIso === aIso(manana)) return { orden: "2" + fechaIso, etiqueta: "Mañana" };
    const [a, m, d] = fechaIso.split("-").map(Number);
    const etiqueta = new Date(a, m - 1, d).toLocaleDateString("es-AR", {
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
    });
    return { orden: "2" + fechaIso, etiqueta };
  }

  // Solo el enlace de Maps que cargó la oficina (o, si falta, sus coordenadas). NO se
  // busca por el texto de la dirección: las del sistema viejo son imprecisas y Maps
  // terminaba mostrando cualquier lugar. Sin ubicación cargada no se ofrece "Cómo llegar".
  function destinoMaps(c) {
    if (c.ubicacion_maps && /^https?:\/\//i.test(c.ubicacion_maps)) return c.ubicacion_maps;
    if (c.ubicacion_lat != null && c.ubicacion_lng != null) {
      return `https://www.google.com/maps/search/?api=1&query=${c.ubicacion_lat},${c.ubicacion_lng}`;
    }
    return null;
  }

  function telefonoLimpio(telefono) {
    const t = (telefono || "").replace(/[^\d+]/g, "");
    return t.replace(/\D/g, "").length >= 6 ? t : null;
  }

  function crearEnlaceAccion(texto, href, externo) {
    const a = document.createElement("a");
    a.className = "boton-secundario";
    a.href = href;
    a.textContent = texto;
    if (externo) {
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    }
    return a;
  }

  function crearTarjeta(p) {
    const c = p.cliente;
    const nombre = c.nombre || `Cliente ${c.id}`;

    const li = document.createElement("li");
    li.className = "tarjeta-entrega";

    const cabecera = document.createElement("div");
    cabecera.className = "entrega-cabecera";
    const elNombre = document.createElement("strong");
    elNombre.className = "entrega-cliente";
    elNombre.textContent = nombre;
    const pastilla = document.createElement("span");
    pastilla.className = `pastilla pastilla-${p.estado === "en camino" ? "camino" : "programado"}`;
    pastilla.textContent = ESTADOS[p.estado] || p.estado;
    cabecera.append(elNombre, pastilla);
    li.appendChild(cabecera);

    if (c.direccion) {
      const dir = document.createElement("p");
      dir.className = "entrega-direccion";
      dir.textContent = c.direccion;
      li.appendChild(dir);
    }

    const destino = destinoMaps(c);
    if (c.ubicacion_lat != null && c.ubicacion_lng != null && destino) {
      li.appendChild(MapaMini.crear(c.ubicacion_lat, c.ubicacion_lng, destino));
    }

    if (!destino) {
      const aviso = document.createElement("p");
      aviso.className = "entrega-sin-ubicacion";
      aviso.textContent = "Sin ubicación cargada";
      li.appendChild(aviso);

      const btnUbicacion = document.createElement("button");
      btnUbicacion.type = "button";
      btnUbicacion.className = "boton-secundario boton-ubicacion";
      btnUbicacion.textContent = "Guardar mi ubicación actual";
      btnUbicacion.addEventListener("click", () => guardarUbicacion(c, nombre, btnUbicacion));
      li.appendChild(btnUbicacion);
    }

    const tel = telefonoLimpio(c.telefono);
    if (destino || tel) {
      const acciones = document.createElement("div");
      acciones.className = "entrega-acciones";
      if (destino) acciones.appendChild(crearEnlaceAccion("Cómo llegar", destino, true));
      if (tel) acciones.appendChild(crearEnlaceAccion(`Llamar · ${c.telefono.trim()}`, `tel:${tel}`, false));
      li.appendChild(acciones);
    }

    const productos = document.createElement("details");
    productos.className = "entrega-productos";
    const resumen = document.createElement("summary");
    const unidades = p.lineas.reduce((suma, l) => suma + l.cantidad, 0);
    resumen.textContent = `${p.lineas.length} ${p.lineas.length === 1 ? "producto" : "productos"} · ${unidades} u.`;
    const ul = document.createElement("ul");
    for (const l of p.lineas) {
      const item = document.createElement("li");
      const cant = document.createElement("strong");
      cant.textContent = `${l.cantidad} ×`;
      const desc = document.createElement("span");
      desc.textContent = ` ${l.nombre || l.id_producto}`;
      item.append(cant, desc);
      if (l.entregada > 0) {
        const parcial = document.createElement("small");
        parcial.textContent = ` (ya entregadas: ${l.entregada})`;
        item.appendChild(parcial);
      }
      ul.appendChild(item);
    }
    productos.append(resumen, ul);
    li.appendChild(productos);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "boton-entregar";
    btn.textContent = "Marcar entregado";
    btn.addEventListener("click", () => entregar(p, nombre, btn));
    li.appendChild(btn);
    return li;
  }

  function render() {
    elLista.textContent = "";
    titulo.textContent = pedidos.length ? `Entregas (${pedidos.length})` : "Entregas";
    elVacio.hidden = !(hayLista && pedidos.length === 0);

    const grupos = new Map();
    for (const p of pedidos) {
      const g = grupoDe(p.fecha_entrega);
      if (!grupos.has(g.orden)) grupos.set(g.orden, { etiqueta: g.etiqueta, pedidos: [] });
      grupos.get(g.orden).pedidos.push(p);
    }
    for (const orden of [...grupos.keys()].sort()) {
      const g = grupos.get(orden);
      const h = document.createElement("h3");
      h.className = "grupo-entregas";
      h.textContent = `${g.etiqueta} · ${g.pedidos.length}`;
      const ul = document.createElement("ul");
      ul.className = "lista-entregas";
      for (const p of g.pedidos) ul.appendChild(crearTarjeta(p));
      elLista.append(h, ul);
    }
  }

  async function cargar() {
    if (cargando) return;
    cargando = true;
    btnActualizar.disabled = true;
    btnActualizar.classList.add("girando");
    try {
      const traidos = await Api.llamar("/reparto/pedidos");
      const firma = JSON.stringify(traidos);
      hayLista = true;
      elError.hidden = true;
      if (firma !== firmaLista) {
        firmaLista = firma;
        pedidos = traidos;
        render();
      }
    } catch (e) {
      if (typeof e.status === "number") {
        mostrarError(e.message);
      } else {
        mostrarError(
          hayLista
            ? "Sin conexión: se ve la última lista que se pudo traer. Tocá ↻ para reintentar."
            : "Sin conexión. Tocá ↻ para reintentar."
        );
      }
    } finally {
      cargando = false;
      btnActualizar.disabled = false;
      btnActualizar.classList.remove("girando");
    }
  }

  async function entregar(p, nombre, btn) {
    if (!confirm(`¿Marcar como entregado el pedido de ${nombre}?`)) return;
    ocultarMensajes();
    btn.disabled = true;
    btn.textContent = "Guardando…";
    try {
      await Api.llamar(`/reparto/pedidos/${p.id_pedido}/entregar`, { method: "POST" });
      pedidos = pedidos.filter((x) => x.id_pedido !== p.id_pedido);
      render();
      mostrarOk(`Entregado: ${nombre}.`);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Marcar entregado";
      if (e.status === 404 || e.status === 409) {
        // La lista quedó vieja (alguien lo cambió en la oficina): se refresca.
        mostrarError(e.message);
        cargar();
      } else if (typeof e.status !== "number") {
        mostrarError("Sin conexión: no se pudo marcar como entregado. Probá de nuevo cuando tengas señal.");
      } else {
        mostrarError(e.message);
      }
    }
  }

  function obtenerPosicion() {
    return new Promise((ok, mal) => {
      if (!("geolocation" in navigator)) {
        mal({ sinGps: true });
        return;
      }
      navigator.geolocation.getCurrentPosition(ok, mal, { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
    });
  }

  function mensajeDeGps(e) {
    if (e.sinGps) return "Este teléfono no permite obtener la ubicación.";
    if (e.code === 1) return "Sin permiso de ubicación. Habilitala para esta app en los ajustes del teléfono.";
    if (e.code === 2) return "No se pudo determinar la ubicación. Probá a cielo abierto y con el GPS activado.";
    if (e.code === 3) return "La ubicación tardó demasiado. Probá de nuevo.";
    return null;
  }

  // Guarda la posición actual como la ubicación del cliente. Hay que estar en el lugar:
  // por eso se confirma, y se avisa si el GPS no es preciso.
  async function guardarUbicacion(cliente, nombre, btn) {
    if (!confirm(`¿Estás en el lugar de ${nombre}?
Se guarda tu ubicación actual como la de este cliente.`)) return;
    ocultarMensajes();
    btn.disabled = true;
    btn.textContent = "Buscando ubicación…";
    try {
      const { coords } = await obtenerPosicion();
      if (coords.accuracy > PRECISION_MAX_M) {
        const metros = Math.round(coords.accuracy);
        if (!confirm(`La precisión es baja (unos ${metros} m). ¿Guardarla igual?`)) {
          btn.disabled = false;
          btn.textContent = "Guardar mi ubicación actual";
          return;
        }
      }
      btn.textContent = "Guardando…";
      await Api.llamar(`/reparto/clientes/${cliente.id}/ubicacion`, {
        method: "POST",
        body: JSON.stringify({ lat: coords.latitude, lng: coords.longitude }),
      });
      mostrarOk(`Ubicación guardada: ${nombre}.`);
      await cargar();
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Guardar mi ubicación actual";
      if (typeof e.status === "number") {
        mostrarError(e.message);
        if (e.status === 404 || e.status === 409) cargar(); // alguien más la cargó / ya no hay entrega
      } else {
        mostrarError(
          mensajeDeGps(e) || "Sin conexión: no se pudo guardar la ubicación. Probá de nuevo cuando tengas señal."
        );
      }
    }
  }

  function limpiar() {
    pedidos = [];
    hayLista = false;
    firmaLista = "";
    elLista.textContent = "";
    elVacio.hidden = true;
    ocultarMensajes();
  }

  function visible() {
    return !pantalla.hidden && !document.hidden;
  }

  btnActualizar.addEventListener("click", () => {
    ocultarMensajes();
    cargar();
  });
  document.getElementById("btn-salir-reparto").addEventListener("click", limpiar);
  document.addEventListener("mana:sesion-vencida", limpiar);
  document.addEventListener("mana:reparto-iniciado", () => {
    limpiar();
    cargar();
  });
  document.addEventListener("visibilitychange", () => {
    if (visible()) cargar();
  });
  window.addEventListener("online", () => {
    if (visible()) cargar();
  });
  setInterval(() => {
    if (visible()) cargar();
  }, INTERVALO_MS);
})();
