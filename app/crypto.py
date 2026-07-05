"""Cifratura simmetrica dei contenuti sensibili a riposo (GDPR).

Pensata per la colonna `documents.content_encrypted` (bytea) dello schema OVYON:
i metadati restano in chiaro (servono ai filtri/RLS), il corpo sensibile può
essere cifrato. Usa Fernet (AES-128-CBC + HMAC-SHA256), autenticato: un token
manomesso non decifra.

Disattivata di default: senza `CONTENT_ENC_KEY` le funzioni di cifra/decifra non
vanno chiamate (`enabled()` è False). Supporta la ROTAZIONE delle chiavi: la
variabile può contenere più chiavi separate da virgola — la prima cifra, tutte
decifrano. Genera una chiave con:  python -m app.crypto
"""
from .config import settings

# Marcatore di versione anteposto al token: distingue un contenuto cifrato da
# questo modulo (utile per migrazioni/idempotenza) e permette evoluzioni future.
_PREFIX = b"ovy1:"


def _keys() -> list[str]:
    return [k.strip() for k in (settings.content_enc_key or "").split(",") if k.strip()]


def enabled() -> bool:
    """True se è configurata almeno una chiave."""
    return bool(_keys())


def _fernet():
    keys = _keys()
    if not keys:
        raise RuntimeError("Cifratura non configurata: imposta CONTENT_ENC_KEY.")
    try:
        from cryptography.fernet import Fernet, MultiFernet
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Manca la libreria 'cryptography' per la cifratura.") from e
    fs = [Fernet(k.encode() if isinstance(k, str) else k) for k in keys]
    return MultiFernet(fs) if len(fs) > 1 else fs[0]


def _as_bytes(token) -> bytes:
    if isinstance(token, memoryview):
        return bytes(token)
    if isinstance(token, str):
        return token.encode("utf-8")
    return bytes(token)


def encrypt(plaintext: str) -> bytes:
    """Cifra una stringa → token bytes (da salvare in content_encrypted bytea)."""
    return _PREFIX + _fernet().encrypt((plaintext or "").encode("utf-8"))


def decrypt(token) -> str:
    """Decifra un token prodotto da encrypt(). Solleva (InvalidToken) se il token
    è manomesso o nessuna chiave configurata lo apre. Accetta bytes/bytearray/
    memoryview (colonna bytea) o str."""
    b = _as_bytes(token)
    if b.startswith(_PREFIX):
        b = b[len(_PREFIX):]
    return _fernet().decrypt(b).decode("utf-8")


def is_encrypted(token) -> bool:
    """True se il valore sembra un contenuto cifrato da questo modulo (idempotenza)."""
    try:
        return _as_bytes(token).startswith(_PREFIX)
    except Exception:
        return False


def generate_key() -> str:
    """Nuova chiave Fernet (urlsafe base64, 32 byte) da mettere in CONTENT_ENC_KEY."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


if __name__ == "__main__":  # pragma: no cover
    print(generate_key())
