// Service worker mínimo: solo existe para que el navegador considere la
// página instalable (PWA / "Añadir a pantalla de inicio"). Cachea el
// cascarón de la app pero SIEMPRE pide data.json a la red, para no enseñar
// nunca datos del torneo desactualizados.

const CACHE = 'mundial-bolilla-v1';
const SHELL = ['./index.html', './manifest.json', './icons/icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // data.json: siempre red primero (datos en vivo), con el caché como
  // único respaldo si no hay conexión.
  if (url.pathname.endsWith('data.json')) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }

  // Resto del cascarón: caché primero, red de respaldo.
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
