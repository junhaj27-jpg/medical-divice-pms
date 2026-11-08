"use strict";

const cacheName = "medwatch-rule-batch-demo-v1";
const assets = ["index.html", "demo.css", "demo.js", "engine.js", "examples.json"];
const index = new URL("index.html", self.registration.scope).href;
const urls = new Set(assets.map(asset => new URL(asset, self.registration.scope).href));

self.addEventListener("install", event => {
    event.waitUntil(caches.open(cacheName).then(cache => cache.addAll(assets)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
    event.waitUntil(caches.keys().then(keys => Promise.all(keys
        .filter(key => key.startsWith("medwatch-rule-batch-demo-") && key !== cacheName)
        .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
    const url = new URL(event.request.url);
    const target = url.href === self.registration.scope ? index : url.href;
    if (event.request.method === "GET" && urls.has(target)) {
        event.respondWith(caches.open(cacheName).then(async cache => (await cache.match(target)) || fetch(event.request)));
    }
});
