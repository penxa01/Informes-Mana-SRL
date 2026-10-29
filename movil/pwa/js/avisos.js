// Avisos (notificaciones push) con la app en segundo plano: un pedido nuevo de un vendedor, un pedido
// programado y un pedido entregado (quién recibe cuál lo decide el servidor, movil/avisos/). Acá solo se
// activan y desactivan en ESTE celular: la campana del encabezado.
//
// Activar exige un toque del usuario (el navegador no deja pedir el permiso solo). La suscripción se
// manda al servidor y, mientras el usuario los quiera, se renueva en silencio cada vez que abre la app.
// El service worker (sw.js) es quien recibe los avisos y los muestra, con la app cerrada o no.
const Avisos = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const botones = [...document.querySelectorAll(".boton-avisos")];
  const toast = document.getElementById("toast-avisos");

  const soportado = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  // En iPhone/iPad los avisos solo existen si la app está agregada a la pantalla de inicio (iOS 16.4 o más).
  const esIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const instalada = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  const CLAVE_VAPID = "movil_vapid";
  let clavePublica = null; // la clave del servidor, o null si todavía no se sabe
  let configurado = null; // true = el servidor ofrece avisos, false = no los tiene configurados, null = no se sabe
  let sesionActiva = false;
  let sincronizada = false;
  let ocupado = false;
  let temporizadorToast = null;
  let destinoPendiente = null; // a qué sección ir cuando termine de abrirse la app (admin)

  // ── Lo que el usuario eligió, por usuario (un mismo celular puede usarlo más de una persona) ──
  const claveDeUsuario = () => `movil_avisos:${Api.nombre()}`;

  function quiere() {
    try {
      return localStorage.getItem(claveDeUsuario()) === "1";
    } catch (e) {
      return false;
    }
  }

  function guardarQuiere(si) {
    try {
      localStorage.setItem(claveDeUsuario(), si ? "1" : "0");
    } catch (e) {
      // sin almacenamiento: queda activo mientras la app esté abierta
    }
  }

  // ── Dibujo ──
  function dibujarIcono(boton) {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    for (const [clase, d] of [
      ["campana", "M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z"],
      ["badajo", "M10 19.5a2 2 0 0 0 4 0"],
      ["barra", "M4 4l16 16"],
    ]) {
      const p = document.createElementNS(NS, "path");
      p.setAttribute("class", clase);
      p.setAttribute("d", d);
      svg.appendChild(p);
    }
    boton.appendChild(svg);
  }

  function estado() {
    if (!soportado) return "inactivo";
    if (Notification.permission === "denied") return "bloqueado";
    return quiere() && Notification.permission === "granted" ? "activo" : "inactivo";
  }

  function pintar() {
    const est = estado();
    const etiqueta = {
      activo: "Desactivar los avisos de pedidos en este celular",
      bloqueado: "Los avisos están bloqueados en este navegador",
      inactivo: "Activar los avisos de pedidos en este celular",
    }[est];
    const visible = sesionActiva && configurado === true && (soportado || (esIOS && !instalada));
    for (const b of botones) {
      b.hidden = !visible;
      b.dataset.estado = est;
      b.title = etiqueta;
      b.setAttribute("aria-label", etiqueta);
      b.setAttribute("aria-pressed", String(est === "activo"));
      b.classList.toggle("ocupado", ocupado);
    }
  }

  function mensaje(texto) {
    toast.textContent = texto;
    toast.hidden = false;
    clearTimeout(temporizadorToast);
    temporizadorToast = setTimeout(() => {
      toast.hidden = true;
    }, 6000);
  }

  // ── Clave del servidor y suscripción ──
  function urlBase64ABytes(texto) {
    const base64 = texto.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (texto.length % 4)) % 4);
    return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  }

  function igualesBytes(a, b) {
    if (!a || !b) return false;
    const x = new Uint8Array(a);
    return x.length === b.length && x.every((v, i) => v === b[i]);
  }

  async function cargarClave() {
    try {
      const respuesta = await Api.llamar("/push/clave");
      clavePublica = respuesta.clave;
      configurado = true;
      try {
        localStorage.setItem(CLAVE_VAPID, clavePublica);
      } catch (e) {
        // no pasa nada
      }
    } catch (e) {
      if (e.status === 503) {
        configurado = false; // el servidor todavía no tiene avisos configurados: la campana no aparece
        clavePublica = null;
        return;
      }
      // Sin señal: se usa la última clave conocida (si nunca hubo, no se sabe y la campana no aparece).
      try {
        clavePublica = localStorage.getItem(CLAVE_VAPID);
      } catch (e2) {
        clavePublica = null;
      }
      configurado = clavePublica ? true : null;
    }
  }

  // Un error con un mensaje pensado para mostrárselo al usuario (los demás son del navegador, en inglés).
  function errorLegible(texto) {
    const e = new Error(texto);
    e.legible = true;
    return e;
  }

  // `ready` no se resuelve nunca si el service worker no llegó a registrarse: sin un tope, la campana
  // quedaría "ocupada" para siempre.
  function registroListo() {
    return Promise.race([
      navigator.serviceWorker.ready,
      new Promise((_, rechazar) => setTimeout(() => rechazar(errorLegible("La app todavía no terminó de prepararse. Probá de nuevo en un momento.")), 8000)),
    ]);
  }

  async function suscripcionActual() {
    const registro = await registroListo();
    return registro.pushManager.getSubscription();
  }

  async function suscribir() {
    const registro = await registroListo();
    const clave = urlBase64ABytes(clavePublica);
    let sub = await registro.pushManager.getSubscription();
    // Si el servidor cambió de clave, la suscripción vieja ya no sirve.
    if (sub && !igualesBytes(sub.options && sub.options.applicationServerKey, clave)) {
      await sub.unsubscribe();
      sub = null;
    }
    if (!sub) sub = await registro.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: clave });
    await Api.llamar("/push/suscribir", { method: "POST", body: JSON.stringify(sub.toJSON()) });
    return sub;
  }

  async function activar() {
    if (!clavePublica) await cargarClave();
    if (!clavePublica) throw errorLegible("No se pudo traer la configuración de los avisos. Probá de nuevo con señal.");
    const permiso = await Notification.requestPermission();
    if (permiso !== "granted") {
      mensaje("No diste permiso para mostrar avisos. Podés activarlos cuando quieras tocando la campana.");
      return false;
    }
    await suscribir();
    guardarQuiere(true);
    return true;
  }

  async function desactivar() {
    guardarQuiere(false);
    const sub = await suscripcionActual();
    if (!sub) return;
    try {
      await Api.llamar("/push/baja", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) });
    } catch (e) {
      // sin señal: en el servidor queda hasta que el servicio de push la dé por muerta, y ahí se borra sola
    }
    await sub.unsubscribe();
  }

  async function alternar() {
    if (ocupado) return;
    if (!soportado) {
      mensaje("En iPhone, para recibir avisos agregá primero la app a la pantalla de inicio (Compartir > Agregar a inicio) y abrila desde ahí.");
      return;
    }
    if (estado() === "bloqueado") {
      pintar(); // el permiso pudo cambiar desde la configuración del navegador: el ícono tiene que reflejarlo
      mensaje("Los avisos están bloqueados para este sitio. Habilitalos en la configuración del navegador y volvé a tocar la campana.");
      return;
    }
    ocupado = true;
    pintar();
    try {
      if (estado() === "activo") {
        await desactivar();
        mensaje("Avisos desactivados en este celular.");
      } else if (await activar()) {
        mensaje("Avisos activados: te llegan aunque la app esté cerrada.");
      }
    } catch (e) {
      console.warn("Avisos:", e);
      // Los errores del servidor y los de "todavía no se preparó" ya vienen en castellano; el resto, no.
      mensaje(typeof e.status === "number" || e.legible ? e.message : "No se pudieron activar los avisos. Probá de nuevo con buena señal.");
    } finally {
      ocupado = false;
      pintar();
    }
  }

  // Al abrir la app: si el usuario los quiere, se renueva la suscripción en silencio (también cubre que el
  // servidor la haya perdido, o que el celular la haya cambiado).
  async function sincronizar() {
    if (sincronizada) return;
    sincronizada = true;
    sesionActiva = true;
    pintar();
    await cargarClave();
    pintar();
    if (soportado && configurado === true && quiere() && Notification.permission === "granted") {
      try {
        await suscribir();
      } catch (e) {
        // sin señal: se reintenta la próxima vez que abra la app
      }
    }
  }

  // Al cerrar sesión se da de baja este celular, para que el siguiente usuario no reciba los avisos del anterior.
  // Mejor esfuerzo y rápido (no demora el "Salir"); va directo con fetch para que un token vencido no dispare
  // el aviso de "sesión vencida" en una salida voluntaria.
  async function alSalir() {
    if (!soportado || Notification.permission !== "granted") return;
    const espera = (ms) => new Promise((resolver) => setTimeout(() => resolver(null), ms));
    try {
      const sub = await Promise.race([suscripcionActual(), espera(2000)]);
      if (!sub) return;
      await Promise.race([
        fetch("/push/baja", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${Api.token()}` },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        }),
        espera(3000),
      ]);
    } catch (e) {
      // sin señal: queda en el servidor hasta que se pise o el servicio de push la dé por muerta
    }
  }

  // ── Tocar un aviso ──
  // El service worker abre la app (`/?aviso=...`) o, si ya estaba abierta, le manda el mensaje. Un admin cae
  // en Reparto con los avisos de programado/entregado; el resto de los perfiles tienen una sola pantalla.
  function irAlAviso(evento) {
    if (evento !== "programado" && evento !== "entregado") return;
    if (!sesionActiva) {
      destinoPendiente = "reparto";
      return;
    }
    if (Api.esAdmin()) document.dispatchEvent(new CustomEvent("mana:ir-a-seccion", { detail: "reparto" }));
  }

  function iniciar() {
    for (const b of botones) {
      dibujarIcono(b);
      b.addEventListener("click", alternar);
    }
    pintar();

    const evento = new URLSearchParams(location.search).get("aviso");
    if (evento) {
      irAlAviso(evento);
      history.replaceState(null, "", location.pathname); // la dirección queda limpia
    }
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.addEventListener("message", (ev) => {
        if (ev.data && ev.data.tipo === "aviso-tocado") irAlAviso(ev.data.evento);
      });
    }

    // Al volver a la app (por ejemplo desde la configuración del navegador) el permiso puede haber cambiado.
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) pintar();
    });

    // Los perfiles que no son reparto arrancan con "sesion-iniciada"; el reparto, con "reparto-iniciado".
    document.addEventListener("mana:sesion-iniciada", sincronizar);
    document.addEventListener("mana:reparto-iniciado", sincronizar);
    document.addEventListener("mana:admin-iniciado", () => {
      if (destinoPendiente) {
        document.dispatchEvent(new CustomEvent("mana:ir-a-seccion", { detail: destinoPendiente }));
        destinoPendiente = null;
      }
    });
    document.addEventListener("mana:sesion-cerrada", () => {
      sesionActiva = false;
      sincronizada = false;
      destinoPendiente = null;
      toast.hidden = true;
      pintar();
    });
  }

  iniciar();
  return { alSalir };
})();
