// Pantalla "Pedidos": la única lista de pedidos de la app, para el reparto y para los admin. Muestra lo que todavía hay
// que entregar (pendientes, programados y en camino; los entregados no se listan) y, al tocar un pedido, su detalle:
//   - los dos perfiles: marcarlo EN CAMINO, entregarlo (total o parcial: se eligen los productos y las unidades que se
//     dejaron), y ver o guardar la ubicación del cliente ("Cómo llegar" / "Guardar mi ubicación actual").
//   - solo los admin: programar o reprogramar, quitar un artículo (✕) y borrar el pedido, y "Agregar pedido".
//     El reparto NO puede borrar pedidos.
// Una entrega parcial deja el pedido en "pendiente" con lo que falta (lo hace el servidor).
//
// Lo que se hace en la calle (en camino, entregas, ubicación) funciona sin señal: se guarda en el teléfono y sale solo
// al volver la conexión (cola-reparto.js). Programar, quitar y borrar van directo al servidor y necesitan señal, a
// propósito: no deberían quedar "pendientes de enviar" en un teléfono. Esta pantalla solo DIBUJA lo que dicen el
// servidor (GET /pedidos/gestion) y la cola local.
(() => {
  const $ = (id) => document.getElementById(id);
  const pantalla = $("pantalla-gestion");
  const elError = $("error-gestion");
  const elAviso = $("aviso-gestion");
  const elAvisoCola = $("aviso-cola-gestion");
  const elOk = $("mensaje-gestion");
  const btnActualizar = $("btn-actualizar-gestion");
  const btnAgregar = $("btn-agregar-pedido");
  const zonaClientes = $("clientes-gestion");
  const zonaCola = $("zona-cola-gestion");
  const hoja = $("detalle-pedido");
  const lista = $("lista-pedidos");
  const vacio = $("vacio-pedidos");
  const cuenta = $("cuenta-pedidos");

  const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const ESTADOS = {
    pendiente: ["Pendiente", "pendiente"],
    programado: ["Programado", "programado"],
    "en camino": ["En camino", "camino"],
  };

  const CLAVE_CACHE = "gestion_lista";
  const INTERVALO_MS = 60000;
  const PRECISION_MAX_M = 50; // peor que esto, se avisa antes de guardar una ubicación

  let datos = []; // los pedidos por entregar, como los dijo el servidor (o la copia guardada en el teléfono)
  let acciones = []; // la cola local de este usuario (cola-reparto.js)
  let hayDatos = false;
  let cargando = false;
  let sinConexion = false; // el último intento de traer la lista falló por la red: se ve la última guardada
  let guardadoEn = null; // cuándo se trajo la lista que se está mostrando
  let firmaLista = ""; // para no redibujar (ni perder el scroll) si no cambió nada
  let temporizadorOk = null;
  const enviadosVistos = new Set(); // en camino y entregas parciales ya confirmadas cuya lista ya se refrescó
  const reubicados = []; // nodos de la pantalla del vendedor que se prestan a esta pantalla mientras dure la sesión

  // Lo que muestra la hoja del pedido abierto. `modo`: detalle | entrega | programar | confirmar.
  // { id, nombre, modo, tipo: "total" | "parcial", elegidos: Map(id_detalle -> unidades que se dejan), ocupado,
  //   buscandoGps, error, fecha, confirmacion, firma }
  let hojaEstado = null;

  const esAdmin = () => Api.esAdmin();

  // ── fechas ───────────────────────────────────────────────────────────────
  const pad = (n) => String(n).padStart(2, "0");
  const aIso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const hoyIso = () => aIso(new Date());

  function deIso(iso) {
    const [a, m, d] = iso.split("-").map(Number);
    return new Date(a, m - 1, d);
  }

  function diaCorto(iso) {
    const d = deIso(iso);
    return `${DIAS[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`;
  }

  function sumar(p) {
    return p.lineas.reduce((s, l) => ({ cantidad: s.cantidad + l.cantidad, entregada: s.entregada + l.entregada }), { cantidad: 0, entregada: 0 });
  }

  // Qué se dice de la fecha de un pedido, y si ya se pasó.
  function textoDeFecha(p) {
    if (!p.fecha_entrega) return { texto: "Sin fecha de entrega", atrasado: false };
    const hoy = hoyIso();
    if (p.fecha_entrega < hoy) return { texto: `Debía entregarse el ${diaCorto(p.fecha_entrega)}`, atrasado: true };
    if (p.fecha_entrega === hoy) return { texto: "Entrega hoy", atrasado: false };
    return { texto: `Entrega el ${diaCorto(p.fecha_entrega)}`, atrasado: false };
  }

  // ── piezas de dibujo ─────────────────────────────────────────────────────
  function el(tag, clase, texto) {
    const nodo = document.createElement(tag);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
  }

  function boton(texto, clase, alTocar, tipo = "button") {
    const b = el("button", clase, texto);
    b.type = tipo;
    if (alTocar) b.addEventListener("click", alTocar);
    return b;
  }

  function pastilla(estado, texto) {
    const [nombre, clase] = ESTADOS[estado] || [estado, "pendiente"];
    return el("span", `pastilla pastilla-${clase}`, texto || nombre);
  }

  // Barra fina de cuánto se entregó (solo si hay entrega parcial): de un vistazo, sin abrir el pedido.
  function barraDeAvance(entregada, cantidad) {
    const barra = el("span", "avance");
    barra.setAttribute("role", "img");
    barra.setAttribute("aria-label", `Entregado ${entregada} de ${cantidad} unidades`);
    const relleno = el("i");
    relleno.style.width = `${Math.round((entregada / cantidad) * 100)}%`;
    barra.appendChild(relleno);
    return barra;
  }

  function mostrarOk(texto) {
    elOk.textContent = texto;
    elOk.hidden = false;
    elError.hidden = true;
    clearTimeout(temporizadorOk);
    temporizadorOk = setTimeout(() => {
      elOk.hidden = true;
    }, 6000);
  }

  function mostrarError(texto) {
    elError.textContent = texto;
    elError.hidden = false;
    elOk.hidden = true;
  }

  // ── lo que dice la cola local sobre cada pedido / cliente ────────────────
  const accionesDe = (idPedido) => acciones.filter((a) => a.id_pedido === idPedido);
  const ultima = (idPedido, tipos) => accionesDe(idPedido).filter((a) => tipos.includes(a.tipo)).pop();
  const ubicacionLocal = (idCliente) => acciones.filter((a) => a.tipo === "ubicacion" && a.id_cliente === idCliente).pop();

  // La última orden de entrega (total o parcial) de este pedido, y la de en camino.
  const entregaLocal = (idPedido) => ultima(idPedido, ["entrega", "entrega_parcial"]);
  const caminoLocal = (idPedido) => ultima(idPedido, ["en_camino"]);

  // Una entrega TOTAL ya confirmada saca al pedido de la lista, aunque el servidor todavía lo traiga. Una parcial no:
  // el pedido sigue (como pendiente, con lo que falta).
  function entregadoYa(p) {
    const total = ultima(p.id_pedido, ["entrega"]);
    return Boolean(total && total.estado === "enviado");
  }

  // El estado que se muestra: si se marcó en camino y todavía no llegó al servidor, ya se ve "En camino".
  function estadoVisible(p) {
    const c = caminoLocal(p.id_pedido);
    return c && c.estado === "pendiente" && p.estado !== "en camino" ? "en camino" : p.estado;
  }

  function textoDeAccion(a) {
    if (a.tipo === "en_camino") return "en camino";
    if (a.tipo === "entrega") return "entrega total";
    const que = a.resumen && a.resumen.length ? `: ${a.resumen.join(", ")}` : "";
    return `entrega parcial${que}`;
  }

  // ── la lista ─────────────────────────────────────────────────────────────
  function crearFila(p) {
    const li = el("li");
    const fila = boton("", "fila-pedido", () => abrirHoja(p.id_pedido));
    const fecha = textoDeFecha(p);
    fila.append(el("span", "fila-cliente", p.cliente || "Cliente sin nombre"), pastilla(estadoVisible(p)));
    fila.appendChild(el("span", fecha.atrasado ? "fila-detalle fila-atrasada" : "fila-detalle", fecha.texto));
    if (p.direccion) fila.appendChild(el("span", "fila-detalle", p.direccion));
    // Una pista de que tiene observaciones (en un renglón, cortada con "…"): se lee entera al abrir el pedido.
    if (p.observaciones) fila.appendChild(el("span", "fila-detalle fila-obs", `Obs.: ${p.observaciones.replace(/\s+/g, " ")}`));
    const pendiente = accionesDe(p.id_pedido).filter((a) => a.estado === "pendiente" && a.tipo !== "ubicacion").pop();
    if (pendiente) fila.appendChild(el("span", "fila-detalle fila-por-enviar", `Por enviar: ${textoDeAccion(pendiente)}`));
    const { cantidad, entregada } = sumar(p);
    if (entregada > 0 && entregada < cantidad) fila.appendChild(barraDeAvance(entregada, cantidad));
    li.appendChild(fila);
    return li;
  }

  function render() {
    const visibles = datos.filter((p) => !entregadoYa(p));
    // La fecha de hoy entra en la firma: al cambiar el día, "Entrega hoy" y "Debía entregarse" se vuelven a calcular.
    const firma = JSON.stringify([visibles, acciones.map((a) => [a.uuid, a.estado, a.error]), hayDatos, sinConexion, hoyIso()]);
    if (firma === firmaLista) return;
    firmaLista = firma;
    // La tarjeta del mapa (mapa.js) pinta de otro color a los clientes con pedidos por entregar.
    document.dispatchEvent(new CustomEvent("mana:pedidos-actualizados", { detail: visibles }));
    lista.textContent = "";
    for (const p of visibles) lista.appendChild(crearFila(p));
    cuenta.textContent = String(visibles.length);
    vacio.hidden = !(hayDatos && visibles.length === 0);

    const porEnviar = acciones.filter((a) => a.estado === "pendiente").length;
    elAvisoCola.hidden = porEnviar === 0;
    elAvisoCola.textContent = `${porEnviar} ${porEnviar === 1 ? "acción por enviar" : "acciones por enviar"} · se mandan solas al volver la señal`;
  }

  const hora = (iso) => new Date(iso).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });

  function avisarSinConexion() {
    elAviso.textContent = esAdmin()
      ? `Sin conexión (lista de las ${hora(guardadoEn)}). En camino, entregas y ubicación se guardan en el teléfono; programar, quitar o borrar necesitan señal.`
      : `Sin conexión (lista de las ${hora(guardadoEn)}). Lo que marques se guarda en el teléfono y se manda solo al volver la señal.`;
    elAviso.hidden = false;
  }

  // La última lista que se trajo, para poder abrir la pantalla sin señal. Se usa SOLO si falla la red (nunca antes de
  // preguntarle al servidor) y se borra al salir.
  async function mostrarDesdeCache() {
    try {
      const copia = await MetaDB.leer(CLAVE_CACHE);
      if (copia && copia.usuario === Api.nombre() && Array.isArray(copia.datos) && !hayDatos) {
        datos = copia.datos;
        guardadoEn = copia.guardado_en;
        hayDatos = true;
        render();
      }
    } catch (e) {
      // sin copia: no pasa nada
    }
  }

  async function refrescarAcciones() {
    acciones = await ColaReparto.listar();
    // Un en camino o una entrega parcial confirmados cambian el pedido (sigue en la lista, con otro estado o con otras
    // cantidades): se trae la lista de nuevo, una sola vez por acción, para no mostrar lo viejo.
    const nuevas = acciones.filter((a) => (a.tipo === "en_camino" || a.tipo === "entrega_parcial") && a.estado === "enviado" && !enviadosVistos.has(a.uuid));
    for (const a of nuevas) enviadosVistos.add(a.uuid);
    render();
    if (hojaEstado && !hojaEstado.ocupado) actualizarHojaAbierta();
    if (nuevas.length) cargar();
  }

  async function cargar() {
    if (cargando) return;
    cargando = true;
    btnActualizar.disabled = true;
    btnActualizar.classList.add("girando");
    try {
      datos = await Api.llamar("/pedidos/gestion");
      hayDatos = true;
      sinConexion = false;
      guardadoEn = new Date().toISOString();
      elError.hidden = true;
      elAviso.hidden = true;
      MetaDB.guardar(CLAVE_CACHE, { usuario: Api.nombre(), guardado_en: guardadoEn, datos }).catch(() => {});
      render();
    } catch (e) {
      if (typeof e.status === "number") {
        mostrarError(e.message);
      } else {
        // Sin red: se sigue con la lista que había (la de esta sesión o la guardada en el teléfono).
        if (!hayDatos) await mostrarDesdeCache();
        sinConexion = true;
        if (hayDatos) {
          avisarSinConexion();
          render();
        } else {
          mostrarError("Sin conexión y todavía no hay pedidos para mostrar. Tocá ↻ para reintentar.");
        }
      }
    } finally {
      cargando = false;
      btnActualizar.disabled = false;
      btnActualizar.classList.remove("girando");
      if (hojaEstado) actualizarHojaAbierta(); // el pedido pudo cambiar, o se perdió/volvió la señal
    }
  }

  // ── la hoja con el detalle de un pedido ──────────────────────────────────
  const buscarPedido = (id) => datos.find((p) => p.id_pedido === id) || null;
  const faltan = (l) => l.cantidad - l.entregada;
  const lineasPendientes = (p) => p.lineas.filter((l) => faltan(l) > 0);

  function abrirHoja(id) {
    const p = buscarPedido(id);
    hojaEstado = {
      id, nombre: (p && p.cliente) || "este cliente", modo: "detalle", tipo: "total", elegidos: new Map(),
      ocupado: false, buscandoGps: false, error: null, fecha: "", confirmacion: null, firma: "",
    };
    dibujarHoja();
    if (!hoja.open) hoja.showModal();
  }

  function cerrarHoja() {
    hojaEstado = null;
    if (hoja.open) hoja.close();
  }

  // Lo que cambia lo dibujado: el pedido, la señal, lo que se está eligiendo y lo que dice la cola sobre ese pedido y
  // ese cliente.
  function firmaDeLaHoja(p) {
    const locales = [...accionesDe(p.id_pedido), ...acciones.filter((a) => a.tipo === "ubicacion" && a.id_cliente === p.id_cliente)];
    return JSON.stringify([p, sinConexion, [...hojaEstado.elegidos], locales.map((a) => [a.uuid, a.estado, a.error])]);
  }

  // Después de recargar la lista o de que cambie la cola: si el pedido abierto cambió (o se perdió o volvió la señal) se
  // redibuja; si ya no está, se cierra. Si no cambió nada NO se redibuja: se perdería el foco, el selector de fecha
  // abierto o lo que se esté escribiendo.
  function actualizarHojaAbierta() {
    const p = buscarPedido(hojaEstado.id);
    if (!p || entregadoYa(p)) {
      const nombre = hojaEstado.nombre;
      cerrarHoja();
      mostrarOk(`El pedido de ${nombre} ya no está pendiente: se actualizó la lista.`);
      return;
    }
    if (hojaEstado.ocupado || hojaEstado.buscandoGps) return;
    if (hojaEstado.modo === "entrega" && lineasPendientes(p).length === 0) hojaEstado.modo = "detalle";
    // Si alguien entregó parte mientras tanto, lo que falta es menos: el contador no puede pasarse.
    for (const [id, n] of [...hojaEstado.elegidos]) {
      const l = p.lineas.find((x) => x.id_detalle === id);
      if (!l || faltan(l) <= 0) hojaEstado.elegidos.delete(id);
      else hojaEstado.elegidos.set(id, Math.min(n, faltan(l)));
    }
    if (firmaDeLaHoja(p) === hojaEstado.firma) return;
    dibujarHoja();
  }

  function cambiarModo(modo, extra = {}) {
    Object.assign(hojaEstado, { modo, error: null, ...extra });
    dibujarHoja();
  }

  // Contador de unidades de un producto elegido: nunca menos de 1 (para dejar de entregarlo se lo desmarca).
  function contador(valor, max, etiqueta, alCambiar) {
    const caja = el("div", "contador");
    const menos = boton("−", "contador-boton", () => alCambiar(valor - 1));
    const mas = boton("+", "contador-boton", () => alCambiar(valor + 1));
    menos.setAttribute("aria-label", `Una unidad menos de ${etiqueta}`);
    mas.setAttribute("aria-label", `Una unidad más de ${etiqueta}`);
    menos.disabled = valor <= 1;
    mas.disabled = valor >= max;
    caja.append(menos, el("output", "contador-valor", String(valor)), mas);
    return caja;
  }

  // Un producto de la entrega parcial: se toca la fila para marcarlo como entregado y, ya marcado, se ajusta cuántas
  // unidades se dejaron (por defecto todas las que faltaban).
  function filaElegible(l) {
    const pendiente = faltan(l);
    const nombre = l.nombre || l.id_producto;
    const elegido = hojaEstado.elegidos.has(l.id_detalle);
    const li = el("li", elegido ? "producto-fila producto-elegible producto-elegido" : "producto-fila producto-elegible");
    const toggle = boton("", "elegir-producto", () => {
      if (hojaEstado.elegidos.has(l.id_detalle)) hojaEstado.elegidos.delete(l.id_detalle);
      else hojaEstado.elegidos.set(l.id_detalle, pendiente);
      dibujarHoja();
    });
    toggle.setAttribute("role", "checkbox");
    toggle.setAttribute("aria-checked", String(elegido));
    toggle.disabled = hojaEstado.ocupado;
    const texto = el("span", "elegir-texto");
    texto.append(
      el("strong", null, nombre),
      el("small", null, l.entregada > 0 ? `Faltan ${pendiente} de ${l.cantidad} · ya entregadas: ${l.entregada}` : `Faltan ${pendiente}`),
    );
    toggle.append(el("span", "casilla"), texto);
    li.appendChild(toggle);
    if (elegido) {
      const c = contador(hojaEstado.elegidos.get(l.id_detalle), pendiente, nombre, (nuevo) => {
        hojaEstado.elegidos.set(l.id_detalle, Math.max(1, Math.min(pendiente, nuevo)));
        dibujarHoja();
      });
      if (hojaEstado.ocupado) for (const b of c.querySelectorAll("button")) b.disabled = true;
      li.appendChild(c);
    }
    return li;
  }

  // ── ubicación del cliente ────────────────────────────────────────────────
  // Solo el enlace de Maps que cargó la oficina (o, si falta, sus coordenadas). NO se busca por el texto de la
  // dirección: las del sistema viejo son imprecisas y Maps terminaba mostrando cualquier lugar. Sin ubicación cargada
  // no se ofrece "Cómo llegar": se ofrece guardarla.
  function destinoMaps(c) {
    if (c.ubicacion_maps && /^https?:\/\//i.test(c.ubicacion_maps)) return c.ubicacion_maps;
    if (c.ubicacion_lat != null && c.ubicacion_lng != null) {
      return `https://www.google.com/maps/search/?api=1&query=${c.ubicacion_lat},${c.ubicacion_lng}`;
    }
    return null;
  }

  function crearNota(texto, esError) {
    return el("p", esError ? "entrega-nota entrega-nota-error" : "entrega-nota", texto);
  }

  function bloqueUbicacion(p) {
    const caja = el("div", "hoja-ubicacion");
    const ubi = ubicacionLocal(p.id_cliente);
    // Una ubicación guardada en el teléfono se ve ya, aunque todavía no haya llegado al servidor.
    const c = { ubicacion_maps: p.ubicacion_maps, ubicacion_lat: p.ubicacion_lat, ubicacion_lng: p.ubicacion_lng };
    if (!destinoMaps(c) && ubi && ubi.estado !== "rechazado") {
      c.ubicacion_lat = ubi.lat;
      c.ubicacion_lng = ubi.lng;
    }
    const destino = destinoMaps(c);
    if (destino && c.ubicacion_lat != null && c.ubicacion_lng != null) caja.appendChild(MapaMini.crear(c.ubicacion_lat, c.ubicacion_lng, destino));
    if (destino) {
      const enlace = el("a", "boton-secundario boton-ancho", "Cómo llegar");
      enlace.href = destino;
      enlace.target = "_blank";
      enlace.rel = "noopener noreferrer";
      caja.appendChild(enlace);
    } else {
      caja.appendChild(el("p", "entrega-sin-ubicacion", "Sin ubicación cargada"));
      const buscando = hojaEstado.buscandoGps;
      const guardar = boton(buscando ? "Buscando ubicación…" : "Guardar mi ubicación actual", "boton-secundario boton-ubicacion", () => guardarUbicacion(p));
      guardar.disabled = buscando || hojaEstado.ocupado;
      caja.appendChild(guardar);
    }
    if (ubi && ubi.estado === "pendiente") caja.appendChild(crearNota("Ubicación guardada en el teléfono. Se envía sola al volver la señal."));
    if (ubi && ubi.estado === "rechazado") {
      caja.appendChild(crearNota(`No se pudo guardar la ubicación: ${ubi.error}`, true));
      caja.appendChild(boton("Descartar aviso", "boton-secundario boton-ancho", () => ColaReparto.descartar(ubi.uuid)));
    }
    return caja;
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

  // Guarda la posición actual como la ubicación del cliente. Hay que estar en el lugar: por eso se confirma, y se
  // avisa si el GPS no es preciso. El GPS no necesita internet: sin señal queda guardada en el teléfono y se manda sola.
  async function guardarUbicacion(p) {
    const nombre = hojaEstado.nombre;
    if (!confirm(`¿Estás en el lugar de ${nombre}?\nSe guarda tu ubicación actual como la de este cliente.`)) return;
    hojaEstado.error = null;
    hojaEstado.buscandoGps = true;
    dibujarHoja();
    const terminar = (error) => {
      if (!hojaEstado) return;
      hojaEstado.buscandoGps = false;
      hojaEstado.error = error || null;
      dibujarHoja();
    };
    let coords;
    try {
      ({ coords } = await obtenerPosicion());
    } catch (e) {
      terminar(mensajeDeGps(e) || "No se pudo obtener la ubicación. Probá de nuevo.");
      return;
    }
    if (coords.accuracy > PRECISION_MAX_M && !confirm(`La precisión es baja (unos ${Math.round(coords.accuracy)} m). ¿Guardarla igual?`)) {
      terminar();
      return;
    }
    try {
      // Un aviso viejo de rechazo para este cliente ya no sirve: se reemplaza por este intento.
      for (const a of acciones) {
        if (a.tipo === "ubicacion" && a.id_cliente === p.id_cliente && a.estado === "rechazado") await ColaReparto.descartar(a.uuid);
      }
      const accion = await ColaReparto.guardarUbicacion(p.id_cliente, nombre, coords.latitude, coords.longitude);
      await ColaReparto.sincronizar();
      const estado = (await ColaReparto.listar()).find((a) => a.uuid === accion.uuid);
      terminar();
      if (estado && estado.estado === "enviado") {
        mostrarOk(`Ubicación guardada: ${nombre}.`);
        cargar(); // la lista ya trae la ubicación del cliente
      } else if (estado && estado.estado === "rechazado") {
        mostrarError(`No se pudo guardar la ubicación de ${nombre}: ${estado.error}`);
        cargar();
      } else {
        mostrarOk("Ubicación guardada en el teléfono. Se envía sola apenas haya señal.");
      }
    } catch (e) {
      terminar("No se pudo guardar la ubicación en el teléfono. Probá de nuevo.");
    }
  }

  // ── los botones del pie según lo que se esté haciendo ────────────────────
  function pieDeLaHoja(p) {
    const caja = el("div", "hoja-acciones");
    const { modo, ocupado } = hojaEstado;
    const admin = esAdmin();
    // Programar, quitar y borrar necesitan señal (van directo al servidor); lo de la calle y "Cancelar" no.
    const necesitaSenal = (b) => {
      b.disabled = ocupado || sinConexion;
      return b;
    };
    const libre = (b) => {
      b.disabled = ocupado;
      return b;
    };

    if (modo === "detalle") {
      const entrega = entregaLocal(p.id_pedido);
      const camino = caminoLocal(p.id_pedido);
      if (entrega && entrega.estado === "pendiente") {
        caja.appendChild(crearNota(`Guardado en el teléfono: ${textoDeAccion(entrega)}. Se envía solo al volver la señal.`));
        caja.appendChild(libre(boton("Deshacer", "boton-secundario", () => ColaReparto.descartar(entrega.uuid))));
      } else {
        if (entrega && entrega.estado === "rechazado") {
          caja.appendChild(crearNota(`No se pudo marcar la entrega: ${entrega.error}`, true));
          caja.appendChild(boton("Descartar aviso", "boton-secundario", () => ColaReparto.descartar(entrega.uuid)));
        }
        if (camino && camino.estado === "rechazado") {
          caja.appendChild(crearNota(`No se pudo marcar en camino: ${camino.error}`, true));
          caja.appendChild(boton("Descartar aviso", "boton-secundario", () => ColaReparto.descartar(camino.uuid)));
        }
        caja.appendChild(libre(boton("Entregado", "boton-entregar", () => cambiarModo("entrega", { tipo: "total", elegidos: new Map() }))));
        if (camino && camino.estado === "pendiente") {
          caja.appendChild(crearNota("Marcado en camino en el teléfono. Se envía solo al volver la señal."));
          caja.appendChild(libre(boton("Deshacer en camino", "boton-secundario", () => ColaReparto.descartar(camino.uuid))));
        } else if (estadoVisible(p) !== "en camino") {
          caja.appendChild(libre(boton("En camino", "boton-secundario", () => marcarEnCamino(p))));
        }
      }
      if (admin) {
        if (sinConexion) caja.appendChild(el("p", "hoja-nota hoja-nota-aviso", "Sin conexión. Para programar, quitar un artículo o borrar hace falta señal."));
        caja.appendChild(necesitaSenal(boton(p.fecha_entrega ? "Reprogramar" : "Programar", "boton-secundario", () => cambiarModo("programar", { fecha: fechaInicialParaProgramar(p) }))));
        caja.appendChild(necesitaSenal(boton("Borrar pedido", "boton-borrar", () => cambiarModo("confirmar", {
          confirmacion: { texto: `¿Borrar el pedido de ${p.cliente || "este cliente"}? No se puede deshacer.`, etiqueta: "Sí, borrar pedido", peligro: true, accion: borrarPedido },
        }))));
      }
      return caja;
    }
    if (modo === "entrega") {
      const parcial = hojaEstado.tipo === "parcial";
      const confirmar = boton(ocupado ? "Guardando…" : parcial ? "Confirmar entrega parcial" : "Confirmar entrega total", "boton-entregar", () => confirmarEntrega(p, parcial));
      confirmar.disabled = ocupado || (parcial && hojaEstado.elegidos.size === 0);
      caja.append(confirmar, libre(boton("Cancelar", "boton-secundario", () => cambiarModo("detalle"))));
      return caja;
    }
    if (modo === "programar") {
      const campo = el("div", "campo-fecha");
      const etiqueta = el("label", null, "Fecha de entrega");
      etiqueta.htmlFor = "fecha-programar";
      const entrada = document.createElement("input");
      entrada.type = "date";
      entrada.id = "fecha-programar";
      entrada.min = hoyIso();
      entrada.value = hojaEstado.fecha;
      entrada.addEventListener("input", () => {
        hojaEstado.fecha = entrada.value;
        confirmar.disabled = ocupado || sinConexion || !entrada.value || entrada.value < hoyIso();
      });
      campo.append(etiqueta, entrada);
      const confirmar = necesitaSenal(boton(ocupado ? "Guardando…" : "Programar", "boton-primario", programar));
      confirmar.disabled = ocupado || sinConexion || !hojaEstado.fecha || hojaEstado.fecha < hoyIso();
      caja.append(campo, confirmar, libre(boton("Cancelar", "boton-secundario", () => cambiarModo("detalle"))));
      return caja;
    }
    // confirmar
    const c = hojaEstado.confirmacion;
    caja.appendChild(el("p", "hoja-confirma", c.texto));
    const si = necesitaSenal(boton(ocupado ? "Guardando…" : c.etiqueta, c.peligro ? "boton-peligro" : "boton-entregar", c.accion));
    caja.append(si, libre(boton("Cancelar", "boton-secundario", () => cambiarModo("detalle"))));
    return caja;
  }

  // Mañana, o la fecha ya programada si todavía no pasó.
  function fechaInicialParaProgramar(p) {
    const hoy = hoyIso();
    if (p.fecha_entrega && p.fecha_entrega >= hoy) return p.fecha_entrega;
    const manana = new Date();
    manana.setDate(manana.getDate() + 1);
    return aIso(manana);
  }

  // Una fila de la lista de productos del detalle. La ✕ para quitar el artículo es solo del admin, y solo si el pedido
  // tiene más de un artículo (si es el único, lo que corresponde es "Borrar pedido") y del producto no se entregó nada
  // (si no, se perdería el registro de lo entregado). El servidor lo vuelve a controlar.
  function filaDeProducto(l, p) {
    const li = el("li", "producto-fila");
    li.appendChild(el("span", "producto-nombre", l.nombre || l.id_producto));
    li.appendChild(el("span", "producto-cantidad", l.entregada > 0 ? `${l.entregada} de ${l.cantidad} entregados` : `${l.cantidad} pedidos`));
    if (l.entregada > 0 && l.entregada < l.cantidad) li.appendChild(barraDeAvance(l.entregada, l.cantidad));
    if (hojaEstado.modo === "detalle" && esAdmin() && p.lineas.length > 1 && l.entregada === 0) {
      li.classList.add("producto-con-quitar");
      const quitar = boton("✕", "producto-quitar", () => cambiarModo("confirmar", {
        confirmacion: {
          texto: `¿Quitar ${l.cantidad} × ${l.nombre || l.id_producto} del pedido de ${p.cliente || "este cliente"}?`,
          etiqueta: "Sí, quitar",
          peligro: true,
          accion: () => quitarLinea(l.id_detalle),
        },
      }));
      quitar.setAttribute("aria-label", `Quitar ${l.nombre || l.id_producto} del pedido`);
      quitar.disabled = sinConexion;
      li.appendChild(quitar);
    }
    return li;
  }

  // El cuerpo de la hoja cuando se está entregando: Entrega total o parcial, lado a lado.
  function cuerpoEntrega(p) {
    const frag = document.createDocumentFragment();
    const { ocupado, tipo } = hojaEstado;
    const pendientes = lineasPendientes(p);

    const modos = el("div", "entrega-modos");
    modos.setAttribute("role", "group");
    modos.setAttribute("aria-label", "Tipo de entrega");
    for (const [clave, texto] of [["total", "Entrega total"], ["parcial", "Entrega parcial"]]) {
      const b = boton(texto, "entrega-modo", () => cambiarModo("entrega", { tipo: clave }));
      b.setAttribute("aria-pressed", String(tipo === clave));
      b.disabled = ocupado;
      modos.appendChild(b);
    }
    frag.appendChild(modos);

    const unidades = pendientes.reduce((s, l) => s + faltan(l), 0);
    const productos = el("ul", "producto-lista");
    if (tipo === "total") {
      frag.appendChild(el("p", "hoja-nota hoja-nota-cuerpo", `Se entrega todo lo que falta: ${pendientes.length} ${pendientes.length === 1 ? "producto" : "productos"} · ${unidades} u.`));
      for (const l of pendientes) {
        const li = el("li", "producto-fila");
        li.append(el("span", "producto-nombre", l.nombre || l.id_producto), el("span", "producto-cantidad", `${faltan(l)} u.`));
        productos.appendChild(li);
      }
    } else {
      frag.appendChild(el("p", "hoja-nota hoja-nota-cuerpo", "Tocá los productos que entregaste. Lo que no marques queda pendiente para otra entrega."));
      for (const l of pendientes) productos.appendChild(filaElegible(l));
    }
    frag.appendChild(productos);

    const todoMarcado = tipo === "parcial" && pendientes.length > 0 && pendientes.every((l) => hojaEstado.elegidos.get(l.id_detalle) === faltan(l));
    if (todoMarcado) frag.appendChild(el("p", "hoja-nota hoja-nota-cuerpo hoja-nota-aviso", "Marcaste todo lo que faltaba: el pedido va a quedar entregado por completo."));
    else if (tipo === "parcial" && hojaEstado.elegidos.size > 0) frag.appendChild(el("p", "hoja-nota hoja-nota-cuerpo", "El pedido va a volver a pendiente con lo que no marcaste."));
    return frag;
  }

  function dibujarHoja() {
    const p = buscarPedido(hojaEstado.id);
    if (!p) return;
    hojaEstado.nombre = p.cliente || "este cliente";
    hoja.textContent = "";
    const cab = el("header", "hoja-cabecera");
    const titulo = el("h3", "hoja-titulo", hojaEstado.nombre);
    titulo.id = "titulo-hoja";
    hoja.setAttribute("aria-labelledby", "titulo-hoja");
    const cerrar = boton("Cerrar", "boton-link hoja-cerrar", cerrarHoja);
    cerrar.disabled = hojaEstado.ocupado;
    cab.append(titulo, pastilla(estadoVisible(p)), cerrar);
    hoja.appendChild(cab);

    if (hojaEstado.modo === "entrega") {
      hoja.appendChild(cuerpoEntrega(p));
    } else {
      const meta = el("div", "hoja-meta");
      const fecha = textoDeFecha(p);
      meta.appendChild(el("span", fecha.atrasado ? "fila-atrasada" : null, fecha.texto));
      if (p.fecha_pedido) meta.appendChild(el("span", null, `Pedido del ${diaCorto(p.fecha_pedido)}`));
      meta.appendChild(el("span", null, p.cargado_por ? `Cargado por ${p.cargado_por}` : p.origen === "pc" ? "Cargado desde la PC" : ""));
      for (const sinTexto of [...meta.children].filter((n) => !n.textContent)) sinTexto.remove();
      hoja.appendChild(meta);

      if (hojaEstado.modo === "detalle") {
        const donde = el("div", "hoja-donde");
        if (p.direccion) donde.appendChild(el("p", "entrega-direccion", p.direccion));
        donde.appendChild(bloqueUbicacion(p));
        hoja.appendChild(donde);
      }
      if (p.observaciones) {
        const obs = el("div", "hoja-observaciones");
        obs.append(el("strong", null, "Observaciones"), el("p", null, p.observaciones));
        hoja.appendChild(obs);
      }
      const productos = el("ul", "producto-lista");
      for (const l of p.lineas) productos.appendChild(filaDeProducto(l, p));
      if (p.lineas.length === 0) productos.appendChild(el("li", "producto-fila", "Este pedido no tiene productos."));
      hoja.appendChild(productos);
    }
    if (hojaEstado.error) hoja.appendChild(el("p", "error", hojaEstado.error));
    hoja.appendChild(pieDeLaHoja(p));
    // Lo que quedó dibujado: así `actualizarHojaAbierta` sabe si hace falta redibujar después de recargar la lista.
    hojaEstado.firma = firmaDeLaHoja(p);
  }

  // ── lo de la calle: va a la cola del teléfono y de ahí al servidor ───────
  // `crear` guarda la orden en el teléfono. Se cierra la hoja, se intenta mandar y se avisa cómo quedó.
  async function mandar(crear, nombre, { ok, guardada, fallo }) {
    hojaEstado.ocupado = true;
    hojaEstado.error = null;
    dibujarHoja();
    let accion;
    try {
      accion = await crear();
    } catch (e) {
      if (hojaEstado) {
        hojaEstado.ocupado = false;
        hojaEstado.error = "No se pudo guardar en el teléfono. Probá de nuevo.";
        dibujarHoja();
      }
      return;
    }
    cerrarHoja();
    await ColaReparto.sincronizar();
    const estado = (await ColaReparto.listar()).find((a) => a.uuid === accion.uuid);
    if (estado && estado.estado === "enviado") mostrarOk(ok);
    else if (estado && estado.estado === "rechazado") mostrarError(`${fallo} ${nombre}: ${estado.error}`);
    else mostrarOk(guardada);
    await cargar(); // el pedido cambió (o se rechazó porque lo cambiaron en la oficina): se muestra como está ahora
  }

  function marcarEnCamino(p) {
    const nombre = hojaEstado.nombre;
    return mandar(() => ColaReparto.enCamino(p.id_pedido, nombre), nombre, {
      ok: `En camino: ${nombre}.`,
      guardada: "Guardado en el teléfono. Se envía solo apenas haya señal.",
      fallo: "No se pudo marcar en camino el pedido de",
    });
  }

  function confirmarEntrega(p, parcial) {
    const nombre = hojaEstado.nombre;
    let crear;
    let todoMarcado = false; // una parcial que marca todo lo que faltaba es, de hecho, una entrega total
    if (parcial) {
      // Se manda el TOTAL que tiene que quedar en cada línea, con la lista de ahora (nunca más de lo que falta).
      const lineas = [];
      const resumen = [];
      for (const l of lineasPendientes(p)) {
        const n = Math.min(hojaEstado.elegidos.get(l.id_detalle) || 0, faltan(l));
        if (n <= 0) continue;
        lineas.push({ id_detalle: l.id_detalle, entregada: l.entregada + n });
        resumen.push(`${n} × ${l.nombre || l.id_producto}`);
      }
      if (lineas.length === 0) return Promise.resolve();
      todoMarcado = lineasPendientes(p).every((l) => (hojaEstado.elegidos.get(l.id_detalle) || 0) >= faltan(l));
      crear = () => ColaReparto.entregarParcial(p.id_pedido, nombre, lineas, resumen);
    } else {
      crear = () => ColaReparto.entregar(p.id_pedido, nombre);
    }
    const parcialDeVerdad = parcial && !todoMarcado;
    return mandar(crear, nombre, {
      ok: parcialDeVerdad ? `Entrega parcial registrada: ${nombre}. El pedido quedó pendiente con lo que falta.` : `Entregado: ${nombre}.`,
      guardada: `${parcialDeVerdad ? "Entrega parcial guardada" : "Entrega guardada"} en el teléfono. Se envía sola apenas haya señal.`,
      fallo: "No se pudo marcar la entrega de",
    });
  }

  // ── lo del admin: va directo al servidor y, si sale bien, recarga la lista ──
  // `mensaje` es el texto de éxito, o una función que lo arma con la respuesta del servidor. Con `mantener` la hoja no
  // se cierra: vuelve al detalle del mismo pedido (por ejemplo, después de quitar un artículo).
  async function ejecutar(ruta, opciones, mensaje, { mantener = false } = {}) {
    hojaEstado.ocupado = true;
    hojaEstado.error = null;
    dibujarHoja();
    let respuesta;
    try {
      respuesta = await Api.llamar(ruta, opciones);
    } catch (e) {
      hojaEstado.ocupado = false;
      hojaEstado.error = typeof e.status === "number" ? e.message : "No hay conexión. Probá de nuevo cuando tengas señal.";
      if (e.status === 409) await cargar(); // el pedido cambió en la oficina: se muestra como está ahora
      if (hojaEstado) dibujarHoja();
      return;
    }
    if (mantener && hojaEstado) {
      hojaEstado.ocupado = false;
      hojaEstado.modo = "detalle";
      mostrarOk(typeof mensaje === "function" ? mensaje(respuesta) : mensaje);
      await cargar();
      if (hojaEstado) dibujarHoja(); // el modo y el "guardando" cambiaron aunque la lista no
      return;
    }
    cerrarHoja();
    mostrarOk(typeof mensaje === "function" ? mensaje(respuesta) : mensaje);
    await cargar();
  }

  const cuerpo = (objeto) => ({ method: "POST", body: JSON.stringify(objeto) });

  // Quita un artículo del pedido y deja la hoja abierta, para seguir revisando el resto.
  function quitarLinea(idDetalle) {
    return ejecutar(`/pedidos/${hojaEstado.id}/lineas/${idDetalle}`, { method: "DELETE" },
      (r) => (r.completo ? "Artículo quitado. Lo que quedaba ya estaba entregado: el pedido quedó entregado." : "Artículo quitado del pedido."),
      { mantener: true });
  }

  function programar() {
    const fecha = hojaEstado.fecha;
    return ejecutar(`/pedidos/${hojaEstado.id}/programar`, cuerpo({ fecha }), `Pedido programado para el ${diaCorto(fecha)}.`);
  }

  function borrarPedido() {
    return ejecutar(`/pedidos/${hojaEstado.id}`, { method: "DELETE" }, "Pedido borrado.");
  }

  // ── "Agregar pedido" (solo admin): se le prestan a esta pantalla la lista de clientes y la cola del vendedor ──
  // Son los mismos nodos (con sus eventos), no copias: así catalogo.js y cola-ui.js siguen funcionando sin cambios.
  function reubicar(id, destino) {
    const nodo = $(id);
    reubicados.push({ nodo, padre: nodo.parentNode, siguiente: nodo.nextSibling });
    destino.appendChild(nodo);
  }

  function restaurar() {
    for (const r of reubicados.reverse()) r.padre.insertBefore(r.nodo, r.siguiente);
    reubicados.length = 0;
  }

  function alternarClientes(abrir) {
    const mostrar = abrir === undefined ? zonaClientes.hidden : abrir;
    zonaClientes.hidden = !mostrar;
    btnAgregar.setAttribute("aria-expanded", String(mostrar));
    if (mostrar) $("buscar-cliente").focus();
  }

  function limpiar() {
    cerrarHoja();
    datos = [];
    acciones = [];
    hayDatos = false;
    sinConexion = false;
    guardadoEn = null;
    firmaLista = "";
    enviadosVistos.clear();
    elError.hidden = elAviso.hidden = elOk.hidden = elAvisoCola.hidden = true;
    alternarClientes(false);
    render();
    restaurar();
    // Los pedidos del negocio (con direcciones) no quedan guardados en un teléfono que ya no está con la sesión abierta.
    MetaDB.borrar(CLAVE_CACHE).catch(() => {});
  }

  // Al entrar: según el perfil, se ve o no "Agregar pedido". Se borra la copia que guardaba la pantalla de reparto
  // de antes (traía direcciones y teléfonos).
  function configurarPerfil() {
    btnAgregar.hidden = !esAdmin();
    MetaDB.borrar("reparto_lista").catch(() => {});
  }

  async function empezar() {
    configurarPerfil();
    await refrescarAcciones();
    await mostrarDesdeCache(); // se ve algo al instante, aunque no haya señal
    cargar();
    ColaReparto.sincronizar();
  }

  btnActualizar.addEventListener("click", () => {
    cargar();
    ColaReparto.sincronizar();
  });
  btnAgregar.addEventListener("click", () => alternarClientes());
  // Un toque en el fondo oscuro cierra la hoja; Esc también (lo hace el navegador y dispara "close").
  hoja.addEventListener("click", (ev) => {
    if (ev.target === hoja && !(hojaEstado && (hojaEstado.ocupado || hojaEstado.buscandoGps))) cerrarHoja();
  });
  hoja.addEventListener("close", () => {
    hojaEstado = null;
  });
  hoja.addEventListener("cancel", (ev) => {
    if (hojaEstado && (hojaEstado.ocupado || hojaEstado.buscandoGps)) ev.preventDefault(); // no se cierra a mitad de guardar
  });

  // El reparto entra directo a esta pantalla (no lleva barra de secciones); el admin llega por la pestaña Pedidos.
  document.addEventListener("mana:reparto-iniciado", empezar);
  document.addEventListener("mana:admin-iniciado", () => {
    reubicar("panel-cola", zonaCola);
    reubicar("buscar-cliente", zonaClientes);
    reubicar("estado-catalogo", zonaClientes);
    reubicar("lista-clientes", zonaClientes);
  });
  document.addEventListener("mana:gestion-mostrada", empezar);
  document.addEventListener("mana:volvio-a-gestion", cargar); // se cargó un pedido: tiene que aparecer en la lista
  // "Ver pedido" en un pin del mapa (mapa.js): se abre el detalle de ese pedido, como si se hubiera tocado en la lista.
  document.addEventListener("mana:abrir-pedido", (ev) => {
    if (buscarPedido(ev.detail) && !hojaEstado) abrirHoja(ev.detail);
  });
  document.addEventListener("mana:cliente-elegido", () => alternarClientes(false));
  document.addEventListener("mana:sesion-cerrada", limpiar);
  document.addEventListener("mana:cola-reparto-cambio", () => {
    if (!pantalla.hidden) refrescarAcciones();
  });

  // Vivo: se actualiza sola mientras se mira (cada minuto, al volver a la app, al volver la señal y apenas llega un
  // aviso de pedido nuevo, programado o entregado). Si no se está mirando esta pantalla, no se gasta red: al volver a
  // ella se actualiza.
  const mirando = () => !pantalla.hidden && !document.hidden;
  const actualizarSiSeMira = () => {
    if (mirando() && !(hojaEstado && hojaEstado.ocupado)) {
      cargar();
      ColaReparto.sincronizar();
    }
  };
  document.addEventListener("visibilitychange", actualizarSiSeMira);
  window.addEventListener("online", actualizarSiSeMira);
  document.addEventListener("mana:aviso-recibido", actualizarSiSeMira);
  setInterval(actualizarSiSeMira, INTERVALO_MS);
})();
