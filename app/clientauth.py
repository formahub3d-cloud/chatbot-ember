"""Accessi console per i CLIENTI, gestiti da FORMA (owner-managed).

Il modello di fiducia è rovesciato rispetto a un signup classico: è FORMA che
provisiona tutto — crea l'account, custodisce la chiave tenant (il cliente non
la vede MAI: resta server-side, cifrata a riposo se CONTENT_ENC_KEY è attiva),
imposta la password del primo accesso e genera/rigenera il CODICE a 6 cifre.

Flusso:
  1. FORMA crea l'account (email + nome + chiave tenant + password iniziale).
  2. Il cliente entra la PRIMA volta con email+password.
  3. FORMA genera il codice a 6 cifre → da quel momento la password è disattivata
     e si entra SOLO col codice. Solo FORMA può rigenerarlo (o sbloccarlo).
  4. FORMA può entrare nel pannello del cliente ("ghost", sessione breve, audit).

Sicurezza:
  - Fail-closed: senza CLIENT_SESSION_SECRET la feature è spenta (503).
  - Hash scrypt (stdlib) per password e PIN; confronti in tempo costante.
  - Lockout: 5 tentativi errati → bloccato finché FORMA non rigenera il codice.
  - Sessioni = token HMAC firmati con scadenza (client 12h, ghost 30min),
    consegnati come cookie HttpOnly: mai token in localStorage per i clienti.
  - Nessun DELETE (regola del progetto): la rimozione è status='rimosso'.
  - La chiave master ('*') non è MAI associabile a un accesso cliente.

Storage: tabella Supabase `client_access` (db/ovyon_client_access.sql) via
tenants._conn(); fallback in memoria (demo/dev/test) se il DB non è configurato.
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid

from . import crypto
from .config import settings

log = logging.getLogger("ember.clientauth")

STATUSES = ("attivo", "sospeso", "rimosso")
MAX_ATTEMPTS = 5
SESSION_TTL = {"client": 12 * 3600, "ghost": 30 * 60}

_MEM: dict[str, dict] = {}          # fallback in memoria: id -> record


def enabled() -> bool:
    """Feature ON solo con un segreto di sessione configurato (fail-closed)."""
    return bool(settings.client_session_secret.strip())


# ── hashing (scrypt stdlib, salt per-record, confronto tempo-costante) ────────
def _hash(value: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(value.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + dk.hex()


def _verify(value: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        dk = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt_hex),
                            n=2**14, r=8, p=1)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ── chiave tenant a riposo: cifrata se la cifratura contenuti è attiva ────────
def _seal_key(tenant_key: str) -> str:
    if crypto.enabled():
        return "enc:" + base64.b64encode(crypto.encrypt(tenant_key)).decode()
    return "plain:" + tenant_key


def _unseal_key(stored: str) -> str:
    if stored.startswith("enc:"):
        return crypto.decrypt(base64.b64decode(stored[4:]))
    return stored.removeprefix("plain:")


# ── storage (Supabase con fallback memoria, stesso pattern di braintasks) ─────
def _use_db() -> bool:
    return bool(settings.database_url.strip())


_COLS = ("id, email, display_name, tenant_key_enc, password_hash, pin_hash, "
         "status, failed_attempts, locked, created_at, last_login_at")


def _row_to_rec(r) -> dict:
    keys = [c.strip() for c in _COLS.split(",")]
    return dict(zip(keys, r))


def _db_get(email: str | None = None, cid: str | None = None) -> dict | None:
    from . import tenants
    with tenants._conn() as c:
        with c.cursor() as cur:
            if email is not None:
                cur.execute(f"SELECT {_COLS} FROM client_access WHERE lower(email)=lower(%s)", (email,))
            else:
                cur.execute(f"SELECT {_COLS} FROM client_access WHERE id=%s", (cid,))
            r = cur.fetchone()
            return _row_to_rec(r) if r else None


def _db_write(rec: dict) -> None:
    from . import tenants
    with tenants._conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """INSERT INTO client_access (id, email, display_name, tenant_key_enc,
                       password_hash, pin_hash, status, failed_attempts, locked)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                       display_name=EXCLUDED.display_name,
                       tenant_key_enc=EXCLUDED.tenant_key_enc,
                       password_hash=EXCLUDED.password_hash,
                       pin_hash=EXCLUDED.pin_hash,
                       status=EXCLUDED.status,
                       failed_attempts=EXCLUDED.failed_attempts,
                       locked=EXCLUDED.locked""",
                (rec["id"], rec["email"], rec["display_name"], rec["tenant_key_enc"],
                 rec["password_hash"], rec["pin_hash"], rec["status"],
                 rec["failed_attempts"], rec["locked"]))
        c.commit()


def _db_touch_login(cid: str) -> None:
    from . import tenants
    with tenants._conn() as c:
        with c.cursor() as cur:
            cur.execute("UPDATE client_access SET last_login_at=now(), "
                        "failed_attempts=0 WHERE id=%s", (cid,))
        c.commit()


def _get(email: str | None = None, cid: str | None = None) -> dict | None:
    if _use_db():
        try:
            return _db_get(email=email, cid=cid)
        except Exception:
            log.exception("client_access: DB non raggiungibile, fallback memoria")
    for rec in _MEM.values():
        if email is not None and rec["email"].lower() == email.lower():
            return dict(rec)
        if cid is not None and rec["id"] == cid:
            return dict(rec)
    return None


def _save(rec: dict) -> None:
    if _use_db():
        try:
            _db_write(rec)
            return
        except Exception:
            log.exception("client_access: scrittura DB fallita, fallback memoria")
    _MEM[rec["id"]] = dict(rec)


# ── operazioni FORMA (owner) ──────────────────────────────────────────────────
def create(email: str, display_name: str, tenant_key: str, password: str) -> dict:
    """Crea l'accesso cliente. La chiave tenant resta server-side (mai al client).
    Rifiuta email duplicate, campi vuoti e la chiave master."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("email non valida")
    if not (tenant_key or "").strip():
        raise ValueError("chiave tenant obbligatoria")
    if len((password or "")) < 8:
        raise ValueError("password iniziale troppo corta (min 8)")
    from . import tenants
    t = tenants.get_tenant_by_key(tenant_key)
    if not t:
        raise ValueError("chiave tenant sconosciuta: creala prima in Tenant")
    scopes = t.get("allowed_scopes") or []
    if scopes == "*" or "*" in (scopes if isinstance(scopes, (list, tuple)) else []):
        raise ValueError("la chiave master non può essere data a un cliente")
    if _get(email=email):
        raise ValueError("esiste già un accesso con questa email")
    rec = {"id": str(uuid.uuid4()), "email": email,
           "display_name": (display_name or "").strip() or email.split("@")[0],
           "tenant_key_enc": _seal_key(tenant_key.strip()),
           "password_hash": _hash(password), "pin_hash": "",
           "status": "attivo", "failed_attempts": 0, "locked": False,
           "created_at": None, "last_login_at": None}
    _save(rec)
    return public(rec)


def set_pin(cid: str) -> str:
    """Genera (o RIGENERA) il codice a 6 cifre — solo FORMA. Da questo momento
    la password è disattivata e l'account è sbloccato. Ritorna il codice UNA volta."""
    rec = _get(cid=cid)
    if not rec or rec["status"] == "rimosso":
        raise KeyError("accesso cliente sconosciuto")
    code = f"{secrets.randbelow(10**6):06d}"
    rec.update(pin_hash=_hash(code), failed_attempts=0, locked=False)
    _save(rec)
    return code


def set_status(cid: str, status: str) -> dict:
    if status not in STATUSES:
        raise ValueError(f"status non valido: {status}")
    rec = _get(cid=cid)
    if not rec:
        raise KeyError("accesso cliente sconosciuto")
    rec["status"] = status
    _save(rec)
    return public(rec)


def list_accounts() -> list[dict]:
    """Elenco per il pannello FORMA — mai segreti, mai la chiave tenant."""
    if _use_db():
        try:
            from . import tenants
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(f"SELECT {_COLS} FROM client_access "
                                "WHERE status != 'rimosso' ORDER BY email")
                    return [public(_row_to_rec(r)) for r in cur.fetchall()]
        except Exception:
            log.exception("client_access: lista DB fallita, fallback memoria")
    return [public(r) for r in sorted(_MEM.values(), key=lambda r: r["email"])
            if r["status"] != "rimosso"]


def public(rec: dict) -> dict:
    """Proiezione senza segreti (niente hash, niente chiave tenant)."""
    return {"id": rec["id"], "email": rec["email"],
            "display_name": rec["display_name"], "status": rec["status"],
            "pin_set": bool(rec["pin_hash"]), "locked": bool(rec["locked"]),
            "last_login_at": str(rec.get("last_login_at") or "")}


def tenant_key_of(cid: str) -> str:
    """La chiave tenant in chiaro — SOLO per uso server-side (/client/chat)."""
    rec = _get(cid=cid)
    if not rec:
        raise KeyError("accesso cliente sconosciuto")
    return _unseal_key(rec["tenant_key_enc"])


# ── login del cliente ─────────────────────────────────────────────────────────
def _fail(rec: dict) -> None:
    rec["failed_attempts"] = int(rec.get("failed_attempts") or 0) + 1
    if rec["failed_attempts"] >= MAX_ATTEMPTS:
        rec["locked"] = True
    _save(rec)


def login(email: str, credential: str) -> dict | None:
    """Autentica il cliente. Un solo ingresso per entrambe le fasi:
    - PIN non ancora generato → `credential` è la PASSWORD del primo accesso;
    - PIN generato → `credential` è il CODICE a 6 cifre (la password è spenta).
    Ritorna il record pubblico, o None (mai il perché: niente oracoli)."""
    rec = _get(email=(email or "").strip().lower())
    if not rec or rec["status"] != "attivo" or rec["locked"]:
        return None
    if rec["pin_hash"]:
        ok = _verify(credential or "", rec["pin_hash"])
    else:
        ok = _verify(credential or "", rec["password_hash"])
    if not ok:
        _fail(rec)
        return None
    rec["failed_attempts"] = 0
    _save(rec)
    if _use_db():
        try:
            _db_touch_login(rec["id"])
        except Exception:
            pass
    return public(rec)


# ── sessioni firmate (HMAC, scadenza) ─────────────────────────────────────────
def make_session(cid: str, kind: str = "client") -> str:
    payload = {"cid": cid, "kind": kind,
               "exp": int(time.time()) + SESSION_TTL.get(kind, 3600)}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(settings.client_session_secret.encode(), raw.encode(),
                   hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def check_session(token: str) -> dict | None:
    """Valida firma e scadenza; l'account deve essere ancora attivo (una
    sospensione taglia fuori anche le sessioni già emesse)."""
    if not enabled() or not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    good = hmac.new(settings.client_session_secret.encode(), raw.encode(),
                    hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < time.time():
        return None
    rec = _get(cid=payload.get("cid"))
    if not rec or rec["status"] != "attivo":
        return None
    return {"account": public(rec), "kind": payload.get("kind") or "client"}
