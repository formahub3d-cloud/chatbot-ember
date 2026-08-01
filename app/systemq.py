"""Fase 6 + task 16 · Le domande SUL SISTEMA e la conversazione normale.

«Dimmi cosa sai» non è una domanda sul contenuto: la ricerca semantica cerca
note simili alla frase, nessuna nota parla di «cosa so», e tornano frammenti
arbitrari. Serve un percorso diverso, non un recupero migliore. Lo stesso vale
per un saluto: chi dice «ciao» non deve sentirsi rispondere «non ho questa
informazione nelle aree a cui ho accesso» — un cliente che saluta e trova quel
muro chiude la finestra.

Due riconoscitori PRUDENTI (meglio un falso negativo che un collage):
  - saluto/convenevoli  → risposta cortese e deterministica, senza inventare
    contenuti (zero LLM: testabile offline, latenza zero, nessun rischio);
  - domanda sul sistema → risposta costruita dai METADATI dell'indice (note
    per area visibile, ultimo aggiornamento del vault, aree di accesso),
    compresi i BUCHI: dire cosa non si sa è metà del valore.
Fallback ESPLICITO: intento non riconosciuto → recupero normale. Mai collage.
«Cosa sai di X» si intercetta SOLO se X è un'area che il chiamante vede
davvero: altrimenti è una domanda di contenuto e va al retrieval.
"""
import logging
import re

log = logging.getLogger("ember.systemq")

# ── Saluti e convenevoli: match sull'INTERA frase, mai su un pezzo ───────────
_SALUTI = [
    (re.compile(r"^(ciao|salve|hey|ehi|buongiorno|buonasera|buonanotte|hola)"
                r"[\s!.,]*(divina)?[\s!.,]*$", re.I), "saluto"),
    (re.compile(r"^come (stai|va|andiamo)[\s?!.]*$", re.I), "come-stai"),
    (re.compile(r"^(ok[\s,]*)?(va bene[\s,]*)?(perfetto[\s,]*)?grazie( mille| tante)?[\s!.]*$", re.I), "grazie"),
    (re.compile(r"^(chi|cosa|che cosa) sei[\s?!.]*$", re.I), "chi-sei"),
    (re.compile(r"^(ci sei|tutto bene|mi senti)[\s?!.]*$", re.I), "ci-sei"),
    (re.compile(r"^(a dopo|a presto|buona giornata|arrivederci)[\s!.]*$", re.I), "congedo"),
]

_RISPOSTE_SALUTO = {
    "saluto": "Ciao! Sono qui. Chiedimi qualcosa sul tuo mondo — o dimmi «cosa sai» e ti racconto cosa ho in testa.",
    "come-stai": "Tutto acceso, grazie! Di cosa parliamo?",
    "grazie": "Di niente. Se serve altro sono qui.",
    "chi-sei": "Sono Divina, l'AI di FORMA: rispondo su ciò che c'è nel cervello aziendale e cito sempre le fonti. Chiedimi dei clienti, dei servizi — o dimmi «cosa sai».",
    "ci-sei": "Ci sono, e ti sento. Dimmi pure.",
    "congedo": "A presto! Resto qui, col cervello acceso.",
}

# ── Domande sul sistema ──────────────────────────────────────────────────────
# Esclusioni PRIMA di tutto: «sai dirmi…», «sai se…» sono domande di CONTENUTO.
_NON_SISTEMA = re.compile(r"\bsai\s+(dirmi|se|come|perch|quando|dove|quanto|cosa\s+costa)", re.I)
_SISTEMA = [
    ("di", re.compile(r"^(?:dimmi\s+)?(?:che\s+)?(?:cosa|che\s+cosa|che)\s+(?:sai|conosci)\s+(?:di|su|del(?:la)?|dei|dello)\s+(.{2,60}?)[\s?!.]*$", re.I)),
    ("cosa-sai", re.compile(r"^(?:dimmi\s+)?(?:che\s+)?(?:cosa|che\s+cosa|che)\s+(?:sai|conosci)(?:\s+fare)?[\s?!.]*$", re.I)),
    ("cosa-sai", re.compile(r"^cosa c'?è nel(?:\s+tuo)?\s+cervello[\s?!.]*$", re.I)),
    ("quante", re.compile(r"\bquant[ei]\s+(note|documenti|informazioni)\s+(hai|conosci|ci sono)", re.I)),
    ("clienti", re.compile(r"\b(quali|che)\s+clienti\s+(conosci|hai|segui|gestisci)", re.I)),
    ("aggiornamento", re.compile(r"(quando|quanto)\s+(ti\s+sei|sei\s+stat[ao]|sei)\s+aggiornat|ultimo aggiornamento", re.I)),
    ("buchi", re.compile(r"cosa\s+non\s+sai|cosa\s+ti\s+manca|dove\s+sei\s+debole", re.I)),
]


def saluto(q: str) -> str | None:
    """Il TIPO di convenevole, o None. Match sull'intera frase, max 40 char:
    «ciao, quanto costa la stampa?» NON è un saluto — va al retrieval."""
    q = (q or "").strip()
    if not q or len(q) > 40:
        return None
    for rx, kind in _SALUTI:
        if rx.match(q):
            return kind
    return None


def domanda_sistema(q: str):
    """(tipo, argomento|None) se la domanda è SUL sistema, altrimenti None."""
    q = (q or "").strip()
    if not q or len(q) > 120 or _NON_SISTEMA.search(q):
        return None
    for kind, rx in _SISTEMA:
        m = rx.search(q)
        if m:
            arg = m.group(1).strip() if (kind == "di" and m.groups()) else None
            return (kind, arg)
    return None


def quadro(grants) -> dict:
    """I numeri VERI dall'indice, per i grants del chiamante: note distinte per
    scope, data dell'ultimo aggiornamento del vault. Best-effort: quello che
    manca si dice, non si inventa. (Nei test si monkeypatcha questo.)"""
    from . import rag
    from .config import settings
    out = {"scopes": {}, "aggiornato": ""}
    try:
        from .ingest import vault_info
        vi = vault_info() or {}
        out["aggiornato"] = vi.get("date") or vi.get("commit_date") or ""
    except Exception:
        pass
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        c = rag.client()
        scopes = rag.scopes_of(grants) or []
        for s in scopes:
            if s == "*":
                continue
            try:
                flt = Filter(must=[FieldCondition(key="tenant", match=MatchValue(value=s))])
                slugs = set()
                offset = None
                for _ in range(5):                      # cap: 5×1000 chunk bastano e avanzano
                    pts, offset = c.scroll(collection_name=settings.qdrant_collection,
                                           scroll_filter=flt, limit=1000,
                                           with_payload=["slug"], offset=offset)
                    slugs.update(p.payload.get("slug") for p in pts if p.payload)
                    if offset is None:
                        break
                out["scopes"][s] = len(slugs)
            except Exception:
                out["scopes"][s] = None
    except Exception:
        log.warning("systemq: quadro non disponibile", exc_info=True)
    return out


def _fmt_scope(s: str, n) -> str:
    if n is None:
        return f"— {s}: non riesco a contare adesso"
    return f"— {s}: {n} not{'a' if n == 1 else 'e'}"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def rispondi_sistema(kind: str, arg, grants) -> str | None:
    """La risposta dai metadati. Per 'di <X>': SOLO se X è uno scope visibile
    (altrimenti None → retrieval normale: è una domanda di contenuto)."""
    qd = quadro(grants)
    scopes, agg = qd.get("scopes", {}), qd.get("aggiornato", "")
    coda_agg = f" Mi sono aggiornata l'ultima volta: {agg}." if agg else ""
    if kind == "di":
        chiave = _slug(arg)
        match = next((s for s in scopes if _slug(s) == chiave or chiave in _slug(s)), None)
        if match is None:
            return None                                  # contenuto, non sistema
        n = scopes[match]
        if not n:
            return (f"Di {arg} ho la cartella, ma quasi niente dentro: "
                    f"è uno dei miei buchi. Dire cosa non so è metà del mio lavoro."
                    + coda_agg)
        return (f"Di {arg} ho {n} not{'a' if n == 1 else 'e'} nel cervello."
                + coda_agg + " Chiedimi pure nel dettaglio: cito sempre da dove rispondo.")
    if kind == "clienti":
        cli = {s: n for s, n in scopes.items() if s not in ("forma-core", "andrea", "ovyon")}
        if not cli:
            return "Nel perimetro di questa chiave non vedo aree cliente." + coda_agg
        righe = ", ".join(f"{s} ({n} note)" for s, n in sorted(cli.items(), key=lambda x: -(x[1] or 0)))
        return f"I clienti che vedo da qui: {righe}." + coda_agg
    if kind == "aggiornamento":
        if agg:
            return f"L'ultimo aggiornamento del cervello è di: {agg}. Se ti serve più fresco, va lanciata una ingest."
        return "Non riesco a leggere la data dell'ultimo aggiornamento in questo momento: meglio dirlo che inventarla."
    if kind == "buchi":
        vuoti = [s for s, n in scopes.items() if not n]
        base = "Dire cosa non so è metà del mio valore. "
        if vuoti:
            return base + f"Le aree quasi vuote adesso: {', '.join(vuoti)}." + coda_agg
        return base + "Nessuna area visibile è vuota, ma i punti «da definire» nelle note restano il posto giusto dove guardare." + coda_agg
    # cosa-sai / quante
    if not scopes:
        return "In questo momento non riesco a leggere l'indice: meglio dirtelo che improvvisare." + coda_agg
    righe = "\n".join(_fmt_scope(s, n) for s, n in sorted(scopes.items(), key=lambda x: -(x[1] or 0)))
    tot = sum(n for n in scopes.values() if n)
    return (f"Ecco cosa ho in testa adesso — {tot} note, nelle aree che questa chiave può vedere:\n"
            f"{righe}\n"
            + (f"Ultimo aggiornamento: {agg}. " if agg else "")
            + "Chiedimi qualcosa in una di queste aree: rispondo citando le fonti, e se un dato non c'è te lo dico.")


def intercetta(question: str, grants) -> str | None:
    """Il punto d'ingresso: la risposta diretta, o None → retrieval normale."""
    k = saluto(question)
    if k:
        return _RISPOSTE_SALUTO[k]
    ds = domanda_sistema(question)
    if ds is None:
        return None
    return rispondi_sistema(ds[0], ds[1], grants)
