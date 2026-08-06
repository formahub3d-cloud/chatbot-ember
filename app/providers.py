"""Astrazione provider: embeddings + chat. Cambia fornitore da .env.

- Embeddings: Mistral (`mistral-embed`, 1024 dim). Claude non offre embeddings.
- Chat: Mistral oppure Claude (Anthropic).
"""
import logging
import time

import httpx

from . import uso
from .config import settings

log = logging.getLogger("ember.providers")

MISTRAL_BASE = "https://api.mistral.ai/v1"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"
EMBED_DIM = 1024  # mistral-embed


def _post_with_retry(url: str, *, headers: dict, json: dict, timeout: int,
                     attempts: int = 8, cap: float = 60.0) -> httpx.Response:
    """POST resiliente: ritenta su 429 (rate-limit) e 5xx con backoff esponenziale,
    rispettando l'header Retry-After quando presente. Solleva l'ultimo errore se
    esaurisce i tentativi."""
    last: httpx.Response | None = None
    for attempt in range(attempts):
        r = httpx.post(url, headers=headers, json=json, timeout=timeout)
        if r.status_code == 429 or r.status_code >= 500:
            last = r
            retry_after = r.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else 0.0
            except ValueError:
                wait = 0.0
            wait = wait or min(2.0 ** attempt, cap)
            log.warning("Provider %s su %s: attendo %.1fs e ritento (%d/%d)",
                        r.status_code, url, wait, attempt + 1, attempts)
            time.sleep(wait)
            continue
        return r
    if last is not None:
        last.raise_for_status()
    raise RuntimeError(f"Nessuna risposta da {url}")


def embed(texts: list[str]) -> list[list[float]]:
    """Ritorna un vettore per ogni testo in input."""
    if settings.embed_provider == "mistral":
        r = _post_with_retry(
            f"{MISTRAL_BASE}/embeddings",
            headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
            json={"model": settings.mistral_embed_model, "input": texts},
            timeout=60,
        )
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]
    raise ValueError(f"EMBED_PROVIDER non supportato: {settings.embed_provider}")


def chat(system: str, user: str) -> str:
    """Una risposta dal modello di dialogo selezionato."""
    return chat_con_uso(system, user)[0]


def chat_con_uso(system: str, user: str) -> tuple[str, uso.Uso | None]:
    """Come `chat()`, ma dice anche quanti token è costata (S5.1a).

    Il secondo valore è `None` quando il provider non l'ha detto: **non è
    zero**. Da quando i token diventano denaro, «non misurato» e «gratis» sono
    due fatti diversi, e confonderli si vede in fattura.
    """
    if settings.llm_provider == "mistral":
        r = _post_with_retry(
            f"{MISTRAL_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
            json={
                "model": settings.mistral_llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            },
            timeout=120,
        )
        r.raise_for_status()
        corpo = r.json()
        return (corpo["choices"][0]["message"]["content"],
                uso.da_risposta(corpo, settings.mistral_llm_model))

    if settings.llm_provider == "claude":
        r = _post_with_retry(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": settings.claude_llm_model,
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=120,
        )
        r.raise_for_status()
        corpo = r.json()
        return (corpo["content"][0]["text"],
                uso.da_risposta(corpo, settings.claude_llm_model))

    raise ValueError(f"LLM_PROVIDER non supportato: {settings.llm_provider}")


def chat_stream(system: str, user: str, misura: "uso.UsoInStream | None" = None):
    """Come chat(), ma in streaming: genera i token man mano che arrivano.

    Ritorna un generatore di stringhe (delta di testo). Usato dall'endpoint
    SSE /chat con {"stream": true}. Niente retry qui: lo stream o parte o
    fallisce subito (gli errori pre-stream sollevano httpx.HTTPStatusError).

    **S5.1a · `misura`** è un `uso.UsoInStream` che il chiamante tiene e
    interroga a stream finito. Non si restituisce l'uso come ultimo elemento
    generato: cambierebbe il tipo di quello che esce dal generatore, e ogni
    consumatore dovrebbe imparare a distinguere un delta di testo da un conto.
    """
    if settings.llm_provider == "mistral":
        with httpx.stream(
            "POST",
            f"{MISTRAL_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
            json={
                "model": settings.mistral_llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "stream": True,
                # Spento di default: vedi `settings.mistral_stream_usage`. Da
                # spento il consumo dello stream resta dichiarato non misurato.
                **({"stream_options": {"include_usage": True}}
                   if settings.mistral_stream_usage else {}),
            },
            timeout=120,
        ) as r:
            r.raise_for_status()
            import json as _json
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    blocco = _json.loads(payload)
                except ValueError:
                    continue
                if misura is not None:
                    misura.aggiungi(blocco)
                try:
                    delta = blocco["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, TypeError):
                    continue
                if delta:
                    yield delta
        return

    if settings.llm_provider == "claude":
        with httpx.stream(
            "POST",
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": settings.claude_llm_model,
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "stream": True,
            },
            timeout=120,
        ) as r:
            r.raise_for_status()
            import json as _json
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                try:
                    ev = _json.loads(line[5:].strip())
                except ValueError:
                    continue
                if misura is not None:
                    misura.aggiungi(ev)
                if ev.get("type") == "content_block_delta":
                    delta = ev.get("delta", {}).get("text")
                    if delta:
                        yield delta
        return

    raise ValueError(f"LLM_PROVIDER non supportato: {settings.llm_provider}")
