/* AubeVideo - Service Worker basique (cache shell + push notifs) */
const CACHE = 'aubevideo-v1';
const CORE = [
  '/', '/static/css/style.css', '/static/js/app.js',
  '/static/img/logo.svg', '/static/img/placeholder.svg',
  '/static/img/avatar-default.svg', '/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE).catch(()=>{})));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/stream/') || url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/caption/') || url.pathname.startsWith('/logout')) {
    return;  // pas de cache pour le streaming / api
  }
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(resp => {
      if (resp.ok && url.origin === location.origin) {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
      }
      return resp;
    }).catch(() => caches.match('/')))
  );
});

self.addEventListener('push', (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch(err) {}
  const title = data.title || 'AubeVideo';
  e.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      icon: '/static/img/logo.svg',
      badge: '/static/img/logo.svg',
      data: {url: data.url || '/'},
    })
  );
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(clients.openWindow(url));
});
