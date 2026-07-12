"""Ricerca web via Tavily — capability agente OPT-IN per Ember.

Oltre a rispondere dal cervello (vault → Qdrant), Ember può cercare su internet e
sintetizzare, quando la capability è abilitata. Il pattern è quello di Divina
(ovy-orchestrator/app/tavily.py) ma reso provider-agnostico e INERTE di default.

Regole:
  - INERTE senza TAVILY_API_KEY: `search()` ritorna [] e NON fa alcuna chiamata di
    rete (nessun costo, comportamento storico). `enabled()` lo riflette.
  - Nessuna dipendenza nuova: usa `httpx`, lo stesso client HTTP già in uso in Ember
    (providers.py / rag.py).
  - Il testo restituito è DATO NON FIDATO: chi lo consuma (rag) deve trattarlo come
    informazione da consultare, MAI come istruzioni — vedi security.sanitize_context
    e il system prompt anti-injection.
  - Nessun segreto nei log; niente contenuti sensibili loggati (GDPR).

Se un giorno si cambia motore di ricerca, cambia SOLO questo file (provider-agnostico).
"""
import logging

import httpx

from .config import settings

log = logging.getLogger("ember.websearch")

TAVILY_URL = "https://api.tavily.com/search"


def enabled() -> bool:
    """True se la ricerca web può operare, cioè se TAVILY_API_KEY è impostata.
    Senza chiave la capability resta inerte a prescindere dai flag di gating."""
    return bool(settings.tavily_api_key)


def search(query: str, max_results: int = 5, timeout: float = 15.0) -> list[dict]:
    """Ricerca web → lista di risultati `{title, url, snippet}` (URL sempre presente).

    Inerte (ritorna []) se manca TAVILY_API_KEY o la query è vuota: nessuna chiamata,
    nessun costo. Gli errori di rete/HTTP sono assorbiti (ritorna [] e logga senza
    segreti): la ricerca web è additiva e non deve MAI far esplodere /chat.
    """
    if not enabled():
        return []
    q = (query or "").strip()
    if not q:
        return []
    try:
        r = httpx.post(
            TAVILY_URL,
            json={"api_key": settings.tavily_api_key, "query": q,
                  "max_results": max_results, "search_depth": "basic"},
            timeout=timeout,
        )
        r.raise_for_status()
        results = r.json().get("results", []) or []
    except Exception:
        # niente query/segreti nel log: solo il fatto che è fallita.
        log.warning("websearch: ricerca fallita (ignorata)")
        return []
    out = []
    for it in results:
        url = it.get("url")
        if not url:
            continue                     # niente URL = niente fonte → si scarta
        out.append({
            "title": it.get("title", "") or "",
            "url": url,
            "snippet": (it.get("content") or "")[:2000],
        })
    return out
