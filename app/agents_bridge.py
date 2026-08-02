"""Ponte Divina → agenti Divina (ovy-orchestrator) — capability OPT-IN.

Quando la chat Divina riceve un COMPITO (non semplice Q&A), può instradarlo all'agente
Divina giusto (Dante/Virgilio/Beatrice) invece di rispondere col RAG sul cervello.
Divina (servizio separato) espone `POST {DIVINA_URL}/agents/route` (Bearer admin) e
ritorna `{routed, agent, skill, output, confidence, web_sources?}` oppure, se non
instrada, un dict con `routed:false` (eventuale suggerimento).

Regole (non negoziabili):
  - OFF di default: opera SOLO se `settings.agents_bridge` E DIVINA_URL +
    DIVINA_ADMIN_TOKEN sono configurati. Altrimenti INERTE — `route()` ritorna None e
    NON fa alcuna chiamata di rete → /chat resta identico a oggi (RAG).
  - Scope: a Divina si passa SOLO il `tenant_code`; lo scope lo applica Divina con la
    sua RLS. Il ponte NON tocca i grant né il filtro Qdrant del RAG (scope invariato).
  - Fallback pulito: rete irraggiungibile/errore → `route()` ritorna None e il chiamante
    ripiega sul RAG. Con `routed:false` il chiamante ripiega ugualmente. Mai un errore secco.
  - Nessuna dipendenza nuova: usa `httpx`, lo stesso client HTTP già in Divina.
  - Nessun segreto nei log; niente contenuti sensibili loggati (GDPR).

Se un giorno cambia l'orchestratore, cambia SOLO questo file (provider-agnostico).
"""
import logging
import re as _re
import time
from threading import Lock

import httpx

from .config import settings

log = logging.getLogger("ember.agents_bridge")

# Verbi imperativi tipici di un COMPITO (non di una semplice domanda). Euristico
# volutamente minimale e conservativo, usato SOLO se settings.agents_auto è true.
_TASK_VERBS = (
    "scrivi", "analizza", "prepara", "genera", "crea", "redigi", "calcola",
    "riassumi", "traduci", "progetta", "pianifica", "elabora", "compila",
    "imposta", "organizza",
)


def enabled() -> bool:
    """True se il ponte può operare: flag AGENTS_BRIDGE attivo E Divina configurata
    (URL + token). Senza tutto questo il ponte resta inerte a prescindere dai trigger."""
    return bool(settings.agents_bridge
                and settings.divina_url.strip()
                and settings.divina_admin_token.strip())


# V7/A2 · Le persone non parlano all'imperativo. «mi prepari i solleciti?»,
# «puoi scrivere la mail?», «vorrei un'analisi dei margini» sono compiti quanto
# «prepara i solleciti», ma la prima versione dell'euristico ne riconosceva uno
# su quattro: guardava solo la PRIMA parola. Da qui in poi si guardano anche le
# forme di cortesia — che in italiano sono il modo normale di chiedere una cosa,
# non un caso limite.
_CORTESIA = _re.compile(
    r"(?i)^\s*(?:mi\s+|ci\s+)?(?:puoi|potresti|riesci\s+a|sapresti|riusciresti)\b"
    r"|^\s*(?:vorrei|volevo|avrei\s+bisogno|mi\s+serve|mi\s+servirebbe|ho\s+bisogno|"
    r"per\s+favore|per\s+cortesia)\b"
    r"|^\s*mi\s+[a-zà-ù]+i\b"
)
# radici dei verbi-compito: «prepari/preparare/preparami» → prepar…
_RADICI = tuple(v[:-1] for v in _TASK_VERBS)


def is_task_like(message: str) -> bool:
    """Euristico leggero: il messaggio sembra un COMPITO (non una domanda)?

    Due strade, entrambe prudenti: un verbo imperativo come prima parola, oppure
    una forma di cortesia seguita — entro poche parole — da un verbo che sappiamo
    fare. È solo un suggerimento per l'auto-instradamento (settings.agents_auto,
    spento di default); il flag esplicito `agent:true` resta la via primaria e il
    fallback al RAG è sempre pulito. Un falso positivo costa una chiamata al
    ponte, non una risposta sbagliata: per questo si può permettere di allargare."""
    m = (message or "").strip().lower()
    if not m:
        return False
    parole = [w.strip('.,:;!?"\'') for w in m.split()]
    if parole and parole[0] in _TASK_VERBS:
        return True
    if _CORTESIA.search(m):
        return any(w.startswith(_RADICI) for w in parole[:7])
    return False


def route(tenant_code: str, message: str, history=None, timeout: float = 30.0,
          agent: str | None = None) -> dict | None:
    """Instrada il messaggio all'agente Divina giusto. Ritorna il dict di Divina
    (`{routed, agent, skill, output, confidence, web_sources?}`) o None se inerte/errore.

    INERTE (ritorna None, nessuna chiamata di rete) se il ponte è disabilitato o manca
    il `tenant_code`/il messaggio. Gli errori di rete/HTTP sono assorbiti (ritorna None,
    log senza segreti): il ponte è additivo e non deve MAI far esplodere /chat → il
    chiamante ripiega sul RAG. Si passa a Divina SOLO il `tenant_code`: lo scope lo
    applica Divina con la sua RLS. `agent` (opzionale) = companion scelto ESPLICITAMENTE
    dall'utente nella console; un orchestratore datato ignora il campo extra (additivo).
    """
    if not enabled():
        return None
    code = (tenant_code or "").strip()
    if not code or not (message or "").strip():
        return None
    url = settings.divina_url.strip().rstrip("/") + "/agents/route"
    payload = {"tenant": code, "input": message, "history": history or []}
    if agent:
        payload["agent"] = agent
    try:
        r = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.divina_admin_token}"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        # niente input/segreti nel log: solo il fatto che è fallita → fallback al RAG.
        log.warning("agents_bridge: instradamento a Divina fallito (fallback al RAG)")
        return None
    if not isinstance(data, dict):
        return None
    return data


# ══════════════════════════════════════════════════════════════════════════
# V9/C · Le capacità raggiungibili dalla CONVERSAZIONE (audit-2026-07-31-06)
# ══════════════════════════════════════════════════════════════════════════
# Le 42 skill esistono, la Squadra le mostra, Caronte ha la sua — e dalla chat
# non ci si arriva: `rag.py` non le nomina mai. Il criterio del V6 vale identico
# qui: **una capacità esiste quando qualcuno può usarla senza sapere come si
# chiama.** Chi scrive «cerca chi vende stampa 3D a Benevento» non deve sapere
# che esiste una skill che si chiama `customer-research`.
#
# Il V7 aveva messo il riconoscitore NELLA CONSOLE, leggendo `/agents`: giusto
# per non duplicare il catalogo, ma esiste solo lì. Nel widget sul sito di un
# cliente non c'è, e **a voce non c'è affatto** — un chip non si può cliccare
# mentre si parla. Perciò adesso il riconoscimento sta anche qui, e il catalogo
# continua a NON essere duplicato: si legge da `/agents` e si tiene in RAM per
# qualche minuto. Se l'orchestratore è giù, non si suggerisce niente — mai un
# errore in chat per un suggerimento.
#
# Il vincolo non si tocca: qui si OFFRE, non si esegue. Ciò che ha effetto fuori
# nasce `in-approvazione` e col livello 3 spento non si accoda nemmeno; porta
# principale e porta di servizio restano chiuse dal V5c.

_CAT_TTL = 600.0                 # dieci minuti: il catalogo cambia con un deploy
_cat_lock = Lock()
_cat: list[dict] = []
_cat_at = 0.0

# Parole che non distinguono nulla: senza toglierle, «come» e «per» darebbero
# punteggio a qualunque skill e il suggerimento diventerebbe rumore.
_STOP = frozenset("""
il lo la i gli le un uno una di a da in con su per tra fra e o ma se che chi cui
come cosa quale quali quando dove perche perché quanto mi ti ci vi si non del
della dello dei degli delle al alla allo ai agli alle dal dalla nel nella sul
sulla piu più molto tutto tutti essere avere fare puoi potresti vorrei voglio
serve bisogno favore cortesia grazie ciao adesso oggi
""".split())


def _parole(testo: str) -> set[str]:
    return {w for w in _re.split(r"[^a-zà-ù0-9]+", (testo or "").lower())
            if len(w) > 2 and w not in _STOP}


def catalogo(timeout: float = 8.0) -> list[dict]:
    """Le capacità dell'orchestratore → [{agente, skill, role, desc, parole}].

    NON è una copia: è una lettura con scadenza. Il catalogo vive in un posto
    solo (`/agents`), e se un giorno lo si duplicasse qui sarebbe la terza copia
    della stessa cosa — lo stesso errore della console duplicata."""
    global _cat, _cat_at
    with _cat_lock:
        if _cat and (time.time() - _cat_at) < _CAT_TTL:
            return list(_cat)
    if not enabled():
        return []
    url = settings.divina_url.strip().rstrip("/") + "/agents"
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {settings.divina_admin_token}"},
                      timeout=timeout)
        r.raise_for_status()
        dati = r.json()
    except Exception:
        log.info("agents_bridge: catalogo non leggibile (nessun suggerimento)")
        return []
    out: list[dict] = []
    for gruppo, chiave in ((dati.get("agents") or [], "id"),
                           (dati.get("subagents") or [], "sotto")):
        for a in gruppo:
            agente = a.get(chiave) or a.get("id") or ""
            for sk in (a.get("skills") or []):
                testo = " ".join(str(sk.get(k) or "") for k in ("id", "role", "desc", "department"))
                out.append({"agente": agente, "skill": sk.get("id") or "",
                            "role": sk.get("role") or sk.get("id") or "",
                            "desc": sk.get("desc") or "",
                            "parole": _parole(testo)})
    with _cat_lock:
        _cat, _cat_at = out, time.time()
    return list(out)


# Soglie SEVERE, e volutamente. Un suggerimento sbagliato sotto ogni risposta
# diventa rumore, e il rumore si impara a ignorare: meglio non suggerire.
SOGLIA = 2               # parole in comune, quando si può contare solo quelle
SOGLIA_COS = 0.62        # somiglianza di significato (coseno), quando c'è il vettore


def _cos(a, b) -> float:
    na = nb = p = 0.0
    for x, y in zip(a, b):
        p += x * y
        na += x * x
        nb += y * y
    return p / ((na ** 0.5) * (nb ** 0.5)) if na and nb else 0.0


def vettori(cat=None) -> list[dict]:
    """Il catalogo con un VETTORE per ogni capacità, calcolato una volta e
    tenuto insieme al catalogo (stessa scadenza).

    Perché serve, e perché le parole non bastavano. Il criterio è «una capacità
    esiste quando qualcuno può usarla senza sapere come si chiama»: chi scrive
    «cerca chi vende stampa 3D a Benevento» non deve sapere che la skill si
    chiama `customer-research`. Ma quel messaggio e quella descrizione **non
    hanno una parola in comune** — contarle sarebbe chiedere all'utente di
    indovinare il vocabolario della skill, cioè il nome, solo scritto peggio.
    Un embedding invece le avvicina, e gli embedding in questa casa ci sono già.

    Costa una chiamata ogni dieci minuti, non una per messaggio: il vettore della
    DOMANDA lo calcola già il retrieval, e si riusa quello."""
    cat = catalogo() if cat is None else cat
    if not cat or all("vec" in c for c in cat):
        return cat
    from .providers import embed
    testi = [f"{c['role']}. {c['desc']}" for c in cat]
    try:
        vs = embed(testi)
    except Exception:
        log.info("agents_bridge: vettori delle capacità non calcolabili (resta il lessico)")
        return cat
    if len(vs) != len(cat):
        return cat
    for c, v in zip(cat, vs):
        c["vec"] = v
    return cat


def trova(messaggio: str, cat=None, qvec=None) -> dict | None:
    """La capacità che sa fare questa cosa, o None (il caso più frequente).

    Due strade, e la prima è quella buona: se c'è il VETTORE della domanda (lo
    calcola già il retrieval, quindi è gratis) si confrontano i significati.
    Senza vettore — orchestratore appena avviato, embedding non disponibile — si
    ripiega sulle parole in comune: peggio, ma onesto, e non tace del tutto."""
    cat = catalogo() if cat is None else cat
    if not cat:
        return None
    if qvec:
        cat = vettori(cat)
        migliore, punti = None, 0.0
        for c in cat:
            if "vec" not in c:
                continue
            s = _cos(qvec, c["vec"])
            if s > punti:
                migliore, punti = c, s
        if migliore and punti >= SOGLIA_COS:
            return {**_pubblica(migliore), "quanto": round(punti, 3), "come": "significato"}
        if migliore is not None:
            return None      # il vettore c'era e ha detto di no: non si ripiega
    p = _parole(messaggio)
    if not p:
        return None
    migliore, punti = None, 0
    for c in cat:
        n = len(p & c["parole"])
        if n > punti:
            migliore, punti = c, n
    if not migliore or punti < SOGLIA:
        return None
    return {**_pubblica(migliore), "quanto": punti, "come": "parole"}


def _pubblica(c: dict) -> dict:
    return {"agente": c["agente"], "skill": c["skill"],
            "role": c["role"], "desc": c["desc"]}


def reset_catalogo() -> None:
    """Solo per i test."""
    global _cat, _cat_at
    with _cat_lock:
        _cat, _cat_at = [], 0.0
