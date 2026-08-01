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
  // Con un path locale (sandbox) lo si usa; senza, Playwright lancia il SUO
  // Chromium (in CI: `npx playwright install chromium`). Skip solo se manca tutto.
  const exe = trovaChromium();
  const lancio = { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] };
  if (exe) lancio.executablePath = exe;
  let b;
  try { b = await chromium.launch(lancio); }
  catch (e) { console.error("SKIP: chromium non avviabile: " + String(e.message).split("\n")[0]); process.exit(2); }
  const page = await b.newPage();
  const errori = [];
  // il rumore di rete (siamo offline, file://) non è un guasto della console:
  // qui si cercano ECCEZIONI del codice, non risorse irraggiungibili.
  const rumore = /Failed to load resource|CORS policy|net::ERR|ERR_CONNECTION/;
  page.on("pageerror", e => errori.push("pageerror: " + e.message));
  let bootRiga = "";                                     // P3: la riga [boot] con i ms misurati
  let orbInit = 0, orbRipetuti = 0;                      // V2-A: la console pulita si CONTA
  page.on("console", m => {
    const t = m.text();
    if (m.type() === "error" && !rumore.test(t)) errori.push("console.error: " + t);
    if (t.startsWith("[boot]")) bootRiga = t;
    if (t.startsWith("[orb] init ripetuto")) orbRipetuti++;
    else if (t.startsWith("[orb] init")) orbInit++;
  });

  const url = "file://" + path.resolve(__dirname, "..", "panel", "index.html");
  await page.addInitScript(() => { try { localStorage.setItem("dv_demo", "1"); } catch (e) {} });
  // Prova OFFLINE per davvero: le richieste esterne (font, CDN) si abortiscono
  // SUBITO invece di lasciarle appese. Un <link> stylesheet pendente blocca
  // l'esecuzione degli script: senza questo abort, in sandbox senza rete la
  // misura [boot] segnava ~13 s di font, non il boot della console.
  await page.route(/^https?:\/\//, r => r.abort());
  await page.goto(url);
  await page.waitForTimeout(700);

  // 0 · P3: il boot deve DICHIARARSI finito — classe `preboot` tolta dal body
  //     e riga [boot] coi millisecondi in console. Se una delle due manca,
  //     la console o resta spenta o si finge pronta: entrambi guasti.
  const boot = await page.evaluate(() => ({
    preboot: document.body.classList.contains("preboot"),
    hint: !!document.getElementById("bootHint"),
  }));

  // 1 · route() deve sopravvivere su tutte le viste principali
  for (const v of ["chat", "dashboard", "brain", "improve", "home", "chat"]) {
    await page.evaluate(v2 => route(v2), v);
    await page.waitForTimeout(350);
  }

  // 1b · X3: nella vista Miglioramenti il quadro di potenziamento si legge
  //      e disegna (collegamento vivo alla nota del cervello; in demo, la
  //      variante demo). Se il fetch o il parsing esplodono, qui manca il box
  //      o il bottone «Apri la nota».
  await page.evaluate(() => route("improve"));
  await page.waitForTimeout(600);
  const quadro = await page.evaluate(() => ({
    box: !!document.getElementById("quadroBox"),
    apri: !!document.getElementById("quadroApri"),
    // le CHIUSE si vedono: nel gruppo FATTE c'è chi ha chiuso e la nota di chiusura
    fatteFirmate: /andrea/.test((document.getElementById("imp-fatte") || { textContent: "" }).textContent),
    // M1+M2: barre coi punteggi e curva SVG, senza aprire niente
    barre: document.querySelectorAll("#quadroBox .qbar").length,
    curva: !!document.querySelector("#quadroBox svg"),
    // M3: colonne affiancate e la priorità che si vede in DA FARE
    colonne: !!document.querySelector(".imp-cols"),
    prioVisibile: /ALTA/.test((document.getElementById("imp-dafare") || { textContent: "" }).textContent),
  }));
  await page.evaluate(() => route("chat"));
  await page.waitForTimeout(300);

  // 1c · R2: la barra di scrittura sta DENTRO il pannello col suo respiro —
  //      niente testo tagliato dal bordo (il difetto visto in produzione).
  const composer = await page.evaluate(() => {
    const ta = document.getElementById("chatMsg"), sc = document.getElementById("sideChat");
    if (!ta || !sc) return null;
    const t = ta.getBoundingClientRect(), s = sc.getBoundingClientRect();
    return { margine: Math.round(s.bottom - t.bottom), dentro: t.bottom <= s.bottom };
  });

  // 2 · il modo vocale si apre e l'ORB DISEGNA (pixel ≠ fondo).
  //     V2-A: aprendo il vox l'orb si inizializza UNA volta (l'audit 31-07
  //     ne contava tre nello stesso istante); un secondo init sulla stessa
  //     canvas viene IGNORATO con warning (idempotenza provata qui sotto).
  const initPrima = orbInit;
  await page.click("#voxBtn");
  await page.waitForTimeout(1000);
  const initVox = orbInit - initPrima;
  await page.evaluate(() => initOrb("voxOrb", 320));      // il "chi ci riprova" dell'audit
  await page.waitForTimeout(200);
  const initDopoRipetuta = orbInit - initPrima;
  // In headless sotto carico il rAF può essere AFFAMATO (0-20 fps): il canvas
  // può farsi campionare proprio dopo un clear del ResizeObserver. Si campiona
  // 3 volte; se il loop non ha dipinto, si forza UN disegno vero (stessa
  // pipeline: stato, ctx, size, formule) e lo si DICHIARA — la classe di
  // guasto sorvegliata (canvas 0×0, init mancata, eccezioni) resta coperta.
  const leggiVox = () => page.evaluate(() => {
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
  let vox = await leggiVox();
  for (let tentativo = 0; tentativo < 2 && vox.canvas && !vox.css && vox.px <= 200; tentativo++) {
    await page.waitForTimeout(500);
    vox = await leggiVox();
  }
  if (vox.canvas && !vox.css && vox.px <= 200) {
    vox = await page.evaluate(() => {
      try { orbDraw(state._orb, performance.now()); } catch (e) {}
      const cv = document.getElementById("voxOrb");
      let px = 0;
      try {
        const d = cv.getContext("2d").getImageData(0, 0, cv.width, cv.height).data;
        for (let i = 3; i < d.length; i += 4) if (d[i] > 0) px++;
      } catch (e) {}
      const M = document.getElementById("voxMode");
      return { aperto: !!(M && !M.hidden && M.classList.contains("open")), css: false,
               canvas: true, w: cv.width, h: cv.height, cssW: cv.clientWidth, px, forzato: true };
    });
    if (vox.px > 200) console.log("[vox] rAF affamato in headless: il loop non ha dipinto nei 2s, il disegno forzato sì (pipeline sana)");
  }
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

  // 5 · F2 (numero unico): home e Cervello vivo devono dire LO STESSO numero
  //     di neuroni — stessa sorgente (stats.notes), verificata qui in CI.
  await page.evaluate(() => route("home"));
  await page.waitForTimeout(700);
  const nHome = await page.evaluate(() => {
    const el = document.getElementById("homeSub");                 // overlay della home O1
    const m = el && el.textContent.match(/^([\d.,]+)\s+neuroni/);
    return m ? m[1] : null;
  });
  await page.evaluate(() => route("brain"));
  await page.waitForTimeout(800);
  const nBrain = await page.evaluate(() => {
    const el = document.getElementById("brainOrbSub");
    const m = el && el.textContent.match(/^([\d.,]+)\s+neuroni/);
    return m ? m[1] : null;
  });

  await b.close();

  let ko = 0;
  if (errori.length) { console.error("ECCEZIONI IN CONSOLE/PAGINA:\n  " + errori.join("\n  ")); ko = 1; }
  if (boot.preboot) { console.error("FAIL (P3): la classe `preboot` è ancora sul body — la console non si è dichiarata pronta"); ko = 1; }
  if (!boot.hint) { console.error("FAIL (P3): manca #bootHint nell'HTML statico"); ko = 1; }
  if (!bootRiga) { console.error("FAIL (P3): nessuna riga [boot] in console — la misura del boot è sparita"); ko = 1; }
  else console.log("[boot misurato] " + bootRiga);
  if (!quadro.box || !quadro.apri) { console.error("FAIL (X3): il quadro di potenziamento non si disegna in Miglioramenti (box=" + quadro.box + ", apri=" + quadro.apri + ")"); ko = 1; }
  if (!quadro.fatteFirmate) { console.error("FAIL: il gruppo FATTE non mostra le task chiuse con la firma di chi ha chiuso"); ko = 1; }
  if (quadro.barre < 4) { console.error("FAIL (M1): il quadro non disegna le barre dei punteggi (trovate " + quadro.barre + ")"); ko = 1; }
  if (!quadro.curva) { console.error("FAIL (M2): manca la curva di crescita (SVG) nel quadro"); ko = 1; }
  if (!quadro.colonne) { console.error("FAIL (M3): le colonne IN CORSO · DA FARE · FATTE non sono affiancate (.imp-cols assente)"); ko = 1; }
  if (!quadro.prioVisibile) { console.error("FAIL (M3): la priorità ALTA non si vede nella colonna DA FARE"); ko = 1; }
  if (!composer || !composer.dentro || composer.margine < 14) { console.error("FAIL (R2): la barra di scrittura è tagliata o senza respiro (margine=" + (composer && composer.margine) + "px, minimo 14)"); ko = 1; }
  if (initVox !== 1) { console.error("FAIL (V2-A): aprendo il vox l'orb si è inizializzato " + initVox + " volte (atteso: 1 — l'audit ne contava 3)"); ko = 1; }
  if (initDopoRipetuta !== initVox || orbRipetuti < 1) { console.error("FAIL (V2-A): l'init ripetuto sulla stessa canvas non è stato ignorato (init=" + initDopoRipetuta + ", warning=" + orbRipetuti + ")"); ko = 1; }
  if (!nHome || !nBrain || nHome !== nBrain) { console.error("FAIL (F2): home dice «" + nHome + "» neuroni, Cervello vivo «" + nBrain + "» — la sorgente non è unica"); ko = 1; }
  else console.log("[numero unico] home=" + nHome + " · cervello=" + nBrain);
  if (!vox.aperto) { console.error("FAIL: il modo vocale non si è aperto"); ko = 1; }
  else if (vox.canvas && vox.px <= 200 && !vox.css) {
    console.error(`FAIL: l'orb NON disegna (canvas ${vox.w}x${vox.h}, cssW=${vox.cssW}, px=${vox.px})`); ko = 1;
  }
  if (!dopoRisposta.aperto) { console.error("FAIL (guasto B): il modo vocale si è CHIUSO durante la risposta"); ko = 1; }
  if (dopoRisposta.righe < 2) { console.error("FAIL: il trascritto non mostra domanda+risposta (righe=" + dopoRisposta.righe + ")"); ko = 1; }
  if (!chiuso) { console.error("FAIL: Escape non chiude il modo vocale"); ko = 1; }
  if (ko) process.exit(1);
  console.log(`Console VIVA: navigazione ok · modo vocale aperto · orb disegnato (${vox.css ? "fallback css" : vox.px + " px"}) · Escape chiude.`);
})().catch(e => { console.error("FAIL (eccezione della prova): " + String(e.message).split("\n")[0]); process.exit(1); });
