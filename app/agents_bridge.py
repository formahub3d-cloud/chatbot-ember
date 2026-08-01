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
