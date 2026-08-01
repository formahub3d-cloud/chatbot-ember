/* Fase 9 · Service worker di Divina — il GUSCIO offline, niente di più.
 *
 * Strategia deliberatamente prudente:
 *  - le NAVIGAZIONI (index.html) vanno SEMPRE prima in rete: un deploy non
 *    deve mai restare imprigionato in cache (la console si aggiorna con
 *    ./deploy.command e deve arrivare subito); la cache è solo il paracadute
 *    quando la rete manca del tutto;
 *  - gli asset del guscio (voce.js, brain3d.js, manifest, icone) sono
 *    cache-first con revalidazione in background;
 *  - le API (/chat, /admin/*, /voice/*…) NON si toccano: niente cache su
 *    dati vivi, mai una risposta vecchia spacciata per fresca.
 * La versione della cache segue la versione della console: bump = pulizia. */
"use strict";
const VERSIONE = "divina-guscio-01-08e";
const GUSCIO = ["./", "./index.html", "./voce.js", "./brain3d.js", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSIONE).then(c => c.addAll(GUSCIO)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSIONE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const asset = GUSCIO.some(g => url.pathname.endsWith(g.replace("./", "/")));
  if (e.request.mode === "navigate") {
    // rete prima, cache come paracadute: un deploy arriva SUBITO
    e.respondWith(fetch(e.request).then(r => {
      const cp = r.clone(); caches.open(VERSIONE).then(c => c.put("./index.html", cp));
      return r;
    }).catch(() => caches.match("./index.html")));
    return;
  }
  if (asset) {
    e.respondWith(caches.match(e.request).then(hit => {
      const rete = fetch(e.request).then(r => { const cp = r.clone(); caches.open(VERSIONE).then(c => c.put(e.request, cp)); return r; }).catch(() => hit);
      return hit || rete;
    }));
  }
  // tutto il resto (API): passa dritto alla rete, nessuna cache
});
