// Pestaña "Pedidos" del admin: dos tarjetas (lo que falta entregar y lo entregado en los últimos 7 días) y, al
// tocar un pedido, su detalle con las acciones de la PC: entregar todo, entrega parcial, programar (o reprogramar)
// y borrar. El botón "Agregar pedido" despliega la misma lista de clientes que ve un vendedor.
//
// Todo lo que cambia un pedido va directo al servidor (GET /pedidos/gestion y las rutas de routers/gestion.py):
// necesita señal, a propósito. No hay cola sin conexión como en el reparto: un borrado o una entrega no deberían
// quedar "pendientes de enviar" en un teléfono. Esta pantalla solo dibuja lo que dice el servidor.
(() => {
  const $ = (id) => document.getElementById(id);
  const pantalla = $("pantalla-gestion");
  const elError = $("error-gestion");
  const elAviso = $("aviso-gestion");
  const elOk = $("mensaje-gestion");
  const btnActualizar = $("btn-actualizar-gestion");
  const btnAgregar = $("btn-agregar-pedido");
  const zonaClientes = $("clientes-gestion");
  const zonaCola = $("zona-cola-gestion");
  const hoja = $("detalle-pedido");
  const listas = {
    pendientes: { lista: $("lista-pendientes"), vacio: $("vacio-pendientes"), cuenta: $("cuenta-pendientes") },
    entregados: { lista: $("lista-entregados"), vacio: $("vacio-entregados"), cuenta: $("cuenta-entregados") },
  };

  const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const ESTADOS = {
    pendiente: ["Pendiente", "pendiente"],
    programado: ["Programado", "programado"],
    "en camino": ["En camino", "camino"],
    entregado: ["Entregado", "entregado"],
  };

  const CLAVE_CACHE = "gestion_lista";
  const INTERVALO_MS = 60000;

  let datos = { pendientes: [], entregados: [] };
  let hayDatos = false;
  let cargando = false;
  let sinConexion = false; // el último intento de traer la lista falló por la red: se ve la última guardada y no se puede actuar
  let guardadoEn = null; // cuándo se trajo la lista que se está mostrando
  let firmaListas = ""; // para no redibujar (ni perder el scroll) si no cambió nada
  let temporizadorOk = null;
  const reubicados = []; // nodos de la pantalla del vendedor que se prestan a esta pantalla mientras dure la sesión

  // Lo que muestra la hoja del pedido abierto. `modo`: detalle | parcial | programar | confirmar.
  let hojaEstado = null; // { id, modo, ocupado, error, ahora: Map(id_detalle -> n), fecha, confirmacion }

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
    if (p.estado === "entregado") return { texto: p.fecha_entrega ? `Entregado el ${diaCorto(p.fecha_entrega)}` : "Entregado", atrasado: false };
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

  function pastilla(estado) {
    const [texto, clase] = ESTADOS[estado] || [estado, "pendiente"];
    return el("span", `pastilla pastilla-${clase}`, texto);
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
    clearTimeout(temporizadorOk);
    temporizadorOk = setTimeout(() => {
      elOk.hidden = true;
    }, 6000);
  }

  function mostrarError(texto) {
    elError.textContent = texto;
    elError.hidden = false;
  }

  // ── las dos tarjetas ─────────────────────────────────────────────────────
  function crearFila(p) {
    const li = el("li");
    const fila = boton("", "fila-pedido", () => abrirHoja(p.id_pedido));
    const fecha = textoDeFecha(p);
    fila.append(el("span", "fila-cliente", p.cliente || "Cliente sin nombre"), pastilla(p.estado));
    fila.appendChild(el("span", fecha.atrasado ? "fila-detalle fila-atrasada" : "fila-detalle", fecha.texto));
    const { cantidad, entregada } = sumar(p);
    if (p.estado !== "entregado" && entregada > 0 && entregada < cantidad) fila.appendChild(barraDeAvance(entregada, cantidad));
    li.appendChild(fila);
    return li;
  }

  function dibujarLista(clave, pedidos) {
    const { lista, vacio, cuenta } = listas[clave];
    lista.textContent = "";
    for (const p of pedidos) lista.appendChild(crearFila(p));
    cuenta.textContent = String(pedidos.length);
    vacio.hidden = !(hayDatos && pedidos.length === 0);
  }

  function render() {
    // La fecha de hoy entra en la firma: al cambiar el día, "Entrega hoy" y "Debía entregarse" se vuelven a calcular.
    const firma = JSON.stringify([datos, hayDatos, hoyIso()]);
    if (firma === firmaListas) return;
    firmaListas = firma;
    dibujarLista("pendientes", datos.pendientes);
    dibujarLista("entregados", datos.entregados);
  }

  const hora = (iso) => new Date(iso).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });

  function avisarSinConexion() {
    elAviso.textContent = `Sin conexión (lista de las ${hora(guardadoEn)}). Para entregar, programar o borrar hace falta señal.`;
    elAviso.hidden = false;
  }

  // La última lista que se trajo, para poder abrir la pestaña sin señal. Se usa SOLO si falla la red (nunca antes de
  // preguntarle al servidor: sobre una lista vieja no se debería actuar) y se borra al salir.
  async function mostrarDesdeCache() {
    try {
      const copia = await MetaDB.leer(CLAVE_CACHE);
      if (copia && copia.usuario === Api.nombre() && !hayDatos) {
        datos = copia.datos;
        guardadoEn = copia.guardado_en;
        hayDatos = true;
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
        // Sin red: se sigue con la lista que había (la de esta sesión o la guardada en el teléfono), sin poder actuar.
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
  const buscarPedido = (id) => [...datos.pendientes, ...datos.entregados].find((p) => p.id_pedido === id) || null;

  function abrirHoja(id) {
    hojaEstado = { id, modo: "detalle", ocupado: false, error: null, ahora: new Map(), fecha: "", confirmacion: null };
    dibujarHoja();
    if (!hoja.open) hoja.showModal();
  }

  function cerrarHoja() {
    hojaEstado = null;
    if (hoja.open) hoja.close();
  }

  // Después de recargar la lista: si el pedido abierto cambió (o se perdió o volvió la señal) se redibuja; si ya no
  // está, se cierra. Si no cambió nada NO se redibuja: se perdería el foco, el selector de fecha abierto o lo que
  // se esté escribiendo.
  function actualizarHojaAbierta() {
    const p = buscarPedido(hojaEstado.id);
    if (!p) {
      cerrarHoja();
      return;
    }
    if (p.estado === "entregado" && hojaEstado.modo !== "detalle") hojaEstado.modo = "detalle";
    // Si alguien entregó parte mientras tanto, lo que falta es menos: el contador no puede pasarse.
    for (const l of p.lineas) {
      const n = hojaEstado.ahora.get(l.id_detalle);
      if (n !== undefined) hojaEstado.ahora.set(l.id_detalle, Math.min(n, l.cantidad - l.entregada));
    }
    if (JSON.stringify([p, sinConexion, [...hojaEstado.ahora]]) === hojaEstado.firma) return;
    dibujarHoja();
  }

  function cambiarModo(modo, extra = {}) {
    Object.assign(hojaEstado, { modo, error: null, ...extra });
    dibujarHoja();
  }

  function contador(valor, max, etiqueta, alCambiar) {
    const caja = el("div", "contador");
    const menos = boton("−", "contador-boton", () => alCambiar(valor - 1));
    const mas = boton("+", "contador-boton", () => alCambiar(valor + 1));
    menos.setAttribute("aria-label", `Entregar una unidad menos de ${etiqueta}`);
    mas.setAttribute("aria-label", `Entregar una unidad más de ${etiqueta}`);
    menos.disabled = valor <= 0;
    mas.disabled = valor >= max;
    const numero = el("output", "contador-valor", String(valor));
    caja.append(menos, numero, mas);
    return caja;
  }

  function filaDeProducto(l, modo) {
    const pendiente = l.cantidad - l.entregada;
    const li = el("li", "producto-fila");
    const nombre = el("span", "producto-nombre", l.nombre || l.id_producto);
    li.appendChild(nombre);
    if (modo === "parcial" && pendiente > 0) {
      const n = hojaEstado.ahora.get(l.id_detalle) || 0;
      li.classList.add("producto-editable");
      li.appendChild(el("span", "producto-cantidad", `Pedido ${l.cantidad}, falta entregar ${pendiente}`));
      li.appendChild(contador(n, pendiente, l.nombre || l.id_producto, (nuevo) => {
        hojaEstado.ahora.set(l.id_detalle, Math.max(0, Math.min(pendiente, nuevo)));
        dibujarHoja();
      }));
    } else {
      li.appendChild(el("span", "producto-cantidad", l.entregada > 0 ? `${l.entregada} de ${l.cantidad} entregados` : `${l.cantidad} pedidos`));
      if (l.entregada > 0 && l.entregada < l.cantidad) li.appendChild(barraDeAvance(l.entregada, l.cantidad));
    }
    return li;
  }

  // Los botones del pie según lo que se esté haciendo.
  function acciones(p) {
    const caja = el("div", "hoja-acciones");
    const { modo, ocupado } = hojaEstado;
    // Las acciones necesitan señal (van directo al servidor); "Cancelar" no.
    const bloqueada = (b) => {
      b.disabled = ocupado || sinConexion;
      return b;
    };
    const libre = (b) => {
      b.disabled = ocupado;
      return b;
    };
    if (p.estado === "entregado") {
      caja.appendChild(el("p", "hoja-nota", "Este pedido ya está entregado. Para cambiarlo, usá la PC."));
      return caja;
    }
    if (sinConexion) caja.appendChild(el("p", "hoja-nota hoja-nota-aviso", "Sin conexión. Para entregar, programar o borrar hace falta señal."));
    if (modo === "detalle") {
      caja.append(
        bloqueada(boton("Entregar todo", "boton-entregar", () => cambiarModo("confirmar", {
          confirmacion: { texto: `¿Marcar como entregado todo el pedido de ${p.cliente || "este cliente"}?`, etiqueta: "Sí, entregar todo", peligro: false, accion: entregarTodo },
        }))),
      );
      const fila = el("div", "hoja-acciones-fila");
      fila.append(
        bloqueada(boton("Entrega parcial", "boton-secundario", () => cambiarModo("parcial", { ahora: new Map() }))),
        bloqueada(boton("Programar", "boton-secundario", () => cambiarModo("programar", { fecha: fechaInicialParaProgramar(p) }))),
      );
      caja.appendChild(fila);
      caja.appendChild(bloqueada(boton("Borrar pedido", "boton-borrar", () => cambiarModo("confirmar", {
        confirmacion: { texto: `¿Borrar el pedido de ${p.cliente || "este cliente"}? No se puede deshacer.`, etiqueta: "Sí, borrar pedido", peligro: true, accion: borrarPedido },
      }))));
      return caja;
    }
    if (modo === "parcial") {
      const total = [...hojaEstado.ahora.values()].reduce((s, n) => s + n, 0);
      const confirmar = bloqueada(boton(ocupado ? "Guardando…" : "Confirmar entrega", "boton-entregar", entregaParcial));
      confirmar.disabled = ocupado || sinConexion || total === 0;
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
      const confirmar = bloqueada(boton(ocupado ? "Guardando…" : "Programar", "boton-primario", programar));
      confirmar.disabled = ocupado || sinConexion || !hojaEstado.fecha || hojaEstado.fecha < hoyIso();
      caja.append(campo, confirmar, libre(boton("Cancelar", "boton-secundario", () => cambiarModo("detalle"))));
      return caja;
    }
    // confirmar
    const c = hojaEstado.confirmacion;
    caja.appendChild(el("p", "hoja-confirma", c.texto));
    const si = bloqueada(boton(ocupado ? "Guardando…" : c.etiqueta, c.peligro ? "boton-peligro" : "boton-entregar", c.accion));
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

  function dibujarHoja() {
    const p = buscarPedido(hojaEstado.id);
    if (!p) return;
    hoja.textContent = "";
    const cab = el("header", "hoja-cabecera");
    const titulo = el("h3", "hoja-titulo", p.cliente || "Cliente sin nombre");
    titulo.id = "titulo-hoja";
    hoja.setAttribute("aria-labelledby", "titulo-hoja");
    const cerrar = boton("Cerrar", "boton-link hoja-cerrar", cerrarHoja);
    cab.append(titulo, pastilla(p.estado), cerrar);

    const meta = el("div", "hoja-meta");
    const fecha = textoDeFecha(p);
    meta.appendChild(el("span", fecha.atrasado ? "fila-atrasada" : null, fecha.texto));
    if (p.fecha_pedido) meta.appendChild(el("span", null, `Pedido del ${diaCorto(p.fecha_pedido)}`));
    meta.appendChild(el("span", null, p.cargado_por ? `Cargado por ${p.cargado_por}` : p.origen === "pc" ? "Cargado desde la PC" : ""));
    for (const vacio of [...meta.children].filter((n) => !n.textContent)) vacio.remove();

    const lista = el("ul", "producto-lista");
    for (const l of p.lineas) lista.appendChild(filaDeProducto(l, hojaEstado.modo));
    if (p.lineas.length === 0) lista.appendChild(el("li", "producto-fila", "Este pedido no tiene productos."));

    hoja.append(cab, meta, lista);
    if (hojaEstado.error) hoja.appendChild(el("p", "error", hojaEstado.error));
    hoja.appendChild(acciones(p));
    // Lo que quedó dibujado: así `actualizarHojaAbierta` sabe si hace falta redibujar después de recargar la lista.
    hojaEstado.firma = JSON.stringify([p, sinConexion, [...hojaEstado.ahora]]);
  }

  // ── acciones: todas van al servidor y, si salen bien, recargan la lista ──
  async function ejecutar(ruta, opciones, mensaje) {
    hojaEstado.ocupado = true;
    hojaEstado.error = null;
    dibujarHoja();
    try {
      await Api.llamar(ruta, opciones);
    } catch (e) {
      hojaEstado.ocupado = false;
      hojaEstado.error = typeof e.status === "number" ? e.message : "No hay conexión. Probá de nuevo cuando tengas señal.";
      if (e.status === 409) await cargar(); // el pedido cambió en la oficina: se muestra como está ahora
      if (hojaEstado) dibujarHoja();
      return;
    }
    cerrarHoja();
    mostrarOk(mensaje);
    await cargar();
  }

  const cuerpo = (objeto) => ({ method: "POST", body: JSON.stringify(objeto) });

  function entregarTodo() {
    return ejecutar(`/pedidos/${hojaEstado.id}/entregar`, { method: "POST" }, "Pedido entregado.");
  }

  function entregaParcial() {
    const p = buscarPedido(hojaEstado.id);
    const lineas = p.lineas
      .filter((l) => (hojaEstado.ahora.get(l.id_detalle) || 0) > 0)
      .map((l) => ({ id_detalle: l.id_detalle, entregada: l.entregada + hojaEstado.ahora.get(l.id_detalle) })); // el TOTAL que tiene que quedar
    if (lineas.length === 0) return Promise.resolve();
    return ejecutar(`/pedidos/${hojaEstado.id}/entrega-parcial`, cuerpo({ lineas }), "Entrega registrada.");
  }

  function programar() {
    const fecha = hojaEstado.fecha;
    return ejecutar(`/pedidos/${hojaEstado.id}/programar`, cuerpo({ fecha }), `Pedido programado para el ${diaCorto(fecha)}.`);
  }

  function borrarPedido() {
    return ejecutar(`/pedidos/${hojaEstado.id}`, { method: "DELETE" }, "Pedido borrado.");
  }

  // ── "Agregar pedido": se le prestan a esta pantalla la lista de clientes y la cola del vendedor ──
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
    datos = { pendientes: [], entregados: [] };
    hayDatos = false;
    sinConexion = false;
    guardadoEn = null;
    firmaListas = "";
    elError.hidden = elAviso.hidden = elOk.hidden = true;
    alternarClientes(false);
    render();
    restaurar();
    // Los pedidos del negocio no quedan guardados en un teléfono que ya no está con la sesión abierta.
    MetaDB.borrar(CLAVE_CACHE).catch(() => {});
  }

  btnActualizar.addEventListener("click", cargar);
  btnAgregar.addEventListener("click", () => alternarClientes());
  // Un toque en el fondo oscuro cierra la hoja; Esc también (lo hace el navegador y dispara "close").
  hoja.addEventListener("click", (ev) => {
    if (ev.target === hoja && !(hojaEstado && hojaEstado.ocupado)) cerrarHoja();
  });
  hoja.addEventListener("close", () => {
    hojaEstado = null;
  });
  hoja.addEventListener("cancel", (ev) => {
    if (hojaEstado && hojaEstado.ocupado) ev.preventDefault(); // no se cierra a mitad de guardar
  });

  document.addEventListener("mana:admin-iniciado", () => {
    reubicar("panel-cola", zonaCola);
    reubicar("buscar-cliente", zonaClientes);
    reubicar("estado-catalogo", zonaClientes);
    reubicar("lista-clientes", zonaClientes);
  });
  document.addEventListener("mana:gestion-mostrada", cargar);
  document.addEventListener("mana:volvio-a-gestion", cargar); // se cargó un pedido: tiene que aparecer en Pendientes
  document.addEventListener("mana:cliente-elegido", () => alternarClientes(false));
  document.addEventListener("mana:sesion-cerrada", limpiar);

  // Vivo: se actualiza sola mientras se mira (cada minuto, al volver a la app, al volver la señal y apenas llega un
  // aviso de pedido nuevo, programado o entregado). Si no se está mirando esta pestaña, no se gasta red: al volver a
  // ella (`mana:gestion-mostrada`) se actualiza.
  const mirando = () => !pantalla.hidden && !document.hidden;
  const actualizarSiSeMira = () => {
    if (mirando() && !(hojaEstado && hojaEstado.ocupado)) cargar();
  };
  document.addEventListener("visibilitychange", actualizarSiSeMira);
  window.addEventListener("online", actualizarSiSeMira);
  document.addEventListener("mana:aviso-recibido", actualizarSiSeMira);
  setInterval(actualizarSiSeMira, INTERVALO_MS);
})();
