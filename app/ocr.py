"""OCR dei documenti caricati, via Mistral OCR (UE). Ritorna testo markdown.

Usato quando il consulente carica un contratto/PDF nel pannello del cliente.
"""
import base64
from pathlib import Path

import httpx

from .config import settings

MISTRAL_BASE = "https://api.mistral.ai/v1"


def ocr_document(path: str, mime: str = "application/pdf") -> str:
    raw = Path(path).read_bytes()
    b64 = base64.b64encode(raw).decode()
    # Le immagini usano il campo image_url, gli altri documenti document_url.
    kind = "image_url" if mime.startswith("image/") else "document_url"
    r = httpx.post(
        f"{MISTRAL_BASE}/ocr",
        headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
        json={
            "model": "mistral-ocr-latest",
            "document": {"type": kind, kind: f"data:{mime};base64,{b64}"},
        },
        timeout=180,
    )
    r.raise_for_status()
    pages = r.json().get("pages", [])
    return "\n\n".join(p.get("markdown", "") for p in pages)
