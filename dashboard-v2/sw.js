/**
 * sw.js — NexusTrader Dashboard Service Worker v3
 * Provides offline caching with offline fallback page + stale-while-revalidate for assets
 * Updated: proper cache versioning, stale retry, HTML escaping in fallback
 */
const CACHE = 'nt-cache-v4';
const CACHE_STATIC = 'nt-static-v4';
const CACHE_DYNAMIC = 'nt-dynamic-v4';
const CORE_ASSETS = [
  '/dashboard-v2/',
  '/dashboard-v2/index.html',
  '/dashboard-v2/css/main.css',
  '/dashboard-v2/js/api.js',
  '/dashboard-v2/js/router.js',
  '/dashboard-v2/js/dashboard.js',
  '/dashboard-v2/js/neural.js',
  '/dashboard-v2/js/assets.js',
  '/dashboard-v2/js/llm.js',
  '/dashboard-v2/js/agents.js',
  '/dashboard-v2/js/settings.js',
  '/dashboard-v2/js/strategy.js',
  '/dashboard-v2/js/optimizations.js',
  '/dashboard-v2/js/architecture.js',
  '/dashboard-v2/js/logs.js',
  '/dashboard-v2/manifest.json',
  '/dashboard-v2/vendor/lightweight-charts.standalone.production.js',
  '/dashboard-v2/vendor/chart.umd.min.js',
  '/dashboard-v2/vendor/lucide.min.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_STATIC).then((cache) => {
      // Use addAll with error tolerance — skip individual failures
      return Promise.allSettled(
        CORE_ASSETS.map(url =>
          cache.add(url).catch(err => {
            console.warn('[SW] Failed to cache ' + url + ': ' + err.message);
          })
        )
      );
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_STATIC && k !== CACHE_DYNAMIC && k !== CACHE)
          .map((k) => {
            console.log('[SW] Purging old cache:', k);
            return caches.delete(k);
          })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls: network-first with timeout fallback
  if (url.pathname.includes('/api/')) {
    event.respondWith(networkFirstWithTimeout(event.request, 3000));
    return;
  }

  // Vendor/static assets: cache-first with network fallback
  if (url.pathname.includes('/dashboard-v2/vendor/') ||
      url.pathname.includes('/dashboard-v2/css/') ||
      url.pathname.includes('/dashboard-v2/manifest.json')) {
    event.respondWith(cacheFirstWithNetworkFallback(event.request));
    return;
  }

  // JS modules: stale-while-revalidate for fast loads
  if (url.pathname.startsWith('/dashboard-v2/js/')) {
    event.respondWith(staleWhileRevalidate(event.request));
    return;
  }

  // Dashboard HTML: network-first, fallback to cached
  if (url.pathname === '/dashboard-v2/' || url.pathname.startsWith('/dashboard-v2/index')) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // Everything else: network-first
  event.respondWith(networkFirst(event.request));
});

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_STATIC);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request).then((response) => {
    if (response && response.status === 200) {
      // Cache clone for next time
      const clone = response.clone();
      cache.put(request, clone).catch(() => {});
    }
    return response;
  }).catch((err) => {
    console.log('[SW] staleWhileRevalidate fetch failed:', err.message);
    return cached;
  });

  return cached || fetchPromise;
}

async function cacheFirstWithNetworkFallback(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response && response.status === 200) {
      const cache = await caches.open(CACHE_STATIC);
      cache.put(request, response.clone()).catch(() => {});
    }
    return response;
  } catch (err) {
    console.log('[SW] cacheFirstWithNetworkFallback failed:', err.message);
    return new Response('', { status: 408, statusText: 'Offline' });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response && response.status === 200) {
      const cache = await caches.open(CACHE_STATIC);
      cache.put(request, response.clone()).catch(() => {});
    }
    return response;
  } catch (err) {
    console.log('[SW] networkFirst failed, serving cached:', err.message);
    const cached = await caches.match(request);
    return cached || getOfflineResponse();
  }
}

async function networkFirstWithTimeout(request, timeoutMs) {
  try {
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('timeout')), timeoutMs)
    );
    const response = await Promise.race([fetch(request), timeoutPromise]);
    if (response && response.status === 200) {
      const cache = await caches.open(CACHE_DYNAMIC);
      cache.put(request, response.clone()).catch(() => {});
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    return cached || new Response(JSON.stringify({ offline: true, error: 'No cached data' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

function getOfflineResponse() {
  return new Response(
    '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Offline &mdash; NexusTrader</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#0a0f1e;color:#f1f5f9;font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;text-align:center;padding:20px;margin:0}.card{background:rgba(17,24,39,0.8);border:1px solid rgba(148,163,184,0.1);border-radius:12px;padding:40px;max-width:400px}h1{color:#3b82f6;margin-bottom:10px}p{color:#94a3b8;margin-bottom:20px}.retry-btn{background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.3);color:#3b82f6;padding:10px 24px;border-radius:6px;border:none;cursor:pointer;font-size:14px;font-family:inherit}.retry-btn:hover{background:rgba(59,130,246,0.25)}</style></head><body><div class="card"><h1>🔌 Offline</h1><p>NexusTrader is unavailable while disconnected. Some cached data may still be viewable.</p><button class="retry-btn" onclick="location.reload()">Retry Connection</button></div></body></html>',
    { status: 503, headers: { 'Content-Type': 'text/html;charset=UTF-8' } }
  );
}
