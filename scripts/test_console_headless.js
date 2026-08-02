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
  for (const v of ["chat", "dashboard", "brain", "improve", "human", "home", "chat"]) {
    await page.evaluate(v2 => route(v2), v);
    await page.waitForTimeout(350);
  }

  // 1-bis · V8/D1 · «Il menu si illumina e non cambia pagina».
  //   Riproduzione del difetto visto in produzione il 2/08, con la rete
  //   rallentata a mano: la vista A è lenta, la B veloce, si clicca A e subito
  //   B. Prima della correzione la A arrivava DOPO e passava sopra alla B —
  //   barra e titolo sulla B, contenuto della A, esattamente il sintomo.
  //   (Il sospetto nel prompt era il grafo che occupa il thread: non era quello.)
  const d1 = await page.evaluate(async () => {
    const vero = window.api;
    window.api = (svc, p, o) => new Promise(res => {
      const lenta = p.startsWith("/admin/analytics") || p.startsWith("/admin/brain");
      setTimeout(() => Promise.resolve(vero(svc, p, o)).then(res), lenta ? 400 : 30);
    });
    route("dashboard");
    await new Promise(r => setTimeout(r, 40));
    route("events");
    await new Promise(r => setTimeout(r, 900));
    window.api = vero;
    const c = document.getElementById("content").textContent;
    return {
      titolo: document.getElementById("pageTitle").textContent,
      eventi: /Eventi conversazione/.test(c),
      dashboardRimasta: /Richieste oggi|Note nel cervello/.test(c),
    };
  });
  await page.evaluate(() => route("home"));
  await page.waitForTimeout(300);

  // 1a-bis · Human: la figura disegna (SVG a strati) e la scheda ha le sezioni
  await page.evaluate(() => route("human"));
  await page.waitForTimeout(600);
  const human = await page.evaluate(() => ({
    svg: !!document.querySelector("#humanFig svg .hstrato"),
    scheda: /Salute/.test((document.getElementById("humanScheda") || { textContent: "" }).textContent),
    riservata: /fuori dall'indice/.test(document.getElementById("content").textContent),
  }));
  await page.evaluate(() => route("home"));
  await page.waitForTimeout(300);

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
    // M1: barre coi punteggi, senza aprire niente
    barre: document.querySelectorAll("#quadroBox .qbar").length,
    // V5-2: il radar esagonale (griglia + poligono di oggi; con «prima» anche
    // il tratteggiato) ha preso il posto della polilinea
    radar: document.querySelectorAll("#quadroBox svg polygon").length >= 2,
    // V6/A3: la SETTIMA area («Estetica e resa visiva») c'è, e il radar la
    // disegna — l'esagono è diventato un ETTAGONO. Si contano i vertici del
    // poligono «oggi» (l'ultimo con riempimento), non le etichette.
    punte: (() => {
      const p = [...document.querySelectorAll("#quadroBox svg polygon")].filter(g => g.getAttribute("fill") !== "none").pop();
      return p ? p.getAttribute("points").trim().split(/\s+/).length : 0;
    })(),
    estetica: /Estetica e resa visiva/.test((document.getElementById("quadroBox") || { textContent: "" }).textContent),
    // M3: colonne affiancate e la priorità che si vede in DA FARE
    colonne: !!document.querySelector(".imp-cols"),
    // V7/C · «DA VERIFICARE» è la colonna del merge, e da lì non si esce senza
    //   un nome: il bottone c'è, e il merge NON ha chiuso niente da solo.
    daVerificare: /DA VERIFICARE/.test((document.getElementById("content")||{textContent:""}).textContent),
    confermaUmana: !!document.querySelector("[data-vfok]") && !!document.querySelector("[data-vfno]"),
    prioVisibile: /ALTA/.test((document.getElementById("imp-dafare") || { textContent: "" }).textContent),
  }));
  await page.evaluate(() => route("chat"));
  await page.waitForTimeout(300);

  // 1b-bis · V6/B1 e V6/B3, resi in chat. Si iniettano i due messaggi che il
  //      server sa produrre (una risposta con `gap`, una proposta «imparato»)
  //      e si verifica che la console li mostri per quello che sono: un'offerta
  //      ATTACCATA alla risposta, e una citazione che dice da dove viene.
  const convV6 = await page.evaluate(() => {
    const salvo = state.chat.slice();
    state.demo = false;                       // l'offerta non si mostra in demo
    state.chat = [{ role: "user", text: "che orari fate il sabato?" },
                  { role: "bot", text: "Questo nel cervello non c'è.", sources: [],
                    gap: { question: "che orari fate il sabato?", offer: "Aggiungiamolo al cervello." } },
                  { role: "imparato", voci: [{ nota_titolo: "Il sabato si chiude alle 13",
                    detail: "Orario ridotto il sabato.", citazione: "il sabato chiudiamo all'una" }] }];
    renderChat();
    const out = {
      offerta: !!document.querySelector(".gap-offerta"),
      bottone: /Scrivi la nota adesso/.test(document.getElementById("chatInner").textContent),
      cita: /il sabato chiudiamo all'una/.test(document.getElementById("chatInner").textContent),
      nonSalvate: /non salvate/.test(document.getElementById("chatInner").textContent),
    };
    state.chat = salvo; state.demo = true; renderChat();
    return out;
  });

  // 1b-ter · V8/A + V8/C2 + V8/C3, resi in chat.
  //   A  · quando il sistema registra qualcosa su di te lo dice LÌ, nella
  //        bolla, col bottone per farglielo dimenticare (mai di nascosto);
  //   C2 · la delega compare dentro il filo come riga di SISTEMA — non un
  //        messaggio, non una sezione altrove;
  //   C3 · il risultato è una scheda con un NOME, non testo che scorre via.
  const convV8 = await page.evaluate(() => {
    const salvo = state.chat.slice();
    state.demo = false;
    state.chat = [
      { role: "user", text: "mi prepari il sollecito per ATS?" },
      { role: "delega", agent: "dante", ruolo: "Invoice Chase", fine: false },
      { role: "delega", agent: "dante", fine: true },
      { role: "bot", text: "Fatto: ecco il sollecito.", sources: [],
        ricordato: { id: "m-x", fatto: "Preferisci risposte brevi." } },
      { role: "scheda", agent: "dante", tipo: "Invoice Chase", nome: "Sollecito fattura 214 · ATS",
        testo: "riga\nriga\nriga\nriga\nriga", righe: 5 },
    ];
    renderChat();
    const t = document.getElementById("chatInner").textContent;
    const out = {
      delegaVia: /affido a\s*Dante/.test(t.replace(/\s+/g, " ")),
      delegaFine: /Dante\s*ha finito/.test(t.replace(/\s+/g, " ")),
      righeSistema: document.querySelectorAll("#chatInner .riga-sistema").length,
      scheda: !!document.querySelector("#chatInner .scheda-out"),
      schedaNome: /Sollecito fattura 214/.test(t),
      ricordo: !!document.querySelector("#chatInner .ricordato") && /Dimentica/.test(t),
    };
    state.chat = salvo; state.demo = true; renderChat();
    return out;
  });

  // 1b-quater · V8/A1 · La pagina «Cosa so di te»: l'elenco, la FONTE al posto
  //   della percentuale (in Zoey ogni memoria è al 70%: un numero costante
  //   travestito da misura), il distintivo di quella che sta CAMBIANDO le
  //   risposte adesso, e il bottone che cancella.
  await page.evaluate(() => route("memoria"));
  await page.waitForTimeout(500);
  const memV8 = await page.evaluate(() => {
    const c = document.getElementById("content"), t = c.textContent;
    return {
      righe: c.querySelectorAll(".mem-riga").length,
      fonte: !!c.querySelector(".mem-fonte"),
      nessunaPercentuale: !/\b\d{1,3}\s*%/.test(t),
      inUso: !!c.querySelector(".mem-usata"),
      dimentica: !!c.querySelector("[data-dim]"),
      art17: /art\. 17/.test(t),
    };
  });

  // 1b-quater-bis · V9/D · «Quello che ci siamo detti»: i promemoria stanno
  //   nella STESSA pagina delle memorie, ognuno col suo Dimentica. Se il bottone
  //   non li raggiunge, l'art. 17 è coperto a metà — e mezza copertura, su un
  //   obbligo di legge, è peggio di nessuna promessa.
  const riassV9 = await page.evaluate(() => {
    const c = document.getElementById("content"), t = c.textContent;
    return {
      sezione: /Quello che ci siamo detti/.test(t),
      righe: c.querySelectorAll("[data-dimr]").length,
      retention: /30 giorni/.test(t),
      chiude: typeof window.chiudiConversazione === "function",
    };
  });

  // 1b-quinquies · V8/B · Le due porte del CLIENTE. Girano in demo (il
  //   guardiano non ha cookie né server): quello che si sorveglia è che
  //   esistano, che la kb elenchi con la data e il bottone «è sbagliata», e
  //   che la pagina dei buchi — spenta — DICA perché, invece di sembrare
  //   «nessun buco».
  await page.evaluate(() => route("ckb"));
  await page.waitForTimeout(400);
  const ckbV8 = await page.evaluate(() => {
    const c = document.getElementById("content");
    return { righe: c.querySelectorAll("[data-sbag]").length,
             sappiamo: /sappiamo di voi/i.test(c.textContent),
             nonScrive: /non si scrive nel cervello/i.test(c.textContent) };
  });
  await page.evaluate(() => route("cbuchi"));
  await page.waitForTimeout(400);
  const buchiV8 = await page.evaluate(() => {
    const t = document.getElementById("content").textContent;
    return { spiega: /utenti finali/.test(t) && /decidiamo insieme/.test(t),
             nonFingeVuoto: !/Nessuna domanda rimasta/.test(t) };
  });

  // 1b-quinquies-bis · V9/C · La capacità arriva DAL SERVER e si vede sotto la
  //   risposta, con il bottone per affidarla. Il riconoscitore nella console non
  //   esiste più: era l'unico posto dove funzionava, e a voce non serviva a
  //   niente. Qui si verifica che la console disegni il dato che riceve.
  const capV9 = await page.evaluate(() => {
    const salvo = state.chat.slice();
    state.demo = false;
    state.chat = [{ role: "user", text: "cerca chi vende stampa 3D a Benevento" },
                  { role: "bot", text: "Nel cervello non c'è.", sources: [],
                    cap: { agente: "beatrice", skill: "customer-research",
                           role: "Customer Research", desc: "trova e qualifica potenziali clienti" } }];
    renderChat();
    const t = document.getElementById("chatInner").textContent.replace(/\s+/g, " ");
    const out = {
      offerta: /Questo lo sa fare/.test(t),
      chi: /Beatrice/.test(t),
      bottone: /Affida a/.test(t),
      // il riconoscitore lessicale del V7 non deve più esistere nella console
      niente: typeof window.capTrova === "undefined" && typeof window.capCatalogo === "undefined",
    };
    state.chat = salvo; state.demo = true; renderChat();
    return out;
  });

  // 1b-sexies · V9/A · Una funzione spenta lo dice DOVE si usa.
  //   Il 2/08 «Cosa so di te» diceva «non so niente di te» mentre la verità era
  //   «non posso ricordare niente, mi manca la tabella». Qui si sorveglia che
  //   l'avviso sia UNO e uguale ovunque, che al cliente non si mostri la riga
  //   tecnica (non è lui a dover impostare una variabile su Railway), e che lo
  //   stato vuoto non finga di essere vuoto quando invece è spento.
  const degradoV9 = await page.evaluate(() => {
    const spento = { stato: "spento", titolo: "«Cosa so di te»", dove: "Squadra",
                     perche: "si azzera a ogni redeploy", come: "applica db/tenant_memory.sql", manca: ["tenant_memory"] };
    const nonSo = { stato: "non-so", titolo: "x", dove: "y", perche: "non è leggibile adesso", come: "", manca: [] };
    const owner = boxDegrado(spento), cliente = boxDegrado(spento, { cliente: true });
    return {
      compare: /data-degrado="spento"/.test(owner),
      spiega: /si azzera a ogni redeploy/.test(owner),
      tecnicoOwner: /tenant_memory\.sql/.test(owner),
      tecnicoCliente: /tenant_memory\.sql/.test(cliente),   // deve essere FALSO
      acceso: boxDegrado({ stato: "acceso" }) === "",
      nonSo: /data-degrado="non-so"/.test(boxDegrado(nonSo)),
      vuotoSpento: /Non posso ricordare niente/.test(vuotoOnesto(spento, "Non so niente di te", "", "brain")),
      vuotoNormale: /Non so niente di te/.test(vuotoOnesto({ stato: "acceso" }, "Non so niente di te", "", "brain")),
    };
  });
  // e nella pagina del cliente l'avviso c'è DAVVERO, non solo la funzione che lo sa fare
  const degradoCliente = await page.evaluate(() =>
    !!document.querySelector("#content .degrado[data-degrado='spento']"));
  // Diagnostica: l'elenco completo delle funzioni spente resta, ma non è più l'unico posto
  await page.evaluate(() => { const g = document.getElementById("diagGroup"); if (g) g.hidden = false; route("system"); });
  await page.waitForTimeout(700);
  const diagV9 = await page.evaluate(() => {
    const t = document.getElementById("content").textContent;
    return { elenco: /funzion[ei] spent/.test(t), voceVera: /voce di Divina/.test(t) };
  });
  // 1b-septies · V9/B · La KB del cliente nasce dal suo sito, come PROPOSTA.
  //   Quello che si sorveglia non è che legga un sito (qui non c'è rete): è che
  //   ogni voce arrivi in schermo con la PAGINA e la FRASE da cui viene, e che
  //   la finestra dica a chiare lettere che non sta salvando niente. Una scheda
  //   cliente senza provenienza è peggio di una vuota: sembra verificata.
  await page.evaluate(() => route("clienti"));
  await page.waitForTimeout(600);
  const sitoV9 = await page.evaluate(async () => {
    const b = document.querySelector("[data-sito]");
    if (!b) return { bottone: false };
    b.click();
    const box = document.getElementById("dsBox");
    box.querySelector("#dsUrl").value = "ats.it";
    box.querySelector("#dsGo").click();
    await new Promise(r => setTimeout(r, 400));
    const t = box.textContent;
    const out = {
      bottone: true,
      voci: box.querySelectorAll("#dsOut .imparato-voce").length,
      cita: box.querySelectorAll("#dsOut .imparato-cita").length,
      url: /https:\/\/ats\.it\/servizi/.test(t),
      nonSalvate: /non salvate/.test(t),
      approvi: /solo se le approvi/.test(t),
    };
    box.querySelector("#dsNo").click();     // si chiude dalla sua porta: `.modal-back`
    return out;                             // esiste anche per la finestra Connessione, nascosta
  });

  // Squadra: accanto a chi non ha una voce sua, si vede
  await page.evaluate(() => route("agents"));
  await page.waitForTimeout(600);
  const vociV9 = await page.evaluate(() =>
    (document.getElementById("content").textContent.match(/voce di Divina/g) || []).length);
  await page.evaluate(() => route("home"));
  await page.waitForTimeout(300);

  // 1c · R2: la barra di scrittura sta DENTRO il pannello col suo respiro —
  //      niente testo tagliato dal bordo (il difetto visto in produzione).
  const composer = await page.evaluate(() => {
    const ta = document.getElementById("chatMsg"), sc = document.getElementById("sideChat");
    if (!ta || !sc) return null;
    const t = ta.getBoundingClientRect(), s = sc.getBoundingClientRect();
    return { margine: Math.round(s.bottom - t.bottom), dentro: t.bottom <= s.bottom };
  });

  // 1d · V5-3: le PILLOLE stanno SOPRA il campo di scrittura (revisione di
  //      Andrea: contesto prima, scrittura dopo). Si misura la geometria.
  const pillole = await page.evaluate(() => {
    const fb = document.getElementById("focusBar"), op = document.getElementById("orbPicks"), ta = document.getElementById("chatMsg");
    if (!fb || !op || !ta) return null;
    const f = fb.getBoundingClientRect(), o = op.getBoundingClientRect(), t = ta.getBoundingClientRect();
    return { ordine: f.top <= o.top && o.bottom <= t.top + 1 };
  });

  // 1e · V5-4: la lente Temi si ACCENDE dai tag veri (le note demo li
  //      portano, come il vault dall'1/08): se il calcolo perde i tags → 0.
  const temiN = await page.evaluate(async () => { await ensureOrbite(); return Object.keys((state._orbite || {}).temi || {}).length; });

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
  // 2b · G (01-08): le due domande sono SEPARATE e contano entrambe.
  //     «la pipeline disegna?» → campione (ed eventuale disegno forzato, sotto)
  //     «il ciclo è vivo?»     → contatore di frame, due letture a ~1,5s:
  //     anche a 5 fps cresce — il guasto del 31/07 (orbDraw sana, ciclo morto)
  //     qui diventa rosso. Tre finestre per assorbire il rAF affamato.
  let cicloVivo = false, fA = 0, fB = 0;
  for (let w = 0; w < 3 && !cicloVivo; w++) {
    fA = await page.evaluate(() => (state._orb && state._orb.frames) || 0);
    await page.waitForTimeout(1500);
    fB = await page.evaluate(() => (state._orb && state._orb.frames) || 0);
    cicloVivo = fB > fA;
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
  // V6-2 · la riga DICE quello che dice il colore, e cambia con lo stato vero.
  // È accessibilità, non rifinitura: chi non distingue il rosso dall'azzurro
  // deve capire lo stesso cosa sta succedendo. Gli stati si forzano uno a uno
  // (il riposo per ULTIMO: in demo la regia ha dispatch recenti veri).
  const frasi = await page.evaluate(() => {
    const leggi = () => (document.getElementById("orbFraseT") || {}).textContent || "";
    const out = {};
    state._dispatch = [];                       // la regia demo ha dispatch veri e recenti
    state._pensa = true; aggiornaOrbita(); out.pensa = leggi();
    state._pensa = false;
    state._dispatch = [{ at: Math.floor(Date.now() / 1000) - 5, agent: "virgilio",
                         role: "sta cercando nel cervello", routed: true }];
    aggiornaOrbita(); out.lavora = leggi();
    state._dispatch = [{ at: Math.floor(Date.now() / 1000) - 5, agent: "dante", routed: true },
                       { at: Math.floor(Date.now() / 1000) - 9, agent: "beatrice", routed: true }];
    aggiornaOrbita(); out.due = leggi();
    state._dispatch = []; state._ingestFresca = false; aggiornaOrbita(); out.riposo = leggi();
    return out;
  });
  const nHome = await page.evaluate(() => {
    // V6: i neuroni della home stanno nella RIGA sotto l'orbita (dove sta lo
    // stato), non più nel sottotitolo: un numero, un posto solo.
    const el = document.getElementById("orbFraseT");
    const m = el && el.textContent.match(/([\d.,]+)\s+neuroni/);
    return m ? m[1] : null;
  });
  // 5b · V6-1: titolo in testa, UNA riga di stato sotto l'orbita, e la vecchia
  //      colonnina di tre spie SPARITA (era tre etichette per una cosa sola).
  const homeV6 = await page.evaluate(() => ({
    testa: !!document.querySelector(".home-testa h1"),
    riga: !!document.getElementById("orbFrase"),
    spieVia: !["stPensa", "stLavora", "stAggiorna"].some(id => !!document.getElementById(id)),
    // `state` è un binding const del modulo, NON una proprietà di window: si
    // legge per nome, altrimenti il controllo passa sempre… fallendo.
    api: !!(state._brain3d && state._brain3d.setMood && state._brain3d.setAccent),
  }));

  await page.evaluate(() => route("brain"));
  await page.waitForTimeout(800);
  const nBrain = await page.evaluate(() => {
    const el = document.getElementById("brainOrbSub");
    const m = el && el.textContent.match(/^([\d.,]+)\s+neuroni/);
    return m ? m[1] : null;
  });
  // 5c · V5b (punto 9): i DUE commit affiancati — quello che il cervello ha
  //      letto e quello del vault — e, allineati (demo), NESSUN allarme:
  //      l'1/08 il buco era invisibile perché si guardavano le ore.
  const commitV5b = await page.evaluate(() => {
    const txt = document.getElementById("content").textContent;
    const a = document.getElementById("brainAlert");
    return { cerv: /cervello\s*1f73289abc12/.test(txt), vault: /vault\s*1f73289abc12/.test(txt),
             allarme: !!(a && !a.hidden) };
  });

  // V7/B1 · Diagnostica → Sistema: le migrazioni mancanti si vedono, e ognuna
  //   dice cosa smette di funzionare. In demo ce n'è UNA (il caso vero di
  //   stanotte: tenant_flags.libera), così si prova la resa del problema.
  await page.evaluate(() => route("system"));
  await page.waitForTimeout(500);
  const diag = await page.evaluate(() => {
    const t = (document.getElementById("content") || { textContent: "" }).textContent;
    return { migrazioni: /migrazion[ei] da applicare/i.test(t),
             cosaRompe: /conoscenza generale non si può concedere/i.test(t),
             ddl: /tenant_flags_libera\.sql/.test(t),
             parita: /La console è la stessa nei due servizi/.test(t) };
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
  if (!quadro.radar) { console.error("FAIL (V5-2): il radar esagonale non si disegna nel quadro (poligoni SVG assenti)"); ko = 1; }
  if (quadro.punte !== 7 || !quadro.estetica) { console.error("FAIL (V6-3): il quadro non ha la settima area «Estetica e resa visiva» (punte=" + quadro.punte + ", area=" + quadro.estetica + ")"); ko = 1; }
  else console.log("[quadro] ettagono: " + quadro.punte + " aree");
  if (!quadro.colonne) { console.error("FAIL (M3): le colonne IN CORSO · DA FARE · FATTE non sono affiancate (.imp-cols assente)"); ko = 1; }
  if (!quadro.daVerificare || !quadro.confermaUmana) { console.error("FAIL (V7-C): manca la colonna «DA VERIFICARE» o la conferma umana che la chiude " + JSON.stringify({c: quadro.daVerificare, b: quadro.confermaUmana})); ko = 1; }
  if (!quadro.prioVisibile) { console.error("FAIL (M3): la priorità ALTA non si vede nella colonna DA FARE"); ko = 1; }
  if (!convV6.offerta || !convV6.bottone) { console.error("FAIL (V6-B1): la risposta che ammette il buco non porta l'offerta di colmarlo " + JSON.stringify(convV6)); ko = 1; }
  if (!convV6.cita || !convV6.nonSalvate) { console.error("FAIL (V6-B3): le «cose imparate» non mostrano la citazione o non dichiarano di NON essere salvate " + JSON.stringify(convV6)); ko = 1; }
  if (!composer || !composer.dentro || composer.margine < 14) { console.error("FAIL (R2): la barra di scrittura è tagliata o senza respiro (margine=" + (composer && composer.margine) + "px, minimo 14)"); ko = 1; }
  if (!pillole || !pillole.ordine) { console.error("FAIL (V5-3): le pillole cliente/tema e i companion non stanno SOPRA il campo di scrittura " + JSON.stringify(pillole)); ko = 1; }
  if (temiN < 1) { console.error("FAIL (V5-4): la lente Temi resta spenta anche coi tag presenti (temi=" + temiN + ")"); ko = 1; }
  else console.log("[temi] accesi: " + temiN + " dai tag tema/*");
  if (!homeV6.testa || !homeV6.riga || !homeV6.spieVia || !homeV6.api) { console.error("FAIL (V6-1): la home non è l'orbita col titolo in testa e UNA riga di stato " + JSON.stringify(homeV6)); ko = 1; }
  if (!/pensando/i.test(frasi.pensa || "") || !/virgilio/i.test(frasi.lavora || "")
      || !/dante/i.test(frasi.due || "") || !/beatrice/i.test(frasi.due || "")
      || !/riposo/i.test(frasi.riposo || "")) {
    console.error("FAIL (V6-2): la riga sotto l'orbita non dice lo stato a parole " + JSON.stringify(frasi)); ko = 1;
  } else console.log("[orbita] " + frasi.riposo + " · " + frasi.pensa + " · " + frasi.lavora + " · " + frasi.due);
  if (!commitV5b.cerv || !commitV5b.vault) { console.error("FAIL (V5b-9): la riga «cervello · vault» non mostra i due commit affiancati " + JSON.stringify(commitV5b)); ko = 1; }
  if (commitV5b.allarme) { console.error("FAIL (V5b-9): allarme acceso coi commit ALLINEATI — il confronto è rotto"); ko = 1; }
  if (!human.svg || !human.scheda || !human.riservata) { console.error("FAIL (Human): figura/scheda/avviso-riservatezza mancanti " + JSON.stringify(human)); ko = 1; }
  if (initVox !== 1) { console.error("FAIL (V2-A): aprendo il vox l'orb si è inizializzato " + initVox + " volte (atteso: 1 — l'audit ne contava 3)"); ko = 1; }
  if (initDopoRipetuta !== initVox || orbRipetuti < 1) { console.error("FAIL (V2-A): l'init ripetuto sulla stessa canvas non è stato ignorato (init=" + initDopoRipetuta + ", warning=" + orbRipetuti + ")"); ko = 1; }
  if (!nHome || !nBrain || nHome !== nBrain) { console.error("FAIL (F2): home dice «" + nHome + "» neuroni, Cervello vivo «" + nBrain + "» — la sorgente non è unica"); ko = 1; }
  else console.log("[numero unico] home=" + nHome + " · cervello=" + nBrain);
  if (!diag.migrazioni || !diag.cosaRompe || !diag.ddl) { console.error("FAIL (V7-B1): Diagnostica non dichiara le migrazioni mancanti (o non dice cosa rompono) " + JSON.stringify(diag)); ko = 1; }
  if (!diag.parita) { console.error("FAIL (V7-B3): Diagnostica non confronta le due console"); ko = 1; }
  if (!d1.eventi || d1.dashboardRimasta) {
    console.error("FAIL (V8-D1): il menu si illumina e il contenuto resta indietro — titolo «" + d1.titolo
      + "», contenuto della vista precedente=" + d1.dashboardRimasta); ko = 1;
  } else console.log("[navigazione] la vista lenta non passa più sopra a quella nuova");
  if (!convV8.delegaVia || !convV8.delegaFine || convV8.righeSistema !== 2) {
    console.error("FAIL (V8-C2): la delega non si vede dentro il filo " + JSON.stringify(convV8)); ko = 1;
  }
  if (!convV8.scheda || !convV8.schedaNome) {
    console.error("FAIL (V8-C3): il risultato non è una scheda con un nome " + JSON.stringify(convV8)); ko = 1;
  }
  if (!convV8.ricordo) {
    console.error("FAIL (V8-A): il sistema registra qualcosa su di te e non lo dice nella bolla (o manca il Dimentica)"); ko = 1;
  }
  if (!memV8.righe || !memV8.fonte || !memV8.dimentica || !memV8.art17) {
    console.error("FAIL (V8-A1): la pagina «Cosa so di te» non elenca, non mostra la fonte o non ha il Dimentica " + JSON.stringify(memV8)); ko = 1;
  }
  if (!memV8.nessunaPercentuale) {
    console.error("FAIL (V8-A3): è comparsa una PERCENTUALE nella memoria — è l'errore di Zoey (tutte al 70%): senza criterio si scrive la fonte"); ko = 1;
  }
  if (!memV8.inUso) {
    console.error("FAIL (V8-A4): nessuna memoria è marcata «in uso adesso»: una memoria che non cambia niente è una vetrina"); ko = 1;
  }
  if (!riassV9.sezione || !riassV9.righe || !riassV9.retention) {
    console.error("FAIL (V9-D): i promemoria delle conversazioni non stanno in «Cosa so di te» col loro Dimentica " + JSON.stringify(riassV9)); ko = 1;
  }
  if (!riassV9.chiude) {
    console.error("FAIL (V9-D): la console non sa dire al motore che una conversazione è finita: nessun riassunto verrebbe mai scritto"); ko = 1;
  }
  if (!ckbV8.righe || !ckbV8.sappiamo || !ckbV8.nonScrive) {
    console.error("FAIL (V8-B2): il pannello del cliente non elenca la sua knowledge base " + JSON.stringify(ckbV8)); ko = 1;
  }
  if (!degradoV9.compare || !degradoV9.spiega || !degradoV9.acceso || !degradoV9.nonSo) {
    console.error("FAIL (V9-A3): l'avviso di funzione spenta non si disegna (o compare quando è accesa) " + JSON.stringify(degradoV9)); ko = 1;
  }
  if (!degradoV9.tecnicoOwner || degradoV9.tecnicoCliente) {
    console.error("FAIL (V9-A3): la riga tecnica va a chi può farci qualcosa — mai al cliente " + JSON.stringify(degradoV9)); ko = 1;
  }
  if (!degradoV9.vuotoSpento || !degradoV9.vuotoNormale) {
    console.error("FAIL (V9-A1): lo stato vuoto finge di essere vuoto anche quando la funzione è SPENTA — è il difetto del 2/08"); ko = 1;
  }
  if (!degradoCliente) {
    console.error("FAIL (V9-A1): la pagina del cliente non mostra l'avviso della funzione spenta"); ko = 1;
  }
  if (!diagV9.elenco || !diagV9.voceVera) {
    console.error("FAIL (V9-A3): Diagnostica non elenca le funzioni spente " + JSON.stringify(diagV9)); ko = 1;
  }
  if (!vociV9) {
    console.error("FAIL (V9-A2): in Squadra non si vede chi parla ancora con la voce di Divina"); ko = 1;
  } else console.log("[voci] " + vociV9 + " agenti senza voce propria, dichiarati accanto al nome");
  if (!capV9.offerta || !capV9.chi || !capV9.bottone) {
    console.error("FAIL (V9-C): la capacità che il server suggerisce non si vede sotto la risposta " + JSON.stringify(capV9)); ko = 1;
  }
  if (!capV9.niente) {
    console.error("FAIL (V9-C): il riconoscitore lessicale è rimasto nella console — due matcher divergono, e quello sbagliato è sempre quello che vede l'utente"); ko = 1;
  }
  if (!sitoV9.bottone || !sitoV9.voci || sitoV9.cita !== sitoV9.voci || !sitoV9.url) {
    console.error("FAIL (V9-B): le voci proposte dal sito non portano tutte la pagina e la frase da cui vengono " + JSON.stringify(sitoV9)); ko = 1;
  }
  if (!sitoV9.nonSalvate || !sitoV9.approvi) {
    console.error("FAIL (V9-B3): la finestra non dichiara che le voci NON sono salvate finché non le approvi"); ko = 1;
  }
  if (!buchiV8.spiega || !buchiV8.nonFingeVuoto) {
    console.error("FAIL (V8-B3): la pagina dei buchi spenta non DICE perché è spenta " + JSON.stringify(buchiV8)); ko = 1;
  }
  if (!vox.aperto) { console.error("FAIL: il modo vocale non si è aperto"); ko = 1; }
  else if (vox.canvas && vox.px <= 200 && !vox.css) {
    console.error(`FAIL: l'orb NON disegna (canvas ${vox.w}x${vox.h}, cssW=${vox.cssW}, px=${vox.px})`); ko = 1;
  }
  if (!cicloVivo) { console.error("FAIL (G): il ciclo di disegno non gira — frame fermi (" + fA + " → " + fB + " in 3 finestre da 1,5s)"); ko = 1; }
  else console.log("[ciclo] vivo: " + fA + " → " + fB + " frame");
  if (!dopoRisposta.aperto) { console.error("FAIL (guasto B): il modo vocale si è CHIUSO durante la risposta"); ko = 1; }
  if (dopoRisposta.righe < 2) { console.error("FAIL: il trascritto non mostra domanda+risposta (righe=" + dopoRisposta.righe + ")"); ko = 1; }
  if (!chiuso) { console.error("FAIL: Escape non chiude il modo vocale"); ko = 1; }
  if (ko) process.exit(1);
  console.log(`Console VIVA: navigazione ok · modo vocale aperto · orb disegnato (${vox.css ? "fallback css" : vox.px + " px"}) · Escape chiude.`);
})().catch(e => { console.error("FAIL (eccezione della prova): " + String(e.message).split("\n")[0]); process.exit(1); });
