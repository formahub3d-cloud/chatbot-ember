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
    """Valore di un'etichetta UniLav. Robusto verso l'output OCR reale:
    - la label è a inizio riga (ancoraggio: evita falsi match come Nome↔Cognome);
    - il separatore può essere ':', '-' o solo spazi (l'OCR spesso mette i due punti);
    - case-insensitive (l'OCR varia il maiuscolo);
    - il valore è il resto della riga, ripulito.
    La label è escapata: eventuali caratteri speciali non rompono la regex."""
    m = re.search(rf"(?im)^\s*{re.escape(label)}\s*[:\-]?\s*(\S.*?)\s*$", text)
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
