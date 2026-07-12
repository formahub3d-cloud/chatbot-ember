"""Firma elettronica semplice (SES) — in casa, senza provider a pagamento.

Un SES (*Simple Electronic Signature*, eIDAS art. 25) è sufficiente per i contratti
SaaS B2B in UE: il cliente CONFERMA l'accordo e Ember registra un record verificabile
che lega quattro cose al documento esatto:

  - CHI   ha firmato   → nome, ragione sociale, email e/o IP (identificativo)
  - QUANDO             → timestamp UTC in ISO 8601
  - COSA               → sha256 del PDF (l'IMPRONTA, non il contenuto)
  - COME               → canale/metodo della conferma

Il modulo è PURO (input → record/PDF): non salva né logga il contenuto del contratto,
che è PII (regola 6). Il record contiene solo l'hash + metadati minimi, così la firma
è verificabile senza trattenere il documento. Riusa il generatore PDF dei contratti
(`contracts.to_pdf`) per apporre una pagina/timbro di certificato di firma.
"""
import hashlib
from datetime import datetime, timezone

from . import contracts

STANDARD = "SES-eIDAS-art25"


def pdf_hash(pdf: bytes) -> str:
    """sha256 (hex) del PDF: lega la firma al documento esatto. Cambia se il PDF cambia.
    Solleva ValueError se il PDF è vuoto/assente."""
    if not pdf:
        raise ValueError("PDF mancante: impossibile calcolare l'hash della firma.")
    return hashlib.sha256(bytes(pdf)).hexdigest()


def build_record(nome: str, ragione_sociale: str, pdf_sha256: str,
                 email: str = "", ip: str = "", metodo: str = "conferma-online") -> dict:
    """Record di firma verificabile: chi/quando/cosa/come. Solleva ValueError (messaggio
    chiaro) se manca chi (nome + ragione sociale), l'identificativo (email o IP), o cosa
    (l'hash) — i requisiti minimi di un SES tracciabile."""
    nome = (nome or "").strip()
    ragione_sociale = (ragione_sociale or "").strip()
    email = (email or "").strip()
    ip = (ip or "").strip()
    pdf_sha256 = (pdf_sha256 or "").strip()
    if not nome or not ragione_sociale:
        raise ValueError("Firma: 'nome' e 'ragione_sociale' sono obbligatori.")
    if not email and not ip:
        raise ValueError("Firma: serve un identificativo (email o IP).")
    if not pdf_sha256:
        raise ValueError("Firma: manca l'hash del documento (cosa si firma).")
    return {
        "standard": STANDARD,
        "chi": {"nome": nome, "ragione_sociale": ragione_sociale,
                "email": email, "ip": ip},
        "quando": datetime.now(timezone.utc).isoformat(),
        "cosa": {"algoritmo": "sha256", "hash": pdf_sha256},
        "come": metodo,
    }


def certificate_text(record: dict) -> str:
    """Testo umano-leggibile del certificato di firma, da apporre in coda al PDF."""
    chi = record.get("chi", {})
    ident = " / ".join(x for x in (chi.get("email"), chi.get("ip")) if x) or "—"
    cosa = record.get("cosa", {})
    return (
        "\n\nCERTIFICATO DI FIRMA ELETTRONICA (SES)\n"
        f"Standard: {record.get('standard', STANDARD)}\n"
        f"Firmatario: {chi.get('nome', '')} — {chi.get('ragione_sociale', '')}\n"
        f"Identificativo: {ident}\n"
        f"Data e ora (UTC): {record.get('quando', '')}\n"
        f"Metodo: {record.get('come', '')}\n"
        f"Impronta documento ({cosa.get('algoritmo', 'sha256')}):\n{cosa.get('hash', '')}\n"
        "\nApponendo la presente firma il firmatario dichiara di accettare "
        "integralmente il contratto sopra riportato.\n"
    )


def stamp(contract_text: str, record: dict, titolo: str = "Contratto") -> bytes:
    """Ri-genera il PDF del contratto con in coda il certificato di firma (timbro).
    L'hash nel certificato si riferisce al PDF del contratto SENZA timbro (il documento
    accettato), così la firma resta verificabile rigenerando il contratto originale."""
    return contracts.to_pdf(contract_text + certificate_text(record), titolo)
