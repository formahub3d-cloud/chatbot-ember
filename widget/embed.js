/* Ember — widget di chat embeddable (vanilla JS, nessuna dipendenza).
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
 *    (vedi cartella widget/proxy: route Next.js o Cloudflare Worker pronti)
 *
 * 2) DIRETTA (solo pilota/demo): la chiave è nell'HTML. Accettabile perché di SOLA
 *    LETTURA e limitata allo scope del tenant, ma esposta a chi guarda il sorgente.
 *    <script src="https://.../embed.js"
 *            data-api="https://ember.tuodominio.it"
 *            data-key="CHIAVE_TENANT"
 *            data-title="Assistente FORMA" data-accent="#0ED4E4"></script>
 *
 * Oppure: window.EMBER_CONFIG = { proxy } | { api, key }, title, accent prima dello script.
 */
(function () {
  "use strict";
  var s = document.currentScript || {};
  var d = (s.dataset || {});
  var CFG = window.EMBER_CONFIG || window.JARVIS_CONFIG || {}; // JARVIS_CONFIG: retro-compat
  var PROXY = (CFG.proxy || d.proxy || "").replace(/\/$/, "");
  var API   = (CFG.api   || d.api   || "http://localhost:8000").replace(/\/$/, "");
  var KEY   = CFG.key    || d.key   || "CHIAVE_FORMA_INTERNO";
  var TITLE = CFG.title  || d.title || "Ember · Assistente";
  var ACC   = CFG.accent || d.accent || "#0ED4E4";
  var DARK  = "#0e0e10", LINE = "#26262e", TXT = "#f4f4f6", MUT = "#9a9aa6";

  var css = `
  .jv-btn{position:fixed;right:22px;bottom:22px;width:58px;height:58px;border-radius:50%;
    background:${ACC};color:#06262b;border:none;cursor:pointer;z-index:2147483000;
    box-shadow:0 8px 28px rgba(0,0,0,.35);font-size:26px;display:grid;place-items:center;transition:transform .15s}
  .jv-btn:hover{transform:scale(1.06)}
  .jv-panel{position:fixed;right:22px;bottom:92px;width:360px;max-width:calc(100vw - 32px);
    height:520px;max-height:calc(100vh - 130px);background:${DARK};border:1px solid ${LINE};
    border-radius:16px;z-index:2147483000;display:none;flex-direction:column;overflow:hidden;
    box-shadow:0 18px 50px rgba(0,0,0,.5);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .jv-open{display:flex}
  .jv-hd{padding:14px 16px;background:linear-gradient(135deg,${ACC}22,transparent);border-bottom:1px solid ${LINE};
    color:${TXT};font-weight:700;font-size:15px;display:flex;justify-content:space-between;align-items:center}
  .jv-x{background:none;border:none;color:${MUT};font-size:20px;cursor:pointer;line-height:1}
  .jv-body{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
  .jv-msg{max-width:85%;padding:9px 12px;border-radius:12px;font-size:14px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}
  .jv-u{align-self:flex-end;background:${ACC};color:#06262b;border-bottom-right-radius:3px}
  .jv-a{align-self:flex-start;background:#1b1b22;color:${TXT};border:1px solid ${LINE};border-bottom-left-radius:3px}
  .jv-src{font-size:11px;color:${MUT};margin-top:4px}
  .jv-ft{border-top:1px solid ${LINE};padding:10px;display:flex;gap:8px}
  .jv-in{flex:1;background:#15151a;border:1px solid ${LINE};color:${TXT};border-radius:10px;padding:10px 12px;font-size:14px;outline:none}
  .jv-in:focus{border-color:${ACC}}
  .jv-send{background:${ACC};color:#06262b;border:none;border-radius:10px;padding:0 14px;font-weight:700;cursor:pointer}
  .jv-send:disabled{opacity:.5;cursor:default}
  .jv-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:${MUT};margin:0 1px;animation:jvb 1s infinite}
  .jv-dot:nth-child(2){animation-delay:.15s}.jv-dot:nth-child(3){animation-delay:.3s}
  @keyframes jvb{0%,60%,100%{opacity:.25}30%{opacity:1}}`;
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  var btn = document.createElement("button");
  btn.className = "jv-btn"; btn.innerHTML = "&#128172;"; btn.setAttribute("aria-label","Apri chat");

  var panel = document.createElement("div");
  panel.className = "jv-panel";
  panel.innerHTML =
    '<div class="jv-hd"><span>' + esc(TITLE) + '</span><button class="jv-x" aria-label="Chiudi">&times;</button></div>' +
    '<div class="jv-body"></div>' +
    '<div class="jv-ft"><input class="jv-in" placeholder="Scrivi una domanda..."><button class="jv-send">Invia</button></div>';

  document.body.appendChild(btn);
  document.body.appendChild(panel);

  var body = panel.querySelector(".jv-body");
  var input = panel.querySelector(".jv-in");
  var send = panel.querySelector(".jv-send");
  var greeted = false;

  function esc(t){var e=document.createElement("div");e.textContent=t==null?"":t;return e.innerHTML;}
  function toggle(open){
    panel.classList.toggle("jv-open", open);
    if (open){ input.focus(); if(!greeted){greeted=true; addMsg("a","Ciao! Sono "+TITLE+". Posso rispondere solo sulle aree a cui ho accesso. Come posso aiutarti?");} }
  }
  function addMsg(role, text, sources){
    var m = document.createElement("div");
    m.className = "jv-msg " + (role === "u" ? "jv-u" : "jv-a");
    m.textContent = text;
    if (sources && sources.length){
      var s2 = document.createElement("div"); s2.className = "jv-src";
      s2.textContent = "Fonti: " + sources.join(", ");
      m.appendChild(s2);
    }
    body.appendChild(m); body.scrollTop = body.scrollHeight; return m;
  }
  function typing(){
    var m = document.createElement("div"); m.className="jv-msg jv-a";
    m.innerHTML = '<span class="jv-dot"></span><span class="jv-dot"></span><span class="jv-dot"></span>';
    body.appendChild(m); body.scrollTop = body.scrollHeight; return m;
  }

  async function ask(){
    var q = input.value.trim(); if(!q) return;
    input.value = ""; addMsg("u", q); send.disabled = true;
    var t = typing();
    try{
      // Modalità proxy: POST all'endpoint del sito (la chiave la mette il server).
      // Modalità diretta: POST a Ember con l'header X-Tenant-Key.
      var url = PROXY || (API + "/chat");
      var headers = {"Content-Type":"application/json"};
      if (!PROXY) headers["X-Tenant-Key"] = KEY;
      var r = await fetch(url, {
        method:"POST",
        headers: headers,
        body: JSON.stringify({message:q})
      });
      t.remove();
      if(!r.ok){ addMsg("a","⚠️ Errore "+r.status+". Riprova tra poco."); }
      else { var data = await r.json(); addMsg("a", data.answer || "(nessuna risposta)", data.sources); }
    }catch(e){ t.remove(); addMsg("a","⚠️ Connessione non riuscita. Verifica che il servizio sia attivo."); }
    send.disabled = false; input.focus();
  }

  btn.addEventListener("click", function(){ toggle(!panel.classList.contains("jv-open")); });
  panel.querySelector(".jv-x").addEventListener("click", function(){ toggle(false); });
  send.addEventListener("click", ask);
  input.addEventListener("keydown", function(e){ if(e.key==="Enter") ask(); });
})();
