// Service worker: solo cachea el cascarón de la app (HTML/CSS/JS/íconos)
// para que la PWA sea instalable y abra aunque no haya señal. Los datos
// (catálogo, pedidos) nunca se cachean acá; eso lo maneja IndexedDB
// (Tareas 8 y 10 del plan), no el service worker.
const CACHE_NAME = "mana-pedidos-v13";
const CASCARON = [
  "/",
  "/index.html",
  "/css/estilos.css",
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
  "/js/login.js",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
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

const RUTAS_API = ["/auth", "/catalogo", "/pedidos", "/reparto", "/panel", "/health"];

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
