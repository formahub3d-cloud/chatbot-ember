"""Ricerca web via Tavily — capability agente OPT-IN per Divina.

Oltre a rispondere dal cervello (vault → Qdrant), Divina può cercare su internet e
sintetizzare, quando la capability è abilitata. Il pattern è quello di Divina
(ovy-orchestrator/app/tavily.py) ma reso provider-agnostico e INERTE di default.

Regole:
  - INERTE senza TAVILY_API_KEY: `search()` ritorna [] e NON fa alcuna chiamata di
    rete (nessun costo, comportamento storico). `enabled()` lo riflette.
  - Nessuna dipendenza nuova: usa `httpx`, lo stesso client HTTP già in uso in Divina
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
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"


def enabled() -> bool:
    """True se la ricerca web può operare, cioè se TAVILY_API_KEY è impostata.
    Senza chiave la capability resta inerte a prescindere dai flag di gating."""
    return bool(settings.tavily_api_key)


def search(query: str, max_results: int = 5, timeout: float = 15.0,
           domini: list[str] | None = None) -> list[dict]:
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
    corpo = {"api_key": settings.tavily_api_key, "query": q,
             "max_results": max_results, "search_depth": "basic"}
    if domini:
        # V9/B · Cercare DENTRO un sito solo. Serve a scoprire le pagine interne
        # di un cliente (chi siamo, servizi, contatti) senza inventarsi un
        # crawler: il perimetro resta un parametro del provider, non nostro.
        corpo["include_domains"] = list(domini)[:5]
    try:
        r = httpx.post(TAVILY_URL, json=corpo, timeout=timeout)
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


def estrai(urls: list[str], timeout: float = 30.0) -> dict[str, str]:
    """V9/B · Il TESTO di pagine già note → {url: testo}. Inerte senza chiave.

    Perché passare dal provider invece di scaricare le pagine da qui: un motore
    che scarica un URL arbitrario deciso da chi fa la richiesta è un ponte verso
    la rete interna (SSRF). Delegando, l'unica cosa che entra è testo.

    Un fallimento non è un errore fatale: chi chiama ripiega sugli snippet della
    ricerca, che sono più corti ma altrettanto veri — e portano il loro URL."""
    if not enabled() or not urls:
        return {}
    try:
        r = httpx.post(
            TAVILY_EXTRACT_URL,
            json={"api_key": settings.tavily_api_key, "urls": list(urls)[:10]},
            timeout=timeout,
        )
        r.raise_for_status()
        dati = r.json()
    except Exception:
        log.warning("websearch: estrazione fallita (si ripiega sugli snippet)")
        return {}
    out: dict[str, str] = {}
    for it in (dati.get("results") or []):
        u, testo = it.get("url"), (it.get("raw_content") or "")
        if u and testo.strip():
            out[u] = testo[:20000]
    return out
