"""Write-back dei dati estratti nel cervello.

- `save_contract_note`: crea la nota markdown del contratto nel vault (cartella
  privata del cliente, già gitignorata).
- `notion_upsert`: STUB — inserire nel database Notion via API (richiede token).

Principio: si scrive SOLO dopo conferma umana dei campi (vedi extract.py).
"""
from datetime import date, datetime
from pathlib import Path

import httpx

from .config import settings

NOTION_API = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"

NOTE_TEMPLATE = """---
title: {title}
summary: {summary}
tags: [forma, cliente, {cliente_tag}, contratti, cat/doc]
status: historical
created: {today}
updated: {today}
related:
  - "[[registro-contratti-ats]]"
  - "[[cliente-ats]]"
---

# {title}

> ⚠️ Dati personali (GDPR). Nota in cartella privata/gitignorata.

| Campo | Valore |
|---|---|
| Nome e Cognome | **{nome} {cognome}** |
| Codice Fiscale | `{codice_fiscale}` |
| Codice Comunicazione | `{codice_comunicazione}` |
| Data avvio | {data_inizio} |
| Data scadenza | {data_fine} |
| Tipologia | {tipologia} |

→ [[registro-contratti-ats]] · [[cliente-ats]]
"""


def save_contract_note(fields: dict, cliente: str = "ats") -> str:
    """Scrive la nota nel vault e ritorna il path relativo creato."""
    vault = Path(settings.vault_path)
    folder = vault / "forma" / "clienti" / cliente / "contratti"
    folder.mkdir(parents=True, exist_ok=True)
    cognome = (fields.get("cognome") or "senza-nome").lower().replace(" ", "-")
    slug = f"unilav-{cognome}-{fields.get('data_inizio','').replace('/','-')}"
    note = NOTE_TEMPLATE.format(
        title=f"UNILAV — {fields.get('cognome','')} {fields.get('nome','')}",
        summary="Contratto importato via OCR — da rivedere.",
        cliente_tag=f"cliente/{cliente}",
        today=date.today().isoformat(),
        nome=fields.get("nome", ""), cognome=fields.get("cognome", ""),
        codice_fiscale=fields.get("codice_fiscale", ""),
        codice_comunicazione=fields.get("codice_comunicazione", ""),
        data_inizio=fields.get("data_inizio", ""),
        data_fine=fields.get("data_fine", ""),
        tipologia=fields.get("tipologia", ""),
    )
    (folder / f"{slug}.md").write_text(note, "utf-8")
    return f"forma/clienti/{cliente}/contratti/{slug}.md"


# Opzioni del select "Tipo contratto" nel database Notion (devono combaciare).
NOTION_TIPI = ["Determinato", "Indeterminato", "Apprendistato", "Stagionale",
               "Collaborazione", "Intermittente", "Altro"]


def _to_iso(value: str) -> str:
    """Converte una data in ISO YYYY-MM-DD. Accetta DD/MM/YYYY, DD-MM-YYYY o già ISO.
    Ritorna stringa vuota se non riconosciuta (così il campo data resta vuoto)."""
    v = (value or "").strip()
    if not v:
        return ""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _map_tipo(value: str) -> str:
    """Mappa la tipologia estratta su un'opzione valida del select Notion."""
    v = (value or "").strip().lower()
    for opt in NOTION_TIPI:
        if opt.lower() in v:
            return opt
    return "Altro"


def notion_upsert(fields: dict, db_id: str = "") -> dict:
    """Inserisce una riga nel database Notion dei contratti via API.

    Inerte (status='skipped') finché NOTION_TOKEN e NOTION_CONTRACTS_DB non sono
    configurati. Lo schema sotto combacia col database reale "Contratti ATS"
    (id df21fc1d-cf37-4cf0-b396-4f9af6ca372c): Data inizio/scadenza sono di tipo
    DATA, Tipo contratto è un SELECT. Si invoca SOLO dopo conferma umana dei campi.
    """
    token = settings.notion_token
    db = db_id or settings.notion_contracts_db
    if not token or not db:
        return {"status": "skipped", "reason": "NOTION_TOKEN o NOTION_CONTRACTS_DB non configurati"}

    nome = f"{fields.get('nome', '')} {fields.get('cognome', '')}".strip()

    def rt(v):  # rich_text helper
        return {"rich_text": [{"text": {"content": str(v or "")}}]}

    props = {
        "Nome e Cognome": {"title": [{"text": {"content": nome or "—"}}]},
        "Codice Fiscale": rt(fields.get("codice_fiscale")),
        "Codice Comunicazione": rt(fields.get("codice_comunicazione")),
        "Tipo contratto": {"select": {"name": _map_tipo(fields.get("tipologia"))}},
    }
    if fields.get("slug"):
        props["Nota Obsidian"] = rt(fields.get("slug"))
    inizio = _to_iso(fields.get("data_inizio"))
    if inizio:
        props["Data inizio"] = {"date": {"start": inizio}}
    fine = _to_iso(fields.get("data_fine"))
    if fine:
        props["Data scadenza"] = {"date": {"start": fine}}
    try:
        r = httpx.post(
            NOTION_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            json={"parent": {"database_id": db}, "properties": props},
            timeout=30,
        )
        if r.status_code in (200, 201):
            return {"status": "ok", "page_id": r.json().get("id")}
        return {"status": "error", "code": r.status_code, "detail": r.text[:300]}
    except Exception as e:  # rete / config
        return {"status": "error", "detail": str(e)}
