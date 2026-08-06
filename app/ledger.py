"""S5.1b (motore) · Il registro dei token, scritto dalla parte della chat.

La chat è il consumo grosso: se il registro lo tenesse solo l'orchestratore,
conterebbe metà del traffico, e il fail-closed (S5.1c) chiuderebbe la porta
guardando un numero sbagliato.

**Questo modulo apre una connessione SUA, con il ruolo `divina`.**
`DATABASE_URL_LEDGER` è una variabile a parte, e non è un vezzo: la
`DATABASE_URL` del motore è la connection string del progetto Supabase, cioè un
ruolo privilegiato. Le due garanzie di `token_ledger` — append-only (`UPDATE` e
`DELETE` negati) e isolamento RLS — **sono grant sul ruolo `divina`**, e il
proprietario del database le scavalca per costruzione. Scrivendo con la
connessione di sempre, l'append-only sarebbe vero per l'orchestratore e falso
per la chat: la stessa tabella con due regole a seconda di chi scrive, che è
peggio di una tabella senza regole.

**Senza `DATABASE_URL_LEDGER` questo modulo è SPENTO e lo dichiara.** Non
ripiega sulla connessione privilegiata: il ripiego silenzioso è esattamente il
difetto per cui la variabile esiste. Un consumo non registrato è un problema di
fatturazione; un consumo registrato scavalcando le difese del database è un
problema di fiducia nei dati, e non si ripara guardando le righe.

La logica di calcolo (borselli, arrotondamento, periodo) è la stessa
dell'orchestratore, e per lo stesso motivo dichiarato in `app/uso.py`: i due
servizi non condividono una libreria. Qui c'è in più la connessione, perché il
motore non ha `db.tenant_session`.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from . import rls, tariffa
from .config import settings

log = logging.getLogger("ember.ledger")

BORSELLI = ("mensile", "extra", "regalo")

# Le operazioni che il CHECK della colonna ammette (db/004 dell'orchestratore).
OPERAZIONI = ("chat", "ulisse", "caronte", "bozza-email", "documento",
              "azione", "voce", "rinnovo", "pacchetto", "regalo", "rettifica")

_senza_misura = False
_spento_detto = False


def attivo() -> bool:
    """Il registro può scrivere? Solo con la connessione del ruolo `divina`."""
    return bool((settings.database_url_ledger or "").strip())


def periodo_di(quando: datetime | None = None) -> str:
    """Il mese di competenza, in UTC. `YYYY-MM`."""
    q = quando or datetime.now(timezone.utc)
    return f"{q.year:04d}-{q.month:02d}"


def ripartisci(quanti: int, saldi: dict[str, int]) -> list[tuple[str, int]]:
    """Da quali borselli togliere `quanti` token: prima quello che scade.

    Copia della funzione dell'orchestratore, con gli stessi test da entrambe le
    parti: se un giorno divergessero, lo stesso cliente pagherebbe in due modi
    diversi a seconda di quale servizio ha risposto.
    """
    if quanti <= 0:
        return []
    fuori: list[tuple[str, int]] = []
    resto = quanti
    for borsello in BORSELLI:
        disponibile = max(0, int(saldi.get(borsello, 0) or 0))
        if disponibile <= 0:
            continue
        preso = min(resto, disponibile)
        fuori.append((borsello, preso))
        resto -= preso
        if resto <= 0:
            break
    return fuori


def costo(uso_chiamata, moltiplicatore: float) -> int:
    """(input + output) × moltiplicatore, arrotondato per eccesso."""
    if uso_chiamata is None:
        return 0
    grezzo = (uso_chiamata.input + uso_chiamata.output) * float(moltiplicatore or 0)
    intero = int(grezzo)
    return intero + 1 if grezzo > intero else intero


@contextmanager
def _sessione(tenant: dict):
    """Una transazione col ruolo `divina` e i GUC del tenant.

    I GUC servono anche in scrittura: la policy RLS ha un `with check`, e senza
    di loro l'INSERT viene rifiutato dal database — il che, va detto, è la prova
    che l'isolamento c'è.
    """
    import psycopg2

    conn = psycopg2.connect(settings.database_url_ledger, connect_timeout=5)
    try:
        cur = conn.cursor()
        rls.set_grants(cur, tenant.get("allowed_scopes") or [])
        yield cur
        conn.commit()
    finally:
        conn.close()


def saldi(cur, tenant_code: str) -> dict[str, int]:
    """Quanti token restano, borsello per borsello. Gli scaduti non contano."""
    cur.execute(
        "SELECT bucket, "
        "  coalesce(sum(case when direzione='accredito' then token else -token end), 0) "
        "FROM token_ledger "
        "WHERE tenant_code=%s AND (scade_il IS NULL OR scade_il >= current_date) "
        "GROUP BY bucket",
        (tenant_code,),
    )
    fuori = {b: 0 for b in BORSELLI}
    for bucket, totale in cur.fetchall() or []:
        if bucket in fuori:
            fuori[bucket] = int(totale or 0)
    return fuori


def addebita(tenant: dict, operazione: str, uso_chiamata, *,
             lista_propria: bool = False, conversation_id: str | None = None) -> dict:
    """Scrive il consumo di un'operazione della chat. **Non solleva mai.**

    A questo punto la risposta è già stata data all'utente: far fallire la
    richiesta perché la contabilità non è riuscita a scrivere trasformerebbe una
    riga mancante in una risposta che sembra andata storta. L'errore si urla nel
    log — ed è il registro stesso, con le sue righe mancanti, il posto dove il
    problema si vede.
    """
    global _spento_detto
    if not attivo():
        if not _spento_detto:
            _spento_detto = True
            log.error("registro token SPENTO: manca DATABASE_URL_LEDGER. Il consumo "
                      "della chat non viene contato. NON si ripiega sulla "
                      "connessione privilegiata: scavalcherebbe append-only e RLS.")
        return {"scritto": False, "motivo": "spento", "token": 0}

    if operazione not in OPERAZIONI:
        log.error("operazione non ammessa dal registro: %r", operazione)
        return {"scritto": False, "motivo": "operazione-ignota", "token": 0}

    misura = "misurato" if uso_chiamata is not None else "ignoto"
    try:
        molt = tariffa.moltiplicatore(operazione, lista_propria=lista_propria)
    except tariffa.OperazioneSconosciuta:
        log.error("operazione senza tariffa: %r", operazione)
        return {"scritto": False, "motivo": "senza-tariffa", "token": 0}

    quanti = costo(uso_chiamata, molt)
    try:
        with _sessione(tenant) as cur:
            if quanti <= 0:
                _riga(cur, tenant, operazione, uso_chiamata, molt, "mensile", 0,
                      misura, conversation_id)
                return {"scritto": True, "token": 0, "misura": misura, "righe": []}

            pezzi = ripartisci(quanti, saldi(cur, tenant["code"]))
            scoperto = quanti - sum(t for _, t in pezzi)
            if scoperto > 0:
                log.error("consumo SCOPERTO tenant=%s op=%s token=%s scoperti=%s",
                          tenant["code"], operazione, quanti, scoperto)
                pezzi.append(("extra", scoperto))
            for bucket, token in pezzi:
                _riga(cur, tenant, operazione, uso_chiamata, molt, bucket, token,
                      misura, conversation_id)
            return {"scritto": True, "token": quanti, "misura": misura,
                    "righe": pezzi, "scoperto": scoperto}
    except Exception:
        log.exception("registro token non scritto (tenant=%s op=%s token=%s)",
                      tenant.get("code"), operazione, quanti)
        return {"scritto": False, "motivo": "errore", "token": quanti}


def _riga(cur, tenant: dict, operazione: str, uso_chiamata, moltiplicatore: float,
          bucket: str, token: int, misura: str, conversation_id: str | None) -> None:
    global _senza_misura
    valori = (
        tenant["tenant_id"], tenant["org_code"], tenant["code"], "addebito",
        bucket, operazione, moltiplicatore,
        getattr(uso_chiamata, "input", 0) or 0,
        getattr(uso_chiamata, "output", 0) or 0,
        token, periodo_di(), conversation_id,
    )
    colonne = ("tenant_id, org_code, tenant_code, direzione, bucket, operazione, "
               "moltiplicatore, token_input, token_output, token, periodo, "
               "conversation_id")
    segnaposto = "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s"

    if not _senza_misura:
        try:
            cur.execute(
                f"INSERT INTO token_ledger ({colonne}, misura) "
                f"VALUES ({segnaposto},%s)", (*valori, misura))
            return
        except Exception as e:
            if "misura" not in str(e):
                raise
            _senza_misura = True
            log.warning("colonna token_ledger.misura assente: la distinzione "
                        "misurato/ignoto non viene registrata")

    cur.execute(f"INSERT INTO token_ledger ({colonne}) VALUES ({segnaposto})", valori)
