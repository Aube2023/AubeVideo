/* AubeVideo - Service Worker.
   Ne touche JAMAIS aux pages HTML (navigations gérées nativement par le
   navigateur => toujours à jour, redirections login/logout OK). Ne met en
   cache que les assets statiques, avec un fallback qui renvoie toujours une
   Response valide (jamais `undefined`). */
const CACHE = 'aubevideo-v9';
const CORE = [
  '/static/css/style.css', '/static/css/v3.css',
  '/static/js/app.js', '/static/js/v3.js',
  '/static/img/logo.svg', '/static/img/placeholder.svg',
  '/static/img/avatar-default.svg', '/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE).catch(() => {})));
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

  // Navigations (pages HTML) : laisser le navigateur faire. Pas de cache HTML
  // => l'état connecté est toujours frais, et les redirections fonctionnent.
  if (req.mode === 'navigate') return;

  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // Seuls les assets statiques sont mis en cache (stale-while-revalidate).
  const p = url.pathname;
  if (!(p.startsWith('/static/') || p === '/manifest.webmanifest')) return;

  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(req);
    const fetched = fetch(req).then(resp => {
      if (resp && resp.ok) cache.put(req, resp.clone());
      return resp;
    });
    if (hit) {
      fetched.catch(() => {});   // revalidation en arrière-plan, erreurs ignorées
      return hit;                // sert le cache immédiatement
    }
    return fetched;              // pas de cache : attend le réseau (Response ou erreur réseau)
  })());
});

self.addEventListener('push', (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) {}
  const title = data.title || 'AubeVideo';
  e.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      icon: '/static/img/logo.svg',
      badge: '/static/img/logo.svg',
      data: { url: data.url || '/' },
    })
  );
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(clients.openWindow(url));
});
