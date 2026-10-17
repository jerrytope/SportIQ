/* SportIQ service worker: app shell + static assets (network first), offline lesson packs, offline fallback page. */
var CACHE = "sportiq-v3";
var OFFLINE_CACHE = "sportiq-offline-lessons";
var SHELL = ["/offline/", "/static/css/sportiq.css", "/static/js/sportiq.js", "/static/js/offline.js", "/static/img/icon.svg"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE && k !== OFFLINE_CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    // Network first so new deployments are picked up immediately; cache is the offline fallback.
    e.respondWith(fetch(req).then(function (res) {
      var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(req, copy); }); return res;
    }).catch(function () { return caches.match(req); }));
    return;
  }
  if (url.pathname.startsWith("/media/")) {
    // Saved lesson media is served from the offline pack when present.
    e.respondWith(caches.open(OFFLINE_CACHE).then(function (c) {
      return c.match(req, { ignoreSearch: true }).then(function (hit) { return hit || fetch(req); });
    }));
    return;
  }
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(function () {
      return caches.open(OFFLINE_CACHE).then(function (c) { return c.match(req, { ignoreSearch: true }); })
        .then(function (hit) { return hit || caches.match("/offline/"); });
    }));
  }
});
