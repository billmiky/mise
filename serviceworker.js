// Mise service worker.
//  - Pages and scripts: network first (revalidated, so a new deploy is picked up
//    right away), falling back to the last copy so recipes open offline.
//  - Images: cache first.
//  - Only same-origin GETs are handled. GitHub API calls (token, sync, workflows)
//    are never touched or cached.
const VERSION = 'v2';
const PAGES = 'mise-pages-' + VERSION;
const IMAGES = 'mise-images-v1';
const KEEP = [PAGES, IMAGES];
const MAX_IMAGES = 250;

const scope = self.registration.scope; // e.g. https://billmiky.github.io/mise/
const OFFLINE = new URL('offline.html', scope).href;
const SHELL = ['', 'recipes/', 'meal-plan/', 'grocery-list/', 'pantry/', 'offline.html',
  'assets/css/chowdown.css', 'assets/js/chowdown.js', 'assets/js/recipe-edits.js', 'assets/js/recipe-matrix.js', 'icons/icon-192.png']
  .map((p) => new URL(p, scope).href);

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(PAGES)
      .then((cache) => Promise.allSettled(SHELL.map((u) => cache.add(u)))) // one 404 must not fail the install
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => KEEP.indexOf(k) === -1).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function trim(cache, max) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

async function networkFirst(request, navigate) {
  const cache = await caches.open(PAGES);
  try {
    // 'no-cache' = revalidate with the server instead of trusting the 10-minute Pages cache.
    // (A navigation request must be passed as-is so redirects keep working.)
    const response = await fetch(navigate ? request : new Request(request, { cache: 'no-cache' }));
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const hit = await cache.match(request, { ignoreSearch: !navigate });
    if (hit) return hit;
    if (navigate) return (await cache.match(OFFLINE)) || Response.error();
    return Response.error();
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(IMAGES);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) {
    cache.put(request, response.clone());
    trim(cache, MAX_IMAGES);
  }
  return response;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;           // GitHub API, fonts, etc.
  if (url.pathname.endsWith('/serviceworker.js')) return;

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, true));
  } else if (request.destination === 'image') {
    event.respondWith(cacheFirst(request).catch(() => Response.error()));
  } else {
    event.respondWith(networkFirst(request, false));
  }
});
