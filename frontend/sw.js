// ZeroBreakout PWA Service Worker v4.2.0
const CACHE_NAME = 'zerobreakout-pwa-v4.2.0';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/static/css/style.css',
  '/static/js/api.js',
  '/static/js/chart.js',
  '/static/js/app.js',
  '/static/js/firebase-auth.js',
  '/static/assets/icon.png',
  '/static/assets/icon-192.png',
  '/static/assets/icon-512.png',
  '/static/favicon.png'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('PWA Pre-cache notice:', err);
      });
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200 && event.request.method === 'GET') {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
