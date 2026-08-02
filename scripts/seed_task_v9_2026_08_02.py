#!/usr/bin/env python3
"""V9 (2-08, pomeriggio) · Le task del giro «riempire il cervello di un cliente
senza chiederglielo», come DATI.

Sesto seed, stesso stampo dei cinque precedenti: brain_tasks, kind='audit',
idempotency_key stabile (`audit-2026-08-02-44` … `-50`). Rilanciarlo non duplica.

**Va lanciato PRIMA del merge**, come il seed del V8: `audit-merge` legge le
chiavi citate nei commit e non può spostare task che non esistono ancora.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_task_v9_2026_08_02.py
"""
import os
import sys

_K = "audit-2026-08-02-"

# (chiave, titolo, priorità, nota di nascita)
TASK_V9 = [
    (_K + "44", "Una funzione spenta lo dice dove si usa", "alta",
     "Trovato in produzione il 2/08: la pagina «Cosa so di te» diceva «Non so ancora "
     "niente di te» mentre la verità era «non posso ricordare niente, mi manca la "
     "tabella tenant_memory». /admin/status lo sapeva già e lo diceva bene, ma chi apre "
     "una schermata non va a leggere lo stato tecnico: legge quella frase e conclude che "
     "la funzione non serve a niente. Una funzione spenta che sembra inutile non chiede "
     "di essere riparata. Vale ovunque una funzione dipenda da qualcosa che può mancare: "
     "tabella, variabile o chiave."),
    (_K + "45", "La KB di un cliente nasce dal suo sito, come proposta", "alta",
     "Le KB dei cinque clienti stanno fra le 61 e le 77 righe: scheletri. Riempirle è "
     "lavoro manuale che dipende dal cliente, quindi per farlo bisognerebbe chiedergli un "
     "favore prima di avergli mostrato il valore. Il ribaltamento: si prende l'indirizzo "
     "del sito, se ne ricava una bozza in coda, e poi gli si apre il pannello e gli si "
     "chiede «cosa è sbagliato qui?». Correggere è cento volte più facile che compilare. "
     "Il caso giusto per provarlo è ATS: il materiale c'è, il permesso è di Andrea, il "
     "rischio è zero."),
    (_K + "46", "Ogni pezzo della KB automatica porta la sua fonte", "alta",
     "Quale URL e quale frase, con la citazione verificata LETTERALMENTE contro il testo "
     "scaricato — la stessa regola di learned.py, la stessa funzione. Una KB cliente "
     "senza provenienza è peggio di una vuota, perché sembra verificata."),
    (_K + "47", "Le capacità si raggiungono dalla conversazione", "alta",
     "Gemella di audit-2026-07-31-06, aperta dal 31 luglio. Le 42 skill esistono, la "
     "Squadra le mostra, Caronte ha la sua — e dalla chat non ci si arriva perché rag.py "
     "non le nomina mai. Il criterio: una capacità esiste quando qualcuno può usarla "
     "senza sapere come si chiama. Il vincolo resta: ciò che ha effetto fuori nasce "
     "in-approvazione, e col livello 3 spento non si accoda. Il lavoro è collegare, non "
     "allentare."),
    (_K + "48", "Riassunti compressi per la conversazione che dura", "media",
     "Erede della ‑42. Zoey li chiama epoch summaries: invece di tenere tutti i turni si "
     "comprime la conversazione in un riassunto richiamabile. Si scrive una volta a fine "
     "conversazione, non a ogni domanda, quindi non tocca i 55 ms di prima sillaba. Due "
     "limiti: non allarga i permessi (stesso test del filo) ed è un dato personale, con "
     "retention dichiarata."),
    (_K + "49", "Il «Dimentica» raggiunge anche i riassunti", "media",
     "Se il bottone della pagina «Cosa so di te» non arriva ai riassunti delle "
     "conversazioni, l'articolo 17 è coperto a metà — e mezza copertura, su un obbligo "
     "di legge, è peggio di nessuna promessa."),
    (_K + "50", "Le voci degli agenti dichiarano se non sono impostate", "bassa",
     "Il codice c'è dal V8, le variabili su Railway no: /admin/status dice "
     "voci_agente: {divina: true, dante: false, virgilio: false, beatrice: false}. In "
     "produzione Dante, Virgilio e Beatrice parlano ancora con la gola di Divina, e "
     "finora lo si scopriva solo ascoltandoli — cioè in demo, davanti a qualcuno."),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto:
    urllib in produzione, TestClient nei test — stessa logica, testabile."""
    esiti = []
    for key, titolo, priorita, nota in TASK_V9:
        r = post("/admin/tasks", {"kind": "audit", "title": titolo, "note": nota,
                                  "status": "aperta", "priorita": priorita,
                                  "idempotency_key": key})
        t = (r or {}).get("task") or {}
        esiti.append({"key": key, "id": t.get("id"), "status": t.get("status", "?"),
                      "priorita": t.get("priorita", priorita)})
    return esiti


def main() -> int:
    import json as _json
    import urllib.request
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2

    def post(path, body):
        # urllib, non httpx (regola dell'1/08): gira col Python di sistema.
        req = urllib.request.Request(base + path, data=_json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {tok}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode())

    for e in seed(post):
        print(f"  {e['key']} · {e['status']} · {e['priorita']} · id={e['id']}")
    print("Seed V9 completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
