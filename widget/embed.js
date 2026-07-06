/* Ember — widget di chat embeddable (vanilla JS, nessuna dipendenza).
 * v2 · Shadow DOM (CSS isolati dal sito ospite) + voce (input & output) + markdown + chip-fonti.
 * Funziona su qualsiasi sito (FORMA, ATS, ...). Una bolla flottante apre il pannello.
 *
 * USO — due modalità:
 *
 * 1) PROXY (consigliato in produzione): la chiave NON sta nel browser. Il widget
 *    chiama un endpoint del tuo sito che aggiunge la chiave lato server e inoltra a Ember.
 *    <script src="https://.../embed.js"
 *            data-proxy="/api/ember"
 *            data-title="Assistente FORMA"
 *            data-accent="#0ED4E4"></script>
 *
 * 2) DIRETTA (solo pilota/demo): la chiave è nell'HTML (sola lettura, limitata allo scope).
 *    <script src="https://.../embed.js"
 *            data-api="https://ember.formahub.it" data-key="CHIAVE_TENANT"
 *            data-title="Assistente FORMA" data-accent="#0ED4E4"></script>
 *
 * ATTRIBUTI (tutti opzionali, con default):
 *   data-proxy | data-api + data-key   endpoint
 *   data-title      "Ember · Assistente"     titolo pannello
 *   data-subtitle   "Assistente AI"           sottotitolo (disclosure)
 *   data-accent     "#0ED4E4"                 colore brand
 *   data-avatar     URL immagine avatar (altrimenti iniziale del titolo)
 *   data-logo       URL logo nell'header (opzionale)
 *   data-position   "right" | "left"          angolo (default right)
 *   data-lang       "it-IT"                   lingua voce/riconoscimento
 *   data-voice      "true" | "false"          abilita microfono + lettura (default true)
 *   data-voice-auto "false" | "true"          legge in automatico ogni risposta (default false)
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
  var TITLE   = CFG.title  || d.title || "Ember · Assistente";
  var SUBT    = CFG.subtitle || d.subtitle || "Assistente AI";
  var ACC     = CFG.accent || d.accent || "#0ED4E4";
  var AVATAR  = CFG.avatar || d.avatar || "";
  var LOGO    = CFG.logo   || d.logo   || "";
  var POS     = (CFG.position || d.position || "right").toLowerCase() === "left" ? "left" : "right";
  var LANG    = CFG.lang   || d.lang   || "it-IT";
  var VOICE   = String(CFG.voice != null ? CFG.voice : (d.voice != null ? d.voice : "true")) !== "false";
  var VAUTO   = String(CFG.voiceAuto != null ? CFG.voiceAuto : (d.voiceAuto != null ? d.voiceAuto : "false")) === "true";
  var GREET   = CFG.greeting || d.greeting ||
    ("Ciao! Sono " + TITLE + ". Sei in conversazione con un assistente AI: rispondo solo sulle aree a cui ho accesso e cito le fonti. Come posso aiutarti?");

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
  var rec = null, listening = false, mr = null, curAudio = null, cfgLoaded = false;
  function voiceHeaders(extra){ var h = extra || {}; if(!PROXY) h["X-Tenant-Key"] = KEY; return h; }

  // Auto-configurazione dalla CHIAVE del tenant: white-label (titolo, sottotitolo,
  // avatar/logo, benvenuto) + voce PRO se il server la espone. Così un cliente si
  // personalizza da solo con la sua chiave, senza toccare lo snippet. L'accent resta
  // impostato all'embed (data-accent / CFG.accent) perché è cablato nel tema CSS.
  async function maybeAutoConfig(){
    if (cfgLoaded) return;
    cfgLoaded = true;
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
  host.setAttribute("id", "ember-widget");
  var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
  var style = document.createElement("style"); style.textContent = css; root.appendChild(style);

  var btn = document.createElement("button");
  btn.className = "em-btn"; btn.setAttribute("type", "button");
  btn.setAttribute("aria-label", "Apri la chat");
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
        (canSpeak ? '<button class="em-ic em-tog" aria-label="Attiva/disattiva lettura vocale">' + (speakOn ? IC.spkOn : IC.spkOff) + '</button>' : '') +
        '<button class="em-ic em-x" aria-label="Chiudi">' + IC.close + '</button>' +
      '</div>' +
    '</div>' +
    '<div class="em-body" aria-live="polite"></div>' +
    '<div class="em-ft">' +
      '<div class="em-inrow">' +
        (canListen ? '<button class="em-mic" aria-label="Parla">' + IC.mic + '</button>' : '') +
        '<input class="em-in" placeholder="Scrivi una domanda..." aria-label="Messaggio">' +
        '<button class="em-send" aria-label="Invia">' + IC.send + '</button>' +
      '</div>' +
      '<div class="em-note">Assistente AI — può commettere errori. Verifica le informazioni importanti.</div>' +
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
    var h = esc(t);
    h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
    h = h.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    h = h.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>');
    h = h.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    // liste puntate
    var lines = h.split("\n"), out = [], inUl = false;
    for (var i=0;i<lines.length;i++){
      var m = lines[i].match(/^\s*[-•]\s+(.*)$/);
      if (m){ if(!inUl){out.push("<ul>");inUl=true;} out.push("<li>"+m[1]+"</li>"); }
      else { if(inUl){out.push("</ul>");inUl=false;} out.push(lines[i]); }
    }
    if(inUl) out.push("</ul>");
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
  function sendFeedback(up, q, answer, sources){
    // Best-effort: un fallimento non deve mai disturbare la chat.
    try{
      var fbUrl = PROXY ? (String(PROXY).replace(/\/$/, "") + "/feedback") : (API + "/feedback");
      var headers = {"Content-Type":"application/json"};
      if (!PROXY) headers["X-Tenant-Key"] = KEY;
      fetch(fbUrl, { method:"POST", headers:headers, keepalive:true,
        body: JSON.stringify({ vote: up ? "up" : "down", question: q || "",
          answer: String(answer||"").slice(0,500), sources: sources || [] }) }).catch(function(){});
    }catch(e){}
  }
  function finalizeMsg(msg, textAcc, sources, q){
    msg.innerHTML = mdLite(textAcc);
    if (sources && sources.length){
      var wrap = document.createElement("div"); wrap.className = "em-srcs";
      sources.forEach(function(sname){
        var c = document.createElement("span"); c.className = "em-chip"; c.textContent = sname; c.title = sname;
        wrap.appendChild(c);
      });
      msg.appendChild(wrap);
    }
    if (canSpeak){
      var sb = document.createElement("button");
      sb.className = "em-spk"; sb.innerHTML = IC.spkOn + "<span>Ascolta</span>";
      sb.addEventListener("click", function(){ speak(textAcc); });
      msg.appendChild(sb);
    }
    if (q){   // solo su risposte reali (non su errori/saluto): 👍/👎
      var fb = document.createElement("div");
      fb.style.cssText = "display:flex;gap:6px;margin-top:8px;align-items:center;font-size:12px";
      function mkFb(sym, up){
        var b = document.createElement("button");
        b.type = "button"; b.textContent = sym;
        b.setAttribute("aria-label", up ? "Risposta utile" : "Risposta da migliorare");
        b.style.cssText = "cursor:pointer;border:1px solid rgba(127,127,127,.35);background:transparent;border-radius:8px;padding:1px 7px;font-size:13px;line-height:1.3;opacity:.65";
        b.addEventListener("click", function(){
          sendFeedback(up, q, textAcc, sources);
          fb.textContent = up ? "Grazie! 👍" : "Grazie, ne terremo conto.";
          fb.style.opacity = ".6";
        });
        return b;
      }
      fb.appendChild(mkFb("👍", true)); fb.appendChild(mkFb("👎", false));
      msg.appendChild(fb);
    }
    if (speakOn) speak(textAcc);
    body.scrollTop = body.scrollHeight;
  }
  function typing(){
    var row = document.createElement("div"); row.className = "em-row em-a";
    row.innerHTML = '<div class="em-mav">' + mavInner + '</div><div class="em-msg"><span class="em-dots"><span class="em-dot"></span><span class="em-dot"></span><span class="em-dot"></span></span></div>';
    body.appendChild(row); body.scrollTop = body.scrollHeight; return row;
  }

  // ── Voce: sintesi (TTS) — PRO via proxy, fallback browser ──
  function stopAudio(){ try{ if(curAudio){ curAudio.pause(); curAudio=null; } }catch(e){} if(synth) try{synth.cancel();}catch(e){} }
  function speak(t){
    if (!canSpeak || !t) return;
    if (PRO){ ttsPro(t).catch(function(){ speakBrowser(t); }); return; }
    speakBrowser(t);
  }
  function speakBrowser(t){
    if (!synth) return;
    try{
      synth.cancel();
      var u = new SpeechSynthesisUtterance(String(t).replace(/[*`_#>[\]]/g,""));
      u.lang = LANG; u.rate = 1.02; u.pitch = 1;
      var vs = synth.getVoices() || [];
      var v = vs.filter(function(x){ return x.lang && x.lang.toLowerCase().indexOf(LANG.slice(0,2).toLowerCase())===0; })[0];
      if (v) u.voice = v;
      synth.speak(u);
    }catch(e){}
  }
  async function ttsPro(t){
    stopAudio();
    var r = await fetch(VBASE + "/voice/tts", {
      method:"POST", headers: voiceHeaders({"Content-Type":"application/json"}),
      body: JSON.stringify({ text: String(t).replace(/[*`_#>[\]]/g,"").slice(0,2000) })
    });
    if (!r.ok) throw new Error("tts " + r.status);
    var blob = await r.blob();
    curAudio = new Audio(URL.createObjectURL(blob));
    await curAudio.play();
  }

  // ── SSE reader (token per token) ──
  async function readSSE(r, msg, q){
    var reader = r.body.getReader(), dec = new TextDecoder();
    var buf="", acc="", sources=null, idx;
    var cursor = document.createElement("span"); cursor.className = "em-cur"; msg.appendChild(cursor);
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
        else if (obj.delta){ acc += obj.delta; }
        // aggiorna testo mantenendo il cursore in coda (veloce, niente markdown durante lo stream)
        cursor.remove(); msg.textContent = acc; msg.appendChild(cursor);
        body.scrollTop = body.scrollHeight;
      }
    }
    cursor.remove();
    if (!acc) acc = "(nessuna risposta)";
    finalizeMsg(msg, acc, sources, q);
    hist.push({role:"assistant", content:acc});   // memoria per i follow-up
  }

  async function ask(text){
    var q = (text != null ? text : input.value).trim(); if(!q) return;
    input.value = ""; addMsg("u", q); send.disabled = true;
    var sendHist = hist.slice(-6);          // turni precedenti (non include la domanda attuale)
    hist.push({role:"user", content:q});
    var t = typing();
    try{
      var url = PROXY || (API + "/chat");
      var headers = {"Content-Type":"application/json"};
      if (!PROXY) headers["X-Tenant-Key"] = KEY;
      var r = await fetch(url, { method:"POST", headers: headers, body: JSON.stringify({message:q, stream:true, history:sendHist}) });
      if(!r.ok){ t.remove(); finalizeMsg(addMsg("a",""), "⚠️ Errore "+r.status+". Riprova tra poco.", null); }
      else if (((r.headers.get("content-type")||"").indexOf("text/event-stream") !== -1) && r.body && window.TextDecoder){
        t.remove(); await readSSE(r, addMsg("a",""), q);
      } else {
        var data = await r.json(); t.remove();
        var ans = data.answer || "(nessuna risposta)";
        finalizeMsg(addMsg("a",""), ans, data.sources, q);
        hist.push({role:"assistant", content:ans});
      }
    }catch(e){ t.remove(); finalizeMsg(addMsg("a",""), "⚠️ Connessione non riuscita. Verifica che il servizio sia attivo.", null); }
    if (hist.length > 20) hist = hist.slice(-20);
    send.disabled = false; input.focus();
  }

  // ── Voce: riconoscimento (STT) ──
  function setupRec(){
    if (!canListen) return;
    rec = new SR(); rec.lang = LANG; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
    var finalTxt = "";
    rec.onstart = function(){ listening = true; mic.classList.add("live"); input.placeholder = "In ascolto..."; };
    rec.onerror = function(){ stopListen(); };
    rec.onend = function(){
      var t = (finalTxt || input.value).trim(); finalTxt = "";
      stopListen();
      if (t){ ask(t); }            // hands-free: invia a fine dettatura
    };
    rec.onresult = function(ev){
      var interim = "";
      for (var i = ev.resultIndex; i < ev.results.length; i++){
        var tr = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) finalTxt += tr; else interim += tr;
      }
      input.value = (finalTxt + interim).trim();
    };
  }
  function stopListen(){ listening = false; if(mic) mic.classList.remove("live"); input.placeholder = "Scrivi una domanda..."; }

  // STT PRO: registra col microfono e manda l'audio a /voice/stt (chiavi lato server).
  async function proListenStart(){
    var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mr = new MediaRecorder(stream); var chunks = [];
    mr.ondataavailable = function(e){ if (e.data && e.data.size) chunks.push(e.data); };
    mr.onstop = async function(){
      try{ stream.getTracks().forEach(function(t){ t.stop(); }); }catch(e){}
      stopListen();
      try{
        var blob = new Blob(chunks, { type: mr.mimeType || "audio/webm" });
        var fd = new FormData(); fd.append("file", blob, "audio.webm");
        var r = await fetch(VBASE + "/voice/stt", { method:"POST", headers: voiceHeaders({}), body: fd });
        if (!r.ok) throw new Error("stt " + r.status);
        var j = await r.json(); if (j && j.text) ask(j.text);
      }catch(e){ input.placeholder = "Dettatura non riuscita, scrivi pure..."; }
    };
    listening = true; mic.classList.add("live"); input.placeholder = "In ascolto..."; stopAudio(); mr.start();
  }

  function toggleListen(){
    if (PRO){
      if (listening){ try{ mr && mr.stop(); }catch(e){} return; }
      proListenStart().catch(function(){ if (SR) browserListen(); });
      return;
    }
    browserListen();
  }
  function browserListen(){
    if (!SR) return;
    if (!rec) setupRec();
    if (listening){ try{ rec.stop(); }catch(e){} return; }
    try{ stopAudio(); input.value=""; rec.start(); }catch(e){}
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

  // API pubblica minima
  window.Ember = window.Ember || { open:function(){toggle(true);}, close:function(){toggle(false);}, ask:function(t){toggle(true);ask(t);} };
})();
