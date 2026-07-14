"""Metriche in-memory leggere, per scope, dal boot del processo.

Conta: chat con risposta, gap (domande senza risposta), feedback 👍/👎.
Nessuna persistenza: si azzerano a ogni redeploy. Servono a un colpo d'occhio
via GET /admin/analytics; per uno storico duraturo va usata una tabella
(es. access_logs dello schema OVYON). Tutte le operazioni sono best-effort e
thread-safe, e non devono MAI far fallire una richiesta.
"""
from collections import defaultdict, deque
from threading import Lock
import re
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


_NORM_RE = re.compile(r"[^\w\sàèéìòù]", re.UNICODE)


def _norm_q(q: str) -> str:
    """Normalizza una domanda per il raggruppamento: minuscole, niente punteggiatura,
    spazi compattati. Serve a contare come UNA le varianti della stessa domanda."""
    return " ".join(_NORM_RE.sub(" ", (q or "").lower()).split())


def learning_tasks() -> dict:
    """Auto-miglioramento del cervello: trasforma i gap (domande senza risposta) e i
    feedback 👎 in TASK azionabili — raggruppate per scope+domanda, con conteggio e
    un suggerimento concreto. Ordinate per frequenza, poi per recenza. Sola lettura."""
    with _lock:
        gaps = list(_recent_gaps)
        negs = list(_recent_neg)
    groups: dict[tuple, dict] = {}
    for kind, items in (("gap", gaps), ("feedback", negs)):
        for it in items:
            key = (kind, it.get("scope", ""), _norm_q(it.get("q", "")))
            g = groups.get(key)
            if g:
                g["count"] += 1
                g["last_at"] = max(g["last_at"], it.get("at", 0))
            else:
                groups[key] = {"kind": kind, "scope": it.get("scope", ""),
                               "question": it.get("q", ""), "count": 1,
                               "last_at": it.get("at", 0)}
    tasks = []
    for g in sorted(groups.values(), key=lambda g: (-g["count"], -g["last_at"])):
        if g["kind"] == "gap":
            g["suggestion"] = (f'Aggiungi (o arricchisci) una nota nello scope "{g["scope"]}" '
                               f'che risponda a: "{g["question"]}" — poi rilancia l\'ingest.')
        else:
            g["suggestion"] = (f'Risposta segnalata 👎 nello scope "{g["scope"]}": rivedi la nota '
                               f'di origine per "{g["question"]}" e chiarisci il contenuto.')
        tasks.append(g)
    return {"tasks": tasks,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _esc(s: str) -> str:
    """Escape del valore di una label Prometheus."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def prometheus() -> str:
    """Esposizione in formato testo Prometheus (per scraping/Grafana). Totali +
    serie per-scope. Sola lettura. Da servire su GET /metrics (protetto)."""
    s = snapshot()
    t = s["totals"]
    out = [
        "# HELP divina_uptime_seconds Secondi dal boot del processo.",
        "# TYPE divina_uptime_seconds gauge",
        f"divina_uptime_seconds {s['uptime_s']}",
        "# HELP divina_chat_total Chat con risposta.",
        "# TYPE divina_chat_total counter",
        f"divina_chat_total {t['chat']}",
        "# HELP divina_gap_total Domande senza risposta (gap del cervello).",
        "# TYPE divina_gap_total counter",
        f"divina_gap_total {t['gap']}",
        "# HELP divina_feedback_total Feedback ricevuti, per esito.",
        "# TYPE divina_feedback_total counter",
        f'divina_feedback_total{{kind="up"}} {t["feedback_up"]}',
        f'divina_feedback_total{{kind="down"}} {t["feedback_down"]}',
    ]
    for scope, d in s["per_scope"].items():
        lbl = _esc(scope)
        out.append(f'divina_chat_by_scope_total{{scope="{lbl}"}} {d["chat"]}')
        out.append(f'divina_gap_by_scope_total{{scope="{lbl}"}} {d["gap"]}')
        out.append(f'divina_feedback_by_scope_total{{scope="{lbl}",kind="up"}} {d["feedback_up"]}')
        out.append(f'divina_feedback_by_scope_total{{scope="{lbl}",kind="down"}} {d["feedback_down"]}')
    return "\n".join(out) + "\n"


def reset() -> None:
    """Solo per i test."""
    with _lock:
        _chats.clear(); _gaps.clear(); _fb_up.clear(); _fb_down.clear()
        _recent_gaps.clear(); _recent_neg.clear()
