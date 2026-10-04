/*
  sw.js — service worker of static-web-platform: the installed/hosted app
  opens without network. The build (swp) fills in the cache name (it changes
  with every version, so old caches are dropped) and the precache list.

  Defines : a network-first cache for this site's own files.
  Used by : services/offline.ts registers it (hosted site only, never in the single file).
  Uses    : nothing.

  WHY network-first: users get the latest version whenever the network is
  available; the cache is only the fallback when it is not. Other origins are
  never touched or cached.
*/
const CACHE_NAME = "__CACHE_NAME__";
const PRECACHE = __PRECACHE__;

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  event.respondWith(
    fetch(req)
      .then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true })
        .then(hit => hit || (req.mode === "navigate" ? caches.match("./") : undefined))
        .then(hit => hit || Response.error()))
  );
});
