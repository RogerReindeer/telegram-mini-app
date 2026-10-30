"use strict";

const STARTUP_CACHE = "zefirki-startup-v248";
const STARTUP_SHELL_URL = "/startup-shell";
const NETWORK_GRACE_MS = 1200;

function isReaderNavigation(request) {
  if (request.method !== "GET" || request.mode !== "navigate") return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  return url.pathname === "/"
    || url.pathname === "/library"
    || url.pathname.startsWith("/novel/")
    || url.pathname.startsWith("/chapter/")
    || url.pathname === "/reader-preview";
}

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(STARTUP_CACHE)
      .then(function (cache) {
        return cache.add(new Request(STARTUP_SHELL_URL, { cache: "reload" }));
      })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (keys) {
        return Promise.all(keys.filter(function (key) {
          return key.startsWith("zefirki-startup-") && key !== STARTUP_CACHE;
        }).map(function (key) { return caches.delete(key); }));
      })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  if (!isReaderNavigation(event.request)) return;
  const url = new URL(event.request.url);

  // The startup shell adds this one-use marker after /health succeeds. That
  // request must wait for the real HTML instead of receiving the shell again.
  if (url.searchParams.has("__reader_boot")) {
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith((async function () {
    const networkRequest = fetch(event.request).catch(function () { return null; });
    const quickResponse = await Promise.race([
      networkRequest,
      new Promise(function (resolve) {
        setTimeout(function () { resolve(null); }, NETWORK_GRACE_MS);
      }),
    ]);
    if (quickResponse && quickResponse.status < 500) return quickResponse;

    const shell = await caches.match(STARTUP_SHELL_URL, { ignoreSearch: true });
    if (shell) return shell;

    const eventualResponse = await networkRequest;
    return eventualResponse || new Response("Библиотека временно недоступна", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
    });
  })());
});
