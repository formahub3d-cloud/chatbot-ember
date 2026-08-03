"""V7/A1 · Il filo della conversazione: ricordare di cosa si stava parlando.

Il problema, guardato da vicino. Oggi la history arriva dal client e finisce nel
prompt: serve al modello per FORMULARE la risposta. Ma il RETRIEVAL usa la
domanda nuda — e «e per quell'altro cliente?» da sola non somiglia a niente nel
vault. Quindi il modello riceve il contesto giusto per capire la domanda e i
chunk sbagliati per rispondere: sembra smemorato proprio quando l'utente è più
sicuro di essere stato chiaro.

Tre cose, in ordine di quanto pesano:

1. **La domanda di seguito si espande prima del retrieval** (`query_retrieval`).
   Se il turno è corto e anaforico («e per quell'altro?», «torna a prima», «no,
   intendevo l'altro»), alla query si ANTEPONGONO gli ultimi turni utente. Il
   testo espanso serve SOLO a cercare: all'utente non si mostra, e nel prompt
   resta la sua domanda vera.

   Scelta deliberata: **nessuna chiamata LLM** per riscrivere la domanda. Un
   «standalone question rewrite» col modello sarebbe più elegante e costerebbe
   un round-trip in più proprio sui turni brevi — cioè a voce, dove la prima
   sillaba oggi arriva in 55 ms e un secondo in più si sente come un difetto.
   La concatenazione lessicale è deterministica, testabile, gratuita, e per le
   anafore corte fa lo stesso lavoro: la parola che manca («quale cliente?») sta
   quasi sempre nel turno precedente.

2. **La finestra si misura in caratteri, non in turni.** Sei turni sono tanti per
   iscritto e pochissimi a voce, dove si parla per frasi corte. Il budget in
   caratteri si adatta da solo ai due modi di parlare.

3. **Il filo può vivere sul server, ma solo se qualcuno lo chiede.** Se il client
   dimentica la history, la memoria spariva in silenzio. Ora, quando la richiesta
   porta un `conversazione` (un id scelto dal client), il server tiene gli ultimi
   turni IN MEMORIA e li usa come rete di sicurezza. Chi non manda l'id non lascia
   niente sul server: il widget sul sito di un cliente resta apolide per
   costruzione, e la superficie di dati personali cresce solo dove serve davvero
   (la console e il modo vocale, che sono nostri).

   Nessuna tabella nuova (regola 1 del giro): un anello in memoria con TTL corto e
   tetto duro, che si azzera al redeploy — e va benissimo così, perché una
   conversazione di ieri non è contesto, è un archivio, e gli archivi di
   conversazioni coi clienti sono dati personali (task `audit-2026-08-01-27`).

**Il limite che non si supera**: il filo NON allarga i permessi. Ricordare che al
turno prima si parlava di un cliente non dà il diritto di leggere le sue note: lo
scope si ricalcola sempre dai grant, e il testo espanso entra nella QUERY, mai
nel filtro. C'è un test che lo dimostra, e vale più della funzione.
"""
from __future__ import annotations

import re
import time
from threading import Lock

# Finestra: un budget in caratteri, con un tetto di turni per non degenerare.
MAX_TURNI = 20
MAX_CHARS = 4000
MAX_CHARS_TURNO = 1500

# Rete di sicurezza server-side: corta di proposito.
TTL_S = 1800                # 30 minuti: dopo, non è più contesto
MAX_CONVERSAZIONI = 200     # tetto duro: la memoria non è un archivio

_lock = Lock()
_memoria: dict[str, dict] = {}      # id → {"turni": [...], "at": epoch}

# Marcatori di una domanda «di seguito»: pronomi e avverbi che si appoggiano al
# turno prima. Prudenti di proposito: un falso positivo costa solo una query più
# lunga, un falso negativo costa una risposta sbagliata.
_ANAFORA = re.compile(
    r"(?i)(?:^|\b)(?:e\s+(?:per|con|di|a|il|lo|la|gli|le|quell|quest)|"
    r"quell[oaie]?|quest[oaie]?|l'altr[oaie]|gli\s+altri|"
    r"invece|anche|pure|stess[oaie]|"
    r"torna(?:re)?\s+(?:a|su|indietro)|prima|precedente|di\s+nuovo|"
    r"intendevo|volevo\s+dire|no,|allora|quindi|"
    r"lui|lei|loro|ci|ne|lo\s+sai|come\s+sopra)\b"
)
# Sopra questa lunghezza una domanda si regge da sola: espanderla aggiunge solo
# rumore al retrieval.
SOGLIA_AUTONOMA = 90

# V12/B · Un nome proprio o una sigla: il SOGGETTO che una domanda porta con sé.
# Si ignora la prima parola, che in italiano è maiuscola d'obbligo e non dice
# niente.
_PROPRIO = re.compile(r"\b([A-ZÀ-Þ][\wÀ-ÿ'’]{2,}|[A-Z]{2,})\b")


def ha_soggetto(testo: str) -> bool:
    """La frase nomina qualcuno o qualcosa di preciso?"""
    for m in _PROPRIO.finditer(testo or ""):
        if m.start() == 0:
            continue
        return True
    return False


# Un articolo NUDO introduce un soggetto suo («quanto costa **la** stampa 3D?»);
# una preposizione articolata («al mese») no — è un complemento, non il soggetto.
_ARTICOLO = re.compile(r"(?i)(?:^|\s)(?:il|lo|la|i|gli|le|un|una|uno)\s")
_INTERROGATIVA = re.compile(r"(?i)^\W*(?:e\s+)?(?:quanto|quanta|quanti|quante|quando|"
                            r"dove|come|perch[eé]|chi|che|quale|quali|cosa)\b")


def _ellittica(d: str) -> bool:
    """Una domanda che non porta NESSUN soggetto: né un nome proprio, né un
    sintagma introdotto da un articolo. «E quanto paga al mese?» è così; «quanto
    costa la stampa 3D?» no, e infatti quella si regge da sola.

    Deve anche essere una domanda: senza il punto interrogativo (o una parola
    interrogativa in testa) si finirebbe a espandere «ciao»."""
    if ha_soggetto(d) or _ARTICOLO.search(d):
        return False
    return d.rstrip().endswith("?") or bool(_INTERROGATIVA.match(d))


def normalizza(history) -> list[dict]:
    """History del client → turni {role, content} puliti, entro la finestra.

    Si tagliano i turni vuoti e si tronca ogni turno: una risposta lunghissima
    non deve mangiarsi il budget di tutti gli altri."""
    puliti: list[dict] = []
    for h in list(history or []):
        if not isinstance(h, dict):
            continue
        testo = (h.get("content") or "").strip()
        if not testo:
            continue
        ruolo = "user" if h.get("role") == "user" else "assistant"
        puliti.append({"role": ruolo, "content": testo[:MAX_CHARS_TURNO]})
    return finestra(puliti)


def finestra(turni: list[dict]) -> list[dict]:
    """Gli ultimi turni che stanno nel budget di caratteri (tetto: MAX_TURNI).

    Si scorre dal fondo: il contesto vicino vale più di quello lontano."""
    out: list[dict] = []
    spesi = 0
    for t in reversed(turni[-MAX_TURNI:]):
        costo = len(t["content"]) + 10
        if out and spesi + costo > MAX_CHARS:
            break
        out.append(t)
        spesi += costo
    out.reverse()
    return out


def e_di_seguito(domanda: str, turni: list[dict]) -> bool:
    """La domanda si appoggia al turno precedente invece di reggersi da sola?

    Due modi, e il secondo è nato da un difetto visto in produzione il 3/08.

    1. **Un marcatore anaforico** («e quello?», «torna a prima»): il caso
       classico, che c'era dal V7.
    2. **Una domanda corta SENZA un soggetto suo**, quando nel filo un soggetto
       c'è. È il caso che mancava, ed è il più comune di tutti: *«Parlami del
       cliente HRH»* → *«E quanto paga al mese?»*. Il vecchio riconoscitore
       accettava «e» solo se seguita da un articolo o una preposizione («e il
       contratto?»), quindi tutte le domande di seguito che cominciano con una
       parola interrogativa cadevano fuori — e finivano nel retrieval **senza
       soggetto**. Il risultato non era una risposta sbagliata sul cliente
       giusto: era la NOTA sbagliata, perché «quanto paga al mese» somiglia a
       qualunque nota che parli di pagamenti, e la scheda del cliente — dove sta
       la cifra — non è la più somigliante.

    Il compromesso resta quello dichiarato dal modulo: un falso positivo costa
    una query più lunga, un falso negativo costa una risposta sbagliata."""
    d = (domanda or "").strip()
    if not d or not turni:
        return False
    if len(d) > SOGLIA_AUTONOMA:
        return False
    if _ANAFORA.search(d):
        return True
    return _ellittica(d) and any(ha_soggetto(t["content"])
                                 for t in turni if t["role"] == "user")


def query_retrieval(domanda: str, turni: list[dict]) -> str:
    """Il testo con cui CERCARE nel cervello (mai quello che si mostra).

    Per una domanda autonoma è la domanda stessa — il comportamento di sempre.
    Per una domanda di seguito, davanti ci vanno gli ultimi turni UTENTE: sono
    quelli che contengono il soggetto che l'anafora sottintende. Le risposte di
    Divina restano fuori: rimetterle nella query significherebbe cercare le
    parole del modello invece di quelle della persona, e allargare il recupero
    verso ciò che ha già detto."""
    if not e_di_seguito(domanda, turni):
        return domanda
    utente = [t["content"] for t in turni if t["role"] == "user"][-2:]
    if not utente:
        return domanda
    return " ".join(utente + [domanda])[:MAX_CHARS_TURNO]


# ── La rete di sicurezza in memoria (opt-in, corta, senza tabelle) ───────────

def _pulisci(adesso: float) -> None:
    """Scaduti via, e se sono troppe si buttano le più vecchie. Chiamata sotto lock."""
    for k in [k for k, v in _memoria.items() if adesso - v["at"] > TTL_S]:
        _memoria.pop(k, None)
    if len(_memoria) > MAX_CONVERSAZIONI:
        for k, _v in sorted(_memoria.items(), key=lambda kv: kv[1]["at"])[
                :len(_memoria) - MAX_CONVERSAZIONI]:
            _memoria.pop(k, None)


def chiave(tenant_code: str, conversazione: str) -> str:
    """La chiave è per TENANT: due tenant non possono ritrovarsi nello stesso filo
    nemmeno scegliendo lo stesso id per sbaglio (o apposta)."""
    return f"{(tenant_code or '?').strip()}|{(conversazione or '').strip()[:80]}"


def ricorda(tenant_code: str, conversazione: str, turni: list[dict]) -> None:
    """Tiene i turni per questa conversazione. Senza id non si tiene NIENTE."""
    if not (conversazione or "").strip() or not turni:
        return
    adesso = time.time()
    with _lock:
        _memoria[chiave(tenant_code, conversazione)] = {
            "turni": finestra(turni), "at": adesso}
        _pulisci(adesso)


def rammenta(tenant_code: str, conversazione: str) -> list[dict]:
    """I turni tenuti per questa conversazione ([] se scaduti o mai visti)."""
    if not (conversazione or "").strip():
        return []
    adesso = time.time()
    with _lock:
        _pulisci(adesso)
        v = _memoria.get(chiave(tenant_code, conversazione))
        return list(v["turni"]) if v else []


def risolvi(history, tenant_code: str = "", conversazione: str = "") -> tuple[list[dict], str]:
    """I turni da usare, e DA DOVE vengono ('client' | 'server' | 'nessuno').

    La provenienza torna nella risposta perché la console possa dirlo: un filo
    perso in silenzio è il difetto che questa funzione esiste per togliere. Se il
    client manda la history si usa quella (è la più fresca) e la si ricorda; se
    non la manda, si prova la rete di sicurezza."""
    turni = normalizza(history)
    if turni:
        ricorda(tenant_code, conversazione, turni)
        return turni, "client"
    salvati = rammenta(tenant_code, conversazione)
    if salvati:
        return salvati, "server"
    return [], "nessuno"


def aggiungi(tenant_code: str, conversazione: str, turni: list[dict],
             domanda: str, risposta: str) -> None:
    """Chiude il turno nella memoria server-side (solo se c'è un id)."""
    if not (conversazione or "").strip():
        return
    nuovi = list(turni) + [{"role": "user", "content": (domanda or "")[:MAX_CHARS_TURNO]},
                           {"role": "assistant", "content": (risposta or "")[:MAX_CHARS_TURNO]}]
    ricorda(tenant_code, conversazione, nuovi)


def dimentica(tenant_code: str = "", conversazione: str = "") -> int:
    """Cancella un filo (o tutti, senza argomenti: per i test e per il diritto
    all'oblio, che su una memoria in RAM è semplicemente questo)."""
    with _lock:
        if not conversazione:
            n = len(_memoria)
            _memoria.clear()
            return n
        return 1 if _memoria.pop(chiave(tenant_code, conversazione), None) else 0


def quante() -> int:
    """Quanti fili vivi (per /admin/status: una memoria che non si vede è peggio)."""
    adesso = time.time()
    with _lock:
        _pulisci(adesso)
        return len(_memoria)
