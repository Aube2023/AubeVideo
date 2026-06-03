/* AubeVideo - Service Worker (cache assets, JAMAIS le HTML connecté) */
const CACHE = 'aubevideo-v4';
const CORE = [
  '/static/css/style.css', '/static/css/v3.css',
  '/static/js/app.js', '/static/js/v3.js',
  '/static/img/logo.svg', '/static/img/placeholder.svg',
  '/static/img/avatar-default.svg', '/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE).catch(()=>{})));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // Jamais de cache : streaming, API, sous-titres, auth, contenu dynamique
  const p = url.pathname;
  if (p.startsWith('/stream/') || p.startsWith('/api/') || p.startsWith('/caption/') ||
      p.startsWith('/logout') || p.startsWith('/login') || p.startsWith('/register') ||
      p.startsWith('/settings') || p.startsWith('/admin') || p.startsWith('/studio')) {
    return;
  }

  // Pages HTML / navigation : NETWORK-FIRST.
  // => l'état connecté/déconnecté est toujours à jour (corrige « toujours connexion »).
  const isNav = req.mode === 'navigate' ||
                (req.headers.get('accept') || '').includes('text/html');
  if (isNav) {
    e.respondWith(fetch(req).catch(() => caches.match(req)));
    return;
  }

  // Assets statiques (css/js/img) : stale-while-revalidate.
  e.respondWith(
    caches.match(req).then(hit => {
      const net = fetch(req).then(resp => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(req, clone));
        }
        return resp;
      }).catch(() => hit);
      return hit || net;
    })
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
