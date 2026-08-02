"""V8/A · «Cosa so di te»: la memoria che si vede, si usa e si cancella.

Nasce dalla cosa migliore vista dentro Zoey OS — una pagina che elenca, per ogni
companion, quello che ha imparato di te — e dai suoi due difetti, che qui non si
ripetono.

**Difetto 1 · la confidenza finta.** In Zoey ogni memoria è al 70%: un numero
costante travestito da misura. Qui NON c'è nessuna percentuale, e non è una
mancanza — è la scelta. Una percentuale ha senso solo se dietro c'è un criterio;
gli unici criteri veri disponibili sono *quante volte l'hai detto* e *da dove
viene*, e sono già due numeri onesti: si mostrano com'è, un conteggio e una
frase. Vale la regola di sempre: senza dato la spia dice «—», mai un numero
plausibile.

**Difetto 2 · la memoria che non serve a niente.** Fra le memorie di Zoey c'era
«Andrea prefers Italian language for business communication», al 70% — e il
riassunto finale, nella stessa conversazione, era in inglese. Qui una preferenza
registrata **cambia la risposta successiva**: `preferenze()` produce valori
strutturati (lingua, lunghezza) che `main.do_chat` applica prima di rispondere, e
c'è un test che diventa rosso se smette di succedere. Il resto — i fatti senza
una chiave — entra nel prompt come contesto su chi sta parlando, mai come fonte.

**Perché non è una rifinitura.** Il GDPR dà il diritto di sapere cosa sai di una
persona (art. 15) e di farlo cancellare (art. 17). Oggi la risposta a «cosa sa di
me il vostro sistema?» sarebbe una procedura; con questo modulo è un elenco e un
bottone.

**Dimenticare cancella davvero.** Il progetto ha la regola «nessun DELETE: si
archivia», ma qui archiviare tenendo il testo sarebbe il contrario dell'art. 17.
Quindi `dimentica()` **svuota il contenuto** (fatto, citazione, valore) e lascia
una lapide: id, quando, chi. Resta la traccia che qualcosa è stato dimenticato —
non che cosa. È l'unico punto del sistema dove il testo sparisce davvero, ed è
voluto.

Persistenza: tabella `tenant_memory` (DDL `db/tenant_memory.sql`) quando Supabase
è configurato, altrimenti in memoria. La migrazione NON è un prerequisito
(regola 1 del V7): senza tabella la memoria vive finché vive il processo, e
`dbcheck` lo dichiara.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from threading import Lock

from . import tenants
from .config import settings
from .security import redact_pii

log = logging.getLogger("ember.memoria")

AGENTI = ("divina", "dante", "virgilio", "beatrice")
MAX_FATTO = 240
MAX_CITAZIONE = 300
MAX_PER_TENANT = 200        # tetto: una pagina che si legge, non un archivio

# Le CHIAVI sono il pezzo che rende la memoria utile invece che decorativa: un
# fatto con una chiave nota diventa un comportamento, non una riga di prompt.
# Tenerle poche e dichiarate è deliberato — una chiave che nessuno legge è la
# versione lenta della confidenza al 70%.
CHIAVI = {
    "lingua": ("it", "en"),
    "lunghezza": ("breve", "estesa"),
}

# Origine = da dove viene il fatto. Non è una scala di fiducia: sono due strade
# diverse, e la pagina le distingue a parole invece che con un colore.
ORIGINI = ("detto", "mano")

_lock = Lock()
_mem: list[dict] = []       # fallback: si azzera al redeploy, e la console lo dice


def enabled() -> bool:
    """True se la memoria è PERSISTENTE (Supabase configurato + tabella)."""
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


def _ora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


# ══════════════════════════════════════════════════════════════════════════
# Riconoscere una preferenza detta a voce alta — senza chiamare un modello
# ══════════════════════════════════════════════════════════════════════════
# Perché niente LLM: questa funzione gira su OGNI messaggio, anche a voce, dove
# il budget è la prima sillaba a 55 ms. Un round-trip in più si sentirebbe. E
# c'è una ragione migliore: un riconoscitore a regole sbaglia in modo
# prevedibile e si legge — un modello che «capisce» quando ricordarti qualcosa
# è esattamente il pezzo che non voglio non poter spiegare.
_PREF = (
    ("lingua", "it", re.compile(
        r"\b(?:parlami|rispondi(?:mi)?|scrivi(?:mi)?|continua(?:iamo)?)\b[^.?!]{0,30}\bin\s+italiano\b"
        r"|\bin\s+italiano\b[^.?!]{0,20}\b(?:per favore|grazie|d'ora in poi)\b"
        r"|\b(?:speak|answer|reply|write)\b[^.?!]{0,20}\bin\s+italian\b", re.I)),
    ("lingua", "en", re.compile(
        r"\b(?:parlami|rispondi(?:mi)?|scrivi(?:mi)?)\b[^.?!]{0,30}\bin\s+inglese\b"
        r"|\b(?:speak|answer|reply|write)\b[^.?!]{0,20}\bin\s+english\b", re.I)),
    ("lunghezza", "breve", re.compile(
        r"\b(?:rispondi|risposte|scrivi|stai)\b[^.?!]{0,25}\b(?:brev\w+|sintetic\w+|cort\w+)\b"
        r"|\b(?:sii|resta)\s+(?:brev\w+|sintetic\w+)\b"
        r"|\b(?:keep it short|be brief|be concise)\b", re.I)),
    ("lunghezza", "estesa", re.compile(
        r"\b(?:rispondi|risposte|spiega|scrivi)\b[^.?!]{0,25}\b(?:pi[uù] (?:in )?dettagli\w+|estes\w+|approfondit\w+)\b"
        r"|\b(?:in more detail|be thorough)\b", re.I)),
)

_FRASI = {
    ("lingua", "it"): "Preferisci che ti parli in italiano.",
    ("lingua", "en"): "You prefer answers in English.",
    ("lunghezza", "breve"): "Preferisci risposte brevi.",
    ("lunghezza", "estesa"): "Preferisci risposte estese, con i dettagli.",
}


def dalla_frase(testo: str) -> dict | None:
    """Una preferenza dichiarata esplicitamente, o None (il caso normale).

    Ritorna {chiave, valore, fatto, citazione}. La citazione è la frase VERA
    dell'utente: è la stessa regola delle proposte da conversazione — quello che
    si ricorda deve poter mostrare da dove viene.

    Non è estrazione di conoscenza (quella resta in `learned.py`, con la coda e
    la conferma umana): è un'istruzione che la persona ha appena dato. La
    differenza è che qui il consenso è l'atto stesso di dirlo — e comunque la
    console lo mostra nella bolla, con accanto il bottone per dimenticarlo."""
    t = str(testo or "").strip()
    if not t or len(t) > 400:
        return None
    # Il controllo PII sta sul messaggio INTERO, non sulla frase estratta: un
    # indirizzo email contiene un punto, la frase si taglierebbe lì dentro e
    # `mario@ats.it` diventerebbe una citazione che passa il controllo perché
    # mutilata. Meglio perdere una preferenza legittima detta accanto a un
    # indirizzo: senza citazione non c'è fonte, e senza fonte questa pagina
    # tornerebbe a essere il 70% di Zoey con un altro nome.
    if redact_pii(t) != t:
        return None
    for chiave, valore, rx in _PREF:
        m = rx.search(t)
        if not m:
            continue
        return {"chiave": chiave, "valore": valore,
                "fatto": _FRASI[(chiave, valore)], "citazione": _cita(t, m)}
    return None


_FINE_FRASE = ".?!\n"


def _cita(testo: str, m) -> str:
    """La frase in cui è comparsa la preferenza — non tutto il messaggio.

    «Ciao, tutto bene? Rispondimi in inglese d'ora in poi» deve mostrare la
    seconda frase: la prima non c'entra, e una citazione che comincia da un
    saluto sembra presa a caso."""
    inizio = max((testo.rfind(c, 0, m.start()) for c in _FINE_FRASE), default=-1) + 1
    tagli = [testo.find(c, m.end()) for c in _FINE_FRASE]
    fine = min([x for x in tagli if x >= 0], default=len(testo))
    return testo[inizio:fine].strip(" ,;:")[:MAX_CITAZIONE] or testo[:MAX_CITAZIONE]


# ══════════════════════════════════════════════════════════════════════════
# Lo store
# ══════════════════════════════════════════════════════════════════════════
_COLS = ("mem_id, tenant_code, agente, fatto, chiave, valore, origine, citazione, "
         "conferme, created_at, last_at, dimenticato_at, dimenticato_da")


def _riga(r) -> dict:
    return {"id": str(r[0]), "tenant": r[1] or "", "agente": r[2] or "divina",
            "fatto": r[3] or "", "chiave": r[4] or "", "valore": r[5] or "",
            "origine": r[6] or "detto", "citazione": r[7] or "",
            "conferme": int(r[8] or 1),
            "created_at": _iso(r[9]), "last_at": _iso(r[10]),
            "dimenticato_at": _iso(r[11]), "dimenticato_da": r[12] or ""}


def _iso(v) -> str:
    if not v:
        return ""
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def ricorda(tenant_code: str, fatto: str, chiave: str = "", valore: str = "",
            origine: str = "detto", citazione: str = "",
            agente: str = "divina") -> dict | None:
    """Registra (o CONFERMA) un fatto. Ridirlo non crea un doppione: incrementa
    `conferme` e aggiorna la data — che è l'unico criterio onesto che questa
    pagina possiede, ed è il motivo per cui esiste invece di una percentuale.

    None se il fatto è vuoto, se contiene dati personali, o se il tenant ha già
    raggiunto il tetto."""
    tenant_code = (tenant_code or "").strip()
    fatto = re.sub(r"\s+", " ", str(fatto or "")).strip()[:MAX_FATTO]
    if not tenant_code or not fatto:
        return None
    if redact_pii(fatto) != fatto:
        log.info("memoria: scartata (dati personali nel fatto)")
        return None
    agente = agente if agente in AGENTI else "divina"
    origine = origine if origine in ORIGINI else "detto"
    chiave = chiave if chiave in CHIAVI else ""
    valore = valore if (chiave and valore in CHIAVI[chiave]) else ("" if chiave else "")
    if chiave and not valore:
        return None                     # una chiave senza valore non cambia niente
    citazione = str(citazione or "").strip()[:MAX_CITAZIONE]
    if citazione and redact_pii(citazione) != citazione:
        citazione = ""                  # meglio senza fonte che con dentro una PII

    if enabled():
        try:
            return _db_ricorda(tenant_code, agente, fatto, chiave, valore,
                               origine, citazione)
        except Exception:
            log.warning("memoria: scrittura DB fallita, fallback memoria", exc_info=True)
    with _lock:
        vive = [m for m in _mem if m["tenant"] == tenant_code and not m["dimenticato_at"]]
        for m in vive:
            if m["agente"] == agente and _stessa(m, fatto, chiave):
                m["conferme"] += 1
                m["last_at"] = _ora()
                if citazione:
                    m["citazione"] = citazione
                if valore:
                    m["valore"] = valore
                return dict(m)
        if len(vive) >= MAX_PER_TENANT:
            return None
        m = {"id": uuid.uuid4().hex, "tenant": tenant_code, "agente": agente,
             "fatto": fatto, "chiave": chiave, "valore": valore, "origine": origine,
             "citazione": citazione, "conferme": 1, "created_at": _ora(),
             "last_at": _ora(), "dimenticato_at": "", "dimenticato_da": ""}
        _mem.append(m)
    return dict(m)


def _stessa(m: dict, fatto: str, chiave: str) -> bool:
    """Stesso fatto = stessa CHIAVE (una preferenza per chiave, l'ultima vince)
    oppure, senza chiave, lo stesso testo."""
    if chiave:
        return m["chiave"] == chiave
    return not m["chiave"] and _norm(m["fatto"]) == _norm(fatto)


def _db_ricorda(tenant_code, agente, fatto, chiave, valore, origine, citazione) -> dict:
    with tenants._conn() as c:
        with c.cursor() as cur:
            if chiave:
                cur.execute(f"SELECT {_COLS} FROM tenant_memory WHERE tenant_code=%s "
                            "AND agente=%s AND chiave=%s AND dimenticato_at IS NULL",
                            (tenant_code, agente, chiave))
            else:
                cur.execute(f"SELECT {_COLS} FROM tenant_memory WHERE tenant_code=%s "
                            "AND agente=%s AND chiave='' AND lower(fatto)=lower(%s) "
                            "AND dimenticato_at IS NULL", (tenant_code, agente, fatto))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE tenant_memory SET conferme=conferme+1, last_at=now(), "
                            "valore=COALESCE(NULLIF(%s,''), valore), "
                            "citazione=COALESCE(NULLIF(%s,''), citazione) "
                            f"WHERE mem_id=%s RETURNING {_COLS}",
                            (valore, citazione, row[0]))
            else:
                cur.execute(
                    "INSERT INTO tenant_memory (tenant_code, agente, fatto, chiave, "
                    "valore, origine, citazione) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    f"RETURNING {_COLS}",
                    (tenant_code, agente, fatto, chiave, valore, origine, citazione))
            out = _riga(cur.fetchone())
        c.commit()
    return out


def elenco(tenant_code: str, agente: str = "", includi_dimenticate: bool = False) -> list[dict]:
    """Quello che il sistema sa di questo tenant, più recente prima."""
    tenant_code = (tenant_code or "").strip()
    if not tenant_code:
        return []
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    sql = f"SELECT {_COLS} FROM tenant_memory WHERE tenant_code=%s"
                    par: list = [tenant_code]
                    if agente:
                        sql += " AND agente=%s"
                        par.append(agente)
                    if not includi_dimenticate:
                        sql += " AND dimenticato_at IS NULL"
                    cur.execute(sql + " ORDER BY last_at DESC LIMIT 300", par)
                    return [_riga(r) for r in cur.fetchall()]
        except Exception:
            log.warning("memoria: lettura DB fallita, fallback memoria", exc_info=True)
    with _lock:
        out = [dict(m) for m in _mem if m["tenant"] == tenant_code
               and (not agente or m["agente"] == agente)
               and (includi_dimenticate or not m["dimenticato_at"])]
    return sorted(out, key=lambda m: m["last_at"], reverse=True)


def dimentica(mem_id: str, da: str = "") -> bool:
    """Cancella DAVVERO il contenuto e lascia una lapide (id, quando, chi).

    È l'unico punto del sistema in cui un testo sparisce invece di archiviarsi,
    e la deroga è deliberata: l'art. 17 non si soddisfa con `status='archiviato'`
    e il testo ancora lì. Quello che resta è che qualcosa è stato dimenticato —
    non che cosa."""
    mem_id = (mem_id or "").strip()
    if not mem_id:
        return False
    da = str(da or "").strip()[:80]
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute("UPDATE tenant_memory SET fatto='', citazione='', "
                                "valore='', chiave='', dimenticato_at=now(), "
                                "dimenticato_da=%s WHERE mem_id::text=%s "
                                "AND dimenticato_at IS NULL", (da, mem_id))
                    tocca = cur.rowcount
                c.commit()
            return bool(tocca)
        except Exception:
            log.warning("memoria: dimentica su DB fallita", exc_info=True)
            return False
    with _lock:
        for m in _mem:
            if m["id"] == mem_id and not m["dimenticato_at"]:
                m.update(fatto="", citazione="", valore="", chiave="",
                         dimenticato_at=_ora(), dimenticato_da=da)
                return True
    return False


# ══════════════════════════════════════════════════════════════════════════
# A4 · La memoria si USA
# ══════════════════════════════════════════════════════════════════════════
def preferenze(tenant_code: str, agente: str = "") -> dict:
    """Le preferenze STRUTTURATE, pronte da applicare: {'lingua': 'en', …}.

    È il pezzo che separa una memoria vera da una vetrina: `main.do_chat` la
    legge PRIMA di rispondere, e la lingua registrata vince sul default del
    tenant (ma non su una lingua chiesta esplicitamente nella richiesta)."""
    out: dict[str, str] = {}
    for m in elenco(tenant_code, agente):
        if m["chiave"] and m["valore"]:
            out.setdefault(m["chiave"], m["valore"])
    return out


def per_prompt(tenant_code: str, agente: str = "", massimo: int = 8) -> list[str]:
    """I fatti da mettere davanti al modello, come CONTESTO su chi sta parlando.

    Mai come fonte: il prompt lo dice esplicitamente (`rag._memoria_block`),
    perché una preferenza ricordata non è un dato del cervello e non si cita."""
    return [m["fatto"] for m in elenco(tenant_code, agente) if m["fatto"]][:massimo]


def reset() -> None:
    """Solo per i test."""
    with _lock:
        _mem.clear()
