/**
 * MACS service worker. Stale-while-revalidate for /assets/* (hashed, immutable).
 * Network-only for /api/* (always fresh). Cache index.html for offline shell.
 */
const VERSION = "macs-sw-v3";
const SHELL_CACHE = `${VERSION}-shell`;
const ASSET_CACHE = `${VERSION}-assets`;

self.addEventListener("install", (e) => {
  e.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      try {
        await cache.addAll([
          "/",
          "/manifest.json",
          "/icon-192.png",
          "/icon-512.png",
        ]);
      } catch {}
      self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)),
      );
      self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  // Never cache /api/*
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // SSE/stream endpoints — pass through
  if (url.pathname.includes("/sse")) return;

  // Hashed asset: cache-first
  if (url.pathname.startsWith("/assets/")) {
    e.respondWith(
      (async () => {
        const cache = await caches.open(ASSET_CACHE);
        const hit = await cache.match(e.request);
        if (hit) return hit;
        const resp = await fetch(e.request);
        if (resp.ok) cache.put(e.request, resp.clone());
        return resp;
      })(),
    );
    return;
  }

  // Shell (index.html, manifest, icons): network-first w/ cache fallback
  e.respondWith(
    (async () => {
      try {
        const resp = await fetch(e.request);
        if (resp.ok) {
          const cache = await caches.open(SHELL_CACHE);
          cache.put(e.request, resp.clone());
        }
        return resp;
      } catch {
        const cache = await caches.open(SHELL_CACHE);
        const hit = (await cache.match(e.request)) || (await cache.match("/"));
        if (hit) return hit;
        return new Response("offline", { status: 503 });
      }
    })(),
  );
});

// Push notifications (Phase 11b)
self.addEventListener("push", (e) => {
  let data = { title: "MACS", body: "", tag: "macs" };
  try {
    if (e.data) data = { ...data, ...e.data.json() };
  } catch {}
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      tag: data.tag,
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = e.notification.data?.url || "/";
  e.waitUntil(
    (async () => {
      const cs = await self.clients.matchAll({ type: "window" });
      for (const c of cs) {
        if (c.url.includes(target)) {
          c.focus();
          return;
        }
      }
      self.clients.openWindow(target);
    })(),
  );
});
