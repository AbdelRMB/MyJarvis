/* Garde l'interface en cache pour qu'elle s'ouvre instantanément ; les demandes passent toujours par le réseau. */
const CACHE = "wesley-mobile-v2";
const FICHIERS = ["./", "index.html", "style.css", "app.js", "scrypt.js", "manifest.webmanifest", "icone-192.png", "icone-512.png"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FICHIERS))); self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((k) => Promise.all(k.filter((x) => x !== CACHE).map((x) => caches.delete(x)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/v1/") || url.pathname.endsWith("config.js")) return;
  // réseau d'abord (versions à jour), cache si hors ligne
  e.respondWith(fetch(e.request).then((r) => { const c = r.clone(); caches.open(CACHE).then((x) => x.put(e.request, c)); return r; })
    .catch(() => caches.match(e.request)));
});
