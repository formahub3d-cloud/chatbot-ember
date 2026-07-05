"""Metriche in-memory leggere, per scope, dal boot del processo.

Conta: chat con risposta, gap (domande senza risposta), feedback 👍/👎.
Nessuna persistenza: si azzerano a ogni redeploy. Servono a un colpo d'occhio
via GET /admin/analytics; per uno storico duraturo va usata una tabella
(es. access_logs dello schema OVYON). Tutte le operazioni sono best-effort e
thread-safe, e non devono MAI far fallire una richiesta.
"""
from collections import defaultdict, deque
from threading import Lock
import time

_lock = Lock()
_started = time.time()
_chats = defaultdict(int)
_gaps = defaultdict(int)
_fb_up = defaultdict(int)
_fb_down = defaultdict(int)
# Ring-buffer (redatti) delle ultime domande senza risposta e dei feedback negativi:
# servono ad arricchire il cervello (capire cosa manca / dove è debole). In-memory.
_recent_gaps = deque(maxlen=60)
_recent_neg = deque(maxlen=60)


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


def bump_gap(scopes, question: str = "") -> None:
    try:
        with _lock:
            k = _skey(scopes)
            _gaps[k] += 1
            if question:
                _recent_gaps.append({"scope": k, "q": question[:200], "at": int(time.time())})
    except Exception:
        pass


def bump_feedback(scopes, up: bool, question: str = "") -> None:
    try:
        with _lock:
            k = _skey(scopes)
            (_fb_up if up else _fb_down)[k] += 1
            if not up and question:
                _recent_neg.append({"scope": k, "q": question[:200], "at": int(time.time())})
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


def insights() -> dict:
    """Segnali per arricchire il cervello: ultime domande senza risposta (gap) e
    ultimi feedback negativi (👎), redatti, più recenti prima. Sola lettura."""
    with _lock:
        return {
            "gaps": list(_recent_gaps)[::-1],
            "negative_feedback": list(_recent_neg)[::-1],
        }


def reset() -> None:
    """Solo per i test."""
    with _lock:
        _chats.clear(); _gaps.clear(); _fb_up.clear(); _fb_down.clear()
        _recent_gaps.clear(); _recent_neg.clear()
