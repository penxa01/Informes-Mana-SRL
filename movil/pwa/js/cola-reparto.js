// Cola del reparto: las entregas y las ubicaciones se guardan PRIMERO en el teléfono
// (IndexedDB) y después se intentan enviar, en el mismo orden en que se hicieron. Así nada
// se pierde sin señal. Estados de cada acción:
//   pendiente  guardada, todavía no confirmada por el servidor (se reintenta sola)
//   enviado    el servidor la confirmó
//   rechazado  el servidor dijo que no corresponde (ej. el pedido ya no está programado):
//              NO se reintenta sola, se muestra el motivo y se la descarta
//
// Reintentar es seguro: marcar entregado un pedido ya entregado responde OK en el servidor,
// y guardar una ubicación en un cliente que ya tiene una se da por resuelto (409).
// El orden importa solo en un caso: la ubicación de un cliente tiene que llegar mientras
// "tiene entregas", y el servidor lo permite hasta 3 días después de entregarle.
const ColaReparto = (() => {
  const RETENCION_ENVIADOS_MS = 24 * 60 * 60 * 1000;
  const INTERVALO_REINTENTO_MS = 30000;
  const ERRORES_REINTENTABLES = [401, 408, 429]; // 5xx y errores de red también se reintentan

  let sincronizando = false;
  let repetir = false;

  function avisarCambio() {
    document.dispatchEvent(new CustomEvent("mana:cola-reparto-cambio"));
  }

  // Solo las acciones del usuario logueado (dos repartidores pueden compartir teléfono).
  async function listar() {
    const nombre = Api.nombre();
    const todas = await ColaRepartoDB.todos();
    return todas.filter((a) => a.usuario === nombre).sort((a, b) => a.creado_en.localeCompare(b.creado_en));
  }

  async function encolar(datos) {
    const accion = {
      uuid: crypto.randomUUID(),
      usuario: Api.nombre(),
      estado: "pendiente",
      error: null,
      creado_en: new Date().toISOString(),
      enviado_en: null,
      ...datos,
    };
    await ColaRepartoDB.agregar(accion);
    avisarCambio();
    return accion;
  }

  const entregar = (idPedido, clienteNombre) =>
    encolar({ tipo: "entrega", id_pedido: idPedido, cliente_nombre: clienteNombre });

  const guardarUbicacion = (idCliente, clienteNombre, lat, lng) =>
    encolar({ tipo: "ubicacion", id_cliente: idCliente, cliente_nombre: clienteNombre, lat, lng });

  async function descartar(uuid) {
    await ColaRepartoDB.borrar(uuid);
    avisarCambio();
  }

  async function cantidadPorEnviar() {
    return (await listar()).filter((a) => a.estado === "pendiente").length;
  }

  // Las enviadas ya no hacen falta pasado un día; los rechazos también se limpian (si el pedido
  // ya no está en la lista, ninguna tarjeta los mostraría y quedarían guardados para siempre).
  async function purgarEnviadosViejos() {
    const limite = Date.now() - RETENCION_ENVIADOS_MS;
    for (const a of await listar()) {
      const desde = a.estado === "enviado" ? a.enviado_en : a.estado === "rechazado" ? a.creado_en : null;
      if (desde && new Date(desde).getTime() < limite) await ColaRepartoDB.borrar(a.uuid);
    }
  }

  function enviarAlServidor(a) {
    if (a.tipo === "entrega") {
      return Api.llamar(`/reparto/pedidos/${a.id_pedido}/entregar`, { method: "POST" });
    }
    return Api.llamar(`/reparto/clientes/${a.id_cliente}/ubicacion`, {
      method: "POST",
      body: JSON.stringify({ lat: a.lat, lng: a.lng }),
    });
  }

  // Devuelve true si se puede seguir con la próxima acción, false si hay que cortar el ciclo.
  async function enviarUna(a) {
    try {
      await enviarAlServidor(a);
      await ColaRepartoDB.actualizar(a.uuid, { estado: "enviado", enviado_en: new Date().toISOString(), error: null });
      return true;
    } catch (e) {
      // Una ubicación que ya estaba cargada (la puso la oficina u otro repartidor) está resuelta.
      if (a.tipo === "ubicacion" && e.status === 409) {
        await ColaRepartoDB.actualizar(a.uuid, { estado: "enviado", enviado_en: new Date().toISOString(), error: null });
        return true;
      }
      // Rechazo definitivo solo si el servidor respondió con un 4xx que no sea de sesión/saturación.
      // Sin red, timeout, 401, 5xx o un error inesperado: queda pendiente para más tarde.
      const rechazo =
        typeof e.status === "number" && e.status >= 400 && e.status < 500 && !ERRORES_REINTENTABLES.includes(e.status);
      if (!rechazo) return false;
      await ColaRepartoDB.actualizar(a.uuid, { estado: "rechazado", error: e.message });
      return true;
    }
  }

  // Envía las pendientes en orden. Si una falla por red/sesión/servidor corta el ciclo (no tiene
  // sentido seguir pegándole): lo retoma el próximo disparador (volver la conexión, abrir la app
  // o el intervalo).
  async function sincronizar() {
    if (!Api.token() || Api.rol() !== "reparto") return;
    if (sincronizando) {
      repetir = true; // llegó una acción nueva mientras se enviaba: otra vuelta al terminar
      return;
    }
    sincronizando = true;
    try {
      do {
        repetir = false;
        const pendientes = (await listar()).filter((a) => a.estado === "pendiente");
        for (const a of pendientes) {
          const seguir = await enviarUna(a);
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

  document.addEventListener("mana:reparto-iniciado", sincronizar);
  window.addEventListener("online", sincronizar);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) sincronizar();
  });
  setInterval(sincronizar, INTERVALO_REINTENTO_MS);

  return { entregar, guardarUbicacion, sincronizar, listar, descartar, cantidadPorEnviar };
})();
