/* Divina — widget di chat embeddable (vanilla JS, nessuna dipendenza).
 * v4 · U1 «un motore vocale solo»: frasi, coda, barge-in, invio automatico e
 *      parziali vivono in voce.js (fratello di questo script, condiviso con la
 *      console). Misure in window.Divina.voiceStats (disponibile a modulo carico).
 * v3 · «la voce continua»: sintesi PER FRASE durante lo stream, interruzione a
 *      metà frase (barge-in), trascrizione con parziali live.
 * v2 · Shadow DOM (CSS isolati dal sito ospite) + voce (input & output) + markdown + chip-fonti.
 * Funziona su qualsiasi sito (FORMA, ATS, ...). Una bolla flottante apre il pannello.
 *
 * USO — due modalità:
 *
 * 1) PROXY (consigliato in produzione): la chiave NON sta nel browser. Il widget
 *    chiama un endpoint del tuo sito che aggiunge la chiave lato server e inoltra a Divina.
 *    <script src="https://.../embed.js"
 *            data-proxy="/api/divina"
 *            data-title="Assistente FORMA"
 *            data-accent="#0ED4E4"></script>
 *
 * 2) DIRETTA (solo pilota/demo): la chiave è nell'HTML (sola lettura, limitata allo scope).
 *    <script src="https://.../embed.js"
 *            data-api="https://divina.formahub.it" data-key="CHIAVE_TENANT"
 *            data-title="Assistente FORMA" data-accent="#0ED4E4"></script>
 *
 * ATTRIBUTI (tutti opzionali, con default):
 *   data-proxy | data-api + data-key   endpoint
 *   data-title      "Divina · Assistente"     titolo pannello
 *   data-subtitle   "Assistente AI"           sottotitolo (disclosure)
 *   data-accent     "#0ED4E4"                 colore brand
 *   data-avatar     URL immagine avatar (altrimenti iniziale del titolo)
 *   data-logo       URL logo nell'header (opzionale)
 *   data-position   "right" | "left"          angolo (default right)
 *   data-lang       "it-IT"                   lingua voce/riconoscimento
 *   data-voice      "true" | "false"          abilita microfono + lettura (default true)
 *   data-voice-auto "false" | "true"          legge in automatico ogni risposta (default false)
 *   data-autosend   "true" | "false"          a fine parlato invia da solo (default true; il
 *                                             pulsante resta e funziona comunque)
 *   data-barge      "true" | "false"          interruzione a voce mentre Divina parla (default true;
 *                                             si attiva solo se il permesso microfono è già concesso)
 *   data-greeting   testo di benvenuto personalizzato
 *
 * Oppure: window.EMBER_CONFIG = { proxy | api,key, title, accent, ... } prima dello script.
 */
(function () {
  "use strict";
  var s = document.currentScript || {};
  var d = (s.dataset || {});
  var CFG = window.EMBER_CONFIG || window.JARVIS_CONFIG || {}; // JARVIS_CONFIG: retro-compat

  var PROXY   = (CFG.proxy || d.proxy || "").replace(/\/$/, "");
  var API     = (CFG.api   || d.api   || "http://localhost:8000").replace(/\/$/, "");
  var KEY     = CFG.key    || d.key   || "CHIAVE_FORMA_INTERNO";
  var TITLE   = CFG.title  || d.title || "Divina · Assistente";
  var SUBT    = CFG.subtitle || d.subtitle || "Assistente AI";
  var ACC     = CFG.accent || d.accent || "#0ED4E4";
  var AVATAR  = CFG.avatar || d.avatar || "";
  var LOGO    = CFG.logo   || d.logo   || "";
  var POS     = (CFG.position || d.position || "right").toLowerCase() === "left" ? "left" : "right";
  var LANG    = CFG.lang   || d.lang   || "it-IT";
  var VOICE   = String(CFG.voice != null ? CFG.voice : (d.voice != null ? d.voice : "true")) !== "false";
  var VAUTO   = String(CFG.voiceAuto != null ? CFG.voiceAuto : (d.voiceAuto != null ? d.voiceAuto : "false")) === "true";
  // i18n: stringhe fisse dell'interfaccia in IT/EN (le risposte del bot sono gestite
  // dal server). La lingua UI arriva da CFG.lang / data-lang o si deriva da LANG;
  // può essere aggiornata da /config (maybeAutoConfig).
  function _uilang(x){ return (String(x||"").toLowerCase().slice(0,2) === "en") ? "en" : "it"; }
  var UILANG = _uilang(CFG.lang || d.lang || LANG || "it");
  var I18N = {
    it: { open:"Apri la chat", close:"Chiudi", speakTgl:"Attiva/disattiva lettura vocale", talk:"Parla", msg:"Messaggio", send:"Invia",
      ph:"Scrivi una domanda...", note:"Assistente AI — può commettere errori. Verifica le informazioni importanti.",
      listen:"Ascolta", copy:"Copia", copied:"Copiato", retry:"Riprova", reasonPh:"Perché? (opzionale)", reasonSend:"Invia",
      fbUp:"Risposta utile", fbDown:"Risposta da migliorare", thanksUp:"Grazie! 👍", thanksDown:"Grazie, ne terremo conto.",
      listening:"In ascolto...", dictFail:"Dettatura non riuscita, scrivi pure...",
      autosend:"Invio… tocca il microfono per annullare",
      errNet:"⚠️ Connessione non riuscita. Verifica che il servizio sia attivo.",
      errCode:function(s){ return "⚠️ Errore "+s+". Riprova tra poco."; },
      greet:function(t){ return "Ciao! Sono "+t+". Sei in conversazione con un assistente AI: rispondo solo sulle aree a cui ho accesso e cito le fonti. Come posso aiutarti?"; } },
    en: { open:"Open chat", close:"Close", speakTgl:"Toggle read-aloud", talk:"Speak", msg:"Message", send:"Send",
      ph:"Ask a question...", note:"AI assistant — may make mistakes. Verify important information.",
      listen:"Listen", copy:"Copy", copied:"Copied", retry:"Retry", reasonPh:"Why? (optional)", reasonSend:"Send",
      fbUp:"Helpful answer", fbDown:"Answer to improve", thanksUp:"Thanks! 👍", thanksDown:"Thanks, we'll take note.",
      listening:"Listening...", dictFail:"Dictation failed, just type...",
      autosend:"Sending… tap the mic to cancel",
      errNet:"⚠️ Connection failed. Check that the service is up.",
      errCode:function(s){ return "⚠️ Error "+s+". Try again shortly."; },
      greet:function(t){ return "Hi! I'm "+t+". You're chatting with an AI assistant: I only answer from the areas I can access and I cite sources. How can I help?"; } }
  };
  function TT(k){ return (I18N[UILANG] || I18N.it)[k]; }
  var GREET   = CFG.greeting || d.greeting || TT("greet")(TITLE);

  // palette (dark, brand FORMA)
  var DARK="#0e0e10", DARK2="#15151a", BUB="#1b1b22", LINE="#26262e", TXT="#f4f4f6", MUT="#9a9aa6", INK="#06262b";

  // ── Voice capability ──────────────────────────────────────────────
  // Due modalità: "browser" (gratis, Web Speech API) e "pro" (proxy server → Deepgram/
  // ElevenLabs). In PRO l'audio viene registrato e mandato a /voice/stt|tts del backend
  // (le chiavi restano sul server). Fallback automatico al browser se PRO non risponde.
  // "auto" (default) = usa la voce PRO se il server la espone (via /config), altrimenti browser.
  var VMODE = String(CFG.voiceMode || d.voiceMode || "auto").toLowerCase();
  // In modalità proxy le chiamate voce passano dallo stesso proxy (che aggiunge la
  // chiave e inoltra a /voice/* e /config); in diretta si usa l'API con X-Tenant-Key.
  var VBASE = (CFG.voiceBase || d.voiceBase || PROXY || API).replace(/\/$/, "");
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
  var synth = window.speechSynthesis || null;
  var hasMR = !!(window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  var PRO = VOICE && VMODE === "pro" && !!VBASE && hasMR;         // può diventare true dopo /config
  var canListen = VOICE && (!!SR || (hasMR && VMODE !== "browser"));
  var canSpeak  = VOICE && (!!synth || (hasMR && VMODE !== "browser"));
  var speakOn = VAUTO && canSpeak;   // lettura automatica attiva/disattiva
  var rec = null, listening = false, cfgLoaded = false;
  function voiceHeaders(extra){ var h = extra || {}; if(!PROXY) h["X-Tenant-Key"] = KEY; return h; }

  // Auto-configurazione dalla CHIAVE del tenant: white-label (titolo, sottotitolo,
  // avatar/logo, benvenuto) + voce PRO se il server la espone. Così un cliente si
  // personalizza da solo con la sua chiave, senza toccare lo snippet. L'accent resta
  // impostato all'embed (data-accent / CFG.accent) perché è cablato nel tema CSS.
  async function maybeAutoConfig(){
    if (cfgLoaded) return;
    cfgLoaded = true;
    if (VOICE) loadVoce();          // U1: il motore vocale si carica col pannello
    try{
      var r = await fetch(VBASE + "/config", { headers: voiceHeaders({}) });
      if (!r.ok) return;
      var c = await r.json();
      if (!c) return;
      if (c.title){ TITLE = c.title; var tb = panel.querySelector(".em-tt b"); if(tb) tb.textContent = c.title; }
      if (c.subtitle){ SUBT = c.subtitle; var ts = panel.querySelector(".em-tt span"); if(ts) ts.innerHTML = '<i class="em-live"></i>' + esc(c.subtitle); }
      var img = c.avatar || c.logo;
      if (img){ var av = panel.querySelector(".em-av"); if(av) av.innerHTML = '<img src="' + esc(img) + '" alt="">'; }
      if (c.greeting){ GREET = c.greeting; }
      if (c.lang){   // lingua UI dal tenant: aggiorna le stringhe fisse più visibili
        UILANG = _uilang(c.lang);
        try{ input.placeholder = TT("ph"); }catch(e){}
        var nt = panel.querySelector(".em-note"); if(nt) nt.textContent = TT("note");
        var mic2 = panel.querySelector(".em-mic"); if(mic2) mic2.setAttribute("aria-label", TT("talk"));
        var xb = panel.querySelector(".em-x"); if(xb) xb.setAttribute("aria-label", TT("close"));
        if(!c.greeting && !CFG.greeting && !d.greeting && !greeted) GREET = TT("greet")(TITLE);
      }
      if (c.voice_pro && hasMR && VOICE && VMODE !== "browser") PRO = true;
    }catch(e){}
  }

  // ── Styles (dentro lo Shadow DOM: non toccano il sito, il sito non tocca noi) ──
  var css = `
  :host{ all: initial; }
  *{ box-sizing:border-box; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Arial,sans-serif; }
  .em-btn{position:fixed;${POS}:22px;bottom:22px;width:60px;height:60px;border-radius:50%;
    background:linear-gradient(135deg,${ACC},${ACC});color:${INK};border:none;cursor:pointer;z-index:2147483000;
    box-shadow:0 10px 30px rgba(0,0,0,.38);display:grid;place-items:center;transition:transform .18s ease, box-shadow .18s}
  .em-btn:hover{transform:translateY(-2px) scale(1.05);box-shadow:0 14px 36px rgba(0,0,0,.45)}
  .em-btn svg{width:28px;height:28px}
  .em-badge{position:absolute;top:-3px;${POS === "right" ? "left" : "right"}:-3px;width:14px;height:14px;border-radius:50%;
    background:#89D41D;border:2px solid ${DARK};box-shadow:0 0 0 0 rgba(137,212,29,.6);animation:empulse 2.4s infinite}
  @keyframes empulse{0%{box-shadow:0 0 0 0 rgba(137,212,29,.55)}70%{box-shadow:0 0 0 8px rgba(137,212,29,0)}100%{box-shadow:0 0 0 0 rgba(137,212,29,0)}}

  .em-panel{position:fixed;${POS}:22px;bottom:96px;width:380px;max-width:calc(100vw - 32px);
    height:560px;max-height:calc(100vh - 130px);background:${DARK};border:1px solid ${LINE};
    border-radius:18px;z-index:2147483000;display:flex;flex-direction:column;overflow:hidden;
    box-shadow:0 24px 60px rgba(0,0,0,.55);opacity:0;transform:translateY(12px) scale(.98);
    pointer-events:none;transition:opacity .2s ease, transform .2s ease}
  .em-open{opacity:1;transform:none;pointer-events:auto}

  .em-hd{padding:14px 14px;background:
      radial-gradient(120% 140% at 0% 0%, ${ACC}2e, transparent 60%),
      linear-gradient(180deg,${DARK2},${DARK});
    border-bottom:1px solid ${LINE};display:flex;align-items:center;gap:11px}
  .em-av{width:38px;height:38px;border-radius:50%;flex:0 0 auto;display:grid;place-items:center;
    background:linear-gradient(135deg,${ACC},#89D41D);color:${INK};font-weight:800;font-size:16px;overflow:hidden}
  .em-av img{width:100%;height:100%;object-fit:cover}
  .em-tt{flex:1;min-width:0}
  .em-tt b{color:${TXT};font-size:14.5px;display:block;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .em-tt span{color:${MUT};font-size:11.5px;display:flex;align-items:center;gap:5px}
  .em-live{width:7px;height:7px;border-radius:50%;background:#89D41D;display:inline-block}
  .em-hicons{display:flex;gap:2px;align-items:center}
  .em-ic{background:none;border:none;color:${MUT};cursor:pointer;padding:7px;border-radius:9px;display:grid;place-items:center;transition:background .15s,color .15s}
  .em-ic:hover{background:#ffffff12;color:${TXT}}
  .em-ic.on{color:${ACC}}
  .em-ic svg{width:18px;height:18px;display:block}

  .em-body{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;scrollbar-width:thin}
  .em-body::-webkit-scrollbar{width:8px}.em-body::-webkit-scrollbar-thumb{background:#2c2c36;border-radius:8px}
  .em-row{display:flex;gap:8px;align-items:flex-end;max-width:100%}
  .em-row.u{justify-content:flex-end}
  .em-mav{width:24px;height:24px;border-radius:50%;flex:0 0 auto;background:linear-gradient(135deg,${ACC},#89D41D);
    display:grid;place-items:center;color:${INK};font-size:11px;font-weight:800;overflow:hidden}
  .em-mav img{width:100%;height:100%;object-fit:cover}
  .em-msg{max-width:82%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.5;word-wrap:break-word;overflow-wrap:anywhere}
  .em-u .em-msg{background:${ACC};color:${INK};border-bottom-right-radius:4px}
  .em-a .em-msg{background:${BUB};color:${TXT};border:1px solid ${LINE};border-bottom-left-radius:4px}
  .em-msg p{margin:0 0 6px}.em-msg p:last-child{margin:0}
  .em-msg a{color:${ACC};text-decoration:underline}
  .em-msg code{background:#0000003d;padding:1px 5px;border-radius:5px;font-size:12.5px;font-family:ui-monospace,Menlo,Consolas,monospace}
  .em-msg ul{margin:4px 0;padding-left:18px}.em-msg li{margin:2px 0}
  .em-cur{display:inline-block;width:7px;height:14px;background:${ACC};margin-left:1px;border-radius:1px;vertical-align:-2px;animation:emblink 1s steps(2) infinite}
  @keyframes emblink{0%,100%{opacity:1}50%{opacity:0}}
  .em-srcs{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
  .em-chip{font-size:10.5px;color:${MUT};background:#ffffff0d;border:1px solid ${LINE};border-radius:999px;padding:2px 8px;max-width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .em-spk{background:none;border:none;color:${MUT};cursor:pointer;padding:2px;margin-top:5px;display:inline-flex;align-items:center;gap:4px;font-size:11px}
  .em-spk:hover{color:${ACC}}.em-spk svg{width:13px;height:13px}

  .em-dots{display:inline-flex;gap:3px;padding:4px 2px}
  .em-dot{width:6px;height:6px;border-radius:50%;background:${MUT};animation:emb 1s infinite}
  .em-dot:nth-child(2){animation-delay:.15s}.em-dot:nth-child(3){animation-delay:.3s}
  @keyframes emb{0%,60%,100%{opacity:.25;transform:translateY(0)}30%{opacity:1;transform:translateY(-2px)}}

  .em-ft{border-top:1px solid ${LINE};padding:9px 10px 6px}
  .em-inrow{display:flex;gap:7px;align-items:center}
  .em-mic{flex:0 0 auto;width:38px;height:38px;border-radius:11px;border:1px solid ${LINE};background:${DARK2};
    color:${MUT};cursor:pointer;display:grid;place-items:center;transition:all .15s}
  .em-mic:hover{color:${ACC};border-color:${ACC}55}
  .em-mic.live{color:#fff;background:#e0561f;border-color:#e0561f;animation:emmic 1.2s infinite}
  .em-mic.em-close{color:#06262b;background:#EAB308;border-color:#EAB308;animation:none}
  @keyframes emmic{0%{box-shadow:0 0 0 0 rgba(224,86,31,.5)}70%{box-shadow:0 0 0 7px rgba(224,86,31,0)}100%{box-shadow:0 0 0 0 rgba(224,86,31,0)}}
  .em-mic svg{width:18px;height:18px}
  .em-in{flex:1;background:${DARK2};border:1px solid ${LINE};color:${TXT};border-radius:11px;padding:10px 12px;font-size:14px;outline:none;transition:border .15s}
  .em-in:focus{border-color:${ACC}}
  .em-in::placeholder{color:#6a6a76}
  .em-send{flex:0 0 auto;width:38px;height:38px;border-radius:11px;background:${ACC};color:${INK};border:none;cursor:pointer;display:grid;place-items:center;transition:opacity .15s,transform .15s}
  .em-send:hover:not(:disabled){transform:scale(1.06)}
  .em-send:disabled{opacity:.45;cursor:default}
  .em-send svg{width:18px;height:18px}
  .em-note{text-align:center;color:#6a6a76;font-size:10px;margin:6px 2px 0;line-height:1.3}

  @media (max-width:480px){
    .em-panel{${POS}:0;left:0;right:0;bottom:0;width:100vw;max-width:100vw;height:82vh;max-height:82vh;border-radius:18px 18px 0 0}
    .em-btn{${POS}:16px;bottom:16px}
  }
  @media (prefers-reduced-motion: reduce){ *{animation:none !important;transition:none !important} }
  `;

  // ── Icone (SVG inline) ──
  var IC = {
    chat:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    close:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    mic:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/></svg>',
    send:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>',
    spkOn:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a9 9 0 0 1 0 14"/></svg>',
    spkOff:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="m23 9-6 6M17 9l6 6"/></svg>'
  };

  // ── Host + Shadow DOM ──
  var host = document.createElement("div");
  host.setAttribute("id", "divina-widget");
  var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
  var style = document.createElement("style"); style.textContent = css; root.appendChild(style);

  var btn = document.createElement("button");
  btn.className = "em-btn"; btn.setAttribute("type", "button");
  btn.setAttribute("aria-label", TT("open"));
  btn.setAttribute("aria-haspopup", "dialog");
  btn.setAttribute("aria-controls", "em-panel"); btn.setAttribute("aria-expanded", "false");
  btn.innerHTML = IC.chat + '<span class="em-badge"></span>';

  var avInner = AVATAR ? '<img src="' + esc(AVATAR) + '" alt="">' : esc((TITLE.trim()[0] || "E").toUpperCase());
  var panel = document.createElement("div");
  panel.className = "em-panel"; panel.id = "em-panel";
  panel.setAttribute("role", "dialog"); panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", TITLE); panel.setAttribute("tabindex", "-1");
  panel.innerHTML =
    '<div class="em-hd">' +
      '<div class="em-av">' + avInner + '</div>' +
      '<div class="em-tt"><b>' + esc(TITLE) + '</b><span><i class="em-live"></i>' + esc(SUBT) + '</span></div>' +
      '<div class="em-hicons">' +
        (canSpeak ? '<button class="em-ic em-tog" aria-label="' + esc(TT("speakTgl")) + '">' + (speakOn ? IC.spkOn : IC.spkOff) + '</button>' : '') +
        '<button class="em-ic em-x" aria-label="' + esc(TT("close")) + '">' + IC.close + '</button>' +
      '</div>' +
    '</div>' +
    '<div class="em-body" aria-live="polite"></div>' +
    '<div class="em-ft">' +
      '<div class="em-inrow">' +
        (canListen ? '<button class="em-mic" aria-label="' + esc(TT("talk")) + '">' + IC.mic + '</button>' : '') +
        '<input class="em-in" placeholder="' + esc(TT("ph")) + '" aria-label="' + esc(TT("msg")) + '">' +
        '<button class="em-send" aria-label="' + esc(TT("send")) + '">' + IC.send + '</button>' +
      '</div>' +
      '<div class="em-note">' + esc(TT("note")) + '</div>' +
    '</div>';

  root.appendChild(btn); root.appendChild(panel);
  (document.body || document.documentElement).appendChild(host);

  var body  = panel.querySelector(".em-body");
  var input = panel.querySelector(".em-in");
  var send  = panel.querySelector(".em-send");
  var mic   = panel.querySelector(".em-mic");
  var tog   = panel.querySelector(".em-tog");
  var greeted = false;
  var hist = [];   // memoria conversazionale: [{role, content}] per i follow-up

  // ── Helpers ──
  function esc(t){ var e=document.createElement("div"); e.textContent = t==null?"":t; return e.innerHTML; }

  // markdown-lite SICURO: prima escape totale, poi riabilita solo un set ristretto.
  function mdLite(t){
    // O4: marcatori di provenienza (conversazione libera owner) resi VISIBILI
    // anche qui: mai conoscenza generale spacciata per dato del cervello.
    t = String(t == null ? "" : t)
        .replace(/⟦fuori⟧/g, "\n〔fuori dal cervello · non verificato〕 ")
        .replace(/⟦\/fuori⟧/g, "");
    var h = esc(t);
    h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
    h = h.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    h = h.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>');
    h = h.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    // liste puntate (-, •) e numerate (1. 2. …)
    var lines = h.split("\n"), out = [], listType = null;
    for (var i=0;i<lines.length;i++){
      var mu = lines[i].match(/^\s*[-•]\s+(.*)$/);
      var mo = lines[i].match(/^\s*\d+\.\s+(.*)$/);
      if (mu || mo){
        var lt = mu ? "ul" : "ol";
        if (listType !== lt){ if(listType) out.push("</"+listType+">"); out.push("<"+lt+">"); listType = lt; }
        out.push("<li>"+(mu ? mu[1] : mo[1])+"</li>");
      } else { if(listType){ out.push("</"+listType+">"); listType = null; } out.push(lines[i]); }
    }
    if(listType) out.push("</"+listType+">");
    h = out.join("\n").replace(/\n{2,}/g,"</p><p>").replace(/\n/g,"<br>");
    return "<p>"+h+"</p>";
  }

  var mavInner = AVATAR ? '<img src="' + esc(AVATAR) + '" alt="">' : esc((TITLE.trim()[0] || "E").toUpperCase());
  function addMsg(role, text){
    var row = document.createElement("div");
    row.className = "em-row " + (role === "u" ? "u em-u" : "em-a");
    var inner = "";
    if (role !== "u") inner += '<div class="em-mav">' + mavInner + '</div>';
    inner += '<div class="em-msg"></div>';
    row.innerHTML = inner;
    var msg = row.querySelector(".em-msg");
    if (text) msg.textContent = text;
    body.appendChild(row); body.scrollTop = body.scrollHeight;
    return msg;
  }
  function sendFeedback(up, q, answer, sources, reason){
    // Best-effort: un fallimento non deve mai disturbare la chat.
    try{
      var fbUrl = PROXY ? (String(PROXY).replace(/\/$/, "") + "/feedback") : (API + "/feedback");
      var headers = {"Content-Type":"application/json"};
      if (!PROXY) headers["X-Tenant-Key"] = KEY;
      fetch(fbUrl, { method:"POST", headers:headers, keepalive:true,
        body: JSON.stringify({ vote: up ? "up" : "down", question: q || "",
          answer: String(answer||"").slice(0,500), sources: sources || [], reason: reason || "" }) }).catch(function(){});
    }catch(e){}
  }
  function finalizeMsg(msg, textAcc, sources, q){
    msg.innerHTML = mdLite(textAcc);
    if (sources && sources.length){
      var wrap = document.createElement("div"); wrap.className = "em-srcs";
      sources.forEach(function(sname){
        // fonti come oggetti {slug,title} (fix B1); stringhe legacy tollerate
        var label = (sname && typeof sname === "object")
          ? (sname.title || sname.slug || sname.url || "nota") : String(sname);
        var c = document.createElement("span"); c.className = "em-chip"; c.textContent = label; c.title = label;
        wrap.appendChild(c);
      });
      msg.appendChild(wrap);
    }
    if (canSpeak){
      var sb = document.createElement("button");
      sb.className = "em-spk"; sb.innerHTML = IC.spkOn + "<span>" + esc(TT("listen")) + "</span>";
      sb.addEventListener("click", function(){ speak(textAcc); });
      msg.appendChild(sb);
    }
    if (textAcc && textAcc.charAt(0) !== "⚠"){   // Copia (non su errori ⚠️)
      var cb = document.createElement("button");
      cb.className = "em-spk"; cb.type = "button"; cb.style.marginLeft = canSpeak ? "10px" : "0";
      cb.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span>' + esc(TT("copy")) + '</span>';
      cb.addEventListener("click", function(){
        try{ if(navigator.clipboard){ navigator.clipboard.writeText(textAcc).then(function(){
          var s = cb.querySelector("span"); s.textContent = TT("copied"); setTimeout(function(){ s.textContent = TT("copy"); }, 1500);
        }).catch(function(){}); } }catch(e){}
      });
      msg.appendChild(cb);
    }
    if (q){   // solo su risposte reali (non su errori/saluto): 👍/👎
      var fb = document.createElement("div");
      fb.style.cssText = "display:flex;gap:6px;margin-top:8px;align-items:center;font-size:12px";
      function mkFb(sym, up){
        var b = document.createElement("button");
        b.type = "button"; b.textContent = sym;
        b.setAttribute("aria-label", up ? TT("fbUp") : TT("fbDown"));
        b.style.cssText = "cursor:pointer;border:1px solid rgba(127,127,127,.35);background:transparent;border-radius:8px;padding:1px 7px;font-size:13px;line-height:1.3;opacity:.65";
        b.addEventListener("click", function(){
          if (up){ sendFeedback(true, q, textAcc, sources, ""); fb.textContent = TT("thanksUp"); fb.style.opacity = ".6"; return; }
          fb.innerHTML = "";   // 👎: chiedi un motivo opzionale
          var inp = document.createElement("input");
          inp.type = "text"; inp.placeholder = TT("reasonPh");
          inp.style.cssText = "flex:1;min-width:0;background:transparent;border:1px solid rgba(127,127,127,.35);border-radius:8px;padding:3px 8px;color:inherit;font:inherit;font-size:12px";
          var ok = document.createElement("button");
          ok.type = "button"; ok.textContent = TT("reasonSend");
          ok.style.cssText = "cursor:pointer;border:1px solid rgba(127,127,127,.35);background:transparent;border-radius:8px;padding:2px 8px;font-size:12px";
          function submit(){ sendFeedback(false, q, textAcc, sources, inp.value); fb.textContent = TT("thanksDown"); fb.style.opacity = ".6"; }
          ok.addEventListener("click", submit);
          inp.addEventListener("keydown", function(e){ if(e.key === "Enter"){ e.preventDefault(); submit(); } });
          fb.appendChild(inp); fb.appendChild(ok); try{ inp.focus(); }catch(e){}
        });
        return b;
      }
      fb.appendChild(mkFb("👍", true)); fb.appendChild(mkFb("👎", false));
      msg.appendChild(fb);
    }
    // PR1: se la coda per frasi ha già preso in carico la lettura (anche se poi
    // interrotta dal barge-in), niente doppione a fine risposta
    if (speakOn && !liveSpoke) speak(textAcc);
    body.scrollTop = body.scrollHeight;
  }
  function typing(){
    var row = document.createElement("div"); row.className = "em-row em-a";
    row.innerHTML = '<div class="em-mav">' + mavInner + '</div><div class="em-msg"><span class="em-dots"><span class="em-dot"></span><span class="em-dot"></span><span class="em-dot"></span></span></div>';
    body.appendChild(row); body.scrollTop = body.scrollHeight; return row;
  }

  // ── U1 · MOTORE VOCALE UNICO ──────────────────────────────────────
  // Frasi, coda ordinata, barge-in, invio automatico, parziali e ampiezza
  // vivono in voce.js (caricato come fratello di questo script) e sono GLI
  // STESSI della console: una funzione si aggiunge o si toglie in un posto
  // solo. Qui restano interfaccia e cablaggio. Se voce.js non arriva:
  // voce del browser essenziale, mai un widget rotto.
  var BARGE = String(CFG.barge != null ? CFG.barge : (d.barge != null ? d.barge : "true")) !== "false";
  var AUTOSEND = String(CFG.autosend != null ? CFG.autosend : (d.autosend != null ? d.autosend : "true")) !== "false";
  var vce = null, vceLoading = false, liveSpoke = false;
  function loadVoce(cb){
    if (window.DivinaVoce || vceLoading){ if (cb) cb(); return; }
    vceLoading = true;
    var src2 = "";
    try{ src2 = String(s.src || "").replace(/embed(\.min)?\.js([?#].*)?$/, "voce.js"); }catch(e){}
    if (!src2 || src2 === String(s.src || "")){ if (cb) cb(); return; }
    var el = document.createElement("script");
    el.src = src2; el.async = true;
    el.onload = el.onerror = function(){ if (cb) cb(); };
    document.head.appendChild(el);
  }
  function engine(){
    if (vce) return vce;
    if (!window.DivinaVoce) return null;
    vce = window.DivinaVoce({
      base: function(){ return VBASE; },
      headers: function(){ return voiceHeaders({}); },
      pro: function(){ return PRO; },
      lang: LANG, autosend: AUTOSEND, barge: BARGE,
      onState: function(st){
        if (st === "ascolta"){ listening = true; if (mic) mic.classList.add("live"); input.placeholder = TT("listening"); }
        else if (listening){ listening = false; if (mic){ mic.classList.remove("live"); mic.classList.remove("em-close"); } input.placeholder = TT("ph"); }
      },
      onPartial: function(t){ input.value = t; },
      onFinal: function(t){ if (t){ input.value = ""; ask(t); } else input.placeholder = TT("dictFail"); },
      onNotify: function(k){
        if (k === "interrupt"){ if (askCtl) try{ askCtl.abort(); }catch(e){} }
        else if (k === "autosend-window"){ input.placeholder = TT("autosend"); if (mic) mic.classList.add("em-close"); }
        else if (k === "autosend-resume"){ input.placeholder = TT("listening"); if (mic) mic.classList.remove("em-close"); }
      }
    });
    try{ window.Divina.voiceStats = vce.stats(); }catch(e){}
    return vce;
  }

  // ── Voce: sintesi — API storiche sopra il motore unico ──
  function stopAudio(){
    if (vce) vce.stopSpeak();
    if (synth) try{ synth.cancel(); }catch(e){}
  }
  function speak(t){
    if (!canSpeak || !t) return;
    var e2 = engine();
    if (e2){ liveSpoke = true; e2.speak(String(t)); return; }
    speakBrowserBasic(t);
  }
  function speakBrowserBasic(t){   // solo se il modulo non è arrivato
    if (!synth) return;
    try{
      synth.cancel();
      var u = new SpeechSynthesisUtterance(String(t).replace(/[*`_#>[\]]/g, ""));
      u.lang = LANG; u.rate = 1.02; u.pitch = 1;
      var vs = synth.getVoices() || [];
      var v = vs.filter(function(x){ return x.lang && x.lang.toLowerCase().indexOf(LANG.slice(0,2).toLowerCase()) === 0; })[0];
      if (v) u.voice = v;
      synth.speak(u);
    }catch(e){}
  }

  // ── SSE reader (token per token) ──
  async function readSSE(r, msg, q){
    var reader = r.body.getReader(), dec = new TextDecoder();
    var buf="", acc="", sources=null, idx, interrotta=false;
    var cursor = document.createElement("span"); cursor.className = "em-cur"; msg.appendChild(cursor);
    try{
      for(;;){
        var chunk = await reader.read(); if (chunk.done) break;
        buf += dec.decode(chunk.value, {stream:true});
        while((idx = buf.indexOf("\n\n")) !== -1){
          var block = buf.slice(0, idx); buf = buf.slice(idx + 2);
          var event=null, data="";
          block.split("\n").forEach(function(l){
            if (l.indexOf("event:") === 0) event = l.slice(6).trim();
            else if (l.indexOf("data:") === 0) data += l.slice(5).trim();
          });
          if (!data) continue;
          var obj; try { obj = JSON.parse(data); } catch(e){ continue; }
          if (event === "sources") sources = obj.sources;
          else if (event === "error"){ acc += (acc?"\n":"") + "⚠️ " + (obj.message || "Errore."); }
          else if (event === "done"){ /* fine */ }
          else if (obj.delta){ acc += obj.delta; if (speakOn && vce) vce.speakFeed(obj.delta); }   // la voce parte alla prima frase
          // aggiorna testo mantenendo il cursore in coda (veloce, niente markdown durante lo stream)
          cursor.remove(); msg.textContent = acc; msg.appendChild(cursor);
          body.scrollTop = body.scrollHeight;
        }
      }
    }catch(e){
      // PR2: il barge-in abortisce la generazione → non è un errore, è una conversazione
      if (!(e && e.name === "AbortError")) throw e;
      interrotta = true;
    }
    cursor.remove();
    if (interrotta){ acc = acc ? acc + " —" : "—"; }
    else if (speakOn && vce) vce.speakFlush();     // flush: anche l'ultima frase senza punto si sente
    if (!acc) acc = "(nessuna risposta)";
    finalizeMsg(msg, acc, sources, q);
    hist.push({role:"assistant", content:acc});   // memoria per i follow-up
  }

  function _addRetry(msg, text){   // pulsante "Riprova" sui messaggi di errore
    var rb = document.createElement("button");
    rb.className = "em-spk"; rb.type = "button"; rb.style.marginTop = "6px";
    rb.innerHTML = "↻ <span>" + esc(TT("retry")) + "</span>";
    rb.addEventListener("click", function(){
      var row = msg.parentNode; if (row && row.parentNode) row.parentNode.removeChild(row);
      ask(text);
    });
    msg.appendChild(rb);
  }
  var askCtl = null;   // PR2: abort della generazione in corso al barge-in
  async function ask(text){
    var q = (text != null ? text : input.value).trim(); if(!q) return;
    input.value = ""; addMsg("u", q); send.disabled = true;
    var sendHist = hist.slice(-6);          // turni precedenti (non include la domanda attuale)
    hist.push({role:"user", content:q});
    var t = typing();
    // PR1: t0 = invio. La misura che conta è da QUI alla prima sillaba.
    stopAudio();
    liveSpoke = false;                       // nuova domanda, nuova lettura (o nessuna)
    if (speakOn && canSpeak && engine()){ liveSpoke = true; vce.speakStart(performance.now()); }
    askCtl = window.AbortController ? new AbortController() : null;
    try{
      var url = PROXY || (API + "/chat");
      var headers = {"Content-Type":"application/json"};
      if (!PROXY) headers["X-Tenant-Key"] = KEY;
      var r = await fetch(url, { method:"POST", headers: headers,
        body: JSON.stringify({message:q, stream:true, history:sendHist}),
        signal: askCtl ? askCtl.signal : undefined });
      if(!r.ok){ t.remove(); var em=addMsg("a",""); finalizeMsg(em, TT("errCode")(r.status), null); _addRetry(em, q); }
      else if (((r.headers.get("content-type")||"").indexOf("text/event-stream") !== -1) && r.body && window.TextDecoder){
        t.remove(); await readSSE(r, addMsg("a",""), q);
      } else {
        var data = await r.json(); t.remove();
        var ans = data.answer || "(nessuna risposta)";
        if (speakOn && canSpeak && engine()){ liveSpoke = true; vce.speak(ans); }   // niente stream: stessa coda
        finalizeMsg(addMsg("a",""), ans, data.sources, q);
        hist.push({role:"assistant", content:ans});
      }
    }catch(e){
      t.remove();
      if (!(e && e.name === "AbortError")){ var eem=addMsg("a",""); finalizeMsg(eem, TT("errNet"), null); _addRetry(eem, q); }
    }
    askCtl = null;
    if (hist.length > 20) hist = hist.slice(-20);
    send.disabled = false; input.focus();
  }

  // ── Voce: riconoscimento — il modulo fa tutto (parziali, invio a fine
  // parlato, annullo); qui solo il pulsante e il fallback senza modulo. ──
  function toggleListen(){
    var e2 = engine();
    if (e2){
      if (e2.listening()){
        if (e2.inClosing()){ e2.cancelListen(); return; }   // durante «Invio…» il tocco ANNULLA
        e2.stopListen(); return;                            // stop manuale → invia (come sempre)
      }
      stopAudio(); e2.listen();
      return;
    }
    loadVoce(function(){ if (window.DivinaVoce) toggleListen(); else browserListenBasic(); });
  }
  function browserListenBasic(){   // solo se il modulo non è arrivato
    if (!SR) return;
    if (rec){ try{ rec.stop(); }catch(e){} return; }
    rec = new SR(); rec.lang = LANG; rec.interimResults = true; rec.continuous = false;
    var finalTxt = "";
    rec.onstart = function(){ listening = true; if (mic) mic.classList.add("live"); input.placeholder = TT("listening"); };
    rec.onerror = function(){};
    rec.onend = function(){
      var t = (finalTxt || input.value).trim(); finalTxt = ""; rec = null;
      listening = false; if (mic) mic.classList.remove("live"); input.placeholder = TT("ph");
      if (t) ask(t);
    };
    rec.onresult = function(ev){
      var interim = "";
      for (var i = ev.resultIndex; i < ev.results.length; i++){
        var tr = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) finalTxt += tr; else interim += tr;
      }
      input.value = (finalTxt + interim).trim();
    };
    try{ stopAudio(); input.value = ""; rec.start(); }catch(e){}
  }

  // ── Open/close ──
  async function toggle(open){
    panel.classList.toggle("em-open", open);
    btn.style.display = open ? "none" : "grid";
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open){
      await maybeAutoConfig();   // applica il branding del tenant prima del benvenuto
      input.focus();
      if(!greeted){ greeted = true; finalizeMsg(addMsg("a",""), GREET, null); }
    } else { stopAudio(); try{ btn.focus(); }catch(e){} }   // torna il focus al lanciatore
  }

  // Accessibilità da tastiera dentro il pannello: Esc chiude, Tab resta nel dialog.
  panel.addEventListener("keydown", function(e){
    if (e.key === "Escape"){ e.preventDefault(); toggle(false); return; }
    if (e.key !== "Tab") return;
    var f = panel.querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])');
    var vis = []; for (var i=0;i<f.length;i++){ if (f[i].offsetParent !== null) vis.push(f[i]); }
    if (!vis.length) return;
    var first = vis[0], last = vis[vis.length-1];
    var ae = root.activeElement || document.activeElement;   // Shadow DOM: usa lo shadow root
    if (e.shiftKey && ae === first){ e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && ae === last){ e.preventDefault(); first.focus(); }
  });

  // ── Events ──
  btn.addEventListener("click", function(){ toggle(true); });
  panel.querySelector(".em-x").addEventListener("click", function(){ toggle(false); });
  send.addEventListener("click", function(){ ask(); });
  input.addEventListener("keydown", function(e){ if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); ask(); } });
  if (mic) mic.addEventListener("click", toggleListen);
  if (tog) tog.addEventListener("click", function(){
    speakOn = !speakOn; tog.classList.toggle("on", speakOn);
    tog.innerHTML = speakOn ? IC.spkOn : IC.spkOff;
    if (!speakOn) stopAudio();
  });
  // pre-carica le voci TTS (alcuni browser le popolano in modo asincrono)
  if (canSpeak && synth.onvoiceschanged !== undefined){ synth.onvoiceschanged = function(){}; }

  // API pubblica minima (+ voiceStats: le misure della voce continua — prima
  // sillaba in ms, interruzioni, numeri del VAD — per il collaudo sul campo)
  window.Divina = window.Divina || { open:function(){toggle(true);}, close:function(){toggle(false);}, ask:function(t){toggle(true);ask(t);}, voiceStats:null };
})();
