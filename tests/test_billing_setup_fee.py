"""Setup fee una tantum al checkout, INERTE di default (BILLING_SETUP_FEE off).
Stripe finto completo (incl. Price.list per lookup_key), nessuna rete.

- flag OFF → checkout identico a oggi (nessuna setup fee)
- flag ON  → line item one-time risolto dal lookup_key giusto del tier
- mapping starter/pro/enterprise → setup_*
- tier non mappato → nessuna setup fee, nessun errore
"""
import pytest

from app import billing
from app.config import settings


class _Sess:
    url = "https://checkout.stripe.com/pay/cs_test_123"
    id = "cs_test_123"


class _FakeStripe:
    last = None
    price_list_calls = []

    class checkout:
        class Session:
            @staticmethod
            def create(**kw):
                _FakeStripe.last = kw
                return _Sess()

    class Price:
        # data vuota di default → sovrascrivibile per singolo test
        data = None

        @staticmethod
        def list(**kw):
            _FakeStripe.price_list_calls.append(kw)
            if _FakeStripe.Price.data is not None:
                return {"data": _FakeStripe.Price.data}
            lk = (kw.get("lookup_keys") or [""])[0]
            return {"data": [{"id": f"price_{lk}"}]}   # id derivato dal lookup_key


def _en(monkeypatch, setup_fee=False):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(settings, "stripe_price_starter", "price_starter")
    monkeypatch.setattr(settings, "stripe_price_pro", "price_pro")
    monkeypatch.setattr(settings, "stripe_price_enterprise", "price_enterprise")
    monkeypatch.setattr(settings, "billing_setup_fee", setup_fee)
    _FakeStripe.last = None
    _FakeStripe.price_list_calls = []
    _FakeStripe.Price.data = None
    monkeypatch.setattr(billing, "_client", lambda: _FakeStripe)


def _prices(kw):
    return [li["price"] for li in kw["line_items"]]


# ── flag OFF: comportamento identico a oggi ─────────────────────────────────
def test_flag_off_nessuna_setup_fee(monkeypatch):
    _en(monkeypatch, setup_fee=False)
    r = billing.create_checkout("starter", "a@b.it")
    assert r["id"] == "cs_test_123"
    assert _prices(_FakeStripe.last) == ["price_starter"]      # solo il canone
    assert _FakeStripe.price_list_calls == []                 # Price.list mai chiamata


# ── flag ON: setup fee risolta per lookup_key ───────────────────────────────
def test_flag_on_starter_aggiunge_setup(monkeypatch):
    _en(monkeypatch, setup_fee=True)
    billing.create_checkout("starter")
    assert _prices(_FakeStripe.last) == ["price_starter", "price_setup_starter_dante"]
    assert _FakeStripe.price_list_calls[-1]["lookup_keys"] == ["setup_starter_dante"]


def test_mapping_tier_lookup_key(monkeypatch):
    attesi = {
        "starter": "setup_starter_dante",
        "pro": "setup_business_virgilio",
        "enterprise": "setup_enterprise_beatrice",
    }
    for tier, lk in attesi.items():
        _en(monkeypatch, setup_fee=True)
        billing.create_checkout(tier)
        assert _FakeStripe.price_list_calls[-1]["lookup_keys"] == [lk]
        assert _prices(_FakeStripe.last)[-1] == f"price_{lk}"     # line item aggiunto


def test_setup_lookup_unita(monkeypatch):
    # off → sempre "" (anche per tier validi); on → mappa; tier ignoto → ""
    monkeypatch.setattr(settings, "billing_setup_fee", False)
    assert billing._setup_lookup("starter") == ""
    monkeypatch.setattr(settings, "billing_setup_fee", True)
    assert billing._setup_lookup("enterprise") == "setup_enterprise_beatrice"
    assert billing._setup_lookup("boh") == ""                    # tier non mappato
    assert billing._setup_lookup("") == ""


def test_tier_non_mappato_nessuna_setup_nessun_errore(monkeypatch):
    # un tier non nel catalogo prezzi torna l'errore "piano sconosciuto" di sempre,
    # senza toccare la setup fee e senza sollevare eccezioni
    _en(monkeypatch, setup_fee=True)
    r = billing.create_checkout("boh")
    assert "error" in r and _FakeStripe.price_list_calls == []


def test_flag_on_ma_lookup_non_risolto_salta_setup(monkeypatch):
    # se Stripe non trova il prezzo per il lookup_key, il checkout NON si rompe:
    # la setup fee viene semplicemente saltata (resta solo il canone)
    _en(monkeypatch, setup_fee=True)
    _FakeStripe.Price.data = []          # nessun prezzo trovato
    r = billing.create_checkout("pro")
    assert r["id"] == "cs_test_123"
    assert _prices(_FakeStripe.last) == ["price_pro"]
