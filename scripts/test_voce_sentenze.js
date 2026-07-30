#!/usr/bin/env node
/* Test del chunker di frasi della voce continua (PR1).
 *
 * La funzione emSentenze vive DENTRO widget/embed.js (file unico, niente
 * build): questo script la estrae dai marcatori EM_SENTENZE_BEGIN/END e la
 * mette alla prova sui tagli pericolosi dell'italiano scritto. Stessa
 * filosofia del contract test della console: il codice vero, non una copia.
 *
 * Uso:  node scripts/test_voce_sentenze.js   (exit 0 = tutto ok)
 */
"use strict";
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "widget", "embed.js");
const code = fs.readFileSync(SRC, "utf8");
const m = code.match(/\/\* EM_SENTENZE_BEGIN[\s\S]*?\*\/([\s\S]*?)\/\* EM_SENTENZE_END \*\//);
if (!m) { console.error("FAIL: marcatori EM_SENTENZE_BEGIN/END non trovati in widget/embed.js"); process.exit(1); }

// eslint-disable-next-line no-new-func
const emSentenze = new Function(m[1] + "\nreturn emSentenze;")();

let failed = 0;
function eq(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
function caso(nome, fn) {
  try { fn(); console.log("  ok · " + nome); }
  catch (e) { failed++; console.error("FAIL · " + nome + " → " + e.message); }
}
function attesi(testo, frasi, opts) {
  const r = emSentenze(testo, !(opts && opts.noflush));
  if (!eq(r.frasi, frasi)) throw new Error("attese " + JSON.stringify(frasi) + ", avute " + JSON.stringify(r.frasi));
  return r;
}

caso("due frasi semplici", () => attesi("Ciao. Come stai?", ["Ciao.", "Come stai?"]));
caso("Dott. non spezza", () => attesi("Il Dott. Rossi è qui. Bene.", ["Il Dott. Rossi è qui.", "Bene."]));
caso("S.r.l. non spezza", () => attesi("La S.r.l. ha sede a Roma. Fine.", ["La S.r.l. ha sede a Roma.", "Fine."]));
caso("art. 3 non spezza", () => attesi("Vedi l'art. 3 del contratto. Ok bene.", ["Vedi l'art. 3 del contratto.", "Ok bene."]));
caso("numero con separatore", () => attesi("Costa 1.234,56 euro al mese. Caro no?", ["Costa 1.234,56 euro al mese.", "Caro no?"]));
caso("iniziale di nome", () => attesi("Parla con G. Verdi domani. Poi dimmi.", ["Parla con G. Verdi domani.", "Poi dimmi."]));
caso("S.p.A. a metà frase", () => attesi("FORMA S.p.A. vende servizi. Molti.", ["FORMA S.p.A. vende servizi.", "Molti."]));
caso("elenco puntato: a-capo = confine", () => attesi("Ecco i punti:\n- primo punto\n- secondo punto",
  ["Ecco i punti:", "- primo punto", "- secondo punto"]));
caso("elenco numerato: il numero solo non si pronuncia", () => {
  const r = emSentenze("1. Primo elemento\n2. Secondo elemento\n", true);
  if (r.frasi.some(f => /^\d+\.$/.test(f))) throw new Error("numero nudo tra le frasi: " + JSON.stringify(r.frasi));
  if (!eq(r.frasi, ["Primo elemento", "Secondo elemento"])) throw new Error("avute " + JSON.stringify(r.frasi));
});
caso("puntini di sospensione + minuscola: nessun taglio", () => attesi("Vediamo... forse sì. Anzi no!", ["Vediamo... forse sì.", "Anzi no!"]));
caso("puntini di sospensione + maiuscola: taglio", () => attesi("Aspetta... Ora ci sono. Bene.", ["Aspetta...", "Ora ci sono.", "Bene."]));
caso("ellissi tipografica … come i tre punti", () => attesi("Vediamo… forse sì. Chiaro?", ["Vediamo… forse sì.", "Chiaro?"]));
caso("?! doppio", () => attesi("Davvero?! Non ci credo.", ["Davvero?!", "Non ci credo."]));
caso("senza flush l'ultima frase resta nel buffer", () => {
  const r = emSentenze("Prima frase. Seconda incompl", false);
  if (!eq(r.frasi, ["Prima frase."])) throw new Error("avute " + JSON.stringify(r.frasi));
  if (r.resto.trim() !== "Seconda incompl") throw new Error("resto: " + JSON.stringify(r.resto));
});
caso("streaming: 'art.' a fine buffer NON spezza (aspetta conferma)", () => {
  const r = emSentenze("Vedi l'art.", false);
  if (r.frasi.length) throw new Error("spezzato troppo presto: " + JSON.stringify(r.frasi));
});
caso("feed incrementale carattere per carattere = feed intero", () => {
  const testo = "Il Dott. Rossi vede l'art. 3. Costa 1.234,56 euro. Ecco:\n- punto uno\nChiaro?";
  const intero = emSentenze(testo, true).frasi;
  let buf = "", frasi = [];
  for (const c of testo) { buf += c; const r = emSentenze(buf, false); frasi.push(...r.frasi); buf = r.resto; }
  const r = emSentenze(buf, true); frasi.push(...r.frasi);
  if (!eq(frasi, intero)) throw new Error("incrementale " + JSON.stringify(frasi) + " ≠ intero " + JSON.stringify(intero));
});
caso("flush di testo senza punteggiatura finale", () => attesi("Certo, posso aiutarti", ["Certo, posso aiutarti"]));

if (failed) { console.error("\n" + failed + " casi FALLITI"); process.exit(1); }
console.log("\nTutti i casi del chunker passano.");
