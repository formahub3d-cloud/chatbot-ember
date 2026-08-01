/* brain3d.js — il renderer 3D del cervello, estratto UNA volta sola (B1, 30-07).
   Origine: cervello-vivo.html del vault (branch main, versione pubblicata),
   trasformato da pagina con dati incorporati a MODULO a istanza:

     const api = createBrain(canvas, opzioni)
     api.setData(nodi, archi)   // sostituisce i dati e rifà il layout
     api.fire(slug)             // scarica un impulso da un nodo
     api.setThink(attivo)       // stato «sta ragionando» (sostenuto, non one-shot)
     api.setHeat(attivo)        // mappa di calore on/off
     api.setUsage(mappa)        // {slug: 0..1} — RICALCOLA l'attività dei nodi
     api.destroy()              // ferma l'animazione e stacca OGNI listener

   opzioni: { palette: {categoria: '#colore'},   // default = palette FORMA
              reducedMotion: bool|undefined,     // override della media query
              onHover(nodo|null, x, y),          // per il tooltip del consumatore
              onStats({nodes, links, cats}) }    // per legenda/contatori esterni

   nodi:  [{id, title, cat, color?, deg?, born?, fresh?, usage?}]
   archi: [[i,j], …] (indici) oppure [{s,t}, …] (id)

   Differenze deliberate dall'originale (rilievi B1):
   - stato in un'istanza, MAI variabili di modulo: due istanze convivono;
   - dimensioni dal riquadro del canvas (ResizeObserver), non da window;
   - panX/panY (dichiarate, mai scritte, lette in tre punti) ELIMINATE nei
     tre punti d'uso — niente funzionalità a metà;
   - hexA (definita e mai usata) eliminata;
   - la heatmap non è più un calcolo one-shot all'avvio: setUsage() ricalcola
     n.act su TUTTI i nodi (usage reale se presente, altrimenti grado);
   - senza dati: nessun nodo inventato — il modulo non disegna nulla e il
     consumatore mostra il suo stato vuoto. */
(function () {
  'use strict';

  var PALETTE_FORMA = ['#89D41D', '#0ED4E4', '#DD24F2', '#F8693C', '#EAB308', '#F63E3D'];
  var BIRTH_DAYS = 5, FRESH_DAYS = 14, BIRTH_DUR = 1700, BIRTH_STAGGER = 320;
  var THINK_EASE = 0.06, WAVE_DUR = 900, FOCAL = 1250;

  function hexRGB(hex) {
    var h = String(hex || '#888').replace('#', '');
    var n = parseInt(h.length === 3 ? h.split('').map(function (c) { return c + c; }).join('') : h, 16);
    return ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255);
  }
  function heatColor(a) {
    var g = Math.round(210 - a * 150), b = Math.round(60 - a * 60);
    return '255,' + Math.max(0, g) + ',' + Math.max(0, b);
  }

  function createBrain(canvas, opts) {
    opts = opts || {};
    var ctx = canvas.getContext('2d');
    if (!ctx) return { setData: function(){}, fire: function(){}, setThink: function(){},
                       setHeat: function(){}, setUsage: function(){}, destroy: function(){} };

    // ── stato dell'ISTANZA (niente di condiviso fra istanze) ──────────────────
    var W = 0, H = 0, DPR = 1, R_SPH = 180;
    var NODES = [], edges = [], byId = new Map(), neigh = new Map(), adj = new Map();
    var bows = new Map(), srcPool = [], shell = [], signals = [], waves = [];
    var MAX_SIGNALS = 40, MAX_GEN = 3;
    var rot = 0.2, autoRot = 0.0011, zoom = 1, tilt = 0.42;
    var dragNode = null, dragging = false, lastX = 0, lastY = 0, moved = false;
    var hover = null, lastFired = null, mouseX = -1, mouseY = -1;
    var thinking = false, thinkF = 0, heat = false;
    var physT = 0, t0 = -1, rafId = 0, hiddenAt = -1, destroyed = false;
    var signalSeed = 1;
    function rnd() { signalSeed = (signalSeed * 1103515245 + 12345) & 0x7fffffff; return signalSeed / 0x7fffffff; }

    var rmQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    // R1 (01-08): labels:'hover' = i nomi SOLO al passaggio/clic (la home);
    // default 'auto' = anche sui nodi molto connessi (la porta Cervello, dove
    // si viene per cercare una nota, non per un colpo d'occhio).
    var labelsAuto = opts.labels !== 'hover';
    // R4: adattamento fps anche qui — tela più grande = più lavoro per frame.
    var lowFx = false, slowFrom = 0, lastT = 0;
    var reduceMotion = (typeof opts.reducedMotion === 'boolean') ? opts.reducedMotion
                       : !!(rmQuery && rmQuery.matches);
    function onRM(e) { if (typeof opts.reducedMotion !== 'boolean') reduceMotion = e.matches; }

    // ── dimensioni dal RIQUADRO DEL CANVAS, mai da window (rilievo B1) ────────
    function resize() {
      var r = canvas.getBoundingClientRect();
      DPR = Math.min(window.devicePixelRatio || 1, 2);
      W = Math.max(1, r.width); H = Math.max(1, r.height);
      canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      R_SPH = Math.max(120, Math.min(W, H) * 0.36);
    }
    var ro = window.ResizeObserver ? new ResizeObserver(function () { if (!destroyed) resize(); }) : null;
    if (ro) ro.observe(canvas);

    // ── dati: setData rifà TUTTO il derivato (layout, archi, pool) ────────────
    function setData(nodes, links) {
      NODES = (nodes || []).map(function (n, i) {
        return { id: n.id, title: String(n.title || n.id || ''), cat: String(n.cat || ''),
                 color: n.color || PALETTE_FORMA[i % PALETTE_FORMA.length],
                 deg: n.deg || 0, born: (n.born == null ? 9999 : n.born),
                 fresh: (n.fresh == null ? 9999 : n.fresh),
                 usage: (typeof n.usage === 'number' ? n.usage : null) };
      });
      byId = new Map(); edges = []; bows = new Map(); signals.length = 0; waves.length = 0;
      neigh = new Map(); adj = new Map(); srcPool = [];
      NODES.forEach(function (n, i) {
        n.i = i;
        n.phase = (i * 1.6180339887) % (Math.PI * 2);
        byId.set(n.id, n);
        neigh.set(n.id, new Set()); adj.set(n.id, []);
      });
      (links || []).forEach(function (l) {
        var a = Array.isArray(l) ? NODES[l[0]] : byId.get(l.s);
        var b = Array.isArray(l) ? NODES[l[1]] : byId.get(l.t);
        if (!a || !b || a === b) return;
        var h = (((a.i + 1) * 73856093) ^ ((b.i + 1) * 19349663)) >>> 0;
        var bow = (0.10 + (h % 89) / 89 * 0.08) * ((h & 8) ? 1 : -1);
        edges.push({ a: a, b: b, bow: bow });
        bows.set(a.id + '|' + b.id, bow); bows.set(b.id + '|' + a.id, -bow);
        neigh.get(a.id).add(b.id); neigh.get(b.id).add(a.id);
        adj.get(a.id).push(b); adj.get(b.id).push(a);
        a.deg = (a.deg || 0); b.deg = (b.deg || 0);
      });
      // grado dagli archi se non fornito
      NODES.forEach(function (n) { if (!n.deg) n.deg = adj.get(n.id).length; });
      NODES.forEach(function (n) {
        n.rad = 3.2 + Math.sqrt(n.deg) * 1.7;
        n.pAmp = 0.12 + Math.min(0.24, n.deg * 0.02);
        n.pSpd = 0.0020 + Math.min(0.0016, n.deg * 0.00014);
        n.freshK = Math.max(0, 1 - n.fresh / FRESH_DAYS);
        for (var k = 0; k < Math.max(1, n.deg); k++) srcPool.push(n);
      });
      // SFERA di Fibonacci — ordinamento per CATEGORIA poi id: le categorie
      // formano chiazze contigue (INVARIANTE del layout, non toccare).
      var rank = NODES.slice().sort(function (a, b) {
        return a.cat < b.cat ? -1 : a.cat > b.cat ? 1 : (a.id < b.id ? -1 : 1);
      });
      var N = Math.max(1, rank.length);
      rank.forEach(function (n, r) {
        var y = 1 - (r + 0.5) / N * 2;
        var rr0 = Math.sqrt(Math.max(0, 1 - y * y));
        var az = r * 2.399963229;
        n.hx = Math.cos(az) * rr0; n.hy = y; n.hz = Math.sin(az) * rr0;
        var s = ((r + 1) * 2654435761) >>> 0;
        var rnd0 = function () { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
        n.dax = 0.018 + rnd0() * 0.05; n.day = 0.018 + rnd0() * 0.05; n.daz = 0.018 + rnd0() * 0.05;
        n.jphase = rnd0() * Math.PI * 2;
        n.x = n.hx * R_SPH; n.y = n.hy * R_SPH; n.z = n.hz * R_SPH;
      });
      var nb = 0;
      NODES.forEach(function (n) { n.birth = (n.born <= BIRTH_DAYS) ? nb++ : -1; n.born_done = false; n.born_fired = false; });
      MAX_SIGNALS = Math.min(140, Math.max(40, Math.round(edges.length * 0.8)));
      recomputeAct();
      t0 = -1;                                   // le nascite ripartono coi dati nuovi
      if (opts.onStats) {
        var cats = [], seen = {};
        NODES.forEach(function (n) { if (!seen[n.cat]) { seen[n.cat] = 1; cats.push({ cat: n.cat, color: n.color }); } });
        opts.onStats({ nodes: NODES.length, links: edges.length, cats: cats });
      }
    }

    // ── heatmap: RICALCOLO su tutti i nodi (fix B1 §4 — non più one-shot) ────
    function recomputeAct() {
      var maxDeg = 1;
      NODES.forEach(function (n) { if (n.deg > maxDeg) maxDeg = n.deg; });
      NODES.forEach(function (n) {
        n.act = (typeof n.usage === 'number') ? Math.max(0, Math.min(1, n.usage)) : n.deg / maxDeg;
      });
    }
    function setUsage(map) {
      map = map || {};
      NODES.forEach(function (n) { n.usage = (typeof map[n.id] === 'number') ? map[n.id] : n.usage; });
      recomputeAct();
    }

    // ── guscio di particelle (stessa rotazione/prospettiva dei nodi) ──────────
    (function seedShell() {
      for (var p = 0; p < 320; p++) {
        var y = 1 - (p + 0.5) / 320 * 2;
        var rr0 = Math.sqrt(Math.max(0, 1 - y * y));
        var az = p * 2.399963229 + 0.6;
        var s = ((p + 7) * 40503) >>> 0;
        var rnd0 = function () { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
        var rad = 0.78 + rnd0() * 0.5;
        shell.push({ hx: Math.cos(az) * rr0 * rad, hy: y * rad, hz: Math.sin(az) * rr0 * rad,
                     sz: 0.5 + rnd0() * 1.3, tw: rnd0() * Math.PI * 2,
                     col: ['137,212,29', '14,212,228', '221,36,242', '248,105,60', '234,179,8', '246,62,61'][(rnd0() * 6) | 0] });
      }
    })();

    // ── proiezione (panX/panY ELIMINATE nei tre punti d'uso — rilievo B1) ────
    function project(n) {
      var cy = Math.cos(rot), sy = Math.sin(rot);
      var x1 = n.x * cy - n.z * sy, z1 = n.x * sy + n.z * cy;
      var ct = Math.cos(tilt), st = Math.sin(tilt);
      var y2 = n.y * ct - z1 * st, z2 = n.y * st + z1 * ct;
      var persp = FOCAL / (FOCAL + z2);
      return { sx: W / 2 + x1 * zoom * persp, sy: H / 2 + y2 * zoom * persp, persp: persp, z3: z2 };
    }
    function ctrlPoint(pa, pb, bow) {
      var dx = pb.sx - pa.sx, dy = pb.sy - pa.sy;
      var wob = 0.06 * Math.sin(physT * 0.0011 + (pa.sx + pb.sy) * 0.012);
      var b = bow + wob;
      return { x: (pa.sx + pb.sx) / 2 - dy * b, y: (pa.sy + pb.sy) / 2 + dx * b };
    }
    function qBez(pa, c, pb, t) {
      var u = 1 - t;
      return { x: u * u * pa.sx + 2 * u * t * c.x + t * t * pb.sx,
               y: u * u * pa.sy + 2 * u * t * c.y + t * t * pb.sy };
    }
    function pickNearest(sx, sy) {
      var best = null, bd = 1e9, brr = 0;
      for (var i = 0; i < NODES.length; i++) {
        var n = NODES[i], p = project(n);
        var dx = p.sx - sx, dy = p.sy - sy, d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = n; brr = n.rad * zoom * p.persp + 9; }
      }
      return (best && bd < brr * brr) ? best : null;
    }
    function canvasXY(ev) {
      var r = canvas.getBoundingClientRect();
      return { x: ev.clientX - r.left, y: ev.clientY - r.top };
    }

    // ── segnali, cascata, firing (identici all'originale) ─────────────────────
    function emit(from, to, gen, color) {
      if (signals.length >= MAX_SIGNALS) return;
      signals.push({ a: from, b: to, p: 0, speed: 0.006 + rnd() * 0.012,
                     color: color || from.color, gen: gen, bow: bows.get(from.id + '|' + to.id) || 0 });
    }
    function fireNode(node, gen) {
      var ns = adj.get(node.id) || [];
      for (var i = 0; i < ns.length; i++) emit(node, ns[i], gen, node.color);
    }
    function clickFire(node) { fireNode(node, 0); waves.push({ n: node, t0: performance.now() }); }
    function spawnAmbient(inward) {
      if (!srcPool.length) return;
      var src = srcPool[(rnd() * srcPool.length) | 0];
      var ns = adj.get(src.id); if (!ns || !ns.length) return;
      var to;
      if (inward) {
        var best = ns[0], bd = best.x * best.x + best.y * best.y + best.z * best.z;
        for (var i = 0; i < ns.length; i++) { var m = ns[i]; var d = m.x * m.x + m.y * m.y + m.z * m.z; if (d < bd) { bd = d; best = m; } }
        to = best;
      } else to = ns[(rnd() * ns.length) | 0];
      emit(src, to, 0, src.color);
    }
    function cascade(sig) {
      if (sig.gen >= MAX_GEN) return;
      var ns = adj.get(sig.b.id) || [];
      var pCont = 0.5 - sig.gen * 0.13;
      for (var i = 0; i < ns.length; i++) {
        var m = ns[i];
        if (m === sig.a) continue;
        if (rnd() < pCont) emit(sig.b, m, sig.gen + 1, sig.color);
      }
    }
    function drift(t) {
      var a = t * 0.00032;
      for (var i = 0; i < NODES.length; i++) {
        var n = NODES[i];
        if (n === dragNode) continue;
        n.x = (n.hx + n.dax * Math.sin(a + n.phase)) * R_SPH;
        n.y = (n.hy + n.day * Math.sin(a * 0.83 + n.jphase)) * R_SPH;
        n.z = (n.hz + n.daz * Math.sin(a * 1.17 + n.phase * 1.3)) * R_SPH;
      }
    }

    // ── disegno (identico all'originale, meno pan; EEG e shell inclusi) ──────
    var EEG = [
      { y: 0.20, amp: 16, f1: 0.013, f2: 0.041, sp: 0.00045, col: '14,212,228' },
      { y: 0.52, amp: 22, f1: 0.009, f2: 0.034, sp: 0.00031, col: '221,36,242' },
      { y: 0.82, amp: 14, f1: 0.017, f2: 0.052, sp: 0.00058, col: '137,212,29' },
    ];
    var eegAct = 0;
    function drawEEG(t) {
      var target = Math.min(1, signals.length / Math.max(1, MAX_SIGNALS)) * 0.7 + thinkF * 0.3;
      eegAct += (target - eegAct) * 0.04;
      ctx.globalCompositeOperation = 'lighter';
      ctx.lineWidth = 1.4;
      for (var wi = 0; wi < EEG.length; wi++) {
        var w = EEG[wi], baseY = H * w.y, amp = w.amp * (1 + eegAct * 0.6);
        ctx.strokeStyle = 'rgba(' + w.col + ',' + (0.05 + eegAct * 0.07) + ')';
        ctx.beginPath();
        for (var x = 0; x <= W; x += 7) {
          var y = baseY + amp * Math.sin(x * w.f1 + t * w.sp) + amp * 0.45 * Math.sin(x * w.f2 - t * w.sp * 1.7);
          x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      ctx.globalCompositeOperation = 'source-over';
    }
    function drawShell(t) {
      ctx.globalCompositeOperation = 'lighter';
      for (var i = 0; i < shell.length; i++) {
        var d = shell[i];
        d.x = d.hx * R_SPH; d.y = d.hy * R_SPH; d.z = d.hz * R_SPH;
        var p = project(d);
        var tw = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 0.0016 + d.tw));
        var depth = Math.max(0.25, Math.min(1.1, p.persp));
        ctx.fillStyle = 'rgba(' + d.col + ',' + (0.10 + tw * 0.30 * depth) + ')';
        ctx.beginPath(); ctx.arc(p.sx, p.sy, d.sz * zoom * depth, 0, 7); ctx.fill();
      }
      ctx.globalCompositeOperation = 'source-over';
    }

    function draw(t) {
      var breath = reduceMotion ? 0.5 : 0.5 + 0.5 * Math.sin(t * 0.0006);
      ctx.clearRect(0, 0, W, H);
      var g = ctx.createRadialGradient(W / 2, H * 0.46, 0, W / 2, H * 0.46, Math.max(W, H) * 0.62);
      g.addColorStop(0, 'rgba(14,212,228,' + (0.05 + breath * 0.03) + ')');
      g.addColorStop(0.5, 'rgba(221,36,242,' + (0.03 + breath * 0.02) + ')');
      g.addColorStop(1, 'rgba(5,5,5,0)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      if (!reduceMotion) drawEEG(t);
      drawShell(t);
      if (!NODES.length) return;                 // senza dati: MAI nodi inventati

      var hoverSet = hover ? neigh.get(hover.id) : null;
      var elapsed = (t0 < 0) ? 0 : (t - t0);

      ctx.lineWidth = 1.3; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      for (var ei = 0; ei < edges.length; ei++) {
        var e = edges[ei];
        var pa = project(e.a), pb = project(e.b);
        var c = ctrlPoint(pa, pb, e.bow);
        var lit = hover && (e.a === hover || e.b === hover);
        if (hover && !lit) ctx.strokeStyle = 'rgba(120,125,140,.05)';
        else ctx.strokeStyle = lit ? 'rgba(255,255,255,.30)' : 'rgba(150,170,205,.17)';
        ctx.beginPath(); ctx.moveTo(pa.sx, pa.sy); ctx.quadraticCurveTo(c.x, c.y, pb.sx, pb.sy); ctx.stroke();
      }

      var cap = reduceMotion ? 0 : MAX_SIGNALS * (0.7 + thinkF * 0.3);
      var rate = 0.5 + thinkF * 0.45;
      var bursts = 1 + Math.round(thinkF * 2);
      for (var k = 0; k < bursts; k++) if (signals.length < cap && rnd() < rate) spawnAmbient(thinkF > 0.4);

      ctx.globalCompositeOperation = 'lighter';
      for (var i = signals.length - 1; i >= 0; i--) {
        var s = signals[i];
        s.p += s.speed * (1 + thinkF * 0.8);
        if (s.p >= 1) { cascade(s); signals.splice(i, 1); continue; }
        var pa2 = project(s.a), pb2 = project(s.b);
        var c2 = ctrlPoint(pa2, pb2, s.bow);
        var head = qBez(pa2, c2, pb2, s.p);
        var tailP = Math.max(0, s.p - 0.16);
        var tpt = qBez(pa2, c2, pb2, tailP);
        var grad = ctx.createLinearGradient(tpt.x, tpt.y, head.x, head.y);
        grad.addColorStop(0, 'rgba(255,255,255,0)'); grad.addColorStop(1, s.color);
        ctx.strokeStyle = grad; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(tpt.x, tpt.y);
        for (var q = 1; q <= 3; q++) {
          var qq = qBez(pa2, c2, pb2, tailP + (s.p - tailP) * q / 3);
          ctx.lineTo(qq.x, qq.y);
        }
        ctx.stroke();
        var gr = ctx.createRadialGradient(head.x, head.y, 0, head.x, head.y, 7);
        gr.addColorStop(0, s.color); gr.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(head.x, head.y, 7, 0, 7); ctx.fill();
      }
      for (var wi2 = waves.length - 1; wi2 >= 0; wi2--) {
        var wv = waves[wi2];
        var kk = (t - wv.t0) / WAVE_DUR;
        if (kk >= 1) { waves.splice(wi2, 1); continue; }
        var pw = project(wv.n);
        var base = wv.n.rad * zoom * pw.persp;
        ctx.strokeStyle = 'rgba(' + hexRGB(wv.n.color) + ',' + ((1 - kk) * 0.55) + ')';
        ctx.lineWidth = 2.5 * (1 - kk) + 0.5;
        ctx.beginPath(); ctx.arc(pw.sx, pw.sy, base + kk * 90 * zoom, 0, 7); ctx.stroke();
        if (kk > 0.12) {
          var k2 = kk - 0.12;
          ctx.strokeStyle = 'rgba(255,255,255,' + ((1 - k2) * 0.25) + ')';
          ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.arc(pw.sx, pw.sy, base + k2 * 90 * zoom, 0, 7); ctx.stroke();
        }
      }
      ctx.globalCompositeOperation = 'source-over';

      if (thinkF > 0.01) {
        var cx = W / 2, cyg = H / 2;               // pan eliminato anche qui
        var throb = 0.6 + 0.4 * Math.sin(t * 0.009);
        var rad = Math.max(W, H) * 0.26 * thinkF * (0.8 + 0.2 * throb);
        ctx.globalCompositeOperation = 'lighter';
        var cg = ctx.createRadialGradient(cx, cyg, 0, cx, cyg, rad);
        cg.addColorStop(0, 'rgba(14,212,228,' + (0.16 * thinkF * throb) + ')');
        cg.addColorStop(0.5, 'rgba(221,36,242,' + (0.08 * thinkF) + ')');
        cg.addColorStop(1, 'rgba(5,5,5,0)');
        ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(cx, cyg, rad, 0, 7); ctx.fill();
        ctx.globalCompositeOperation = 'source-over';
      }

      var order = NODES.map(function (n) { var p = project(n); n._sx = p.sx; n._sy = p.sy; n._pp = p.persp; n._z3 = p.z3; return n; })
                       .sort(function (a, b) { return b._z3 - a._z3; });
      for (var oi = 0; oi < order.length; oi++) {
        var n = order[oi];
        var sx = n._sx, sy2 = n._sy, persp = n._pp;
        var depth = Math.max(0.4, Math.min(1.25, persp));
        var ampEff = n.pAmp * (1 + thinkF * 0.9);
        var pulse = reduceMotion ? 1 : (1 - ampEff) + ampEff * (0.5 + 0.5 * Math.sin(t * n.pSpd + n.phase));
        var dim = hover && n !== hover && !(hoverSet && hoverSet.has(n.id));
        var scale = 1, flash = 0;
        if (n.birth >= 0 && !n.born_done) {
          if (reduceMotion) { n.born_done = true; }
          else {
            var el = elapsed - n.birth * BIRTH_STAGGER;
            if (el < 0) continue;
            if (el < BIRTH_DUR) {
              var kb = el / BIRTH_DUR, c1 = 1.70158, c3 = c1 + 1;
              scale = Math.max(0.05, 1 + c3 * Math.pow(kb - 1, 3) + c1 * Math.pow(kb - 1, 2));
              flash = 1 - kb;
              if (!n.born_fired) { fireNode(n, 1); n.born_fired = true; }
            } else n.born_done = true;
          }
        }
        var rgb = heat ? heatColor(n.act) : hexRGB(n.color);
        var actK = heat ? (0.3 + 0.7 * n.act) : 1;
        var r = n.rad * zoom * scale * depth * (heat ? (0.7 + 0.6 * n.act) : 1);
        var freshGlow = reduceMotion ? 0 : (n.freshK || 0) * (0.5 + 0.5 * Math.sin(t * 0.003 + n.phase));
        ctx.globalCompositeOperation = 'lighter';
        var halo = r * (hover && n === hover ? 5 : (3.2 + thinkF * 1.4)) * pulse;
        var haloA = (dim ? 0.06 : ((0.5 * pulse + 0.18 * freshGlow + 0.5 * flash + 0.25 * thinkF) * depth)) * actK;
        if (lowFx) {
          // modalità leggera: niente gradiente radiale per nodo (il costo n.1)
          ctx.fillStyle = 'rgba(' + rgb + ',' + (haloA * 0.5) + ')';
          ctx.beginPath(); ctx.arc(sx, sy2, halo * 0.65 * (1 + flash), 0, 7); ctx.fill();
        } else {
          var gh = ctx.createRadialGradient(sx, sy2, 0, sx, sy2, halo);
          gh.addColorStop(0, 'rgba(' + rgb + ',' + haloA + ')');
          gh.addColorStop(1, 'rgba(' + rgb + ',0)');
          ctx.fillStyle = gh; ctx.beginPath(); ctx.arc(sx, sy2, halo * (1 + flash), 0, 7); ctx.fill();
        }
        if (flash > 0) {
          ctx.strokeStyle = 'rgba(255,255,255,' + (flash * 0.8) + ')'; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(sx, sy2, r + (1 - flash) * 46, 0, 7); ctx.stroke();
        }
        ctx.globalCompositeOperation = 'source-over';
        ctx.fillStyle = 'rgba(' + rgb + ',' + (dim ? 0.28 : Math.min(1, depth) * (heat ? actK : 1)) + ')';
        ctx.beginPath(); ctx.arc(sx, sy2, r * (0.9 + 0.1 * pulse), 0, 7); ctx.fill();
        if (!dim) { ctx.fillStyle = 'rgba(255,255,255,' + (0.85 * depth) + ')'; ctx.beginPath(); ctx.arc(sx, sy2, Math.max(0.8, r * 0.34), 0, 7); ctx.fill(); }
        if ((n === hover) || (hoverSet && hoverSet.has(n.id)) || (labelsAuto && !hover && n.deg >= 12)) {
          ctx.font = '600 11px Montserrat, sans-serif';
          ctx.fillStyle = (n === hover) ? '#fff' : 'rgba(236,239,244,.7)';
          ctx.textAlign = 'center';
          // fillText su canvas: i titoli con caratteri di chiusura tag sono INERTI
          ctx.fillText(n.title.length > 30 ? n.title.slice(0, 29) + '…' : n.title, sx, sy2 - r - 6);
        }
      }
    }

    // ── interazione (listener TRACCIATI per il destroy) ──────────────────────
    function onDown(ev) {
      var p = canvasXY(ev);
      dragging = true; moved = false; lastX = ev.clientX; lastY = ev.clientY;
      dragNode = pickNearest(p.x, p.y);
    }
    function onUp() {
      if (!moved && dragNode && !reduceMotion) clickFire(dragNode);
      dragging = false; dragNode = null;
    }
    function onMove(ev) {
      var p = canvasXY(ev);
      mouseX = p.x; mouseY = p.y;
      if (dragging) {
        var dx = ev.clientX - lastX, dy = ev.clientY - lastY;
        if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
        rot += dx * 0.006;
        tilt = Math.max(-1.35, Math.min(1.35, tilt + dy * 0.005));
        lastX = ev.clientX; lastY = ev.clientY;
      }
    }
    function onWheel(ev) {
      ev.preventDefault();
      zoom = Math.max(0.35, Math.min(3, zoom * (ev.deltaY < 0 ? 1.1 : 0.9)));
    }
    function onVis() {
      if (destroyed) return;
      if (document.hidden) { hiddenAt = performance.now(); cancelAnimationFrame(rafId); }
      else if (hiddenAt >= 0) {
        var gap = performance.now() - hiddenAt;
        if (t0 >= 0) t0 += gap;
        for (var i = 0; i < waves.length; i++) waves[i].t0 += gap;
        hiddenAt = -1;
        rafId = requestAnimationFrame(tick);
      }
    }
    canvas.addEventListener('mousedown', onDown);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('mousemove', onMove);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    document.addEventListener('visibilitychange', onVis);
    if (rmQuery && rmQuery.addEventListener) rmQuery.addEventListener('change', onRM);

    function tick(t) {
      if (destroyed) return;
      if (t0 < 0) t0 = t;
      // R4 · sotto ~30 fps CONTINUATIVI per >2s: alone semplificato, per sempre
      if (lastT && !lowFx && !reduceMotion) {
        var dtf = t - lastT;
        if (dtf > 33.4) { if (!slowFrom) slowFrom = t; else if (t - slowFrom > 2000) { lowFx = true; try { console.info('[brain3d] fps bassi per >2s: aloni semplificati'); } catch (e) {} } }
        else slowFrom = 0;
      }
      lastT = t;
      thinkF += ((thinking ? 1 : 0) - thinkF) * THINK_EASE;
      physT = t;
      if (!reduceMotion) drift(t);
      if (!dragging && !reduceMotion) rot += autoRot * (1 + thinkF * 0.8);
      var prev = hover;
      hover = (mouseX < 0) ? null : pickNearest(mouseX, mouseY);
      if (!reduceMotion && hover && hover !== lastFired) { fireNode(hover, 1); lastFired = hover; }
      if (!hover) lastFired = null;
      if (opts.onHover && hover !== prev) opts.onHover(hover || null, mouseX, mouseY);
      draw(t);
      rafId = requestAnimationFrame(tick);
    }
    resize();
    rafId = requestAnimationFrame(tick);

    // ── API pubblica ──────────────────────────────────────────────────────────
    return {
      setData: setData,
      fire: function (slug) {
        var n = byId.get(slug);
        if (n && !reduceMotion) clickFire(n);      // A9: niente impulsi in reduce-motion
      },
      setThink: function (on) { thinking = !!on; },
      setHeat: function (on) { heat = !!on; },
      setUsage: setUsage,
      destroy: function () {
        destroyed = true;
        cancelAnimationFrame(rafId);
        canvas.removeEventListener('mousedown', onDown);
        window.removeEventListener('mouseup', onUp);
        window.removeEventListener('mousemove', onMove);
        canvas.removeEventListener('wheel', onWheel);
        document.removeEventListener('visibilitychange', onVis);
        if (rmQuery && rmQuery.removeEventListener) rmQuery.removeEventListener('change', onRM);
        if (ro) ro.disconnect();
      },
    };
  }

  window.createBrain = createBrain;
})();
