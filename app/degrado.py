"""V9/A · Una funzione spenta lo dice DOVE si usa, non solo in /admin/status.

Il difetto, visto in produzione il 2/08 pomeriggio. La pagina «Cosa so di te»
diceva *«Non so ancora niente di te»* — che è una frase perfetta e sbagliata: la
verità era *«non posso ricordare niente, mi manca la tabella `tenant_memory`»*.
Chi apre quella pagina non va a leggere lo stato tecnico: legge quella riga e
conclude che la funzione non serve a niente. Una funzione spenta che sembra una
funzione inutile è peggio di un errore, perché non chiede di essere riparata.

`dbcheck` sapeva già tutto: quale tabella manca e cosa smette di funzionare, con
la frase giusta già scritta. Mancava il tubo che porta quella frase **dentro la
schermata interessata**.

**Perché un modulo e non tre `if`.** I casi trovati erano tre (memoria, pannello
cliente, buchi) e sarebbero diventati cinque il mese prossimo. Tre `if` sparsi
sono tre posti dove dimenticarsene; e soprattutto la dipendenza non è sempre una
tabella — le voci degli agenti dipendono da variabili d'ambiente, la ricerca web
da una chiave. Qui la forma è una sola, qualunque sia la cosa che manca.

**Tre esiti, mai due.** È la regola di `dbcheck` e vale identica:

    acceso      tutto quello che serve c'è
    spento      manca qualcosa, e si dice cosa e come si accende
    non so      non si è potuto guardare (schema illeggibile, DB assente)

«Non lo so» NON è «acceso», e non è nemmeno «spento»: dirlo come uno dei due è
il modo esatto in cui nasce un pannello che mente. Con `persist` a false — cioè
in sviluppo, senza database — la funzione è spenta ma la ragione è una
configurazione, non un guasto, e la frase lo dice.
"""
from __future__ import annotations

from . import dbcheck
from .config import settings

# ── I mattoni: cosa può mancare ──────────────────────────────────────────────
# Una dipendenza sa dire soltanto due cose: se c'è, e come si fa a farla esserci.
# Il PERCHÉ (cosa smette di funzionare) per le tabelle non si riscrive qui: si
# legge da `dbcheck.ATTESE`, dove è già scritto bene. Due copie della stessa
# frase divergono, e quella sbagliata è sempre quella che legge l'utente.


def tab(nome: str) -> dict:
    return {"tipo": "tabella", "tabella": nome, "colonna": None}


def col(tabella: str, colonna: str) -> dict:
    return {"tipo": "tabella", "tabella": tabella, "colonna": colonna}


def env(campo: str, variabile: str, rompe: str) -> dict:
    """Una variabile d'ambiente. `campo` è il nome in `settings`, `variabile`
    quello che una persona deve impostare su Railway — non sempre coincidono, e
    scrivere quello sbagliato manda qualcuno a cercare una cosa che non esiste."""
    return {"tipo": "env", "campo": campo, "variabile": variabile, "rompe": rompe}


def vault() -> dict:
    """V10/A1 · Il clone del vault, che non è né una tabella né una variabile.

    Su Railway ogni redeploy crea un container nuovo, e la cartella del vault
    non c'è. `vault_info()` torna `{}`, e l'allarme sui commit — che ha bisogno
    di DUE valori per confrontarli — **si spegne da solo senza dichiararlo**: la
    fascia sparisce, e una fascia che sparisce si legge come «va tutto bene».

    Il 2/08 è successo due volte, la seconda con conseguenze: il V9 era mergiato
    da venti minuti e il pannello mostrava ancora il quadro del V8. Nessuno se ne
    sarebbe accorto senza confrontare i due commit a mano.

    Non è un caso raro: succede a OGNI configurazione. Quel giorno le variabili
    di Railway sono state toccate cinque volte — cinque redeploy, cinque volte
    l'allarme cieco."""
    return {"tipo": "vault"}


# ── Il registro: quale funzione dipende da cosa ──────────────────────────────
# `dove` è la schermata che deve dichiararlo. Serve a due cose: a ricordarsi che
# ogni voce qui dentro ha un posto dove si vede, e a far fallire il test se una
# funzione viene registrata e poi nessuno la mostra.
FUNZIONI: dict[str, dict] = {
    "memoria": {
        "titolo": "«Cosa so di te»",
        "dove": "Squadra → Cosa so di te",
        "serve": [tab("tenant_memory")],
    },
    "riassunti": {
        "titolo": "La conversazione che dura",
        "dove": "Squadra → Cosa so di te",
        "serve": [tab("conversation_summary")],
    },
    "cliente-segnala": {
        "titolo": "Le segnalazioni del cliente",
        "dove": "pannello cliente → la vostra knowledge base",
        "serve": [tab("client_report")],
    },
    "cliente-buchi": {
        "titolo": "I buchi visibili al cliente",
        "dove": "pannello cliente → cosa non sappiamo",
        "serve": [col("tenant_flags", "buchi")],
    },
    "task": {
        "titolo": "La coda «Miglioramenti»",
        "dove": "Miglioramenti",
        "serve": [tab("brain_tasks")],
    },
    "voci-agente": {
        "titolo": "Una voce per ogni agente",
        "dove": "Squadra → le tab degli agenti",
        # `frase` scavalca la composizione automatica quando le ragioni sono
        # tante e uguali: «Dante parla con la voce di Divina, Virgilio parla con
        # la voce di Divina e Beatrice parla…» è tecnicamente giusto e nessuno
        # lo legge fino in fondo.
        "frase": "{cose} parla{no} ancora con la voce di Divina: le variabili "
                 "non sono impostate.",
        "serve": [
            env("elevenlabs_voice_id_dante", "ELEVENLABS_VOICE_ID_DANTE", "Dante"),
            env("elevenlabs_voice_id_virgilio", "ELEVENLABS_VOICE_ID_VIRGILIO", "Virgilio"),
            env("elevenlabs_voice_id_beatrice", "ELEVENLABS_VOICE_ID_BEATRICE", "Beatrice"),
        ],
    },
    "allarme-commit": {
        "titolo": "L'allarme «il cervello è fermo»",
        "dove": "la fascia in alto, ovunque · Cervello → il vault",
        "serve": [vault(), tab("ingest_meta")],
    },
    "kb-da-sito": {
        "titolo": "La knowledge base che nasce dal sito del cliente",
        "dove": "Clienti → Proponi dal sito",
        "serve": [env("tavily_api_key", "TAVILY_API_KEY",
                      "il sito del cliente non si può leggere: niente proposte")],
    },
}


def _rompe_tabella(tabella: str, colonna: str | None) -> tuple[str, str]:
    """(cosa smette di funzionare, quale DDL applicare), da `dbcheck.ATTESE`."""
    for t, c, ddl, rompe in dbcheck.ATTESE:
        if t == tabella and c == colonna:
            return rompe, ddl
    return f"manca {tabella}" + (f".{colonna}" if colonna else ""), ""


def clone_del_vault() -> dict:
    """L'accertamento che `dbcheck` non può fare, perché il clone non è una
    tabella. Quattro esiti, e il terzo è quello che ci interessa:

        non-configurato  nessun VAULT_GIT_URL: il motore legge una cartella
                         locale e non esiste un commit da confrontare — è una
                         configurazione (sviluppo), non un guasto
        c'è              clone presente, `vault_info()` sa dire il commit
        manca            container nuovo dopo un redeploy: il clone non c'è
        non-so           l'accertamento stesso non è riuscito

    Import pigro: `ingest` tira dentro qdrant_client e i provider, e questo
    modulo lo importa anche chi vuole solo disegnare un avviso."""
    if not str(getattr(settings, "vault_git_url", "") or "").strip():
        return {"stato": "non-configurato", "commit": ""}
    try:
        from . import ingest
        info = ingest.vault_info()
    except Exception as e:  # pragma: no cover - difensivo
        return {"stato": "non-so", "commit": "", "errore": type(e).__name__}
    sha = info.get("vault_commit", "")
    return {"stato": "c'è" if sha else "manca", "commit": sha}


def per(funzione: str) -> dict:
    """Lo stato di UNA funzione, nella forma che la console sa disegnare:

        {stato: 'acceso'|'spento'|'non-so', titolo, dove, perche, come, manca[]}

    `perche` è sempre una frase compiuta rivolta a chi guarda la schermata, non
    un nome di tabella. `come` è l'unica riga tecnica, ed è rivolta a chi può
    fare qualcosa: dice cosa applicare o quale variabile impostare."""
    f = FUNZIONI.get(funzione)
    if not f:
        return {"stato": "acceso", "titolo": funzione, "dove": "",
                "perche": "", "come": "", "manca": []}
    base = {"titolo": f["titolo"], "dove": f["dove"], "manca": []}

    serve_db = any(d["tipo"] == "tabella" for d in f["serve"])
    schema = dbcheck.stato() if serve_db else None
    if schema is not None and not schema["persist"]:
        return {**base, "stato": "spento",
                "perche": f"{f['titolo']} vive solo finché il motore resta acceso: "
                          "senza database quello che registra sparisce al prossimo riavvio.",
                "come": "Configura GRANTS_BACKEND=supabase e DATABASE_URL.",
                "manca": ["database"]}
    if schema is not None and schema["errore"]:
        # Il terzo esito. Dire «acceso» qui sarebbe la bugia comoda; dire
        # «spento» sarebbe un allarme inventato.
        return {**base, "stato": "non-so",
                "perche": f"Non è stato possibile verificare se {f['titolo']} può "
                          "funzionare: lo schema del database non è leggibile adesso.",
                "come": schema["errore"], "manca": []}

    clone = clone_del_vault() if any(d["tipo"] == "vault" for d in f["serve"]) else None
    if clone is not None and clone["stato"] == "non-so":
        return {**base, "stato": "non-so",
                "perche": f"Non è stato possibile verificare se {f['titolo']} può "
                          "funzionare: la copia locale del vault non è ispezionabile adesso.",
                "come": clone.get("errore", ""), "manca": []}

    perche, come, manca = [], [], []
    mancanti = {(m["tabella"], m["colonna"]) for m in (schema or {}).get("mancanti", [])}
    for d in f["serve"]:
        if d["tipo"] == "vault":
            if clone["stato"] == "c'è":
                continue
            if clone["stato"] == "manca":
                # LA frase del 2/08. Non «manca il clone» — quello è il come.
                perche.append("non si può confrontare: il cervello non ha ancora "
                              "letto il vault dopo il riavvio")
                come.append("lancia una ingest (dopo un redeploy il clone si "
                            "riprende da solo entro un minuto)")
                manca.append("clone del vault")
            else:                                    # non-configurato
                perche.append("il motore legge una cartella locale invece di un "
                              "repo: non esiste un commit del vault da confrontare")
                come.append("imposta VAULT_GIT_URL")
                manca.append("VAULT_GIT_URL")
        elif d["tipo"] == "tabella":
            if (d["tabella"], d["colonna"]) not in mancanti:
                continue
            r, ddl = _rompe_tabella(d["tabella"], d["colonna"])
            perche.append(r)
            come.append(f"applica {ddl}" if ddl else f"crea {d['tabella']}")
            manca.append(d["tabella"] + (f".{d['colonna']}" if d["colonna"] else ""))
        else:
            if str(getattr(settings, d["campo"], "") or "").strip():
                continue
            perche.append(d["rompe"])
            come.append(f"imposta {d['variabile']}")
            manca.append(d["variabile"])

    if not manca:
        return {**base, "stato": "acceso", "perche": "", "come": ""}
    if f.get("frase"):
        testo = f["frase"].format(cose=_elenco(perche), no="no" if len(perche) > 1 else "")
    else:
        testo = _frase(perche)
    return {**base, "stato": "spento", "manca": manca,
            "perche": testo, "come": _come(come)}


def _elenco(pezzi: list[str]) -> str:
    """«a, b e c» — l'unica congiunzione che serve."""
    p = [x.rstrip(".") for x in pezzi if x]
    if not p:
        return ""
    return p[0] if len(p) == 1 else ", ".join(p[:-1]) + " e " + p[-1]


def _frase(pezzi: list[str]) -> str:
    """Le ragioni in UNA frase. Un elenco puntato dentro un avviso lo fa leggere
    come documentazione; una frase la si legge."""
    t = _elenco(pezzi)
    return (t[0].upper() + t[1:] + ".") if t else ""


def _come(pezzi: list[str]) -> str:
    """La riga tecnica, senza ripetere il verbo tre volte."""
    if not pezzi:
        return ""
    if all(p.startswith("imposta ") for p in pezzi):
        return "Imposta " + _elenco([p[len("imposta "):] for p in pezzi]) + "."
    if all(p.startswith("applica ") for p in pezzi):
        return "Applica " + _elenco([p[len("applica "):] for p in pezzi]) + "."
    return _elenco(pezzi)[0].upper() + _elenco(pezzi)[1:] + "."


def tutte() -> dict:
    """Tutte le funzioni, per /admin/status e per la Diagnostica."""
    return {k: per(k) for k in FUNZIONI}


def spente() -> list[dict]:
    """Solo quelle spente o non verificabili — l'elenco che vale la pena mostrare."""
    return [{"funzione": k, **v} for k, v in tutte().items() if v["stato"] != "acceso"]
