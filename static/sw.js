/**
 * Nearby Chat — Service Worker (PWA Shell & Web Push Notification Handler)
 */

const CACHE_NAME = 'nearby-chat-v1.0';
const STATIC_ASSETS = [
  '/',
  '/static/css/base.css',
  '/static/css/layout.css',
  '/static/css/components.css',
  '/static/js/websocket.js',
  '/static/js/moderation.js',
  '/static/js/app.js',
  '/static/images/icon.svg',
  '/static/images/default-avatar.svg',
  '/static/manifest.webmanifest',
];

// Install Event — Pre-cache critical app shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('Non-fatal asset caching error:', err);
      });
    })
  );
  self.skipWaiting();
});

// Activate Event — Clean up stale caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// Fetch Event — Network-first with Cache Fallback for static assets
self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // Do not intercept WebSocket, API, or non-GET requests
  if (event.request.method !== 'GET' || requestUrl.pathname.startsWith('/ws/') || requestUrl.pathname.startsWith('/admin/')) {
    return;
  }

  // Cache-first for static assets
  if (requestUrl.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        return cachedResponse || fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseToCache));
          }
          return networkResponse;
        });
      })
    );
    return;
  }

  // Network-first for navigation pages
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});

// Push Notification Event
self.addEventListener('push', (event) => {
  let payload = {
    title: 'Nearby Chat',
    body: 'You have a new message!',
    url: '/chats/',
  };

  if (event.data) {
    try {
      payload = event.data.json();
    } catch (e) {
      payload.body = event.data.text();
    }
  }

  const notificationOptions = {
    body: payload.body,
    icon: '/static/images/icon.svg',
    badge: '/static/images/icon.svg',
    data: {
      url: payload.url || '/chats/',
    },
    vibrate: [100, 50, 100],
    actions: [
      { action: 'open', title: 'Open Chat' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(payload.title, notificationOptions)
  );
});

// Notification Click Event
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data && event.notification.data.url ? event.notification.data.url : '/chats/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(targetUrl) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
