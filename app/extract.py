"""Estrazione dei campi chiave dal testo OCR.

Due strade:
- `extract_unilav`: regex veloci per il modulo UniLav (formato noto).
- `extract_fields_llm`: estrazione generica via LLM (per documenti vari), ritorna JSON.

In ENTRAMBI i casi i valori vanno SEMPRE confermati da un umano prima di
consolidarli (vale soprattutto per codice fiscale e codice comunicazione).
"""
import json
import re

from .providers import chat


def _find(text: str, label: str) -> str:
    m = re.search(rf"{label}\s+(.+)", text)
    return m.group(1).strip() if m else ""


def extract_unilav(text: str) -> dict:
    return {
        "codice_comunicazione": _find(text, "Codice comunicazione"),
        "codice_fiscale": _find(text, "Codice fiscale"),
        "cognome": _find(text, "Cognome"),
        "nome": _find(text, "Nome"),
        "data_inizio": _find(text, "Data inizio"),
        "data_fine": _find(text, "Data fine"),
        "datore": _find(text, "Denominazione"),
        "tipologia": _find(text, "Tipologia contrattuale"),
    }


# CF italiano: 6 lettere + 2 cifre + lettera + 2 cifre + lettera + 3 cifre + lettera
_CF_RE = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$")


def validate_unilav(fields: dict) -> list[str]:
    """Controlli formali PRIMA del consolidamento (la conferma umana resta
    obbligatoria: qui si bloccano solo gli errori oggettivi). Ritorna l'elenco
    dei problemi; lista vuota = campi formalmente ok."""
    problems = []
    f = fields or {}
    if not (f.get("nome") or "").strip():
        problems.append("nome mancante")
    if not (f.get("cognome") or "").strip():
        problems.append("cognome mancante")
    cf = (f.get("codice_fiscale") or "").strip().upper()
    if not cf:
        problems.append("codice fiscale mancante")
    elif not _CF_RE.match(cf):
        problems.append("codice fiscale non valido (atteso formato a 16 caratteri)")
    if not (f.get("codice_comunicazione") or "").strip():
        problems.append("codice comunicazione mancante")
    return problems


def extract_fields_llm(text: str, fields: list[str]) -> dict:
    system = (
        "Estrai dal testo i campi richiesti. Rispondi SOLO con JSON valido, "
        "chiavi = nomi dei campi, valori = stringhe; usa \"\" se assente. Non inventare."
    )
    user = f"CAMPI: {', '.join(fields)}\n\nTESTO:\n{text}"
    out = chat(system, user)
    try:
        start, end = out.find("{"), out.rfind("}")
        return json.loads(out[start:end + 1])
    except Exception:
        return {"_raw": out}
