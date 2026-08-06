"""S5.2 · Quanto costa un'operazione, in multipli dei token che consuma.

La tabella di §3.1, e nient'altro. È una **funzione pura** perché è la metà del
prezzo che un cliente può contestare: dev'essere leggibile accanto al listino
senza aprire un database, e dev'essere provabile senza rete.

    chat                     1×
    Ulisse (trova clienti)   3×
    Caronte (email)          5×
    bozza email, lista tua   1×
    documento                4×
    altre azioni             2×
    voce                     0×  (inclusa)

**Zero non è «non contare».** La voce è inclusa nel prezzo, e la sua riga nel
registro si scrive lo stesso a `token = 0`: «gratis» è un'informazione — dice
quanto ci costa una cosa che regaliamo — mentre una riga assente dice soltanto
che non è successo niente.

**Un accredito non ha moltiplicatore.** Rinnovo, pacchetto, regalo e rettifica
sono token che entrano: moltiplicarli sarebbe come applicare uno sconto a un
bonifico. Chiederne il moltiplicatore è un errore di chi chiama, e infatti
solleva invece di rispondere 1 — un 1 silenzioso qui vorrebbe dire che qualcuno
sta addebitando un accredito.
"""
from __future__ import annotations

# Il moltiplicatore di ogni operazione CONSUMANTE. Le chiavi sono le stesse del
# CHECK di `token_ledger.operazione` (db/004): se qui ne mancasse una, il
# registro accetterebbe una riga che nessuno sa prezzare.
CONSUMI: dict[str, float] = {
    "chat": 1,
    "ulisse": 3,
    "caronte": 5,
    "bozza-email": 5,     # su una lista che abbiamo trovato noi: è lavoro di Caronte
    "documento": 4,
    "azione": 2,
    "voce": 0,            # inclusa nel prezzo — la riga si scrive lo stesso
}

# Quello che ENTRA nel borsello. Non si moltiplica: sarebbe uno sconto su un
# bonifico.
ACCREDITI = ("rinnovo", "pacchetto", "regalo", "rettifica")

# §3.1: «bozza su lista propria 1×». Scrivere email a contatti che il cliente ha
# già è un altro mestiere dal trovarne di nuovi, e costa come una chat.
BOZZA_LISTA_PROPRIA = 1


class OperazioneSconosciuta(ValueError):
    """Un'operazione che nessuno sa prezzare. Meglio fermarsi che indovinare."""


def moltiplicatore(operazione: str, *, lista_propria: bool = False) -> float:
    """Il moltiplicatore di un'operazione. Solleva se non è nel listino.

    `lista_propria` conta solo per `bozza-email`: sulla lista del cliente la
    bozza è 1×, su una lista trovata da Ulisse fa parte del lavoro di Caronte e
    resta 5×. Passarlo altrove non cambia niente, e non è un errore: rende
    innocuo il chiamante che lo mette per abitudine.
    """
    chiave = (operazione or "").strip().lower()
    if chiave in ACCREDITI:
        raise OperazioneSconosciuta(
            f"«{chiave}» è un accredito: i token che entrano non si moltiplicano")
    if chiave == "bozza-email" and lista_propria:
        return BOZZA_LISTA_PROPRIA
    if chiave not in CONSUMI:
        raise OperazioneSconosciuta(f"operazione senza tariffa: {operazione!r}")
    return CONSUMI[chiave]


def e_inclusa(operazione: str) -> bool:
    """Vero se l'operazione è nel prezzo (moltiplicatore 0).

    Serve a chi disegna: «incluso» è una parola che si può scrivere a schermo,
    «moltiplicatore 0» no.
    """
    try:
        return moltiplicatore(operazione) == 0
    except OperazioneSconosciuta:
        return False


def listino() -> list[tuple[str, float]]:
    """Il listino intero, in ordine di prezzo crescente e poi alfabetico.

    È quello che la pagina Piano (S5.5) deve poter mostrare **senza riscriverlo**:
    una seconda copia dei prezzi in un componente è la cosa che, il giorno che
    cambiano, resta indietro.
    """
    return sorted(CONSUMI.items(), key=lambda v: (v[1], v[0]))
