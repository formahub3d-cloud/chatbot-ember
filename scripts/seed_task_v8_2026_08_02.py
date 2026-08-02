#!/usr/bin/env python3
"""V8 (2-08) · Le task del giro «quello che si vede al primo incontro», come DATI.

Quinto seed, non una modifica dei quattro precedenti: quelli sono già girati in
produzione e restano riproducibili com'erano. Stesso stampo: brain_tasks,
kind='audit', idempotency_key stabile — rilanciarlo non duplica niente. La
numerazione continua (‑33 … ‑42) e la DATA è quella di nascita, 02-08.

**Va lanciato PRIMA del merge della PR di questo giro.** Non è pignoleria: il
workflow `audit-merge` legge le chiavi citate nei commit e chiede al motore di
metterle «da verificare». Se le task non esistono ancora, le chiavi risultano
sconosciute — lo dice con un `::warning::`, ma il lavoro resta in DA FARE, cioè
esattamente il difetto che la regola 3 di questo giro doveva chiudere.

La ‑42 è dichiarata ma NON è lavoro di adesso, e nasce lo stesso: una task che
esiste solo nella testa di chi l'ha pensata non è una decisione presa, è una
cosa che si ridiscute daccapo fra un mese.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_task_v8_2026_08_02.py
"""
import os
import sys

_K = "audit-2026-08-02-"

# (chiave, titolo, priorità, nota di nascita)
TASK_V8 = [
    # ── A · La memoria visibile ─────────────────────────────────────────────
    (_K + "33", "La pagina «Cosa so di te», con la fonte e il Dimentica", "alta",
     "Dal confronto con Zoey OS: per ogni companion, l'elenco di ciò che ha "
     "imparato — il fatto, da quanto lo sa, e un bottone per farglielo "
     "dimenticare. È insieme la cosa che si vede in demo e la risposta a un "
     "obbligo di legge (GDPR art. 15 e 17): oggi «cosa sa di me il vostro "
     "sistema?» è una procedura manuale, con la pagina è un elenco e un bottone. "
     "Nessuna percentuale senza un criterio dietro: in Zoey sono tutte al 70%, "
     "un numero costante travestito da misura — meglio la fonte."),
    (_K + "34", "La memoria registrata deve cambiare la risposta", "alta",
     "Il difetto più istruttivo di Zoey: fra le sue memorie c'è «Andrea prefers "
     "Italian language for business communication», al 70%, e il riassunto "
     "finale della stessa conversazione è in inglese. Ricorda e non se ne serve. "
     "Serve un test che diventi rosso se una preferenza registrata non cambia la "
     "risposta successiva."),
    # ── B · Il pannello del cliente ─────────────────────────────────────────
    (_K + "35", "Il cliente vede la propria knowledge base", "alta",
     "Nel sistema ci sono tre tipi di persone e ne sono implementate due: "
     "l'owner vede tutto, i visitatori del sito vedono solo risposte, e il "
     "CLIENTE (ATS come azienda) non esiste. Entrando con le sue credenziali "
     "deve vedere l'elenco delle note che lo riguardano, con quando sono state "
     "aggiornate: «ecco le dodici cose che so di voi». È l'unica cosa di tutto "
     "il confronto con Zoey che nessuno dei due prodotti ha, ed è quella che si "
     "vende."),
    (_K + "36", "Il cliente segnala un errore, non lo corregge da sé", "media",
     "Una proposta di correzione che arriva nella coda dell'owner, non una "
     "modifica diretta: la governance non cambia. Va prima della raccolta "
     "automatica dalle conversazioni — dieci minuti del cliente che guarda e "
     "corregge valgono più di cento conversazioni raccolte da sole, e quando la "
     "raccolta si accenderà sarà lui ad approvare sulla sua roba."),
    (_K + "37", "Il cliente vede i buchi delle sue risposte", "media",
     "Le domande a cui il bot non ha saputo rispondere sui suoi dati: è l'elenco "
     "di cosa gli conviene aggiungere, e viene dai gap già raccolti. Attenzione: "
     "quelle domande le hanno fatte i SUOI utenti finali — sono dati dei clienti "
     "del cliente e il motore gira ancora in US West. Va deciso con lui, non "
     "acceso di default."),
    # ── C · Le tre cose che si vedono in trenta secondi ─────────────────────
    (_K + "38", "Una voce diversa per ogni agente", "media",
     "Zoey ha 63 voci ricercabili, scelte per companion. Divina ha una sola voce "
     "ElevenLabs per tutti e quattro: Dante, Virgilio e Beatrice hanno colori e "
     "forme diversi e parlano con la stessa gola. È un parametro "
     "(ELEVENLABS_VOICE_ID per agente), non un progetto. La chiave resta sul "
     "server."),
    (_K + "39", "La delega si vede dentro la conversazione", "media",
     "In Zoey, quando un companion passa il lavoro a un altro, nella chat "
     "compaiono righe di sistema distinte dai messaggi («↗ delegating to Marta», "
     "«✓ Marta finished»). Divina ha la Regia live come sezione a parte: va "
     "portata dentro il filo, dove sta l'attenzione. La sezione resta per la "
     "vista d'insieme."),
    (_K + "40", "Il risultato del lavoro è una scheda, non testo", "bassa",
     "Quando un agente finisce, il documento prodotto deve apparire come una "
     "scheda con un nome e i suoi bottoni, non come testo che scorre via. "
     "Divina ha già «Salva nel cervello» attaccato alla risposta: il passo è "
     "renderlo un oggetto che si può prendere."),
    # ── D · I due difetti trovati guardando ─────────────────────────────────
    (_K + "41", "Il menu si illumina e non cambia pagina", "alta",
     "Riproducibile, verificato più volte in produzione il 2/08: si clicca una "
     "voce della barra laterale, la voce si illumina, l'intestazione cambia, e "
     "il contenuto resta quello di prima. Servono due o tre clic. Non sono i "
     "primi secondi di caricamento: succede anche dopo venti secondi."),
    # ── La strada dichiarata, non da fare adesso ────────────────────────────
    (_K + "42", "Riassunti compressi per la memoria lunga", "bassa",
     "La strada giusta per la memoria di lungo periodo (Zoey la chiama «epoch "
     "summaries»: comprime il contesto invece di tenerlo tutto), ma viene DOPO "
     "che il filo breve funziona bene. Dichiarata qui apposta e non da fare "
     "adesso: una task che esiste solo nella testa di chi l'ha pensata si "
     "ridiscute daccapo fra un mese."),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto:
    urllib in produzione, TestClient nei test — stessa logica, testabile."""
    esiti = []
    for key, titolo, priorita, nota in TASK_V8:
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
        # urllib, non httpx (regola dell'1/08): uno script di manutenzione gira
        # col Python di sistema, senza costruire un ambiente virtuale.
        req = urllib.request.Request(base + path, data=_json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {tok}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode())

    for e in seed(post):
        print(f"  {e['key']} · {e['status']} · {e['priorita']} · id={e['id']}")
    print("Seed V8 completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
