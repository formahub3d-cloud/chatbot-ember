"""S5.1a · I token che una chiamata è costata davvero.

Il punto di partenza: `usage` le risposte lo portano da sempre, e il codice lo
buttava via. Finché il conto si faceva a richieste andava bene; da quando i
token diventano denaro, buttarlo via vuol dire fatturare a stima.

Le due cose che questi test tengono ferme, e sono la stessa detta due volte:

  · **«non misurato» torna `None`, mai `Uso(0, 0)`.** Zero vuol dire «è costato
    zero» e finisce dritto in fattura; `None` vuol dire «è successo e non
    sappiamo quanto», che è un fatto diverso e va scritto come tale;
  · **l'`output_tokens` di Claude in streaming è CUMULATIVO.** Sommarlo a ogni
    `message_delta` farebbe pagare una risposta lunga due volte e mezza — è il
    difetto che si vede solo in bolletta, cioè tardi.
"""
import pytest

from app import uso


# ── risposte intere ──────────────────────────────────────────────────────────

def test_mistral():
    u = uso.da_risposta({"usage": {"prompt_tokens": 12, "completion_tokens": 40}},
                        "mistral-small-latest")
    assert (u.input, u.output, u.totale) == (12, 40, 52)
    assert u.modello == "mistral-small-latest"


def test_claude():
    u = uso.da_risposta({"usage": {"input_tokens": 300, "output_tokens": 7}})
    assert (u.input, u.output, u.totale) == (300, 7, 307)


def test_il_modello_si_prende_dalla_risposta_se_non_lo_dice_il_chiamante():
    u = uso.da_risposta({"model": "mistral-large", "usage": {"prompt_tokens": 1}})
    assert u.modello == "mistral-large"


def test_senza_usage_e_NONE_non_zero():
    """La differenza che vale soldi: `Uso(0,0)` direbbe «gratis»."""
    for corpo in ({}, {"choices": []}, {"usage": None}, None, "non un dict"):
        assert uso.da_risposta(corpo) is None, corpo


def test_un_usage_di_forma_sconosciuta_e_NONE(caplog):
    """Se il provider cambia i nomi dei campi, si vede: non si fattura zero."""
    assert uso.da_risposta({"usage": {"tokens_totali": 50}}) is None


def test_un_campo_solo_basta_e_l_altro_vale_zero():
    # una risposta vuota ha `completion_tokens: 0` legittimo: qui zero è un
    # numero misurato, non un dato mancante
    u = uso.da_risposta({"usage": {"prompt_tokens": 9, "completion_tokens": 0}})
    assert (u.input, u.output) == (9, 0)


def test_i_numeri_storti_non_diventano_token():
    """`True` in Python è un intero: senza il controllo scriverebbe 1 token
    fantasma. E un negativo è un dato rotto, non un accredito."""
    assert uso.da_risposta({"usage": {"prompt_tokens": True, "completion_tokens": True}}) is None
    u = uso.da_risposta({"usage": {"prompt_tokens": -5, "completion_tokens": 10}})
    assert (u.input, u.output) == (0, 10)
    assert uso.da_risposta({"usage": {"prompt_tokens": "molti"}}) is None


# ── streaming ────────────────────────────────────────────────────────────────

def test_stream_claude_input_subito_output_alla_fine():
    m = uso.UsoInStream("claude-haiku-4-5")
    m.aggiungi({"type": "message_start", "message": {"usage": {"input_tokens": 120,
                                                               "output_tokens": 0}}})
    m.aggiungi({"type": "content_block_delta", "delta": {"text": "ciao"}})
    m.aggiungi({"type": "message_delta", "usage": {"output_tokens": 45}})
    u = m.finale()
    assert (u.input, u.output) == (120, 45)
    assert u.modello == "claude-haiku-4-5"


def test_stream_claude_l_output_e_CUMULATIVO_non_si_somma():
    """Il difetto che si vedrebbe solo in bolletta.

    Claude manda `output_tokens` crescente a ogni `message_delta`: 10, 25, 45.
    Sommandoli si fatturerebbero 80 token invece di 45.
    """
    m = uso.UsoInStream()
    m.aggiungi({"type": "message_start", "message": {"usage": {"input_tokens": 100}}})
    for parziale in (10, 25, 45):
        m.aggiungi({"type": "message_delta", "usage": {"output_tokens": parziale}})
    assert m.finale().output == 45


def test_stream_mistral_l_ultimo_blocco_porta_il_conto():
    m = uso.UsoInStream()
    m.aggiungi({"choices": [{"delta": {"content": "ciao"}}]})
    m.aggiungi({"model": "mistral-small-latest",
                "usage": {"prompt_tokens": 30, "completion_tokens": 8}})
    u = m.finale()
    assert (u.input, u.output) == (30, 8)
    assert u.modello == "mistral-small-latest"


def test_uno_stream_senza_usage_e_NONE():
    """È il caso vero di oggi: `include_usage` è spento, e il consumo dello
    stream Mistral risulta dichiaratamente non misurato."""
    m = uso.UsoInStream()
    for _ in range(5):
        m.aggiungi({"choices": [{"delta": {"content": "x"}}]})
    assert m.finale() is None


def test_uno_stream_che_non_e_mai_partito_e_NONE():
    assert uso.UsoInStream().finale() is None


def test_il_misuratore_non_solleva_MAI():
    """Un errore qui spegnerebbe una risposta che l'utente sta già leggendo.

    Il prezzo di una misura mancata è una riga di log; quello di una risposta
    troncata è il prodotto.
    """
    m = uso.UsoInStream()
    for spazzatura in (None, "stringa", 42, [], {"type": "message_start"},
                       {"type": "message_start", "message": None},
                       {"type": "message_delta", "usage": "no"}):
        m.aggiungi(spazzatura)
    assert m.finale() is None


def test_uno_stream_interrotto_a_meta_tiene_quello_che_sa():
    """Claude ha già detto l'input al primo evento: se lo stream cade dopo,
    quella parte è misurata e va tenuta — è consumo davvero avvenuto."""
    m = uso.UsoInStream()
    m.aggiungi({"type": "message_start", "message": {"usage": {"input_tokens": 200}}})
    u = m.finale()
    assert u is not None and (u.input, u.output) == (200, 0)


# ── il ponte con i provider ──────────────────────────────────────────────────

def test_chat_con_uso_restituisce_testo_e_conto(monkeypatch):
    from app import providers
    from app.config import settings

    class _R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ciao"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2}}

    monkeypatch.setattr(settings, "llm_provider", "mistral")
    monkeypatch.setattr(providers, "_post_with_retry", lambda *a, **k: _R())

    testo, u = providers.chat_con_uso("s", "u")
    assert testo == "ciao"
    assert (u.input, u.output) == (5, 2)
    # e `chat()` continua a restituire solo il testo: nessun chiamante cambia
    assert providers.chat("s", "u") == "ciao"


def test_chat_con_uso_regge_una_risposta_senza_usage(monkeypatch):
    from app import providers
    from app.config import settings

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ciao"}}]}

    monkeypatch.setattr(settings, "llm_provider", "mistral")
    monkeypatch.setattr(providers, "_post_with_retry", lambda *a, **k: _R())

    testo, u = providers.chat_con_uso("s", "u")
    assert testo == "ciao"
    assert u is None, "senza usage il conto è ignoto, non zero"


def test_include_usage_si_manda_SOLO_se_acceso(monkeypatch):
    """È un campo in più nella richiesta della chat in produzione, e non è
    stato verificato contro l'API vera: parte spento, e questo test è la prova
    che non parte da solo."""
    from app import providers
    from app.config import settings

    visti = {}

    class _Stream:
        def __init__(self, **kw):
            visti.update(kw.get("json") or {})

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter([])

    monkeypatch.setattr(settings, "llm_provider", "mistral")
    monkeypatch.setattr(settings, "mistral_stream_usage", False)
    monkeypatch.setattr(providers.httpx, "stream", lambda *a, **k: _Stream(**k))
    list(providers.chat_stream("s", "u"))
    assert "stream_options" not in visti

    visti.clear()
    monkeypatch.setattr(settings, "mistral_stream_usage", True)
    list(providers.chat_stream("s", "u"))
    assert visti["stream_options"] == {"include_usage": True}
