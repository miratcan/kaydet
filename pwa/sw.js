const CACHE_NAME = 'kaydet-v1';
const ASSETS = [
  'index.html',
  'style.css',
  'app.js',
  'manifest.json',
  'assets/logo.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
