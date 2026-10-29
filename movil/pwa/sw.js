// Service worker: solo cachea el cascarón de la app (HTML/CSS/JS/íconos)
// para que la PWA sea instalable y abra aunque no haya señal. Los datos
// (catálogo, pedidos) nunca se cachean acá; eso lo maneja IndexedDB
// (Tareas 8 y 10 del plan), no el service worker.
const CACHE_NAME = "mana-pedidos-v17";
const CASCARON = [
  "/",
  "/index.html",
  "/css/estilos.css",
  "/css/avisos.css",
  "/js/api.js",
  "/js/db.js",
  "/js/cola.js",
  "/js/cola-ui.js",
  "/js/catalogo.js",
  "/js/pedido.js",
  "/js/mapa-mini.js",
  "/js/cola-reparto.js",
  "/js/graficos.js",
  "/js/panel.js",
  "/js/admin.js",
  "/js/reparto.js",
  "/js/avisos.js",
  "/js/login.js",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/badge-96.png",
  "/icons/logo-mana.png",
];

self.addEventListener("install", (ev) => {
  // cache: "reload" salta la caché HTTP del navegador. Sin esto, al actualizar
  // el service worker podría guardar copias viejas de los archivos (el servidor
  // no manda Cache-Control y el navegador los da por "frescos" varias horas).
  const pedidos = CASCARON.map((url) => new Request(url, { cache: "reload" }));
  ev.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(pedidos)));
  self.skipWaiting();
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(
    caches
      .keys()
      .then((claves) => Promise.all(claves.filter((c) => c !== CACHE_NAME).map((c) => caches.delete(c))))
  );
  self.clients.claim();
});

const RUTAS_API = ["/auth", "/catalogo", "/pedidos", "/reparto", "/panel", "/push", "/health"];

// ── Avisos (push) ──────────────────────────────────────────────────────────
// El servidor manda un aviso cifrado (movil/avisos/): { evento, id_pedido, titulo, cuerpo, etiqueta }.
// Se muestra siempre (el navegador lo exige: una suscripción es "solo para avisos visibles"), aunque la
// app esté cerrada. El contenido no se guarda en ningún lado: solo se muestra.
const EVENTOS_DE_AVISO = ["nuevo", "programado", "entregado"];

self.addEventListener("push", (ev) => {
  let datos = {};
  try {
    datos = ev.data ? ev.data.json() : {};
  } catch (e) {
    // un aviso sin forma de JSON se muestra igual, con el título genérico
  }
  const texto = (valor) => (typeof valor === "string" ? valor : "");
  ev.waitUntil(
    self.registration.showNotification(texto(datos.titulo) || "Mana Pedidos", {
      body: texto(datos.cuerpo),
      icon: "/icons/icon-192.png",
      badge: "/icons/badge-96.png", // la silueta de la barra de estado de Android (monocromo)
      tag: texto(datos.etiqueta) || undefined, // el mismo aviso no se apila dos veces
      lang: "es",
      data: { evento: EVENTOS_DE_AVISO.includes(datos.evento) ? datos.evento : "" },
    })
  );
});

// Al tocar el aviso: si la app está abierta se la trae al frente y se le dice qué aviso fue (para que un admin
// caiga en la pestaña que corresponde); si no, se abre con `?aviso=` (lo lee js/avisos.js).
self.addEventListener("notificationclick", (ev) => {
  ev.notification.close();
  const evento = (ev.notification.data || {}).evento || "";
  ev.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((ventanas) => {
      const abierta = ventanas.find((v) => new URL(v.url).origin === self.location.origin);
      if (abierta) {
        abierta.postMessage({ tipo: "aviso-tocado", evento });
        return abierta.focus();
      }
      return self.clients.openWindow(evento ? `/?aviso=${encodeURIComponent(evento)}` : "/");
    })
  );
});

self.addEventListener("fetch", (ev) => {
  const url = new URL(ev.request.url);
  if (RUTAS_API.some((p) => url.pathname.startsWith(p))) {
    return; // la API nunca se sirve desde el cache
  }
  ev.respondWith(
    caches.match(ev.request).then((cacheada) => {
      if (cacheada) return cacheada;
      return fetch(ev.request).catch(() => {
        // Sin red y sin esto en caché: si es una navegación (ej. el reload
        // de "arrastrar para actualizar"), devolvemos el cascarón en vez de
        // la pantalla de error del navegador — así la app sigue viva y
        // puede seguir leyendo el catálogo de IndexedDB.
        if (ev.request.mode === "navigate") return caches.match("/index.html");
        throw new Error("sin conexión y sin cache para " + ev.request.url);
      });
    })
  );
});
