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


def _esc(s: str) -> str:
    """Escape del valore di una label Prometheus."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def prometheus() -> str:
    """Esposizione in formato testo Prometheus (per scraping/Grafana). Totali +
    serie per-scope. Sola lettura. Da servire su GET /metrics (protetto)."""
    s = snapshot()
    t = s["totals"]
    out = [
        "# HELP ember_uptime_seconds Secondi dal boot del processo.",
        "# TYPE ember_uptime_seconds gauge",
        f"ember_uptime_seconds {s['uptime_s']}",
        "# HELP ember_chat_total Chat con risposta.",
        "# TYPE ember_chat_total counter",
        f"ember_chat_total {t['chat']}",
        "# HELP ember_gap_total Domande senza risposta (gap del cervello).",
        "# TYPE ember_gap_total counter",
        f"ember_gap_total {t['gap']}",
        "# HELP ember_feedback_total Feedback ricevuti, per esito.",
        "# TYPE ember_feedback_total counter",
        f'ember_feedback_total{{kind="up"}} {t["feedback_up"]}',
        f'ember_feedback_total{{kind="down"}} {t["feedback_down"]}',
    ]
    for scope, d in s["per_scope"].items():
        lbl = _esc(scope)
        out.append(f'ember_chat_by_scope_total{{scope="{lbl}"}} {d["chat"]}')
        out.append(f'ember_gap_by_scope_total{{scope="{lbl}"}} {d["gap"]}')
        out.append(f'ember_feedback_by_scope_total{{scope="{lbl}",kind="up"}} {d["feedback_up"]}')
        out.append(f'ember_feedback_by_scope_total{{scope="{lbl}",kind="down"}} {d["feedback_down"]}')
    return "\n".join(out) + "\n"


def reset() -> None:
    """Solo per i test."""
    with _lock:
        _chats.clear(); _gaps.clear(); _fb_up.clear(); _fb_down.clear()
        _recent_gaps.clear(); _recent_neg.clear()
