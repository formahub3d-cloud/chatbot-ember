/* Divina — MOTORE VOCALE UNICO (U1, 31-07-2026).
 *
 * PRIMA questo codice viveva solo in widget/embed.js: barge-in, invio
 * automatico e sintesi per frase esistevano nel widget e NON nella console —
 * «parlo sopra e non si ferma» non era un bug di taratura, era codice mai
 * arrivato lì. Da oggi la voce è UNA: questo modulo è usato dal widget
 * (caricato come fratello di embed.js) e dalla console (copia byte-identica
 * in panel/voce.js, verificata da test come per brain3d.js). Togliere una
 * funzione = toccarla QUI, in un posto solo.
 *
 * Dentro: spezzatura in frasi (emSentenze, testata da
 * scripts/test_voce_sentenze.js sui marcatori), coda audio ordinata (max 2
 * sintesi in volo, interrompibile), barge-in (VAD adattivo, 220ms, cieco
 * 350ms), invio automatico a fine parlato (400ms parlato / 900ms silenzio /
 * finestra annullabile 500ms), trascrizione con parziali live, ampiezza
 * VERA in ingresso e in uscita per l'orb.
 *
 * Le chiavi restano SUL SERVER: il modulo parla solo con /voice/stt e
 * /voice/tts attraverso base() e headers() forniti dal chiamante. Fallback
 * alla voce del browser (SpeechRecognition + speechSynthesis) quando la
 * voce PRO non c'è: per ENTRAMBE le superfici, deciso qui.
 *
 * Interfaccia:
 *   var v = DivinaVoce({
 *     base:()=>url, headers:()=>({}), pro:()=>bool, lang:'it-IT',
 *     autosend:true, barge:true,
 *     onState: s => {},        // 'fermo' | 'ascolta' | 'pensa' | 'parla'
 *     onAmp:   a => {},        // ampiezza 0..1 (microfono o uscita, la corrente)
 *     onPartial: t => {},      // trascrizione parziale mentre parli
 *     onFinal:   t => {},      // trascrizione finale → il chiamante invia
 *     onNotify: (k,info)=>{},  // 'interrupt' · 'autosend-window' · 'autosend-resume'
 *   });                        // · 'autosend-cancel' · 'speech-start' · 'speech-end' · 'measure'
 *   v.listen({autosend}) · v.stopListen() · v.cancelListen() · v.inClosing()
 *   v.listening() · v.speak(testo) · v.speakStart(t0) · v.speakFeed(delta)
 *   v.speakFlush() · v.stopSpeak() · v.think() · v.stop() · v.stats() · v.stato()
 */
(function () {
  "use strict";
  if (window.DivinaVoce) return;

  // ── Spezzatura in FRASI per la sintesi progressiva ──────────────────────
  // Regole per l'italiano scritto: abbreviazioni (Dott., S.r.l., art. 3),
  // numeri con separatore (1.234,56), iniziali (G. Verdi), ellissi+minuscola;
  // l'a-capo chiude gli elenchi puntati.
  /* EM_SENTENZE_BEGIN — estratto e testato da scripts/test_voce_sentenze.js */
  var EM_ABBR = ("dott dott.ssa sig sig.ra sig.na dr prof ing arch avv geom rag on sen " +
    "gen col mons art artt lett n nn p pp pag pagg par cap capp vol fig figg tab all " +
    "es ecc etc ca cfr tel cell fax min max sec srl spa snc sas vs " +
    "s.r.l s.p.a s.n.c s.a.s s.s p.es u.s c.m c.a n.ro co kg mg km cm mm ml cl kw kwh mq").split(" ");
  function emSentenze(buf, flush){
    // Ritorna { frasi:[…], resto:"…" }: le frasi sono complete e pronunciabili,
    // il resto va tenuto nel buffer. Con flush=true anche il resto diventa frase.
    var frasi = [], start = 0, i, ch;
    for (i = 0; i < buf.length; i++){
      ch = buf.charAt(i);
      var punto = (ch === "." || ch === "!" || ch === "?" || ch === "…");
      if (!punto && ch !== "\n") continue;
      if (punto){
        var next = buf.charAt(i + 1);
        if (!next) break;                                   // fine buffer: la conferma non è arrivata
        if (ch === "."){
          if (next >= "0" && next <= "9") continue;         // 1.234 · v2.5 · art.3 attaccato
          var m = buf.slice(start, i).match(/([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.]*)$/);
          var w = m ? m[1].toLowerCase() : "";
          if (w.length === 1) continue;                     // iniziale: "G. Verdi", elenco "A."
          if (EM_ABBR.indexOf(w) !== -1) continue;          // "Dott." "S.r.l." "art." …
          if (next !== " " && next !== "\n") continue;      // "3.x", url, sigle senza spazio
        }
        while (i + 1 < buf.length && ".!?…".indexOf(buf.charAt(i + 1)) !== -1) i++;   // "?!", "..."
        if (i + 1 >= buf.length && buf.charAt(i) !== "\n"){ if (!flush) break; }
        if (ch === "…" || (ch === "." && buf.charAt(i - 1) === ".")){
          // puntini di sospensione: confine solo se poi si riparte con la maiuscola
          var j = i + 1; while (j < buf.length && buf.charAt(j) === " ") j++;
          var c2 = buf.charAt(j);
          if (!c2){ if (!flush) break; }                    // aspetta di sapere come continua
          else if (/[a-zà-ÿ]/.test(c2)) continue;           // "Vediamo... forse" resta unita
        }
      }
      var s = buf.slice(start, i + 1).trim();
      if (/[0-9A-Za-zÀ-ÿ]{2}/.test(s)) frasi.push(s);       // niente segmenti vuoti ("1.", "-")
      start = i + 1;
    }
    var resto = buf.slice(start);
    if (flush){
      var r0 = resto.trim();
      if (/[0-9A-Za-zÀ-ÿ]{2}/.test(r0)) frasi.push(r0);
      resto = "";
    }
    return { frasi: frasi, resto: resto };
  }
  /* EM_SENTENZE_END */
  function emPulisci(s){   // testo → pronunciabile: via markdown e marcatori di elenco
    return String(s).replace(/^\s*(?:[-•*]|\d+[.)])\s*/, "").replace(/[*`_#>[\]]/g, "").trim();
  }

  function rmsDi(an, buf){
    an.getByteTimeDomainData(buf);
    var s = 0, i, v;
    for (i = 0; i < buf.length; i++){ v = (buf[i] - 128) / 128; s += v * v; }
    return Math.sqrt(s / buf.length);
  }

  window.DivinaVoce = function (opts) {
    var O = opts || {};
    var base    = O.base    || function(){ return ""; };
    var headers = O.headers || function(){ return {}; };
    var pro     = O.pro     || function(){ return false; };
    var LANG    = O.lang || "it-IT";
    var DEF_AUTOSEND = O.autosend !== false;
    var BARGE   = O.barge !== false;
    var synth = window.speechSynthesis || null;
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
    var hasMR = !!(window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    var AC = window.AudioContext || window.webkitAudioContext;

    var STATS = { firstSyllableMs:null, samples:[], interruptions:0, vad:null, autosend:null };
    var stato = "fermo";
    function emit(nome){ var f = O["on" + nome]; if (!f) return;
      try{ f.apply(null, [].slice.call(arguments, 1)); }catch(e){} }
    function setStato(s){ if (stato !== s){ stato = s; emit("State", s); } }

    // ── USCITA: coda audio ORDINATA per frase ─────────────────────────────
    var vout = { on:false, buf:"", items:[], next:0, playing:null, gen:0, t0:0,
                 inflight:0, done:false, measured:false, anyOk:false, frasi:[] };
    var outAC = null, outAn = null, outBuf = null, micOk = false;

    function speakStart(t0){
      stopSpeak();
      vout.gen++; vout.on = true; vout.buf = ""; vout.items = []; vout.next = 0;
      vout.inflight = 0; vout.done = false; vout.measured = false; vout.anyOk = false;
      vout.frasi = []; vout.t0 = t0 || performance.now();
    }
    function speakFeed(delta){
      if (!vout.on) return;
      vout.buf += (delta || "");
      var r = emSentenze(vout.buf, false);
      vout.buf = r.resto;
      r.frasi.forEach(accoda);
    }
    function speakFlush(){
      if (!vout.on) return;
      var r = emSentenze(vout.buf, true);
      vout.buf = ""; vout.done = true;
      r.frasi.forEach(accoda);
      if (!vout.items.length && !(synth && (synth.speaking || synth.pending))){
        setStato("fermo"); emit("Notify", "speech-end");    // niente da dire: il loop riparte comunque
      }
    }
    function speak(testo){ speakStart(); speakFeed(String(testo)); speakFlush(); }
    function accoda(f){
      var t = emPulisci(f);
      if (!t) return;
      vout.frasi.push(t);
      if (pro()){ vout.items.push({ text:t, blob:null, err:false, ctl:null, state:"coda" }); pompa(); avanti(); }
      else fraseBrowser(t);
    }
    function pompa(){
      if (!vout.on) return;
      for (var i = vout.next; i < vout.items.length && vout.inflight < 2; i++){
        (function(it){
          if (it.state !== "coda") return;
          it.state = "sintesi"; vout.inflight++;
          it.ctl = window.AbortController ? new AbortController() : null;
          var gen = vout.gen;
          fetch(base() + "/voice/tts", {
            method:"POST",
            headers:(function(h){ h["Content-Type"] = "application/json"; return h; })(headers() || {}),
            body: JSON.stringify({ text: it.text.slice(0, 2000) }),
            signal: it.ctl ? it.ctl.signal : undefined,
            credentials: O.credentials || "same-origin"
          }).then(function(r){ if (!r.ok) throw new Error("tts " + r.status); return r.blob(); })
            .then(function(b){ if (vout.gen !== gen) return;
              // 0 byte = stream vuoto: frase in errore, MAI un mp3 muto per buono
              if (b && b.size){ it.blob = b; } else { it.err = true; }
              it.state = "pronta"; vout.inflight--; pompa(); avanti(); })
            .catch(function(){ if (vout.gen !== gen) return; it.err = true; it.state = "pronta"; vout.inflight--; pompa(); avanti(); });
        })(vout.items[i]);
      }
    }
    function avanti(){
      if (!vout.on || vout.playing) return;
      var it = vout.items[vout.next];
      if (!it){
        if (vout.done){
          if (!vout.anyOk && vout.frasi.length){            // PRO giù su TUTTO: rete di sicurezza browser
            var fr = vout.frasi; vout.frasi = [];
            fr.forEach(fraseBrowser);
            if (!(synth && (synth.speaking || synth.pending))){ setStato("fermo"); emit("Notify", "speech-end"); }
            return;
          }
          setStato("fermo"); emit("Notify", "speech-end");
        }
        return;
      }
      if (it.state !== "pronta") return;                    // la sintesi richiama avanti()
      vout.next++;
      if (it.err || !it.blob){ avanti(); return; }          // frase saltata: mai silenzio totale
      var a = new Audio(URL.createObjectURL(it.blob));
      vout.playing = a; vout.anyOk = true;
      collegaUscita(a);
      a.onplaying = function(){ misura(); setStato("parla"); emit("Notify", "speech-start"); vadArm(); };
      a.onended = a.onerror = function(){
        try{ URL.revokeObjectURL(a.src); }catch(e){}
        if (vout.playing === a) vout.playing = null;
        avanti();
      };
      a.play().catch(function(){ if (vout.playing === a) vout.playing = null; avanti(); });
    }
    function collegaUscita(a){
      // Ampiezza VERA in uscita (per l'orb): analyser sull'elemento audio.
      if (!AC) return;
      try{
        if (!outAC){ outAC = new AC(); outAn = outAC.createAnalyser(); outAn.fftSize = 512;
          outAn.connect(outAC.destination); outBuf = new Uint8Array(outAn.fftSize); ampOutLoop(); }
        outAC.createMediaElementSource(a).connect(outAn);
      }catch(e){}
    }
    function ampOutLoop(){
      if (!outAn) return;
      if (vout.playing) emit("Amp", Math.min(1, rmsDi(outAn, outBuf) * 4));
      requestAnimationFrame(ampOutLoop);
    }
    function fraseBrowser(t){
      if (!synth) return;
      try{
        var u = new SpeechSynthesisUtterance(t);
        u.lang = LANG; u.rate = 1.02; u.pitch = 1;
        var vs = synth.getVoices() || [];
        var v = vs.filter(function(x){ return x.lang && x.lang.toLowerCase().indexOf(LANG.slice(0,2).toLowerCase()) === 0; })[0];
        if (v) u.voice = v;
        u.onstart = function(){ misura(); setStato("parla"); emit("Notify", "speech-start"); vadArm(); };
        u.onend = function(){
          if (!(synth.pending || synth.speaking) && vout.done && vout.next >= vout.items.length){
            setStato("fermo"); emit("Notify", "speech-end");
          }
        };
        synth.speak(u);                                     // la coda del browser è già ordinata
      }catch(e){}
    }
    function misura(){
      if (vout.measured) return;
      vout.measured = true;
      var ms = Math.round(performance.now() - vout.t0);
      STATS.firstSyllableMs = ms; STATS.samples.push(ms);
      emit("Notify", "measure", { firstSyllableMs: ms });
      try{ console.info("[voce] prima sillaba dopo " + ms + " ms"); }catch(e){}
    }
    function parlaAttiva(){
      if (synth && (synth.speaking || synth.pending)) return true;
      if (vout.playing) return true;
      if (!vout.on) return false;
      return !vout.done || vout.next < vout.items.length || !!vout.buf;
    }
    function stopSpeak(){
      vout.gen++; vout.on = false; vout.buf = ""; vout.done = true;
      vout.items.forEach(function(it){ try{ it.ctl && it.ctl.abort(); }catch(e){} });
      vout.items = []; vout.next = 0; vout.inflight = 0; vout.frasi = [];
      if (vout.playing){ try{ vout.playing.pause(); }catch(e){} vout.playing = null; }
      if (synth) try{ synth.cancel(); }catch(e){}
      vadIdle();
    }

    // ── BARGE-IN: interruzione a metà frase ───────────────────────────────
    // Mentre la voce parla, un analyser sul microfono (echoCancellation) fa
    // scattare l'interruzione dopo 220ms consecutivi sopra la soglia ADATTIVA
    // (base*4, pavimento 0.045), con 350ms ciechi a inizio riproduzione.
    // Si arma SOLO se il permesso microfono è già concesso.
    var vad = { stream:null, ac:null, an:null, buf:null, raf:0, base:0.008, over:0,
                lastPlayAt:0, armed:false };
    function vadArm(){
      vad.lastPlayAt = performance.now();
      if (!BARGE || !hasMR || vad.armed || udito.on) return;   // col mic già aperto ci pensa l'autosend
      if (micOk){ vadStart(); return; }
      if (navigator.permissions && navigator.permissions.query){
        navigator.permissions.query({ name: "microphone" })
          .then(function(st){ if (st.state === "granted") vadStart(); }).catch(function(){});
      }
    }
    function vadStart(){
      if (vad.armed) return; vad.armed = true;
      navigator.mediaDevices.getUserMedia({ audio: { echoCancellation:true, noiseSuppression:true, autoGainControl:true } })
        .then(function(st){
          if (!vad.armed || !parlaAttiva()){ try{ st.getTracks().forEach(function(t){ t.stop(); }); }catch(e){} vad.armed = false; return; }
          vad.stream = st; micOk = true;
          vad.ac = new AC(); vad.an = vad.ac.createAnalyser(); vad.an.fftSize = 1024;
          vad.ac.createMediaStreamSource(st).connect(vad.an);
          vad.buf = new Uint8Array(vad.an.fftSize);
          vad.over = 0; vadLoop();
        }).catch(function(){ vad.armed = false; });
    }
    function vadLoop(){
      if (!vad.armed || !vad.an) return;
      var rms = rmsDi(vad.an, vad.buf);
      var now = performance.now();
      var blind = (now - vad.lastPlayAt) < 350;
      if (!blind && rms < Math.max(0.004, vad.base) * 1.5) vad.base = vad.base * 0.995 + rms * 0.005;
      var soglia = Math.max(0.045, vad.base * 4);
      STATS.vad = { rms:+rms.toFixed(4), base:+vad.base.toFixed(4), soglia:+soglia.toFixed(4) };
      if (!parlaAttiva()){ vadIdle(); return; }
      if (!blind && rms > soglia){
        if (!vad.over) vad.over = now;
        else if (now - vad.over > 220){ interrompi(rms, soglia); return; }
      } else vad.over = 0;
      vad.raf = requestAnimationFrame(vadLoop);
    }
    function interrompi(rms, soglia){
      STATS.interruptions++;
      try{ console.info("[voce] interruzione a metà frase", { rms:+(rms||0).toFixed(4), soglia:+(soglia||0).toFixed(4) }); }catch(e){}
      stopSpeak();
      emit("Notify", "interrupt");                          // il chiamante ferma la SUA generazione
      listen();                                             // la parola passa all'utente
    }
    function vadIdle(){
      vad.armed = false; vad.over = 0;
      if (vad.raf){ cancelAnimationFrame(vad.raf); vad.raf = 0; }
      try{ vad.stream && vad.stream.getTracks().forEach(function(t){ t.stop(); }); }catch(e){}
      try{ vad.ac && vad.ac.close(); }catch(e){}
      vad.stream = null; vad.ac = null; vad.an = null;
    }

    // ── INGRESSO: ascolto con parziali live + invio automatico ────────────
    var udito = { on:false, mr:null, rec:null, stream:null, chunks:[], cancel:false,
                  autosend:DEF_AUTOSEND, closing:0, ac:null, an:null, buf:null, raf:0,
                  base:0.008, speechMs:0, sil0:0, last:0, pseq:0, pshown:0, pbusy:false, t0:0 };
    function listen(lopts){
      if (udito.on) return;
      stopSpeak();
      udito.autosend = (lopts && "autosend" in lopts) ? !!lopts.autosend : DEF_AUTOSEND;
      if (pro() && hasMR) listenPro();
      else listenBrowser();
    }
    function listenPro(){
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function(stream){
        micOk = true;
        udito.on = true; udito.stream = stream; udito.chunks = []; udito.cancel = false;
        udito.closing = 0; udito.speechMs = 0; udito.sil0 = 0; udito.pseq = 0;
        udito.pshown = 0; udito.pbusy = false; udito.t0 = performance.now();
        var mr = udito.mr = new MediaRecorder(stream);
        setStato("ascolta");
        mr.ondataavailable = function(e){
          if (e.data && e.data.size) udito.chunks.push(e.data);
          // parziali per i primi 90s (oltre: solo la finale, costi sotto controllo)
          if (udito.on && (performance.now() - udito.t0) < 90000) parziale();
        };
        mr.onstop = function(){ chiudiAscolto(); };
        // analyser per ampiezza orb + invio automatico (stessa misura RMS)
        try{
          udito.ac = new AC(); udito.an = udito.ac.createAnalyser(); udito.an.fftSize = 1024;
          udito.ac.createMediaStreamSource(stream).connect(udito.an);
          udito.buf = new Uint8Array(udito.an.fftSize); udito.last = performance.now(); uditoLoop();
        }catch(e){}                                         // senza WebAudio: niente autosend, il pulsante c'è
        mr.start(1200);                                     // timeslice → parziali live
      }).catch(function(){ listenBrowser(); });
    }
    async function parziale(){
      if (udito.pbusy || !udito.on) return;
      udito.pbusy = true; var mySeq = ++udito.pseq;
      try{
        var blob = new Blob(udito.chunks, { type: (udito.mr && udito.mr.mimeType) || "audio/webm" });
        if (blob.size < 1200) return;                       // troppo poco audio
        var fd = new FormData(); fd.append("file", blob, "audio.webm");
        var r = await fetch(base() + "/voice/stt", { method:"POST", headers: headers() || {}, body: fd,
                                                     credentials: O.credentials || "same-origin" });
        if (!r.ok) return;
        var j = await r.json();
        if (udito.on && j && j.text != null && mySeq > udito.pshown){ udito.pshown = mySeq; emit("Partial", j.text); }
      }catch(e){}
      finally{ udito.pbusy = false; }
    }
    function uditoLoop(){
      // V2 «mani libere»: ≥400ms di parlato VERO, poi 900ms di silenzio sotto
      // la soglia adattiva → finestra «Invio…» di 500ms annullabile (tocca il
      // mic, o riprendi a parlare e svanisce: un respiro NON è una fine frase).
      if (!udito.on || !udito.an) return;
      var rms = rmsDi(udito.an, udito.buf);
      emit("Amp", Math.min(1, rms * 5));                    // ampiezza VERA del microfono → orb
      var now = performance.now(), dt = Math.min(100, now - udito.last); udito.last = now;
      if (rms < Math.max(0.004, udito.base) * 1.5) udito.base = udito.base * 0.995 + rms * 0.005;
      var soglia = Math.max(0.045, udito.base * 4);
      var parlato = rms > soglia;
      if (parlato) udito.speechMs += dt;
      STATS.autosend = { rms:+rms.toFixed(4), base:+udito.base.toFixed(4), soglia:+soglia.toFixed(4), speechMs:Math.round(udito.speechMs) };
      if (udito.autosend){
        if (udito.closing){
          if (parlato){ udito.closing = 0; udito.sil0 = 0; emit("Notify", "autosend-resume"); }
          else if (now - udito.closing > 500){
            STATS.autosend.silenzioMs = Math.round(now - udito.sil0);
            try{ console.info("[voce] invio automatico a fine parlato", STATS.autosend); }catch(e){}
            try{ udito.mr && udito.mr.stop(); }catch(e){}
            return;
          }
        } else if (udito.speechMs >= 400){
          if (!parlato){
            if (!udito.sil0) udito.sil0 = now;
            else if (now - udito.sil0 > 900){ udito.closing = now; emit("Notify", "autosend-window"); }
          } else udito.sil0 = 0;
        }
      }
      udito.raf = requestAnimationFrame(uditoLoop);
    }
    async function chiudiAscolto(){
      try{ udito.stream && udito.stream.getTracks().forEach(function(t){ t.stop(); }); }catch(e){}
      if (udito.raf){ cancelAnimationFrame(udito.raf); udito.raf = 0; }
      try{ udito.ac && udito.ac.close(); }catch(e){}
      udito.ac = null; udito.an = null;
      var chunks = udito.chunks, mime = (udito.mr && udito.mr.mimeType) || "audio/webm";
      var annullato = udito.cancel;
      udito.on = false; udito.mr = null; udito.stream = null; udito.pseq += 1000;   // invalida i parziali in volo
      setStato("fermo");
      if (annullato){ emit("Notify", "autosend-cancel"); return; }   // il parziale resta al chiamante
      try{
        var blob = new Blob(chunks, { type: mime });
        var fd = new FormData(); fd.append("file", blob, "audio.webm");
        var r = await fetch(base() + "/voice/stt", { method:"POST", headers: headers() || {}, body: fd,
                                                     credentials: O.credentials || "same-origin" });
        if (!r.ok) throw new Error("stt " + r.status);
        var j = await r.json();
        emit("Final", (j && j.text) || "");
      }catch(e){ emit("Final", ""); }
    }
    function listenBrowser(){
      // Rete di sicurezza: riconoscimento del browser (fine parlato gestita
      // dal browser stesso → l'invio a fine frase c'è comunque).
      if (!SR){ emit("Final", ""); return; }
      udito.on = true; udito.cancel = false;
      var rec = udito.rec = new SR();
      rec.lang = LANG; rec.interimResults = true; rec.continuous = !udito.autosend;
      var fin = "";
      setStato("ascolta");
      rec.onresult = function(ev){
        var interim = "";
        for (var i = ev.resultIndex; i < ev.results.length; i++){
          var tr = ev.results[i][0].transcript;
          if (ev.results[i].isFinal) fin += tr; else interim += tr;
        }
        emit("Partial", (fin + interim).trim());
      };
      rec.onerror = function(){};
      rec.onend = function(){
        udito.rec = null; udito.on = false;
        setStato("fermo");
        if (udito.cancel){ emit("Notify", "autosend-cancel"); return; }
        emit("Final", fin.trim());
      };
      try{ rec.start(); }catch(e){ udito.on = false; setStato("fermo"); emit("Final", ""); }
    }
    function stopListen(){
      if (!udito.on) return;
      if (udito.mr){ try{ udito.mr.stop(); }catch(e){} return; }
      if (udito.rec){ try{ udito.rec.stop(); }catch(e){} }
    }
    function cancelListen(){
      if (!udito.on) return;
      udito.cancel = true;
      stopListen();
    }

    return {
      listen: listen,
      stopListen: stopListen,
      cancelListen: cancelListen,
      inClosing: function(){ return !!udito.closing; },
      listening: function(){ return !!udito.on; },
      speak: speak, speakStart: speakStart, speakFeed: speakFeed, speakFlush: speakFlush,
      stopSpeak: stopSpeak,
      speaking: parlaAttiva,
      think: function(){ setStato("pensa"); },
      interrupt: function(){ interrompi(); },
      stop: function(){ udito.cancel = true; stopListen(); stopSpeak(); setStato("fermo"); },
      stats: function(){ return STATS; },
      stato: function(){ return stato; }
    };
  };
})();
