"""OVY Brain Connector — MCP server (Sezione 5 del doc di architettura OVYON).

Espone a Claude i 5 tool del cervello OVY (ovy_search, ovy_get_document,
ovy_create_document, ovy_update_document, ovy_list_context). È un ADATTATORE
SOTTILE: ogni tool chiama gli endpoint HTTP di Ember (il chatbot integrato in
OVYON), che applica server-side lo stesso filtro per grant. Il connettore non
contiene logica di permessi: l'isolamento resta in Ember/Qdrant.

Config via ambiente (vedi .env.example):
  EMBER_API_URL     base URL di Ember (es. https://ember.formahub.it)
  EMBER_TENANT_KEY  chiave-tenant che definisce lo scope visibile

Avvio (stdio, per Claude Desktop / Claude Code):
  python server.py
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

EMBER_API_URL = os.environ.get("EMBER_API_URL", "http://localhost:8000").rstrip("/")
EMBER_TENANT_KEY = os.environ.get("EMBER_TENANT_KEY", "")
TIMEOUT = float(os.environ.get("EMBER_TIMEOUT", "30"))

mcp = FastMCP("ovy-brain-connector")


def _headers() -> dict:
    return {"X-Tenant-Key": EMBER_TENANT_KEY, "Content-Type": "application/json"}


def _get(path: str, params: dict | None = None) -> dict:
    r = httpx.get(f"{EMBER_API_URL}{path}", headers=_headers(), params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict) -> dict:
    r = httpx.post(f"{EMBER_API_URL}{path}", headers=_headers(), json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def ovy_search(query: str, k: int = 6) -> dict:
    """Cerca nel cervello OVY i contenuti rilevanti per la richiesta corrente.
    Da chiamare PRIMA di generare contenuti nuovi, per non duplicare ciò che esiste.
    Ritorna una lista di risultati (slug, titolo, path, snippet) già filtrati per
    lo scope del tenant."""
    return _post("/search", {"message": query, "k": k})


@mcp.tool()
def ovy_get_document(slug: str) -> dict:
    """Recupera il contenuto completo di una nota/documento del cervello dato il suo
    `slug` (ottenuto da ovy_search). Ritorna 404 se la nota è fuori dallo scope."""
    return _get("/document", {"slug": slug})


@mcp.tool()
def ovy_list_context() -> dict:
    """Elenca i livelli di permesso (org/tenant/sotto-tenant) visibili al tenant
    corrente. Utile all'apertura di una conversazione per capire l'ambito."""
    return _get("/context")


@mcp.tool()
def ovy_create_document(scope: str, title: str, body: str,
                        summary: str = "", tags: list[str] | None = None,
                        confirm: bool = False) -> dict:
    """Crea una nuova nota nel cervello OVY con metadati.
    IMPORTANTE: per default (confirm=false) restituisce solo un'ANTEPRIMA da far
    approvare all'utente (regola: write-back solo dopo conferma umana). Richiama con
    confirm=true SOLO dopo che l'utente ha approvato l'anteprima."""
    return _post("/writeback", {
        "scope": scope, "title": title, "body": body, "summary": summary,
        "tags": tags or [], "confirm": confirm, "overwrite": False,
    })


@mcp.tool()
def ovy_update_document(scope: str, title: str, body: str,
                        summary: str = "", tags: list[str] | None = None,
                        confirm: bool = False) -> dict:
    """Aggiorna una nota esistente nel cervello OVY (stesso titolo → stesso slug).
    Come ovy_create_document, confirm=false = anteprima; confirm=true = scrittura
    (sovrascrive la nota esistente) SOLO dopo conferma umana."""
    return _post("/writeback", {
        "scope": scope, "title": title, "body": body, "summary": summary,
        "tags": tags or [], "confirm": confirm, "overwrite": True,
    })


if __name__ == "__main__":
    mcp.run()
