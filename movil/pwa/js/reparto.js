// Pantalla del perfil de reparto: lista de pedidos programados / en camino (GET
// /reparto/pedidos), con dirección, teléfono, mapita y "Cómo llegar", el botón "Marcar
// entregado" y el de "Guardar mi ubicación actual" (GPS del celular, estando en el lugar).
//
// Funciona sin señal: la última lista se guarda en el teléfono y las entregas/ubicaciones
// pasan por la cola local (cola-reparto.js), que las manda solas al volver la conexión.
// Esta pantalla solo DIBUJA lo que dicen el servidor (la lista) y la cola (lo pendiente).
(() => {
  const pantalla = document.getElementById("pantalla-reparto");
  const titulo = document.getElementById("titulo-entregas");
  const elLista = document.getElementById("lista-reparto");
  const elVacio = document.getElementById("reparto-vacio");
  const elError = document.getElementById("error-reparto");
  const elOk = document.getElementById("mensaje-reparto");
  const elAvisoLista = document.getElementById("aviso-lista-reparto");
  const elAvisoCola = document.getElementById("aviso-cola-reparto");
  const btnActualizar = document.getElementById("btn-actualizar-reparto");

  const INTERVALO_MS = 60000;
  const PRECISION_MAX_M = 50; // peor que esto, se avisa antes de guardar
  const ESTADOS = { programado: "Programado", "en camino": "En camino" };
  const CLAVE_CACHE = "reparto_lista";

  let pedidos = []; // lo último que dijo el servidor (o la copia guardada en el teléfono)
  let acciones = []; // la cola local de este usuario (cola-reparto.js)
  let hayLista = false; // hay una lista para mostrar (del servidor o guardada)
  let sinConexion = false; // el último intento de traer la lista falló por la red
  let ultimaCargaIso = null; // cuándo se trajo la lista que se está mostrando
  let cargando = false;
  let firmaVista = ""; // para no redibujar (y cerrar los productos abiertos) si no cambió nada
  const abiertos = new Set(); // pedidos con la lista de productos desplegada

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function aIso(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function hora(iso) {
    return new Date(iso).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
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

  // ── lo que dice la cola local sobre cada pedido / cliente ─────────────────
  function entregaLocal(idPedido) {
    return acciones.filter((a) => a.tipo === "entrega" && a.id_pedido === idPedido).pop();
  }

  function ubicacionLocal(idCliente) {
    return acciones.filter((a) => a.tipo === "ubicacion" && a.id_cliente === idCliente).pop();
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

  function crearNota(texto, esError) {
    const p = document.createElement("p");
    p.className = esError ? "entrega-nota entrega-nota-error" : "entrega-nota";
    p.textContent = texto;
    return p;
  }

  function crearBotonSecundario(texto, alHacerClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "boton-secundario boton-ancho";
    b.textContent = texto;
    b.addEventListener("click", alHacerClick);
    return b;
  }

  function crearTarjeta(p) {
    const ent = entregaLocal(p.id_pedido);
    const ubi = ubicacionLocal(p.cliente.id);
    // Una ubicación guardada en el teléfono se ve ya, aunque todavía no haya llegado al servidor.
    const c = { ...p.cliente };
    if (!destinoMaps(c) && ubi && ubi.estado !== "rechazado") {
      c.ubicacion_lat = ubi.lat;
      c.ubicacion_lng = ubi.lng;
    }
    const nombre = c.nombre || `Cliente ${c.id}`;

    const li = document.createElement("li");
    li.className = "tarjeta-entrega";

    const cabecera = document.createElement("div");
    cabecera.className = "entrega-cabecera";
    const elNombre = document.createElement("strong");
    elNombre.className = "entrega-cliente";
    elNombre.textContent = nombre;
    const pastilla = document.createElement("span");
    if (ent && ent.estado === "pendiente") {
      pastilla.className = "pastilla pastilla-pendiente";
      pastilla.textContent = "Por enviar";
    } else {
      pastilla.className = `pastilla pastilla-${p.estado === "en camino" ? "camino" : "programado"}`;
      pastilla.textContent = ESTADOS[p.estado] || p.estado;
    }
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
    if (ubi && ubi.estado === "pendiente") {
      li.appendChild(crearNota("Ubicación guardada en el teléfono. Se envía sola al volver la señal."));
    }
    if (ubi && ubi.estado === "rechazado") {
      li.appendChild(crearNota(`No se pudo guardar la ubicación: ${ubi.error}`, true));
      li.appendChild(crearBotonSecundario("Descartar aviso", () => ColaReparto.descartar(ubi.uuid)));
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
      const accionesDiv = document.createElement("div");
      accionesDiv.className = "entrega-acciones";
      if (destino) accionesDiv.appendChild(crearEnlaceAccion("Cómo llegar", destino, true));
      if (tel) accionesDiv.appendChild(crearEnlaceAccion(`Llamar · ${c.telefono.trim()}`, `tel:${tel}`, false));
      li.appendChild(accionesDiv);
    }

    const productos = document.createElement("details");
    productos.className = "entrega-productos";
    productos.open = abiertos.has(p.id_pedido);
    productos.addEventListener("toggle", () => {
      if (productos.open) abiertos.add(p.id_pedido);
      else abiertos.delete(p.id_pedido);
    });
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

    if (ent && ent.estado === "pendiente") {
      li.appendChild(crearNota("Entrega guardada en el teléfono. Se envía sola al volver la señal."));
      li.appendChild(crearBotonSecundario("Deshacer", () => ColaReparto.descartar(ent.uuid)));
    } else if (ent && ent.estado === "rechazado") {
      li.appendChild(crearNota(`No se pudo marcar la entrega: ${ent.error}`, true));
      li.appendChild(crearBotonSecundario("Descartar aviso", () => ColaReparto.descartar(ent.uuid)));
    } else {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "boton-entregar";
      btn.textContent = "Marcar entregado";
      btn.addEventListener("click", () => entregar(p, nombre, btn));
      li.appendChild(btn);
    }
    return li;
  }

  function render() {
    // Lo ya enviado y confirmado deja de aparecer, aunque la lista del servidor todavía lo traiga.
    const visibles = pedidos.filter((p) => {
      const ent = entregaLocal(p.id_pedido);
      return !(ent && ent.estado === "enviado");
    });

    const firma = JSON.stringify([
      visibles,
      acciones.map((a) => [a.uuid, a.estado, a.error]),
      sinConexion,
      ultimaCargaIso,
      hayLista,
    ]);
    if (firma === firmaVista) return;
    firmaVista = firma;

    const porEnviar = acciones.filter((a) => a.estado === "pendiente").length;
    elAvisoCola.hidden = porEnviar === 0;
    elAvisoCola.textContent = `${porEnviar} ${porEnviar === 1 ? "acción por enviar" : "acciones por enviar"} · se mandan solas al volver la señal`;
    elAvisoLista.hidden = !(sinConexion && ultimaCargaIso);
    if (!elAvisoLista.hidden) elAvisoLista.textContent = `Sin conexión · lista de las ${hora(ultimaCargaIso)}`;

    titulo.textContent = visibles.length ? `Entregas (${visibles.length})` : "Entregas";
    elVacio.hidden = !(hayLista && visibles.length === 0);

    elLista.textContent = "";
    const grupos = new Map();
    for (const p of visibles) {
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

  async function refrescarAcciones() {
    acciones = await ColaReparto.listar();
    render();
  }

  // La copia de la última lista, para poder abrir la app sin señal.
  async function mostrarDesdeCache() {
    try {
      const copia = await MetaDB.leer(CLAVE_CACHE);
      if (copia && copia.usuario === Api.nombre() && !hayLista) {
        pedidos = copia.pedidos;
        ultimaCargaIso = copia.guardado_en;
        hayLista = true;
        render();
      }
    } catch (e) {
      // sin copia: no pasa nada
    }
  }

  async function cargar() {
    if (cargando) return;
    cargando = true;
    btnActualizar.disabled = true;
    btnActualizar.classList.add("girando");
    try {
      const traidos = await Api.llamar("/reparto/pedidos");
      pedidos = traidos;
      hayLista = true;
      sinConexion = false;
      ultimaCargaIso = new Date().toISOString();
      elError.hidden = true;
      MetaDB.guardar(CLAVE_CACHE, { usuario: Api.nombre(), guardado_en: ultimaCargaIso, pedidos: traidos }).catch(() => {});
      render();
    } catch (e) {
      if (typeof e.status === "number") {
        mostrarError(e.message);
      } else {
        // Sin red: se sigue con lo que hay (la lista de esta sesión o la guardada en el teléfono).
        await mostrarDesdeCache();
        sinConexion = true;
        if (!hayLista) mostrarError("Sin conexión y todavía no hay una lista guardada. Tocá ↻ para reintentar.");
        render();
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
      const accion = await ColaReparto.entregar(p.id_pedido, nombre);
      await ColaReparto.sincronizar();
      const estado = (await ColaReparto.listar()).find((a) => a.uuid === accion.uuid);
      if (estado && estado.estado === "enviado") {
        mostrarOk(`Entregado: ${nombre}.`);
      } else if (estado && estado.estado === "rechazado") {
        mostrarError(`No se pudo marcar la entrega de ${nombre}: ${estado.error}`);
        cargar(); // la lista quedó vieja (alguien lo cambió en la oficina)
      } else {
        mostrarOk("Entrega guardada en el teléfono. Se envía sola apenas haya señal.");
      }
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Marcar entregado";
      mostrarError("No se pudo guardar la entrega en el teléfono. Probá de nuevo.");
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
  // por eso se confirma, y se avisa si el GPS no es preciso. El GPS no necesita internet:
  // sin señal queda guardada en el teléfono y se manda sola.
  async function guardarUbicacion(cliente, nombre, btn) {
    if (!confirm(`¿Estás en el lugar de ${nombre}?\nSe guarda tu ubicación actual como la de este cliente.`)) return;
    ocultarMensajes();
    btn.disabled = true;
    btn.textContent = "Buscando ubicación…";
    const restaurar = () => {
      btn.disabled = false;
      btn.textContent = "Guardar mi ubicación actual";
    };
    let coords;
    try {
      ({ coords } = await obtenerPosicion());
    } catch (e) {
      restaurar();
      mostrarError(mensajeDeGps(e) || "No se pudo obtener la ubicación. Probá de nuevo.");
      return;
    }
    if (coords.accuracy > PRECISION_MAX_M && !confirm(`La precisión es baja (unos ${Math.round(coords.accuracy)} m). ¿Guardarla igual?`)) {
      restaurar();
      return;
    }
    try {
      btn.textContent = "Guardando…";
      // Un aviso viejo de rechazo para este cliente ya no sirve: se reemplaza por este intento.
      for (const a of acciones) {
        if (a.tipo === "ubicacion" && a.id_cliente === cliente.id && a.estado === "rechazado") await ColaReparto.descartar(a.uuid);
      }
      const accion = await ColaReparto.guardarUbicacion(cliente.id, nombre, coords.latitude, coords.longitude);
      await ColaReparto.sincronizar();
      const estado = (await ColaReparto.listar()).find((a) => a.uuid === accion.uuid);
      if (estado && estado.estado === "enviado") {
        mostrarOk(`Ubicación guardada: ${nombre}.`);
        cargar();
      } else if (estado && estado.estado === "rechazado") {
        mostrarError(`No se pudo guardar la ubicación de ${nombre}: ${estado.error}`);
        cargar();
      } else {
        mostrarOk("Ubicación guardada en el teléfono. Se envía sola apenas haya señal.");
      }
    } catch (e) {
      restaurar();
      mostrarError("No se pudo guardar la ubicación en el teléfono. Probá de nuevo.");
    }
  }

  function limpiar() {
    pedidos = [];
    acciones = [];
    hayLista = false;
    sinConexion = false;
    ultimaCargaIso = null;
    firmaVista = "";
    abiertos.clear();
    elLista.textContent = "";
    elVacio.hidden = true;
    elAvisoCola.hidden = true;
    elAvisoLista.hidden = true;
    ocultarMensajes();
  }

  function visible() {
    return !pantalla.hidden && !document.hidden;
  }

  btnActualizar.addEventListener("click", () => {
    ocultarMensajes();
    cargar();
    ColaReparto.sincronizar();
  });
  // Al salir se borra la copia de la lista (direcciones y teléfonos) de este teléfono.
  // Al vencer la sesión no: se vuelve a entrar enseguida y las acciones por enviar siguen.
  document.getElementById("btn-salir-reparto").addEventListener("click", () => {
    limpiar();
    MetaDB.borrar(CLAVE_CACHE).catch(() => {});
  });
  document.addEventListener("mana:sesion-vencida", limpiar);
  document.addEventListener("mana:cola-reparto-cambio", () => {
    if (!pantalla.hidden) refrescarAcciones();
  });
  document.addEventListener("mana:reparto-iniciado", async () => {
    limpiar();
    await refrescarAcciones();
    await mostrarDesdeCache(); // se ve algo al instante, aunque no haya señal
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
