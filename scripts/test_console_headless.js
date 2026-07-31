#!/usr/bin/env node
/* M4 · La prova che avrebbe evitato tutto questo.
 *
 * I 381 test Python non aprono MAI il pannello: «_rec is not defined» ha
 * lasciato la console morta in produzione e nessun controllo se n'è accorto.
 * Questo script avvia DAVVERO la console (Chromium senza testa, modalità demo,
 * zero rete) e fallisce se:
 *   1. una ECCEZIONE compare in pagina o in console (pageerror/console.error);
 *   2. la navigazione fra le viste non sopravvive (route());
 *   3. il MODO VOCALE non si apre o l'orb non disegna pixel diversi dal fondo.
 *
 * Uso:  node scripts/test_console_headless.js
 * Chromium: PLAYWRIGHT o CHROMIUM_PATH (default: il chromium di Playwright).
 * Il wrapper pytest (tests/test_console_headless.py) salta se mancano
 * node/playwright/chromium — ma dove ci sono, la console si apre DAVVERO.
 */
"use strict";
const path = require("path");
const fs = require("fs");

function trovaChromium() {
  if (process.env.CHROMIUM_PATH && fs.existsSync(process.env.CHROMIUM_PATH)) return process.env.CHROMIUM_PATH;
  const cands = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
  ];
  for (const c of cands) if (fs.existsSync(c)) return c;
  const base = process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers";
  try {
    for (const d of fs.readdirSync(base)) {
      const p = path.join(base, d, "chrome-linux", "chrome");
      if (fs.existsSync(p)) return p;
    }
  } catch (e) {}
  return null;
}

(async () => {
  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch (e) { console.error("SKIP: playwright non installato"); process.exit(2); }
  const exe = trovaChromium();
  if (!exe) { console.error("SKIP: chromium non trovato"); process.exit(2); }

  const b = await chromium.launch({
    executablePath: exe,
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
  });
  const page = await b.newPage();
  const errori = [];
  // il rumore di rete (siamo offline, file://) non è un guasto della console:
  // qui si cercano ECCEZIONI del codice, non risorse irraggiungibili.
  const rumore = /Failed to load resource|CORS policy|net::ERR|ERR_CONNECTION/;
  page.on("pageerror", e => errori.push("pageerror: " + e.message));
  page.on("console", m => { if (m.type() === "error" && !rumore.test(m.text())) errori.push("console.error: " + m.text()); });

  const url = "file://" + path.resolve(__dirname, "..", "panel", "index.html");
  await page.addInitScript(() => { try { localStorage.setItem("dv_demo", "1"); } catch (e) {} });
  await page.goto(url);
  await page.waitForTimeout(700);

  // 1 · route() deve sopravvivere su tutte le viste principali
  for (const v of ["chat", "dashboard", "brain", "home", "chat"]) {
    await page.evaluate(v2 => route(v2), v);
    await page.waitForTimeout(350);
  }

  // 2 · il modo vocale si apre e l'ORB DISEGNA (pixel ≠ fondo)
  await page.click("#voxBtn");
  await page.waitForTimeout(1000);
  const vox = await page.evaluate(() => {
    const M = document.getElementById("voxMode");
    const aperto = !!(M && !M.hidden && M.classList.contains("open"));
    const css = !!document.querySelector("#voxMode .orb-css");
    const cv = document.getElementById("voxOrb");
    let px = 0, w = 0, h = 0, cssW = 0;
    if (cv && cv.getContext) {
      w = cv.width; h = cv.height; cssW = cv.clientWidth;
      try {
        const d = cv.getContext("2d").getImageData(0, 0, cv.width, cv.height).data;
        for (let i = 3; i < d.length; i += 4) if (d[i] > 0) px++;
      } catch (e) {}
    }
    return { aperto, css, canvas: !!(cv && cv.getContext), w, h, cssW, px };
  });
  console.log("[vox]", JSON.stringify(vox));

  // 3 · GUASTO B (audit 31-07): la RISPOSTA non deve chiudere il modo vocale.
  //     Si simula un turno intero in demo (voxSend → chatTurn → speak → loop):
  //     se qualcosa smonta il modale mentre Divina risponde, qui esplode.
  await page.evaluate(() => voxSend("quanto costa la stampa 3d?"));
  await page.waitForTimeout(1500);
  const dopoRisposta = await page.evaluate(() => {
    const M = document.getElementById("voxMode");
    return {
      aperto: !!(M && !M.hidden && M.classList.contains("open")),
      righe: document.querySelectorAll("#voxLog .vox-line").length,
    };
  });
  console.log("[vox dopo risposta]", JSON.stringify(dopoRisposta));

  // 4 · chiusura pulita con Escape
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const chiuso = await page.evaluate(() => {
    const M = document.getElementById("voxMode");
    return !!(M && (M.hidden || !M.classList.contains("open")));
  });

  await b.close();

  let ko = 0;
  if (errori.length) { console.error("ECCEZIONI IN CONSOLE/PAGINA:\n  " + errori.join("\n  ")); ko = 1; }
  if (!vox.aperto) { console.error("FAIL: il modo vocale non si è aperto"); ko = 1; }
  else if (vox.canvas && vox.px <= 200 && !vox.css) {
    console.error(`FAIL: l'orb NON disegna (canvas ${vox.w}x${vox.h}, cssW=${vox.cssW}, px=${vox.px})`); ko = 1;
  }
  if (!dopoRisposta.aperto) { console.error("FAIL (guasto B): il modo vocale si è CHIUSO durante la risposta"); ko = 1; }
  if (dopoRisposta.righe < 2) { console.error("FAIL: il trascritto non mostra domanda+risposta (righe=" + dopoRisposta.righe + ")"); ko = 1; }
  if (!chiuso) { console.error("FAIL: Escape non chiude il modo vocale"); ko = 1; }
  if (ko) process.exit(1);
  console.log(`Console VIVA: navigazione ok · modo vocale aperto · orb disegnato (${vox.css ? "fallback css" : vox.px + " px"}) · Escape chiude.`);
})();
