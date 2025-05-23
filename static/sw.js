self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open("meu-app-cache").then((cache) => {
      return cache.addAll([
        "/",
        "/static/style.css",
        "/static/script.js",
        "/static/iconShrt.png",
        "/static/iconDef.png"
      ]);
    })
  );
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
