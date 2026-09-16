// Minimal service worker - network-first for API, cache-first for static
const CACHE = "whatssup-v1";
const STATIC_ASSETS = ["/", "/static/styles.css", "/static/app.js", "/manifest.json", "/static/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.pathname.startsWith("/api/")) return;  // never cache API

  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok && url.pathname.startsWith("/static/")) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
