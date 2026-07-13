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


def is_task_like(message: str) -> bool:
    """Euristico leggero: True se il messaggio sembra un COMPITO (inizia con un verbo
    imperativo tipo 'scrivi/analizza/prepara/genera/crea'). È solo un suggerimento per
    l'auto-instradamento (settings.agents_auto); il flag esplicito `agent:true` resta
    la via primaria."""
    m = (message or "").strip().lower()
    if not m:
        return False
    first = m.split()[0].strip(".,:;!?\"'")
    return first in _TASK_VERBS


def route(tenant_code: str, message: str, history=None, timeout: float = 30.0) -> dict | None:
    """Instrada il messaggio all'agente Divina giusto. Ritorna il dict di Divina
    (`{routed, agent, skill, output, confidence, web_sources?}`) o None se inerte/errore.

    INERTE (ritorna None, nessuna chiamata di rete) se il ponte è disabilitato o manca
    il `tenant_code`/il messaggio. Gli errori di rete/HTTP sono assorbiti (ritorna None,
    log senza segreti): il ponte è additivo e non deve MAI far esplodere /chat → il
    chiamante ripiega sul RAG. Si passa a Divina SOLO il `tenant_code`: lo scope lo
    applica Divina con la sua RLS.
    """
    if not enabled():
        return None
    code = (tenant_code or "").strip()
    if not code or not (message or "").strip():
        return None
    url = settings.divina_url.strip().rstrip("/") + "/agents/route"
    payload = {"tenant": code, "input": message, "history": history or []}
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
