#!/usr/bin/env python3
"""Reset delle chiavi tenant (1/08) — si revocano TUTTE e si riparte da zero.

Correzione di rotta rispetto al piano «rigenera in quattro passi» (prima
versione del punto 7): Andrea ha confermato l'1/08 che NESSUNA chiave è
installata presso clienti — erano emesse in previsione di vendite non ancora
avvenute. Quindi niente migrazione a tappe: reset. La regola da qui in
avanti: UNA CHIAVE ESISTE SOLO SE QUALCUNO LA STA USANDO.

Una sola eccezione, o Andrea si chiude fuori: la console usa la chiave FORMA
(localStorage `dv_tenant_key`). Ordine obbligato:
  1. `emetti`  — riemette SOLO la chiave FORMA, con un NOME NUOVO (la revoca
                 lavora per nome: il nome nuovo la tiene fuori dal passo 3);
  2. Andrea la incolla in console (Impostazioni → Connessione → chiave
                 tenant) e verifica che la chat risponda;
  3. `revoca`  — con CONFERMA_RESET=si revoca tutto il resto. Senza la
                 chiave nuova attiva, si rifiuta: revocare prima di
                 sostituire spegnerebbe la console.

urllib, non httpx (punto 8): gira col Python di sistema, zero dipendenze —
chi lancia uno script di manutenzione non deve costruire un ambiente.

Uso:
    EMBER_URL=… ADMIN_TOKEN=… python3 scripts/reset_chiavi.py stato
    EMBER_URL=… ADMIN_TOKEN=… python3 scripts/reset_chiavi.py emetti
    EMBER_URL=… ADMIN_TOKEN=… CONFERMA_RESET=si python3 scripts/reset_chiavi.py revoca
"""
import os
import sys

# Il nome NUOVO della chiave FORMA: diverso da ogni nome storico, così la
# revoca per nome non la tocca. Cambia qui se serve (o env FORMA_NOME).
NUOVO_NOME = "FORMA (console) · 2026-08"


def piano_reset(chiavi: list[dict], nuovo_nome: str = NUOVO_NOME) -> dict:
    """Il piano, PURO e testabile: cosa revocare e se si può già.

    `chiavi`: le righe di GET /admin/tenants. `pronto` resta False finché la
    chiave nuova non esiste ATTIVA — il freno che impedisce di chiudersi
    fuori. `revoca`: i nomi attivi da spegnere (dedup, il nuovo escluso)."""
    revoca: list[str] = []
    forma_attiva = False
    for k in chiavi or []:
        nome = (k.get("name") or "").strip()
        if not nome:
            continue
        if nome == nuovo_nome:
            forma_attiva = forma_attiva or bool(k.get("active"))
            continue
        if k.get("active") and nome not in revoca:
            revoca.append(nome)
    return {"pronto": forma_attiva, "revoca": revoca,
            "motivo": "" if forma_attiva else
            (f"la chiave nuova «{nuovo_nome}» non esiste attiva: prima `emetti`, "
             "poi incollala in console e verifica la chat, POI la revoca")}


def main() -> int:
    import json as _json
    import urllib.request
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    nuovo = os.environ.get("FORMA_NOME", NUOVO_NOME)
    conferma = os.environ.get("CONFERMA_RESET", "").strip().lower() in ("si", "sì", "1", "true")
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "stato").strip().lower()
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2

    def get(path):
        req = urllib.request.Request(base + path,
                                     headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode())

    def post(path, body):
        req = urllib.request.Request(base + path, data=_json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {tok}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode())

    chiavi = (get("/admin/tenants") or {}).get("tenants") or []
    piano = piano_reset(chiavi, nuovo)

    if cmd == "stato":
        if not chiavi:
            print("Nessuna chiave nel motore.")
        for k in chiavi:
            print(f"  {'ATTIVA ' if k.get('active') else 'spenta '}"
                  f"{k.get('name','?')} · ultimo uso: {k.get('ultimo_uso') or 'mai'}"
                  f" · usi: {k.get('usi', 0)}")
        print(f"\nPiano: da revocare {len(piano['revoca'])} nom{'e' if len(piano['revoca'])==1 else 'i'}"
              f" · chiave nuova «{nuovo}» {'ATTIVA' if piano['pronto'] else 'ASSENTE'}")
        if not piano["pronto"]:
            print(f"  → {piano['motivo']}")
        return 0

    if cmd == "emetti":
        if piano["pronto"]:
            print(f"«{nuovo}» esiste già attiva. La chiave si mostra UNA sola volta: "
                  "se l'hai persa, revoca quel nome e rilancia `emetti`.")
            return 0
        # Si clona la configurazione della FORMA storica (grant, quota,
        # branding) se c'è; altrimenti i default del tenant interno.
        src = next((k for k in chiavi
                    if k.get("active") and "forma-core" in (k.get("tenants") or [])), None)
        body = {"name": nuovo,
                "orgs": (src or {}).get("orgs") or ["forma"],
                "tenants": (src or {}).get("tenants") or ["forma-core"],
                "subs": (src or {}).get("subs") or [],
                "origins": (src or {}).get("origins") or [],
                "quota": (src or {}).get("quota_day"),
                "branding": (src or {}).get("branding_full") or {}}
        r = post("/admin/tenants", body)
        print("Chiave FORMA nuova — COPIALA ORA, si mostra una sola volta:\n")
        print(f"  {r.get('key', '?')}\n")
        print("Incollala in console (Impostazioni → Connessione… → chiave tenant),")
        print("verifica che la chat risponda, e solo dopo lancia `revoca`.")
        return 0

    if cmd == "revoca":
        if not piano["pronto"]:
            print(f"MI RIFIUTO: {piano['motivo']}", file=sys.stderr)
            return 1
        if not piano["revoca"]:
            print("Niente da revocare: restano solo le chiavi nuove.")
            return 0
        if not conferma:
            print("Sto per revocare questi nomi (le chiavi smettono di funzionare SUBITO):")
            for n in piano["revoca"]:
                print(f"  · {n}")
            print(f"\nLa chiave «{nuovo}» resta attiva. Per procedere: CONFERMA_RESET=si")
            return 1
        tot = 0
        for n in piano["revoca"]:
            r = post("/admin/tenants/revoke", {"name": n})
            quante = int(r.get("revoked", 0))
            tot += quante
            print(f"  revocata «{n}» ({quante} chiav{'e' if quante == 1 else 'i'})")
        print(f"\nReset completato: {tot} chiavi spente, «{nuovo}» attiva.")
        print("Da qui in avanti: una chiave esiste solo se qualcuno la sta usando.")
        return 0

    print(f"Comando sconosciuto: {cmd} (usa: stato · emetti · revoca)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
