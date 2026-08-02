"""V7/B1 · Il motore dichiara quali tabelle si aspetta, e dice cosa non trova.

Il 1/08 sono state applicate a mano QUATTRO migrazioni — `tenant_flags`,
`ingest_meta`, `key_usage`, `tenant_flags_libera` — e ogni volta la scoperta è
arrivata da un 500 o da un degrado silenzioso, ore dopo il merge. Nessuna era un
errore di programmazione: erano migrazioni scritte bene che nessuno aveva
applicato, e il sistema non sapeva dirlo.

Questo modulo è il rimedio, e ha una sola ambizione: **una migrazione non
applicata deve essere visibile in dieci secondi, non in due settimane.** Stessa
idea della riga `[boot]` e del guardiano, applicata al database.

Tre scelte che vale la pena spiegare:

- **Anche le COLONNE, non solo le tabelle.** Il caso `tenant_flags_libera` era una
  `alter table … add column`: la tabella c'era, la colonna no, e un controllo per
  sole tabelle sarebbe stato verde mentre la spunta non funzionava. Metà dei
  guasti di stanotte sarebbero sfuggiti a un controllo più grossolano.

- **Ogni attesa dice COSA SMETTE DI FUNZIONARE**, non solo che manca. «manca
  `ingest_meta`» non aiuta nessuno; «manca `ingest_meta`: l'allarme sui commit è
  cieco» dice se ci si può convivere fino a domani.

- **Nessuna tabella nuova** (regola 1 del giro): si legge `information_schema`,
  che c'è sempre. Senza database configurato non si dichiara «tutto mancante» —
  si dichiara `persist: false`, che è una cosa diversa e va detta diversamente.
"""
from __future__ import annotations

import logging

from . import tenants
from .config import settings

log = logging.getLogger("ember.dbcheck")

# (tabella, cosa|None, file DDL, cosa smette di funzionare senza)
#   cosa = None            → basta che la tabella esista
#   cosa = "nome_colonna"  → serve una `alter table … add column`
#   cosa = "@check:valore" → un CHECK deve ammettere quel valore (`add constraint`)
# Le ultime due esistono perché stanotte i due guasti più insidiosi NON erano
# tabelle mancanti: `tenant_flags` c'era e le mancava la colonna `libera`.
ATTESE: tuple[tuple[str, str | None, str, str], ...] = (
    ("tenants", None, "db/schema.sql",
     "le chiavi tenant vengono solo dal file statico: nessuna chiave creata dalla console funziona"),
    ("api_keys", None, "db/schema.sql",
     "chiavi con hash e scadenza non disponibili: si torna alle chiavi in chiaro del file"),
    ("access_logs", None, "db/schema.sql",
     "nessun audit trail delle azioni sui tenant (serve per il GDPR, non solo per curiosità)"),
    ("documents", None, "db/schema.sql",
     "il Cervello vivo non ha metadati: niente conteggi, niente note recenti, niente esploratore"),
    ("key_usage", None, "db/schema.sql",
     "le quote per chiave non si contano: il tetto giornaliero/mensile non frena nulla"),
    ("analytics_events", None, "db/schema.sql",
     "gli eventi conversazione non si conservano: niente storico, niente trend, i gap si perdono al riavvio"),
    ("brain_tasks", None, "db/brain_tasks.sql",
     "la coda «Miglioramenti» gira in memoria e si azzera a ogni redeploy"),
    ("brain_tasks", "priorita", "db/brain_tasks_priorita.sql",
     "le task non hanno priorità: la colonna DA FARE non sa cosa viene prima"),
    ("brain_tasks", "approved_by", "db/brain_tasks_states.sql",
     "le azioni non hanno stati intermedi: niente approvata/in-esecuzione/fallita"),
    ("brain_tasks", "@check:da-verificare", "db/brain_tasks_da_verificare.sql",
     "il merge non può mettere le task «da verificare»: restano aperte con una nota"),
    ("brain_graph", None, "db/brain_graph.sql",
     "l'orbita disegna i collegamenti per vicinanza d'area invece che le sinapsi vere dei [[link]]"),
    ("client_access", None, "db/client_access.sql",
     "gli accessi cliente non funzionano: nessun PIN, nessuna sessione"),
    ("ingest_meta", None, "db/ingest_meta.sql",
     "l'allarme «cervello fermo» è cieco: non sa a quale commit del vault è ferma l'ingest"),
    ("tenant_flags", None, "db/tenant_flags.sql",
     "il livello 3 non si può accendere per nessun tenant (resta spento, che è il default sicuro)"),
    ("tenant_flags", "libera", "db/tenant_flags_libera.sql",
     "la conoscenza generale non si può concedere a un tenant (resta spenta, default sicuro)"),
    ("tenant_flags", "buchi", "db/tenant_flags_buchi.sql",
     "il cliente non può vedere i buchi delle sue risposte nemmeno se lo si decide "
     "(resta spento, default sicuro: sono domande dei suoi utenti finali)"),
    ("tenant_memory", None, "db/tenant_memory.sql",
     "«Cosa so di te» si azzera a ogni redeploy: le preferenze si perdono e il DIMENTICA "
     "cancella una cosa che sarebbe sparita da sola (art. 15/17 non coperti davvero)"),
    ("client_report", None, "db/client_report.sql",
     "il cliente non può segnalare un errore sulla propria scheda: la segnalazione "
     "vive in memoria e si perde al redeploy invece di arrivare nella coda"),
)


def enabled() -> bool:
    """C'è un database da interrogare? Se no non si controlla niente — e NON si
    dichiara «tutto mancante»: sono due situazioni diverse e vanno dette così."""
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


def _trovate() -> tuple[set[str], set[tuple[str, str]]]:
    """(tabelle, coppie tabella/colonna) + i CHECK, in tre query sole.

    Tre query e non una per attesa: il controllo gira all'avvio e a ogni
    /admin/status, e non deve diventare esso stesso un costo. I CHECK tornano
    come coppie (tabella, "@check:<testo integrale del vincolo>"), così la
    verifica è una banale ricerca di sottostringa."""
    tabelle: set[str] = set()
    colonne: set[tuple[str, str]] = set()
    with tenants._conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'")
            tabelle = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT table_name, column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public'")
            colonne = {(r[0], r[1]) for r in cur.fetchall()}
            cur.execute(
                "SELECT rel.relname, pg_get_constraintdef(con.oid) "
                "FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid "
                "JOIN pg_namespace ns ON ns.oid = rel.relnamespace "
                "WHERE con.contype = 'c' AND ns.nspname = 'public'")
            for tab, definizione in cur.fetchall():
                colonne.add((tab, f"@check:{definizione}"))
    return tabelle, colonne


def stato() -> dict:
    """Cosa il motore si aspetta e cosa trova davvero.

    Ritorna sempre un dict con la stessa forma — anche quando non c'è database e
    anche quando la lettura fallisce — perché il pannello ci disegna una riga e
    una riga non può sparire a seconda dell'esito:

        {ok, persist, attese, presenti, mancanti: [{tabella, colonna, ddl, rompe}],
         errore}

    `ok` è True solo quando si è potuto guardare E non manca niente. Senza
    database `ok` è False e `persist` è False: non è un guasto, è una
    configurazione — e il pannello lo dice con parole diverse."""
    base = {"ok": False, "persist": enabled(), "attese": len(ATTESE),
            "presenti": 0, "mancanti": [], "errore": ""}
    if not enabled():
        base["errore"] = "nessun database configurato (GRANTS_BACKEND/DATABASE_URL)"
        return base
    try:
        tabelle, colonne = _trovate()
    except Exception as e:  # pragma: no cover - DB irraggiungibile
        log.warning("dbcheck: lettura dello schema fallita", exc_info=True)
        # «Non ho potuto guardare» non è «va tutto bene» e non è «manca tutto».
        base["errore"] = f"schema non leggibile: {type(e).__name__}"
        return base
    mancanti = []
    for tabella, colonna, ddl, rompe in ATTESE:
        if colonna is None:
            c_e = tabella in tabelle
        elif colonna.startswith("@check:"):
            atteso = colonna[len("@check:"):]
            c_e = any(t == tabella and v.startswith("@check:") and atteso in v
                      for t, v in colonne)
        else:
            c_e = (tabella, colonna) in colonne
        if not c_e:
            mancanti.append({"tabella": tabella, "colonna": colonna,
                             "ddl": ddl, "rompe": rompe})
    base["mancanti"] = mancanti
    base["presenti"] = len(ATTESE) - len(mancanti)
    base["ok"] = not mancanti
    return base


def riga_boot() -> str:
    """Una riga sola per il log d'avvio, sullo stampo di `[boot]` della console.

    Nel log di produzione questa riga è il posto in cui una migrazione dimenticata
    si vede il giorno stesso invece che due settimane dopo."""
    s = stato()
    if not s["persist"]:
        return "[db] nessun database configurato: coda, grafo e flag girano in memoria"
    if s["errore"]:
        return f"[db] schema NON verificato — {s['errore']}"
    if s["ok"]:
        return f"[db] schema completo: {s['presenti']}/{s['attese']} attese soddisfatte"
    voci = ", ".join((m["tabella"] if m["colonna"] is None
                      else f'{m["tabella"]}.{m["colonna"]}') for m in s["mancanti"])
    return (f"[db] MANCANO {len(s['mancanti'])} migrazioni su {s['attese']}: {voci} "
            f"— dettaglio in /admin/status")
