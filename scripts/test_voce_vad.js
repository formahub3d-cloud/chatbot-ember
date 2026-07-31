#!/usr/bin/env node
/* C3 · Il barge-in non deve interrompersi da solo.
 *
 * Il difetto (31-07, prova col microfono di Andrea): la soglia imparava solo
 * nel silenzio → mentre la voce parlava restava al pavimento 0.045 e l'ECO
 * dagli altoparlanti la superava per 220ms → interrompi(), da capo, per
 * sempre. Questo test estrae la logica VERA dai marcatori EM_VAD di
 * widget/voce.js e simula i casi:
 *   1. uscita alta + microfono che sente SOLO l'eco → NON deve mai scattare
 *      (col vecchio pavimento fisso scattava: dimostrato);
 *   2. l'utente parla sopra → DEVE scattare (il barge-in resta vivo);
 *   3. l'accoppiamento K converge verso quello osservato, senza farsi
 *      gonfiare dalla voce dell'utente.
 *
 * Uso:  node scripts/test_voce_vad.js   (exit 0 = tutto ok)
 */
"use strict";
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "widget", "voce.js");
const code = fs.readFileSync(SRC, "utf8");
const m = code.match(/\/\* EM_VAD_BEGIN[\s\S]*?\*\/([\s\S]*?)\/\* EM_VAD_END \*\//);
if (!m) { console.error("FAIL: marcatori EM_VAD_BEGIN/END non trovati in widget/voce.js"); process.exit(1); }
// eslint-disable-next-line no-new-func
const { vadSoglia, vadImparaK } = new Function(m[1] + "\nreturn { vadSoglia, vadImparaK };")();

let failed = 0;
function caso(nome, fn) {
  try { fn(); console.log("  ok · " + nome); }
  catch (e) { failed++; console.error("FAIL · " + nome + " → " + e.message); }
}

const DT = 16.7;              // un frame a 60fps
const SOSTEGNO = 220;         // ms sopra soglia perché scatti (come nel modulo)

function simula({ out, eco, voce = 0, voceDa = 0, ms = 5000, k0 = 1.2, base = 0.008 }) {
  // riproduce il ciclo del modulo: apprendimento di K a ogni frame + conteggio
  // del sostegno sopra soglia. `voceDa`: quando l'utente inizia a parlare —
  // il barge tipico è A METÀ frase (dopo la finestra «fresco» dell'attacco,
  // dove per scelta si impara l'eco in fretta: intervenire proprio lì è il
  // trade-off accettato). Ritorna se è scattato e lo stato finale.
  let k = k0, over = 0, scattato = false, sogliaUlt = 0;
  for (let t = 350; t < ms; t += DT) {            // i primi 350ms sono ciechi, come nel modulo
    const rms = eco + (t >= voceDa ? voce : 0);
    k = vadImparaK(k, rms, out, t < 900);         // «fresco» = attacco della riproduzione
    sogliaUlt = vadSoglia(base, k, out);
    if (rms > sogliaUlt) { over += DT; if (over > SOSTEGNO) { scattato = true; break; } }
    else over = 0;
  }
  return { scattato, k, soglia: sogliaUlt };
}

caso("il difetto ESISTEVA: l'eco batteva il vecchio pavimento fisso 0.045", () => {
  const eco = 0.9 * 0.25;                          // iMac: mic e casse nello stesso mobile
  if (!(eco > 0.045)) throw new Error("premessa rotta: l'eco simulata non supera il vecchio pavimento");
});

caso("solo eco (uscita alta, nessuna voce umana): NON scatta — il caso di Andrea", () => {
  const r = simula({ out: 0.25, eco: 0.9 * 0.25 });
  if (r.scattato) throw new Error(`scattato con sola eco (soglia ${r.soglia.toFixed(3)})`);
});

caso("solo eco, accoppiamento FORTE (eco ≈ uscita piena): NON scatta", () => {
  const r = simula({ out: 0.3, eco: 0.3 });
  if (r.scattato) throw new Error(`scattato con eco piena (k=${r.k.toFixed(2)}, soglia ${r.soglia.toFixed(3)})`);
});

caso("l'utente parla sopra: DEVE scattare (il barge-in resta vivo)", () => {
  const eco = 0.9 * 0.25;
  const pre = simula({ out: 0.25, eco, ms: 3000 });          // K si assesta sull'eco vera
  const r = simula({ out: 0.25, eco, voce: 0.35, voceDa: 1500, ms: 4000, k0: pre.k });   // barge a metà frase
  if (!r.scattato) throw new Error(`NON scattato con voce vera sopra l'eco (soglia ${r.soglia.toFixed(3)})`);
});

caso("K converge verso l'accoppiamento osservato e la voce utente non lo gonfia", () => {
  const eco = 0.5 * 0.2;
  const assestato = simula({ out: 0.2, eco, ms: 4000 });
  if (Math.abs(assestato.k - 0.5) > 0.15) throw new Error(`k=${assestato.k.toFixed(2)}, atteso ≈0.50`);
  const conVoce = simula({ out: 0.2, eco, voce: 0.4, voceDa: 1000, ms: 2000, k0: assestato.k });
  if (conVoce.k > assestato.k + 0.1) throw new Error(`la voce ha gonfiato k: ${conVoce.k.toFixed(2)}`);
});

caso("accoppiamento più forte del previsto (casse a palla): l'attacco lo impara, niente auto-scatto", () => {
  const r = simula({ out: 0.2, eco: 0.2 * 2.0 });  // eco al mic DOPPIA dell'uscita misurata
  if (r.scattato) throw new Error(`scattato con eco forte (k=${r.k.toFixed(2)}, soglia ${r.soglia.toFixed(3)})`);
});

caso("senza uscita (idle) la soglia torna quella ambiente", () => {
  const s = vadSoglia(0.008, 1.2, 0);
  if (Math.abs(s - 0.045) > 1e-9) throw new Error(`soglia idle ${s}`);
});

if (failed) { console.error("\n" + failed + " casi FALLITI"); process.exit(1); }
console.log("\nIl barge-in non si auto-interrompe più, e resta interrompibile dall'utente.");
