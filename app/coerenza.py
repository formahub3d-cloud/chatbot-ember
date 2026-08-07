"""S5.1c/2 · Le chiavi che il registro non riesce a leggere, dette all'avvio.

Nasce da una voce «DA DECIDERE» del 7/08, guardando perché lo script del
rapporto non vedeva niente. Il registro dei token e la RLS non filtrano per la
stessa cosa:

    il registro:  WHERE tenant_code = branding.tenant_code
    la RLS:       ovyon.can_read(...) su allowed_tenants = allowed_scopes

Oggi combaciano — una chiave cliente nasce con `tenants: [tenant_code]` e la
dogfood ha `forma-core` fra gli scope — ma **nessuno lo impone**. Basta emettere
una chiave con uno scope diverso dal proprio codice perché:

- l'INSERT del consumo venga rifiutato dal `with check` della policy (si vede
  nei log, ma solo se qualcuno li guarda);
- e soprattutto **la SELECT del saldo torni vuota**, che è il caso peggiore: il
  freno leggerebbe zero, `mai_accreditato` direbbe «mai aperto», e passerebbe
  tutto. Fallisce nella direzione giusta — aperto, non chiuso — ma **in
  silenzio**, e il silenzio su un percorso che vale soldi si scopre da una
  bolletta.

Questo modulo non ripara niente e non blocca l'avvio: **guarda e dichiara**, con
i tre esiti che non si confondono (`degrado.py`, regola V9).

    ok       ogni chiave ha un `tenant_code` compreso nei suoi scope
    guasto   almeno una chiave no, ed è elencata per nome
    non-so   l'elenco delle chiavi non è leggibile (Supabase spento)

**Il nome della chiave non è un segreto** (`list_keys` non restituisce mai il
valore, solo l'hash sta nel database): elencare i nomi è quello che rende il
controllo utile invece che un contatore.
"""
from __future__ import annotations

import logging

from . import manage_apikeys, tenants

log = logging.getLogger("ember.coerenza")

OK = "ok"
GUASTO = "guasto"
NON_SO = "non-so"


def _scope_di(chiave: dict) -> list[str]:
    """Gli scope a livello tenant, che sono quelli che la RLS confronta."""
    grezzi = chiave.get("tenants") or []
    if isinstance(grezzi, str):                       # la colonna può essere testo
        grezzi = [p for p in grezzi.replace("{", "").replace("}", "").split(",") if p]
    return [str(x).strip() for x in grezzi if str(x).strip()]


def esamina(chiavi: list[dict]) -> dict:
    """La diagnosi, come funzione pura sull'elenco già letto.

    Due difetti diversi, tenuti separati perché hanno conseguenze diverse:

    - `senza_codice`: la chiave non ha `branding.tenant_code`, quindi il
      consumo **non viene scritto affatto** (`ledger.codice_tenant` rifiuta di
      indovinarlo dagli scope). Il cliente usa il prodotto a gratis;
    - `fuori_scope`: il codice c'è ma non è fra gli scope, quindi la RLS
      nasconde le sue righe. Il consumo non si scrive **e** il freno è cieco.

    La chiave master (`*` fra gli scope) non è un cliente: è l'accesso admin
    server-side, non ha un tenant e non deve averne uno.
    """
    senza, fuori = [], []
    for k in chiavi:
        if not k.get("active", True):
            continue                                  # una chiave revocata non consuma
        scope = _scope_di(k)
        if "*" in scope:
            continue                                  # master: nessun tenant, per disegno
        codice = str((k.get("branding_full") or {}).get("tenant_code") or "").strip()
        nome = str(k.get("name") or "?")
        if not codice:
            senza.append({"chiave": nome, "scope": scope})
        elif codice not in scope:
            fuori.append({"chiave": nome, "tenant_code": codice, "scope": scope})
    return {
        "stato": GUASTO if (senza or fuori) else OK,
        "senza_codice": senza,
        "fuori_scope": fuori,
    }


def stato() -> dict:
    """Come `esamina()`, ma legge le chiavi. Non solleva mai.

    `non-so` quando le chiavi non si leggono: è diverso da «tutte a posto», e
    scriverlo come `ok` sarebbe un controllo che si spegne da solo — il difetto
    del V10, quello dell'allarme che dopo un redeploy diceva «va tutto bene».
    """
    try:
        if not tenants._apikeys_enabled():
            return {"stato": NON_SO, "motivo": "elenco chiavi non configurato "
                                               "(nessun Supabase): niente da confrontare"}
        return esamina(manage_apikeys.list_keys())
    except Exception as e:
        log.warning("coerenza chiavi non verificabile: %s", e)
        return {"stato": NON_SO, "motivo": f"elenco chiavi non leggibile: {type(e).__name__}"}


def riga_boot() -> str:
    """Una riga per il log d'avvio. Sulla falsariga di `dbcheck.riga_boot()`."""
    s = stato()
    if s["stato"] == NON_SO:
        return f"[chiavi] coerenza NON verificata — {s.get('motivo', '')}"
    if s["stato"] == OK:
        return "[chiavi] ogni chiave attiva ha un tenant_code compreso nei suoi scope"
    pezzi = []
    if s["fuori_scope"]:
        nomi = ", ".join(f"{v['chiave']} (tenant_code={v['tenant_code']} "
                         f"non in {v['scope']})" for v in s["fuori_scope"])
        pezzi.append(f"{len(s['fuori_scope'])} col codice FUORI dai propri scope "
                     f"→ registro cieco e freno che passa tutto: {nomi}")
    if s["senza_codice"]:
        nomi = ", ".join(v["chiave"] for v in s["senza_codice"])
        pezzi.append(f"{len(s['senza_codice'])} SENZA tenant_code "
                     f"→ il loro consumo non viene scritto: {nomi}")
    return "[chiavi] " + " · ".join(pezzi)
