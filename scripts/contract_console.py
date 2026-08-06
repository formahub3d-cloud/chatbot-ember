"""Contratto console ↔ backend (CT, sintesi 29-07).

Estrae dal pannello (panel/index.html, SPA a file unico) ogni chiamata di rete
e la confronta con le rotte FastAPI registrate. Nato per rendere impossibile il
ritorno degli «endpoint fantasma»: una vista che chiama una rotta inesistente
deve far fallire la CI, non fallire in silenzio in produzione.

Uso:
  python scripts/contract_console.py            # stampa il referto in markdown
  (il test tests/test_contract_console.py usa le stesse funzioni)

Analisi STATICA: niente rete, niente database. I path non determinabili
staticamente NON vengono indovinati: finiscono nel referto come «dinamici»,
da giudicare a occhio umano.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:            # eseguibile anche da scripts/
    sys.path.insert(0, str(_ROOT))

PANEL = _ROOT / "panel" / "index.html"

# ── PARTE 1: le chiamate del frontend ─────────────────────────────────────────
# api('engine'|'orch', '<path>' | `<template>` | '<path>?'+q(...), {method:...})
_API_RE = re.compile(
    r"""api\(\s*'(?P<svc>engine|orch)'\s*,\s*(?P<q>['`])(?P<path>[^'`]+)(?P=q)"""
)
# fetch('<path>'...) e fetch(<base>+'<path>'...): il pannello è servito
# same-origin dal motore → le fetch dirette sono contratti del MOTORE.
_FETCH_RE = re.compile(
    r"""fetch\(\s*(?:(?P<q>['`])(?P<path>/[^'`]+)(?P=q)|[A-Za-z_$][\w$.]*\s*\+\s*'(?P<cpath>/[^']+)')"""
)
_METHOD_RE = re.compile(r"method\s*:\s*'(?P<m>GET|POST|PUT|DELETE|PATCH)'")


def _norm(path: str) -> str:
    """Normalizza al solo percorso: via querystring e interpolazioni."""
    path = path.split("?")[0]
    # `${expr}` nei template literal → segmento-parametro
    path = re.sub(r"\$\{[^}]*\}", "{param}", path)
    return path.rstrip("&")


def _line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def extract_calls(html: str | None = None) -> list[dict]:
    """Tutte le chiamate di rete del pannello: servizio, metodo, path, riga.
    I casi non determinabili sono marcati dynamic=True (mai indovinati)."""
    src = html if html is not None else PANEL.read_text("utf-8")
    calls: list[dict] = []
    for m in _API_RE.finditer(src):
        ctx = src[m.start(): m.start() + 400]
        method = (_METHOD_RE.search(ctx).group("m") if _METHOD_RE.search(ctx) else "GET")
        raw = m.group("path")
        calls.append({"service": m.group("svc"), "method": method,
                      "path": _norm(raw), "line": _line_of(src, m.start()),
                      "dynamic": "${" in raw and "{param}" not in _norm(raw)})
    for m in _FETCH_RE.finditer(src):
        raw = m.group("path") or m.group("cpath")
        if raw.startswith(("/panel", "/widget", "http")):
            continue                      # asset statici / esterni: non è API
        ctx = src[m.start(): m.start() + 400]
        method = (_METHOD_RE.search(ctx).group("m") if _METHOD_RE.search(ctx) else "GET")
        calls.append({"service": "engine", "method": method,
                      "path": _norm(raw), "line": _line_of(src, m.start()),
                      "dynamic": False})
    # dedup su (service, method, path), tenendo la prima riga
    seen, out = set(), []
    for c in calls:
        k = (c["service"], c["method"], c["path"])
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


# ── PARTE 2: le rotte del backend ─────────────────────────────────────────────
def backend_routes():
    """(metodo, path) per ogni rotta FastAPI registrata + i mount statici."""
    from app.main import app
    routes, mounts = [], []
    for r in app.routes:
        path = getattr(r, "path", "")
        methods = getattr(r, "methods", None)
        if methods:
            for me in methods - {"HEAD", "OPTIONS"}:
                routes.append((me, path))
        elif path:                        # StaticFiles mount
            mounts.append(path)
    return routes, mounts


def _match(call_path: str, route_path: str) -> bool:
    """Confronto tollerante ai parametri: {x} in una delle due parti = jolly."""
    a, b = call_path.strip("/").split("/"), route_path.strip("/").split("/")
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x.startswith("{") or y.startswith("{"):
            continue
        if x != y:
            return False
    return True


def check(service: str = "engine") -> list[dict]:
    """Per ogni chiamata del pannello verso `service`: la rotta esiste?"""
    routes, mounts = backend_routes()
    report = []
    for c in extract_calls():
        if c["service"] != service:
            continue
        if c["dynamic"]:
            report.append({**c, "found": None, "note": "path dinamico: giudizio umano"})
            continue
        hit = any(me == c["method"] and _match(c["path"], p) for me, p in routes)
        if not hit and any(c["path"].startswith(m.rstrip("/") + "/") for m in mounts):
            hit = True                    # servito da un mount statico
        near = sorted({p for _, p in routes if c["path"].split("/")[1:2] == p.split("/")[1:2]})[:3]
        report.append({**c, "found": hit,
                       "note": "" if hit else f"simili: {', '.join(near) or '—'}"})
    return report


# ── V11/A4 · Il contratto AL CONTRARIO: chi chiama questa rotta? ─────────────
# Andrea, il 2/08 sera: «più cose aggiungiamo, più c'è vulnerabilità». Ogni
# endpoint che nessuna schermata chiama è superficie d'attacco che nessuno
# guarda — e che nessuno noterà quando smetterà di funzionare.
#
# Il contratto storico va in una direzione sola (il pannello chiama una rotta
# che non esiste → CI rossa). Questa è l'altra: una rotta che non chiama
# nessuno. Non tutte sono un difetto — alcune hanno un chiamante che sta fuori
# dal repo — ma **il chiamante va DICHIARATO**, con un nome, e una rotta nuova
# senza dichiarazione fa fallire la CI. È la differenza fra tenere una cosa e
# dimenticarsela.
CHIAMANTI_FUORI: dict[str, str] = {
    "POST /search": "connettore MCP (ovy_search) — mcp-connector/server.py",
    "GET /document": "connettore MCP (ovy_get_document)",
    "GET /context": "connettore MCP (ovy_list_context)",
    "POST /writeback": "connettore MCP (ovy_create_document / ovy_update_document)",
    "POST /billing/webhook": "Stripe, che chiama noi: non lo chiama nessuno di nostro",
    "POST /billing/checkout": "il link di pagamento, generato fuori dalla console",
    "GET /admin/gdpr/export": "obbligo di legge (art. 15), si esegue a mano su richiesta",
    "POST /admin/gdpr/erase": "obbligo di legge (art. 17), si esegue a mano su richiesta",
    "POST /admin/retention/run": "pulizia periodica, si lancia a mano (non c'è uno schedulato)",
    "POST /admin/tenants/brand": "provisioning di un tenant, a mano",
    "POST /admin/tasks/claim": "usato dal worker dell'orchestratore, non dalla console",
    "POST /documents/testo": "backend FORMA (S4.1): documento → testo, poi ingest nell'orchestratore",
    "POST /upload": "il widget OCR: caricamento documento → estrazione",
    "POST /upload/confirm": "conferma umana dell'estrazione OCR",
    "GET /contracts/templates": "generazione contratti: nessuna schermata, si usa via API",
    "POST /contracts/fill": "generazione contratti: nessuna schermata, si usa via API",
    "POST /contracts/pdf": "generazione contratti: nessuna schermata, si usa via API",
    "POST /contracts/sign": "firma elettronica: nessuna schermata, si usa via API",
    # Generate da FastAPI, non da noi. Restano perché /docs è il modo in cui si
    # prova un endpoint a mano; vale la pena sapere che espongono l'elenco
    # completo delle rotte a chiunque, ed è una decisione, non una svista.
    "GET /openapi.json": "FastAPI: lo schema che alimenta /docs e /redoc",
    "GET /docs": "FastAPI: la pagina per provare un endpoint a mano",
    "GET /docs/oauth2-redirect": "FastAPI: parte di /docs",
    "GET /redoc": "FastAPI: la stessa cosa, in un'altra veste",
}


def _sorgenti() -> str:
    """Tutto ciò che, nel repo, può chiamare il motore."""
    testo = []
    for f in ["panel/index.html", "panel/voce.js", "widget/embed.js", "widget/voce.js"]:
        pf = _ROOT / f
        if pf.exists():
            testo.append(pf.read_text("utf-8"))
    for d in ["scripts", "mcp-connector"]:
        for pf in (_ROOT / d).rglob("*"):
            if pf.suffix in (".py", ".js", ".md") and pf.name != "contract_console.py":
                testo.append(pf.read_text("utf-8", errors="ignore"))
    return "\n".join(testo)


def orfane() -> list[str]:
    """Le rotte del motore che nessuno chiama, e che nessuno ha dichiarato."""
    routes, _ = backend_routes()
    src = _sorgenti()
    fuori = set()
    for k in CHIAMANTI_FUORI:
        me, p = k.split(" ", 1)
        fuori.add((me, p))
    out = []
    for me, path in sorted(set(routes)):
        if path.startswith("/panel") or path.startswith("/widget") or path == "/health":
            continue
        base = path.split("{")[0].rstrip("/")
        if base and base in src:
            continue
        if (me, path) in fuori:
            continue
        out.append(f"{me} {path}")
    return out


def referto(service: str = "engine") -> str:
    rows = check(service)
    ok = sum(1 for r in rows if r["found"])
    dyn = sum(1 for r in rows if r["found"] is None)
    miss = [r for r in rows if r["found"] is False]
    out = [f"## Contratto console → servizio `{service}`",
           f"{ok} rotte trovate · {len(miss)} mancanti · {dyn} dinamiche\n",
           "| Chiamata | Riga | Trovata | Nota |", "|---|---|---|---|"]
    for r in rows:
        stato = {True: "✅", False: "❌", None: "❔"}[r["found"]]
        out.append(f"| `{r['method']} {r['path']}` | {r['line']} | {stato} | {r['note']} |")
    if miss:
        out.append("\n### Mancanti — da implementare, ripuntare o rimuovere")
        for r in miss:
            out.append(f"- `{r['method']} {r['path']}` (riga {r['line']}) — {r['note']}")
    return "\n".join(out)


if __name__ == "__main__":
    print(referto("engine"))
