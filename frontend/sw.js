// ZeroBreakout PWA Service Worker v5.3.0
const CACHE_NAME = 'zerobreakout-pwa-v5.3.0';
const STATIC_ASSETS = [
  '/',
  '/about',
  '/privacy',
  '/terms',
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
  if (event.request.url.includes('/api/') || event.request.url.includes('/.well-known/')) {
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

// ==================== WEB PUSH NOTIFICATIONS ==================== //

self.addEventListener('push', (event) => {
  let data = {
    title: 'ZeroBreakout Alert',
    body: 'New market breakout setups detected!',
    icon: '/static/assets/icon-192.png',
    badge: '/static/assets/icon-192.png',
    url: '/',
    tag: 'zerobreakout-alert'
  };

  if (event.data) {
    try {
      const parsed = event.data.json();
      data = Object.assign(data, parsed);
    } catch (e) {
      data.body = event.data.text() || data.body;
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/static/assets/icon-192.png',
    badge: data.badge || '/static/assets/icon-192.png',
    tag: data.tag || 'zerobreakout-alert',
    renotify: true,
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/'
    },
    actions: [
      { action: 'open_scanner', title: '📊 View Setups' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Focus open window if available
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // Open new window if none exists
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
