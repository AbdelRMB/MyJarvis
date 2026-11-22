/* Wesley mobile : garde l'appli en cache pour qu'elle s'ouvre instantanément (et hors ligne) ; les données du
 * compte (/v1/) et la clé d'appli (config.js) passent toujours par le réseau. */
const CACHE = "wesley-mobile-v3";
const FICHIERS = ["./", "manifest.webmanifest", "icone-192.png", "icone-512.png"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FICHIERS)));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((k) => Promise.all(k.filter((x) => x !== CACHE).map((x) => caches.delete(x)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/v1/") || url.pathname.endsWith("config.js")) return;
  // réseau d'abord (versions à jour) ; cache si hors ligne. Une page de refus (403) n'est jamais gardée.
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r.ok) {
          const c = r.clone();
          caches.open(CACHE).then((x) => x.put(e.request, c));
        }
        return r;
      })
      .catch(() => caches.match(e.request)),
  );
});
// toucher une notification (rappel, ordre reçu) ouvre Wesley
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: "window" }).then((l) => (l.length ? l[0].focus() : self.clients.openWindow("/mobile/"))),
  );
});
