"""Guard-rail di sicurezza per Ember.

Funzioni pure, senza stato, riusabili da main.py e rag.py:
  - redazione PII (codice fiscale, email, telefono, IBAN) prima di loggare;
  - sanitizzazione del contenuto recuperato contro il prompt-injection;
  - cap della lunghezza dell'input utente;
  - confronto chiavi a tempo costante (anti timing-attack);
  - allowlist degli Origin del browser per tenant.
"""
import hashlib
import hmac
import re
import secrets

# ── PII italiane comuni ────────────────────────────────────────────────
_CF = re.compile(r"\b[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]\b")
_IBAN = re.compile(r"\bIT\d{2}[A-Za-z0-9]{15,30}\b", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"(?<!\d)(?:\+39[\s.-]?)?(?:\d[\s.-]?){8,10}\d(?!\d)")


def redact_pii(text: str) -> str:
    """Maschera i dati personali più comuni. Da usare sui testi che finiscono nei
    log (es. la domanda dell'utente): i log non devono contenere PII (GDPR)."""
    if not text:
        return text or ""
    t = _CF.sub("[CF]", text)
    t = _IBAN.sub("[IBAN]", t)
    t = _EMAIL.sub("[email]", t)
    t = _PHONE.sub("[tel]", t)
    return t


# ── Difesa prompt-injection ────────────────────────────────────────────
# Neutralizza righe del CONTENUTO recuperato che tentano di dirottare le istruzioni.
# Il cervello è fidato, ma un documento caricato via OCR (contratto) no.
_INJECT = re.compile(
    r"(?im)^\s*(?:"
    r"ignora(?:\s+le)?\s+(?:istruzioni|precedenti|regole)|dimentica(?:\s+tutto)?|"
    r"ignore\s+(?:the\s+)?(?:above|previous|instructions?|rules?)|disregard|forget\s+(?:all|everything)|"
    r"override\b|bypass\b|jailbreak|developer\s+mode|"
    r"system\s*:|assistant\s*:|nuove?\s+istruzioni|new\s+instructions?|"
    r"tu\s+sei\s+ora|you\s+are\s+now|agisci\s+come|act\s+as|"
    r"(?:rivela|mostra|stampa|reveal|print|show)\b.*(?:prompt|istruzioni|instructions?|system)|"
    r"<\s*/?\s*system\s*>|\[\s*system\s*\]"
    r").*$"
)


def sanitize_context(text: str) -> str:
    """Rimuove le righe che sembrano tentativi di prompt-injection nel contenuto."""
    if not text:
        return text or ""
    return _INJECT.sub("[riga rimossa]", text)


def cap_input(text: str, limit: int = 2000) -> str:
    """Tronca l'input utente a `limit` caratteri (anti-abuso e controllo costi)."""
    return (text or "").strip()[:limit]


def verify_key(candidate: str, expected: str) -> bool:
    """Confronto a tempo costante fra due chiavi (evita timing-attack)."""
    return hmac.compare_digest((candidate or "").encode("utf-8"),
                               (expected or "").encode("utf-8"))


def hash_key(key: str) -> str:
    """SHA-256 esadecimale della chiave tenant. Nel DB si salva SOLO questo,
    mai la chiave in chiaro: se il DB trapela, le chiavi non sono ricavabili."""
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()


def new_key(prefix: str = "ember") -> str:
    """Genera una chiave tenant robusta e URL-safe (mostrata una sola volta)."""
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def origin_allowed(origin: str, allowed) -> bool:
    """True se l'Origin del browser è tra quelli consentiti per il tenant.
    `allowed` vuoto o contenente '*' = tutti (comportamento pilota)."""
    allowed = allowed or []
    if not allowed or "*" in allowed:
        return True
    if not origin:
        return False
    o = origin.rstrip("/").lower()
    return any(o == str(a).rstrip("/").lower() for a in allowed)
