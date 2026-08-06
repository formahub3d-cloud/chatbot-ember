"""S5.1a · I token che una chiamata è costata davvero.

**Il punto di partenza è che oggi nessuno li legge.** Le risposte di Mistral e
di Claude portano `usage` da sempre; il codice prende `content` e butta via il
resto. Finché il conto si faceva a richieste andava bene; da quando i token
diventano denaro (Sprint 5), buttarlo via vuol dire fatturare a stima.

Questo modulo fa **una cosa sola**: legge quello che l'API ha detto e lo
normalizza. Non decide quanto costa (il moltiplicatore è S5.2), non scrive
niente (il registro è S5.1b), non stima. Tenerlo separato è ciò che permette di
provarlo senza rete e senza database.

**«Non misurato» è un terzo esito, e non vale zero.** Se una risposta non porta
`usage` — un provider che cambia forma, uno stream che finisce a metà — questo
modulo torna `None`. Un `Uso(0, 0)` direbbe «è costato zero», che è falso e
finisce dritto in fattura: è la regola 3 del repo («senza dato la spia dice
"—", e dice QUALE dato manca») applicata dove costa soldi.

Le due forme, che non si somigliano:

    Mistral  {"usage": {"prompt_tokens": 12, "completion_tokens": 40}}
    Claude   {"usage": {"input_tokens": 12,  "output_tokens": 40}}

E in streaming non si somigliano nemmeno un po': Mistral manda `usage`
nell'ultimo blocco (solo se glielo si chiede con `stream_options`), Claude lo
spezza fra `message_start` (input) e `message_delta` (output). Per questo lo
stream ha un accumulatore invece di una funzione pura.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("ember.uso")


@dataclass(frozen=True)
class Uso:
    """Quanto è costata una chiamata, in token, come l'ha detto il provider."""

    input: int
    output: int
    modello: str = ""

    @property
    def totale(self) -> int:
        return self.input + self.output


def _intero(valore) -> int | None:
    """Un intero non negativo, o `None` se quel campo non è un numero.

    `bool` è `int` in Python: `True` passerebbe per 1 e scriverebbe un token
    fantasma nel registro.
    """
    if isinstance(valore, bool) or not isinstance(valore, (int, float)):
        return None
    intero = int(valore)
    return intero if intero >= 0 else None


def da_risposta(corpo: dict | None, modello: str = "") -> Uso | None:
    """L'uso da una risposta NON in streaming, di qualunque dei due provider.

    Una funzione sola per entrambi perché al chiamante non interessa da chi
    arriva: gli interessa quanti token. Il riconoscimento è sui nomi dei campi,
    che sono l'unica differenza.
    """
    if not isinstance(corpo, dict):
        return None
    u = corpo.get("usage")
    if not isinstance(u, dict):
        log.warning("risposta senza usage (modello=%s): consumo NON misurato", modello)
        return None

    dentro = _intero(u.get("prompt_tokens"))
    if dentro is None:
        dentro = _intero(u.get("input_tokens"))
    fuori = _intero(u.get("completion_tokens"))
    if fuori is None:
        fuori = _intero(u.get("output_tokens"))

    if dentro is None and fuori is None:
        # `usage` c'è ma non contiene nessuno dei quattro campi noti: è un
        # cambio di forma del provider, e va visto — non trattato come zero.
        log.warning("usage in una forma sconosciuta (modello=%s): %s",
                    modello, sorted(u)[:6])
        return None
    return Uso(input=dentro or 0, output=fuori or 0,
               modello=modello or str(corpo.get("model") or ""))


class UsoInStream:
    """L'uso che arriva a pezzi, mentre lo stream passa.

    Si dà in pasto ogni evento già decodificato e alla fine si chiede `finale()`.
    Non solleva mai: un errore qui spegnerebbe una risposta che l'utente sta già
    leggendo, e il prezzo di una misura mancata è una riga di log — quello di
    una risposta troncata è il prodotto.
    """

    def __init__(self, modello: str = "") -> None:
        self.modello = modello
        self._input: int | None = None
        self._output: int | None = None

    def aggiungi(self, evento: dict | None) -> None:
        if not isinstance(evento, dict):
            return
        try:
            self._leggi(evento)
        except Exception:            # pragma: no cover - difesa, non logica
            log.exception("evento di stream illeggibile per l'uso")

    def _leggi(self, ev: dict) -> None:
        tipo = ev.get("type")

        # Claude: l'input si sa subito, l'output alla fine.
        if tipo == "message_start":
            u = (ev.get("message") or {}).get("usage") or {}
            self._somma(_intero(u.get("input_tokens")), _intero(u.get("output_tokens")))
            return
        if tipo == "message_delta":
            u = ev.get("usage") or {}
            # `output_tokens` di `message_delta` è CUMULATIVO: si sostituisce,
            # non si somma. Sommandolo, una risposta lunga si pagherebbe due
            # volte e mezza.
            fuori = _intero(u.get("output_tokens"))
            if fuori is not None:
                self._output = fuori
            dentro = _intero(u.get("input_tokens"))
            if dentro is not None:
                self._input = dentro
            return

        # Mistral: l'ultimo blocco porta `usage` completo (arriva solo se la
        # richiesta ha chiesto `stream_options.include_usage`).
        u = ev.get("usage")
        if isinstance(u, dict):
            self._somma(_intero(u.get("prompt_tokens")), _intero(u.get("completion_tokens")))
        if not self.modello and ev.get("model"):
            self.modello = str(ev["model"])

    def _somma(self, dentro: int | None, fuori: int | None) -> None:
        if dentro is not None:
            self._input = dentro
        if fuori is not None:
            self._output = fuori

    def finale(self) -> Uso | None:
        """L'uso misurato, o `None` se lo stream non l'ha mai detto.

        `None` non è zero: vuol dire che quella chiamata è stata fatta e non
        sappiamo quanto sia costata. Chi tiene il registro deve poterlo scrivere
        come tale (S5.1b) invece di regalarla.
        """
        if self._input is None and self._output is None:
            log.warning("stream finito senza usage (modello=%s): consumo NON misurato",
                        self.modello)
            return None
        return Uso(input=self._input or 0, output=self._output or 0, modello=self.modello)
