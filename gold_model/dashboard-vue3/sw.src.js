/* GOLD COMMAND V6 Service Worker - 离线缓存策略
 * - 首次访问：缓存所有资源
 * - 后续访问：缓存优先，失败回退网络
 * - 数据JSON：网络优先（保证最新），失败回退缓存
 */

const CACHE_VERSION = 'gold-cmd-v6-v1'
const STATIC_CACHE = `${CACHE_VERSION}-static`
const DATA_CACHE = `${CACHE_VERSION}-data`

const STATIC_ASSETS = [
  './',
  './index.html',
  './dashboard_data.json',
  './execution_data.json',
  './manifest.json'
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => {})
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter(k => !k.startsWith(CACHE_VERSION)).map(k => caches.delete(k))
      )
    })
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  
  // 只处理同源 GET 请求
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) {
    return
  }
  
  // 数据JSON：网络优先，失败回退缓存
  if (url.pathname.endsWith('.json')) {
    event.respondWith(
      fetch(event.request)
        .then((resp) => {
          // 成功则更新缓存
          if (resp.ok) {
            const clone = resp.clone()
            caches.open(DATA_CACHE).then((c) => c.put(event.request, clone))
          }
          return resp
        })
        .catch(() => caches.match(event.request).then((r) => r || new Response('{}', { headers: { 'Content-Type': 'application/json' } })))
    )
    return
  }
  
  // 其他资源：缓存优先，失败回退网络
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached
      return fetch(event.request).then((resp) => {
        if (resp.ok && (url.pathname.startsWith('./assets') || url.pathname.endsWith('.html'))) {
          const clone = resp.clone()
          caches.open(STATIC_CACHE).then((c) => c.put(event.request, clone))
        }
        return resp
      }).catch(() => cached)
    })
  )
})
