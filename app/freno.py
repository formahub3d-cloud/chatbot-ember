"""S5.1c/2 (motore) · Il freno: il saldo si guarda PRIMA della risposta.

La decisione è la stessa dell'orchestratore — `passa | fermo | non-so`, con
`fermo` che pretende una prova e `non-so` che lascia passare urlando — e il
perché sta scritto per esteso in `divina-agenti/app/freno.py`. Qui c'è quello
che di là non serve, e sono due cose che nascono dalla chat.

**1. La connessione è nostra, e costa.** Il motore non ha `db.tenant_session`:
apre una connessione col ruolo `divina` (la stessa di `ledger.py`, e per lo
stesso motivo: append-only e RLS sono grant su quel ruolo). Ma una connessione
nuova prima di ogni risposta sono decine di millisecondi davanti alla prima
sillaba, in un prodotto dove la prima sillaba è a 55 ms e si sente. Quindi il
saldo si tiene in mente per un minuto, e ogni addebito lo scala di quello che
ha appena consumato: fra due letture il conto resta esatto, perché i token che
escono li sappiamo noi.

Quello che **non** si tiene in mente è il rifiuto. Un `fermo` in cache
significherebbe che un cliente che ha appena comprato un pacchetto resta al
muro fino alla scadenza della cache — cioè il momento peggiore possibile per
essere lenti. Il saldo in cache è sempre positivo per costruzione: quando gli
addebiti lo portano a zero, la riga sparisce e la volta dopo si rilegge.

**2. La frase che esce da qui la può leggere uno sconosciuto.** Il motore
risponde anche al widget sul sito di un cliente, dove chi scrive non è il
cliente ma il cliente del cliente. «I token sono finiti, aggiungi un pacchetto»
davanti a quella persona è due cose sbagliate insieme: un invito rivolto a chi
non può comprare, e un fatto sui conti di un'azienda detto ai suoi visitatori.
Perciò da qui esce una frase **discreta e vera** — non posso rispondere adesso,
non è colpa tua, la domanda non è persa — e il muro con le due CTA di F3 lo
scrive l'area cliente (v4-forma), che sa di avere davanti il titolare.

Il codice macchina (`motivo`, `residuo`, `rinnovo_il`) esce lo stesso: chi lo
legge sono i nostri servizi, non un browser di passaggio.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

from . import ledger, tariffa

log = logging.getLogger("ember.freno")

PASSA = "passa"
FERMO = "fermo"
NON_SO = "non-so"

# §3.2: due milioni al mese. Il numero vive in `dotazione.py`
# dell'orchestratore — qui serve solo per la riga dell'avviso, e duplicarlo è
# meglio che far dipendere la chat da un modulo che sta in un altro servizio.
DOTAZIONE_MENSILE = 2_000_000
QUASI_FINITO = int(DOTAZIONE_MENSILE * 0.20)

# La frase che può leggere uno sconosciuto (vedi il punto 2 in testa al file).
FRASE_FERMO = ("In questo momento non riesco a rispondere. Non è colpa tua e la "
               "tua domanda non è persa: riprova fra poco.")

_TTL = 60.0          # quanto si tiene in mente un saldo positivo
_TTL_NON_SO = 30.0   # e per quanto si evita di ripicchiare su un database muto
_TETTO = 500         # tenant tenuti in mente: oltre, si butta via tutto

# codice tenant → (scadenza monotona, saldi per borsello | None se illeggibile)
_memoria: dict[str, tuple[float, dict[str, int] | None]] = {}


@dataclass(frozen=True)
class Decisione:
    esito: str
    residuo: int | None
    motivo: str
    avviso: bool = False
    rinnovo: date | None = None

    @property
    def blocca(self) -> bool:
        return self.esito == FERMO

    def come_dizionario(self) -> dict:
        fuori: dict = {"esito": self.esito, "motivo": self.motivo,
                       "avviso": self.avviso}
        if self.residuo is not None:
            fuori["residuo"] = self.residuo
        if self.rinnovo is not None:
            fuori["rinnovo_il"] = self.rinnovo.isoformat()
        if self.blocca:
            fuori["frase"] = FRASE_FERMO
        return fuori


def rinnovo_il(quando: datetime | date | None = None) -> date:
    """Il primo del mese prossimo: quando torna la dotazione mensile."""
    q = quando or datetime.now(timezone.utc)
    if q.month == 12:
        return date(q.year + 1, 1, 1)
    return date(q.year, q.month + 1, 1)


def decidi(saldi: dict[str, int] | None, *, operazione: str,
           mai_visto: bool = False,
           lista_propria: bool = False,
           quando: datetime | None = None) -> Decisione:
    """La decisione, come funzione pura. Gemella di quella dell'orchestratore.

    I test stanno da entrambe le parti: se un giorno divergessero, lo stesso
    cliente verrebbe fermato in un servizio e servito nell'altro.
    """
    molt = tariffa.moltiplicatore(operazione, lista_propria=lista_propria)

    if saldi is None:
        return Decisione(NON_SO, None, "saldo-non-leggibile")

    residuo = sum(int(v or 0) for v in saldi.values())

    if molt == 0:
        return Decisione(PASSA, residuo, "operazione-inclusa",
                         avviso=residuo <= QUASI_FINITO,
                         rinnovo=rinnovo_il(quando))

    if residuo <= 0:
        if mai_visto:
            # Zero perché non è mai stato aperto ≠ zero perché ha consumato.
            return Decisione(NON_SO, residuo, "senza-dotazione",
                             rinnovo=rinnovo_il(quando))
        return Decisione(FERMO, residuo, "credito-esaurito",
                         avviso=True, rinnovo=rinnovo_il(quando))

    return Decisione(PASSA, residuo, "credito-disponibile",
                     avviso=residuo <= QUASI_FINITO,
                     rinnovo=rinnovo_il(quando))


def _dalla_memoria(codice: str) -> dict[str, int] | None | str:
    """I saldi tenuti in mente, o `"niente"` se non ce ne sono di validi.

    Il valore `None` è già preso — vuol dire «letto e illeggibile» — quindi
    l'assenza si dice con una stringa invece che con un secondo `None`: due
    significati sullo stesso valore è il modo in cui `tenant=None` è finito nei
    log del 6/08.
    """
    voce = _memoria.get(codice)
    if voce is None:
        return "niente"
    scade, saldi = voce
    if time.monotonic() >= scade:
        _memoria.pop(codice, None)
        return "niente"
    return saldi


def _ricorda(codice: str, saldi: dict[str, int] | None) -> None:
    if len(_memoria) >= _TETTO:
        # Nessuna scadenza fine: è una cache, non un archivio.
        _memoria.clear()
    ttl = _TTL if saldi is not None else _TTL_NON_SO
    _memoria[codice] = (time.monotonic() + ttl, saldi)


def consumato(tenant: dict, righe: list[tuple[str, int]]) -> None:
    """Scala dal saldo tenuto in mente quello che è appena stato addebitato.

    È la parte che rende onesta la cache: fra due letture il conto resta esatto,
    perché i token che escono li abbiamo contati noi. Quello che la cache non
    può sapere sono i token che ENTRANO (un pacchetto comprato altrove), ed è
    per questo che un saldo a zero non si tiene mai in mente: appena scende, la
    riga sparisce e la volta dopo si rilegge dal database.
    """
    codice = ledger.codice_tenant(tenant)
    if not codice:
        return
    voce = _memoria.get(codice)
    if voce is None:
        return
    scade, saldi = voce
    if saldi is None:
        return
    for bucket, token in righe or []:
        saldi[bucket] = int(saldi.get(bucket, 0)) - int(token or 0)
    if sum(saldi.values()) <= 0:
        _memoria.pop(codice, None)
        return
    _memoria[codice] = (scade, saldi)


def dimentica(codice: str = "") -> None:
    """Butta via quello che si ricorda (tutto, o di un tenant solo)."""
    if codice:
        _memoria.pop(codice, None)
    else:
        _memoria.clear()


def controlla(tenant: dict, operazione: str, *,
              lista_propria: bool = False) -> Decisione:
    """Decide se l'operazione può partire. **Non solleva mai.**

    Chi chiama è nel percorso di una risposta: un'eccezione qui trasformerebbe
    un problema di contabilità in una chat rotta, che è esattamente il difetto
    che il freno esiste per non produrre.
    """
    try:
        codice = ledger.codice_tenant(tenant)
        if not codice:
            # Già urlato da `ledger.addebita` per questa chiave: qui non si
            # ripete, ma soprattutto non si blocca — una chiave senza codice è
            # un dato che manca a noi, non un credito finito.
            return Decisione(NON_SO, None, "senza-tenant")
        if not ledger.attivo():
            return Decisione(NON_SO, None, "registro-spento")

        saldi = _dalla_memoria(codice)
        if saldi != "niente":
            # In mente ci finiscono solo saldi positivi (o il «non so»): da qui
            # non può uscire un rifiuto, ed è voluto.
            return decidi(saldi, operazione=operazione, lista_propria=lista_propria)

        saldi, mai_visto = _leggi(codice, tenant)
        d = decidi(saldi, operazione=operazione, mai_visto=mai_visto,
                   lista_propria=lista_propria)

        if d.motivo == "credito-esaurito":
            # Un rifiuto non si tiene in mente: chi compra un pacchetto adesso
            # deve poter scrivere il messaggio dopo, non fra un minuto.
            log.info("freno CHIUSO tenant=%s op=%s residuo=%s",
                     codice, operazione, d.residuo)
        elif d.motivo == "senza-dotazione":
            log.warning("tenant=%s è a zero ma non ha MAI ricevuto una dotazione: "
                        "la chat passa. Non è un cliente esaurito, è un cliente "
                        "non ancora aperto.", codice)
        else:
            # Si ricorda solo quello che serve a evitare una connessione: un
            # saldo positivo, oppure il fatto che il database non risponde (per
            # non ripicchiarci sopra a ogni messaggio).
            _ricorda(codice, saldi)
        return d
    except Exception:
        log.exception("freno: decisione non presa (op=%s). L'operazione PASSA.",
                      operazione)
        return Decisione(NON_SO, None, "freno-rotto")


def _leggi(codice: str, tenant: dict) -> tuple[dict[str, int] | None, bool]:
    """`(saldi, mai_visto)` dal database. `saldi=None` = non si è riusciti."""
    try:
        with ledger._sessione(tenant) as cur:
            saldi = ledger.saldi(cur, codice)
            mai_visto = (ledger.mai_visto(cur, codice)
                         if sum(saldi.values()) <= 0 else False)
            return saldi, mai_visto
    except Exception:
        log.exception("freno: saldo non leggibile per tenant=%s. La chat PASSA — "
                      "un guasto nostro non è un credito esaurito.", codice)
        return None, False
