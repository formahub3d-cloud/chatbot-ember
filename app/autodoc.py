"""V11/D · Divina sa come funziona, e lo sa dal vault — non dal codice.

L'idea è di Andrea, ed è la più originale del giro:

    «Divina deve sapere come funziona e come si può migliorare. Non devi
     saperlo solo tu, ma anche lei.»

Oggi Divina sa tutto dei clienti di FORMA e **niente di sé stessa**. Se qualcuno
le chiede *«cosa puoi fare per la mia azienda?»* o *«come faccio a migliorarti?»*
risponde da istruzioni scritte nel codice — cioè da qualcosa che nessuno può
leggere, correggere o citare.

**La soluzione è la stessa architettura di tutto il resto: note nel vault.** Un
piccolo gruppo in `ovyon/divina/`, che descrivono cosa sa fare, come si alimenta,
cosa serve per farla rispondere meglio e cosa NON fa. Il vantaggio non è
filosofico: **quelle note si aggiornano senza toccare il codice**, e chiunque può
vedere se ciò che dice di sé è vero.

**Perché dal DISCO e non dall'indice.** Il percorso `ovyon/` è uno scope, e uno
scope è un permesso: un tenant cliente non lo ha, e non deve averlo — lì dentro
c'è anche altro. Farle rispondere allargando il filtro vorrebbe dire toccare
`build_filter` per una funzione di documentazione, cioè spostare una decisione di
sicurezza dentro un problema di prodotto. Queste note invece sono **pubbliche per
natura**: è ciò che si racconta a un cliente in una demo. Quindi hanno un canale
loro, in sola lettura, che non passa dal filtro e non lo tocca — e che espone
SOLO questa cartella, mai un percorso costruito da chi fa la domanda.

Le note restano indicizzate come tutte le altre (sono nel vault): chi ha lo scope
`ovyon` le trova anche dal retrieval normale. La fonte è una sola, i modi di
arrivarci due — ed è la stessa nota, quindi non possono divergere.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .config import settings

log = logging.getLogger("ember.autodoc")

# L'unica cartella leggibile da qui. Non è un parametro, ed è deliberato: un
# percorso che arriva dalla richiesta è il modo classico di leggere /etc/passwd.
CARTELLA = ("ovyon", "divina")
MAX_NOTE = 6
MAX_TESTO = 6000


def _dir() -> Path | None:
    base = (settings.vault_path or "").strip()
    if not base:
        return None
    d = Path(base).joinpath(*CARTELLA)
    return d if d.is_dir() else None


def disponibile() -> bool:
    return _dir() is not None


def note() -> list[dict]:
    """Le note di autodocumentazione: `{slug, title, text, path}`.

    Ordinate per nome, così l'ordine è quello che decide chi le scrive
    (`01-…`, `02-…`) e non l'ordine in cui il filesystem le restituisce."""
    d = _dir()
    if d is None:
        return []
    out = []
    for f in sorted(d.glob("*.md"))[:MAX_NOTE]:
        try:
            testo = f.read_text("utf-8")[:MAX_TESTO]
        except OSError:
            continue
        titolo = ""
        m = re.search(r"^title:\s*(.+)$", testo, re.M)
        if m:
            titolo = m.group(1).strip().strip('"')
        if not titolo:
            m = re.search(r"^#\s+(.+)$", testo, re.M)
            titolo = m.group(1).strip() if m else f.stem
        out.append({"slug": f.stem, "title": titolo, "text": _senza_frontmatter(testo),
                    "path": "/".join(CARTELLA) + "/" + f.name})
    return out


def _senza_frontmatter(t: str) -> str:
    if t.startswith("---"):
        fine = t.find("\n---", 3)
        if fine > 0:
            return t[fine + 4:].lstrip("\n")
    return t


# ── Le domande che riguardano Divina stessa ─────────────────────────────────
# Prudenti come tutti i riconoscitori del progetto: un falso negativo lascia il
# retrieval normale (che funziona), un falso positivo risponde di sé a chi
# chiedeva altro. Serve il SOGGETTO — «tu», «Divina» — perché «cosa sai fare»
# senza soggetto, dentro una conversazione su un cliente, non parla di lei.
_SU_DI_SE = re.compile(
    r"(?i)("
    r"cosa\s+(?:sai|puoi)\s+fare(?:\s+(?:tu|per\s+(?:me|la\s+mia|noi)))?|"
    r"migliorar(?:ti|e\s+divina)|"                    # «come faccio a migliorarti?»
    r"come\s+(?:funzioni|funziona\s+divina|ti\s+alimenti|impari|ti\s+alleno)|"
    r"chi\s+sei|a\s+cosa\s+servi|cosa\s+non\s+(?:sai|puoi)\s+fare|"
    r"come\s+(?:ti\s+)?(?:si\s+)?insegna"
    r")")


def e_su_di_se(domanda: str) -> bool:
    d = (domanda or "").strip()
    return bool(d) and bool(_SU_DI_SE.search(d))


def contesto(domanda: str) -> dict | None:
    """Il CONTENUTO da dare al modello quando la domanda riguarda Divina, con le
    fonti — apribili e correggibili come qualunque altra nota.

    `None` quando non c'è niente da dire: e allora si torna al retrieval
    normale, non si inventa una risposta di circostanza. Se la cartella manca,
    lo dice `degrado.per("autodoc")` nella schermata dove si vede."""
    if not e_su_di_se(domanda):
        return None
    n = note()
    if not n:
        return None
    return {
        "content": "\n\n".join(f"### {x['title']}\n{x['text']}" for x in n),
        "sources": [{"slug": x["slug"], "title": x["title"], "path": x["path"],
                     "tenant": "ovyon"} for x in n],
    }


# ── D2 · Il percorso, non solo lo stato ─────────────────────────────────────
# «Cosa sto consegnando e perché» significa saper dire a che punto è il lavoro
# con quel cliente. Il dato c'è già — le note della sua KB, i buchi, le proposte
# in coda: manca che sappia raccontarlo. Niente numeri inventati: se una delle
# tre fonti non risponde, quella riga non si scrive.
SEZIONI_ATTESE = ("orari", "prezzi", "contatti", "servizi", "domande frequenti")


def punto_del_lavoro(scope: str, note_cliente: list[dict], buchi: list[dict] | None = None,
                     proposte: int = 0) -> dict:
    """A che punto è la knowledge base di un cliente, in una forma che si può
    dire a voce. Funzione pura: i dati glieli passa chi li ha già."""
    testi = " ".join(((n.get("title") or "") + " " + (n.get("text") or "")).lower()
                     for n in (note_cliente or []))
    mancano = [s for s in SEZIONI_ATTESE if s.split()[0] not in testi]
    n = len(note_cliente or [])
    frasi = []
    frasi.append(f"La knowledge base di {scope} ha "
                 f"{'una voce' if n == 1 else str(n) + ' voci'}." if n
                 else f"La knowledge base di {scope} è ancora vuota.")
    if mancano:
        elenco = mancano[0] if len(mancano) == 1 else ", ".join(mancano[:-1]) + " e " + mancano[-1]
        frasi.append(f"Mancano {elenco}: finché non ci sono, a chi lo chiede il bot "
                     "risponde che non lo sa.")
    if proposte:
        frasi.append(f"Ci {'è una proposta' if proposte == 1 else f'sono {proposte} proposte'} "
                     "in attesa di essere approvata." if proposte == 1 else
                     f"Ci sono {proposte} proposte in attesa di essere approvate.")
    if buchi:
        frasi.append(f"E {'una domanda è rimasta' if len(buchi) == 1 else str(len(buchi)) + ' domande sono rimaste'} "
                     "senza risposta.")
    return {"scope": scope, "voci": n, "mancano": mancano, "proposte": proposte,
            "racconto": " ".join(frasi)}
