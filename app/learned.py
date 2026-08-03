"""V6/B3 · Le conversazioni che diventano cervello.

Andrea l'ha chiesta come «una knowledge base che tiene i contenuti delle
conversazioni per auto-migliorarsi». I binari esistevano quasi tutti — write-back
con `origin=conversazione` (il server marca «NON verificato»), la coda
`/admin/proposals` con la sua vista in console. Mancava il pezzo in mezzo:
**chi decide cosa vale la pena ricordare.**

Questo modulo è quel pezzo, e nient'altro: a fine conversazione (o su richiesta)
propone da ZERO a TRE «cose imparate», ognuna **con la citazione del punto della
conversazione da cui viene**. Le proposte vanno nella coda; approvate diventano
una nota nel vault, marcata come nata da conversazione; rifiutate spariscono.

Le tre regole non negoziabili, applicate qui in codice e non per convenzione:

1. **Mai salvare in automatico.** Questo modulo NON scrive: ritorna candidati.
   La scrittura resta il write-back a due tempi, con la conferma di un umano.
2. **Ogni proposta porta la sua fonte.** Una citazione che non si ritrova
   davvero nella conversazione fa CADERE la proposta (`_cita_vera`): una nota
   senza provenienza è una voce di corridoio, e qui non passa.
3. **Zero dati personali.** Un candidato il cui testo cambia sotto
   `redact_pii` viene scartato, non redatto: le conversazioni coi clienti
   *sono* dati personali e il motore gira in US West — meglio perdere un
   candidato che tenerne uno di troppo. E `andrea-aloia/human/` non c'entra
   mai: nessuna proposta può indirizzarsi lì (`_scope_ok`).
"""
from __future__ import annotations

import json
import logging
import re

from .providers import chat
from .security import redact_pii, cap_input

log = logging.getLogger("ember.learned")

MAX_ITEMS = 3            # «da zero a tre»: il tetto è del disegno, non del modello
MIN_TURNS = 2            # sotto due turni non c'è una conversazione da cui imparare
_MAX_HISTORY = 20        # ultimi turni considerati (il resto è già cervello o rumore)

# Scope su cui una proposta non può MAI atterrare. `andrea-aloia/human/` è fuori
# dall'indicizzazione per scelta (dati sanitari = categoria speciale GDPR): il
# write-back scrive comunque in `<cartella>/generati/`, ma il divieto va scritto
# dove si legge, non dedotto da come è fatto un percorso altrove.
SCOPE_VIETATI = frozenset({"human", "andrea-human", "andrea-aloia/human"})

_PROMPT_IT = """Sei l'archivista del cervello di FORMA. Leggi la conversazione qui sotto e
individua ciò che vale la pena RICORDARE: fatti stabili e riutilizzabili emersi dalla
conversazione e che il cervello non aveva già.

Regole, tassative:
- da ZERO a {max} elementi. Zero è una risposta giusta e frequente: se non è emerso
  nulla di stabile, restituisci una lista vuota.
- NON proporre: opinioni, cortesie, il riassunto della conversazione, cose che erano
  già nel CONTENUTO citato, o compiti da fare (quelli sono task, non conoscenza).
- ogni elemento deve avere una CITAZIONE: un frammento COPIATO ALLA LETTERA dalla
  conversazione, fra 15 e 200 caratteri, che dimostri da dove viene.
- NIENTE dati personali: nomi di persone fisiche, email, telefoni, IBAN, codici
  fiscali, indirizzi. Se un fatto non si può scrivere senza, scartalo.

Rispondi SOLO con JSON valido, senza testo attorno:
{{"imparato": [{{"titolo": "...", "contenuto": "...", "citazione": "..."}}]}}

CONVERSAZIONE:
{conversazione}
"""


def _turni(history) -> list[dict]:
    """Normalizza la history del client in turni {ruolo, testo}, ultimi N."""
    out: list[dict] = []
    for h in list(history or [])[-_MAX_HISTORY:]:
        if not isinstance(h, dict):
            continue
        testo = (h.get("content") or "").strip()
        if not testo:
            continue
        ruolo = "Utente" if h.get("role") == "user" else "Divina"
        out.append({"ruolo": ruolo, "testo": testo[:1500]})
    return out


def _testo_conversazione(turni: list[dict]) -> str:
    return "\n".join(f"{t['ruolo']}: {t['testo']}" for t in turni)


def _norm(s: str) -> str:
    """Confronto tollerante: spazi collassati, minuscole, virgolette uniformate."""
    s = re.sub(r"[“”„«»\"']", "'", str(s or ""))
    return re.sub(r"\s+", " ", s).strip().lower()


def _cita_vera(citazione: str, conversazione: str) -> bool:
    """Regola 2 · La citazione deve trovarsi DAVVERO nella conversazione.

    Un modello che «cita» ricostruendo a memoria è il modo esatto in cui una
    voce di corridoio diventa una nota: qui non passa. Il confronto è
    normalizzato (spazi/maiuscole/virgolette) ma resta un confronto letterale."""
    c = _norm(citazione)
    return 15 <= len(c) <= 200 and c in _norm(conversazione)


def _senza_pii(*parti: str) -> bool:
    """Regola 3 · Nessun candidato con PII. Si SCARTA, non si redige: una nota
    con «[email]» dentro è peggio di una nota che non esiste."""
    for p in parti:
        testo = str(p or "")
        if testo and redact_pii(testo) != testo:
            return False
    return True


def _scope_ok(scope: str) -> bool:
    """Nessuna proposta può indirizzarsi alla scheda personale (fuori indice)."""
    s = (scope or "").strip().lower()
    return bool(s) and s not in SCOPE_VIETATI and "human" not in s.split("/")


def _parse(raw: str) -> list[dict]:
    """Estrae la lista dal JSON del modello, tollerando il testo attorno."""
    testo = str(raw or "").strip()
    if not testo:
        return []
    if not testo.startswith("{"):
        i, j = testo.find("{"), testo.rfind("}")
        if i < 0 or j <= i:
            return []
        testo = testo[i:j + 1]
    try:
        dati = json.loads(testo)
    except Exception:
        log.info("learned: risposta non JSON, nessuna proposta")
        return []
    voci = dati.get("imparato") if isinstance(dati, dict) else dati
    return [v for v in (voci or []) if isinstance(v, dict)]


def filtra(voci, conversazione: str, scope: str) -> list[dict]:
    """Applica le tre regole ai candidati grezzi. Funzione PURA e testabile:
    è qui che si guarda se il disegno regge, non dentro una chiamata LLM."""
    if not _scope_ok(scope):
        return []
    out: list[dict] = []
    for v in voci or []:
        titolo = cap_input(str(v.get("titolo") or "").strip(), 160)
        contenuto = cap_input(str(v.get("contenuto") or "").strip(), 1200)
        citazione = str(v.get("citazione") or "").strip()[:300]
        if not titolo or not contenuto:
            continue
        if not _cita_vera(citazione, conversazione):
            log.info("learned: scartata (citazione non verificabile) · %r", titolo[:60])
            continue
        if not _senza_pii(titolo, contenuto, citazione):
            log.info("learned: scartata (dati personali) · %r", titolo[:60])
            continue
        out.append({"titolo": titolo, "contenuto": contenuto,
                    "citazione": citazione, "scope": scope})
        if len(out) >= MAX_ITEMS:
            break
    return out


def proponi(history, scope: str) -> list[dict]:
    """Da zero a tre «cose imparate» dalla conversazione. NON scrive nulla.

    Ritorna una lista di dict {titolo, contenuto, citazione, scope}. Lista vuota
    è un esito normale — anzi, quello più frequente: si propone solo ciò che è
    stabile, riutilizzabile e dimostrabile con un pezzo di conversazione."""
    turni = _turni(history)
    if len(turni) < MIN_TURNS or not _scope_ok(scope):
        return []
    conversazione = _testo_conversazione(turni)
    prompt = _PROMPT_IT.format(max=MAX_ITEMS, conversazione=conversazione)
    try:
        raw = chat("Rispondi solo con JSON valido.", prompt)
    except Exception:
        log.warning("learned: il modello non ha risposto", exc_info=True)
        return []
    return filtra(_parse(raw), conversazione, scope)


# ── V11/D3 · Le conclusioni, non solo le cose da ricordare ───────────────────
# `proponi()` risponde a «cosa vale la pena ricordare». Dopo una conversazione
# con un CLIENTE serve un passo diverso e più utile a lui: **cosa è emerso e
# cosa conviene fare**. Sono due domande distinte, e la seconda non si ricava
# dalla prima — una preferenza da ricordare non è un'azione da proporre.
#
# Le due cautele restano identiche, perché il rischio è lo stesso: ogni riga
# porta la CITAZIONE dalla conversazione e viene scartata se la citazione non si
# ritrova (`_cita_vera`, la stessa funzione), e niente viene scritto — è una
# proposta finché non la guarda una persona.
MAX_CONCLUSIONI = 3

_PROMPT_CONCL_IT = (
    "Leggi questa conversazione fra un'assistente e una persona di un'azienda.\n"
    "Rispondi con un JSON: {{\"conclusioni\": [{{\"emerso\": \"…\", \"conviene\": \"…\", "
    "\"citazione\": \"…\"}}]}}\n"
    "Da ZERO a {max} voci — zero è l'esito giusto quando non è emerso niente di "
    "concreto, e vale più di tre voci generiche.\n"
    "REGOLE, tutte obbligatorie:\n"
    "- `emerso`: un fatto detto nella conversazione, in una riga. Mai una deduzione.\n"
    "- `conviene`: una cosa concreta da fare, in una riga, rivolta all'azienda.\n"
    "- `citazione`: una frase COPIATA ALLA LETTERA dalla conversazione che regge "
    "`emerso`. Se non riesci a copiarne una, salta la voce.\n"
    "- Niente nomi di persone, email, telefoni.\n\n"
    "CONVERSAZIONE:\n{conversazione}"
)


def conclusioni(history, scope: str) -> list[dict]:
    """Da zero a tre conclusioni: cosa è emerso, cosa conviene fare. NON scrive.

    Ritorna `[{emerso, conviene, citazione, scope}]`. La lista vuota è l'esito
    più frequente ed è quello giusto: una conversazione in cui non è emerso
    niente esiste, e inventarle una conclusione è peggio che tacere."""
    turni = _turni(history)
    if len(turni) < MIN_TURNS or not _scope_ok(scope):
        return []
    conversazione = _testo_conversazione(turni)
    try:
        raw = chat("Rispondi solo con JSON valido.",
                   _PROMPT_CONCL_IT.format(max=MAX_CONCLUSIONI, conversazione=conversazione))
    except Exception:
        log.warning("learned: il modello non ha risposto (conclusioni)", exc_info=True)
        return []
    out = []
    for v in (_parse_conclusioni(raw))[:MAX_CONCLUSIONI]:
        em, co, ci = v.get("emerso", ""), v.get("conviene", ""), v.get("citazione", "")
        if not (em and co and ci):
            continue
        if not _cita_vera(ci, conversazione):
            continue                       # detta bene, mai detta: cade
        if not _senza_pii(em, co, ci):
            continue                       # scartata, non redatta: stessa scelta di sempre
        out.append({"emerso": em.strip(), "conviene": co.strip(),
                    "citazione": ci.strip(), "scope": scope})
    return out


def _parse_conclusioni(raw: str) -> list[dict]:
    import json as _json
    import re as _re
    t = (raw or "").strip()
    m = _re.search(r"\{.*\}", t, _re.S)
    if not m:
        return []
    try:
        d = _json.loads(m.group(0))
    except ValueError:
        return []
    v = d.get("conclusioni")
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
