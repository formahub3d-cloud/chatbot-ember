"""Metriche in-memory leggere, per scope, dal boot del processo.

Conta: chat con risposta, gap (domande senza risposta), feedback 👍/👎.
Nessuna persistenza: si azzerano a ogni redeploy. Servono a un colpo d'occhio
via GET /admin/analytics; per uno storico duraturo va usata una tabella
(es. access_logs dello schema OVYON). Tutte le operazioni sono best-effort e
thread-safe, e non devono MAI far fallire una richiesta.
"""
from collections import defaultdict
from threading import Lock
import time

_lock = Lock()
_started = time.time()
_chats = defaultdict(int)
_gaps = defaultdict(int)
_fb_up = defaultdict(int)
_fb_down = defaultdict(int)


def _skey(scopes) -> str:
    """Chiave stabile per un insieme di scope (ordinata). Vuoto = '∅'."""
    if not scopes:
        return "∅"
    try:
        return ",".join(sorted(str(s) for s in scopes))
    except Exception:
        return str(scopes)


def bump_chat(scopes) -> None:
    try:
        with _lock:
            _chats[_skey(scopes)] += 1
    except Exception:
        pass


def bump_gap(scopes) -> None:
    try:
        with _lock:
            _gaps[_skey(scopes)] += 1
    except Exception:
        pass


def bump_feedback(scopes, up: bool) -> None:
    try:
        with _lock:
            (_fb_up if up else _fb_down)[_skey(scopes)] += 1
    except Exception:
        pass


def snapshot() -> dict:
    """Fotografia aggregata: totali + dettaglio per scope. Sola lettura."""
    with _lock:
        keys = set(_chats) | set(_gaps) | set(_fb_up) | set(_fb_down)
        per_scope = {
            k: {
                "chat": _chats[k],
                "gap": _gaps[k],
                "feedback_up": _fb_up[k],
                "feedback_down": _fb_down[k],
            }
            for k in sorted(keys)
        }
        return {
            "uptime_s": int(time.time() - _started),
            "totals": {
                "chat": sum(_chats.values()),
                "gap": sum(_gaps.values()),
                "feedback_up": sum(_fb_up.values()),
                "feedback_down": sum(_fb_down.values()),
            },
            "per_scope": per_scope,
        }


def reset() -> None:
    """Solo per i test."""
    with _lock:
        _chats.clear(); _gaps.clear(); _fb_up.clear(); _fb_down.clear()
