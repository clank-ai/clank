// The phone app's service worker (design 0025 §3): it keeps the app's shell (the page, its script, its style, its icon)
// so the app opens and shows its offline screen when the PC cannot be reached; everything else (the API, the stream,
// the files) goes to the network only, never kept. Notifications come with a later step (design 0025 §4).
"use strict";

const SHELL = "clank-shell-v3";
const FILES = ["./", "app.js", "model.mjs", "style.css", "icon.svg", "icon-180.png", "manifest.webmanifest"];
const PAGE = "./"; // the page is served at the app's root: a launch with no network gets it from here

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) => Promise.all(names.filter((name) => name !== SHELL).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.includes("/api/") || url.pathname.endsWith("/pair")) return; // the network only: nothing of the work is kept
  const file = url.pathname.split("/").pop();
  if (!FILES.includes(file) && event.request.mode !== "navigate") return;
  event.respondWith(
    fetch(event.request).then((response) => {
      if (response.ok && event.request.mode !== "navigate") {
        const copy = response.clone();
        caches.open(SHELL).then((cache) => cache.put(event.request, copy));
      }
      return response;
    }).catch(() => caches.match(event.request.mode === "navigate" ? PAGE : event.request)),
  );
});
