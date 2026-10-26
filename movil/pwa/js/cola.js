// Cola de pedidos: todo pedido se guarda PRIMERO en el teléfono (IndexedDB) y
// después se intenta enviar. Así nada se pierde sin señal, ni si se cierra la
// app a mitad de camino. Estados de cada pedido:
//   pendiente  guardado, todavía no confirmado por el servidor (se reintenta solo)
//   enviado    el servidor lo confirmó (guardamos su id_pedido)
//   rechazado  el servidor dijo que es inválido (ej. producto dado de baja): NO se
//              reintenta solo, el vendedor lo descarta y lo vuelve a cargar
//
// Reintentar nunca duplica: el `uuid` lo genera el teléfono y el servidor es
// idempotente por ese uuid (si el envío llegó pero se perdió la respuesta, el
// reintento devuelve el mismo pedido).
const Cola = (() => {
  const RETENCION_ENVIADOS_MS = 3 * 24 * 60 * 60 * 1000;
  const INTERVALO_REINTENTO_MS = 30000;
  const ERRORES_REINTENTABLES = [401, 408, 429]; // 5xx y errores de red también se reintentan

  let sincronizando = false;
  let repetir = false;

  function avisarCambio() {
    document.dispatchEvent(new CustomEvent("mana:cola-cambio"));
  }

  // Solo los pedidos del vendedor logueado: si dos vendedores comparten teléfono,
  // el pedido de uno no se envía (ni se muestra) bajo la sesión del otro.
  async function listar() {
    const nombre = Api.nombre();
    const todos = await ColaDB.todos();
    return todos.filter((p) => p.vendedor === nombre).sort((a, b) => a.creado_en.localeCompare(b.creado_en));
  }

  async function encolar({ id_cliente, cliente_nombre, fecha_pedido, lineas }) {
    const pedido = {
      uuid: crypto.randomUUID(),
      vendedor: Api.nombre(),
      id_cliente,
      cliente_nombre,
      fecha_pedido,
      lineas,
      estado: "pendiente",
      error: null,
      id_pedido: null,
      creado_en: new Date().toISOString(),
      enviado_en: null,
    };
    await ColaDB.agregar(pedido);
    avisarCambio();
    return pedido;
  }

  async function obtener(uuid) {
    return (await listar()).find((p) => p.uuid === uuid);
  }

  async function descartar(uuid) {
    await ColaDB.borrar(uuid);
    avisarCambio();
  }

  async function cantidadPorEnviar() {
    return (await listar()).filter((p) => p.estado === "pendiente").length;
  }

  async function purgarEnviadosViejos() {
    const limite = Date.now() - RETENCION_ENVIADOS_MS;
    for (const p of await listar()) {
      if (p.estado === "enviado" && p.enviado_en && new Date(p.enviado_en).getTime() < limite) {
        await ColaDB.borrar(p.uuid);
      }
    }
  }

  async function enviarUno(p) {
    try {
      const r = await Api.llamar("/pedidos", {
        method: "POST",
        body: JSON.stringify({
          uuid: p.uuid,
          id_cliente: p.id_cliente,
          fecha_pedido: p.fecha_pedido,
          lineas: p.lineas,
        }),
      });
      await ColaDB.actualizar(p.uuid, {
        estado: "enviado",
        id_pedido: r.id_pedido,
        enviado_en: new Date().toISOString(),
        error: null,
      });
      return true;
    } catch (e) {
      // Rechazo definitivo solo si el servidor respondió con un 4xx que no sea
      // de sesión/saturación. Todo lo demás (sin red, timeout, 401, 5xx, error
      // inesperado) deja el pedido pendiente para reintentar más tarde.
      const rechazo =
        typeof e.status === "number" &&
        e.status >= 400 &&
        e.status < 500 &&
        !ERRORES_REINTENTABLES.includes(e.status);
      if (!rechazo) return false;
      await ColaDB.actualizar(p.uuid, { estado: "rechazado", error: e.message });
      return true;
    }
  }

  // Envía los pendientes en orden. Si una llamada falla por red/sesión/servidor
  // corta el ciclo (no tiene sentido seguir pegándole): lo retoma el próximo
  // disparador (volver la conexión, abrir la app, o el intervalo).
  async function sincronizar() {
    if (!Api.token()) return;
    if (sincronizando) {
      repetir = true; // llegó un pedido nuevo mientras se enviaba: otra vuelta al terminar
      return;
    }
    sincronizando = true;
    try {
      do {
        repetir = false;
        const pendientes = (await listar()).filter((p) => p.estado === "pendiente");
        for (const p of pendientes) {
          const seguir = await enviarUno(p);
          avisarCambio();
          if (!seguir) break;
        }
        await purgarEnviadosViejos();
      } while (repetir);
    } finally {
      sincronizando = false;
      avisarCambio();
    }
  }

  document.addEventListener("mana:sesion-iniciada", sincronizar);
  window.addEventListener("online", sincronizar);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) sincronizar();
  });
  setInterval(sincronizar, INTERVALO_REINTENTO_MS);

  return { encolar, sincronizar, listar, obtener, descartar, cantidadPorEnviar };
})();
