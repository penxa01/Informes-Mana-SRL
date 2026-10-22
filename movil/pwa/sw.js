// Service worker: solo cachea el cascarón de la app (HTML/CSS/JS/íconos)
// para que la PWA sea instalable y abra aunque no haya señal. Los datos
// (catálogo, pedidos) nunca se cachean acá; eso lo maneja IndexedDB
// (Tareas 8 y 10 del plan), no el service worker.
const CACHE_NAME = "mana-pedidos-v1";
const CASCARON = [
  "/",
  "/index.html",
  "/css/estilos.css",
  "/js/api.js",
  "/js/login.js",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(CASCARON)));
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

const RUTAS_API = ["/auth", "/catalogo", "/pedidos", "/health"];

self.addEventListener("fetch", (ev) => {
  const url = new URL(ev.request.url);
  if (RUTAS_API.some((p) => url.pathname.startsWith(p))) {
    return; // la API nunca se sirve desde el cache
  }
  ev.respondWith(caches.match(ev.request).then((cacheada) => cacheada || fetch(ev.request)));
});
