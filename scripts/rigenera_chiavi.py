#!/usr/bin/env python3
"""V5 · Rifare le chiavi tenant DA ZERO — ma nell'ordine che regge.

Il prefisso delle chiavi è già nei siti dei clienti (CLAUDE.md): cancellare
prima di sostituire spegne i widget su quattro siti in produzione, in
silenzio. L'ordine:

  1. EMETTERE le nuove accanto alle vecchie (entrambe valide)   → `emetti`
  2. SOSTITUIRLE sui siti, uno per uno                          → Andrea, a mano
  3. VERIFICARE che le vecchie non ricevano più traffico        → `stato`
     (l'ultimo utilizzo per chiave ora esce da /admin/tenants)
  4. REVOCARE le vecchie, e solo allora                         → `revoca`
     (rifiuta se la chiave ha traffico recente, salvo FORZA=si)

Uso:
    EMBER_URL=… ADMIN_TOKEN=… python3 scripts/rigenera_chiavi.py stato
    EMBER_URL=… ADMIN_TOKEN=… python3 scripts/rigenera_chiavi.py emetti --nome ats
    EMBER_URL=… ADMIN_TOKEN=… python3 scripts/rigenera_chiavi.py emetti --tutte
    EMBER_URL=… ADMIN_TOKEN=… python3 scripts/rigenera_chiavi.py revoca --nome ats
    EMBER_URL=… ADMIN_TOKEN=… FORZA=si python3 scripts/rigenera_chiavi.py revoca --nome ats

Le chiavi nuove si stampano UNA volta sola (nel DB c'è solo l'hash):
copiale subito nel posto giusto.
"""
import argparse
import os
import sys
from datetime import date, timedelta

SUFFISSO = "-r2026"          # la sostituta di «ats» si chiama «ats-r2026»
GIORNI_DI_SILENZIO = 7       # una chiave si revoca solo dopo una settimana muta


def si_puo_revocare(ultimo_uso: str, oggi: str, giorni: int = GIORNI_DI_SILENZIO) -> bool:
    """True se la chiave è muta da almeno `giorni` (o non ha MAI avuto traffico).
    Puro e testabile: le date arrivano come stringhe YYYY-MM-DD."""
    if not ultimo_uso:
        return True
    try:
        u = date.fromisoformat(ultimo_uso[:10])
        o = date.fromisoformat(oggi[:10])
    except ValueError:
        return False                       # data illeggibile: in dubbio, freno
    return (o - u) >= timedelta(days=giorni)


def stato(get) -> list[dict]:
    ks = (get("/admin/tenants") or {}).get("tenants", [])
    for k in ks:
        print(f"  {k['name']:28s} {'attiva' if k.get('active') else 'REVOCATA':9s} "
              f"ultimo uso: {k.get('ultimo_uso') or 'mai':12s} usi: {k.get('usi', 0)}")
    return ks


def emetti(get, post, nome: str | None, tutte: bool) -> list[dict]:
    """Passo 1: la sostituta accanto all'originale, con GLI STESSI grant.
    Idempotente: se la sostituta esiste già, non se ne crea una terza."""
    ks = (get("/admin/tenants") or {}).get("tenants", [])
    nomi = {k["name"] for k in ks}
    esiti = []
    for k in ks:
        if not k.get("active") or k["name"].endswith(SUFFISSO):
            continue
        if not tutte and k["name"] != nome:
            continue
        nuovo = k["name"] + SUFFISSO
        if nuovo in nomi:
            esiti.append({"name": nuovo, "esito": "esiste già, non duplicata"})
            continue
        r = post("/admin/tenants", {
            "name": nuovo, "orgs": k.get("orgs") or [], "tenants": k.get("tenants") or [],
            "subs": k.get("subs") or [], "origins": k.get("origins") or [],
            "quota": k.get("quota_day") or 0, "branding": k.get("branding_full") or {}})
        esiti.append({"name": nuovo, "esito": "emessa", "key": r.get("key", "")})
        print(f"  {nuovo} · EMESSA — chiave (mostrata UNA volta): {r.get('key','?')}")
    if not esiti:
        print("  niente da emettere (nome inesistente o già sostituita)")
    return esiti


def revoca(get, post, nome: str, forza: bool) -> dict:
    """Passo 4: solo dopo il silenzio. La sostituta deve esistere ed essere attiva."""
    ks = (get("/admin/tenants") or {}).get("tenants", [])
    per_nome = {k["name"]: k for k in ks}
    k = per_nome.get(nome)
    if not k:
        return {"esito": "chiave inesistente"}
    if nome.endswith(SUFFISSO):
        return {"esito": "questa È la sostituta: non si revoca da qui"}
    sost = per_nome.get(nome + SUFFISSO)
    if not sost or not sost.get("active"):
        return {"esito": f"manca la sostituta attiva ({nome}{SUFFISSO}): prima il passo 1"}
    oggi = date.today().isoformat()
    if not forza and not si_puo_revocare(k.get("ultimo_uso", ""), oggi):
        return {"esito": f"ha traffico recente (ultimo uso {k.get('ultimo_uso')}): il sito "
                         f"non è ancora passato alla nuova. Aspetta {GIORNI_DI_SILENZIO} "
                         f"giorni di silenzio o rilancia con FORZA=si"}
    post("/admin/tenants/revoke", {"name": nome})
    return {"esito": "revocata (active=false, mai cancellata)"}


def main(argv=None) -> int:
    import httpx
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("comando", choices=["stato", "emetti", "revoca"])
    ap.add_argument("--nome")
    ap.add_argument("--tutte", action="store_true")
    a = ap.parse_args(argv)

    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    forza = os.environ.get("FORZA", "").strip().lower() in ("si", "sì", "1", "true")
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2
    h = {"Authorization": f"Bearer {tok}"}

    def get(path):
        r = httpx.get(base + path, headers=h, timeout=30)
        r.raise_for_status()
        return r.json()

    def post(path, body):
        r = httpx.post(base + path, json=body, headers=h, timeout=30)
        r.raise_for_status()
        return r.json()

    if a.comando == "stato":
        stato(get)
    elif a.comando == "emetti":
        if not a.nome and not a.tutte:
            print("emetti: serve --nome <chiave> oppure --tutte", file=sys.stderr)
            return 2
        emetti(get, post, a.nome, a.tutte)
    else:
        if not a.nome:
            print("revoca: serve --nome <chiave>", file=sys.stderr)
            return 2
        print("  " + revoca(get, post, a.nome, forza)["esito"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
