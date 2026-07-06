"""Billing Stripe: checkout a livelli + webhook, con SDK Stripe FINTO (nessuna rete
né libreria reale). Off quando STRIPE_SECRET_KEY è vuota."""
from fastapi.testclient import TestClient

from app import billing, main
from app.config import settings

client = TestClient(main.app)


class _Sess:
    url = "https://checkout.stripe.com/pay/cs_test_123"
    id = "cs_test_123"


class _FakeStripe:
    last = None

    class checkout:
        class Session:
            @staticmethod
            def create(**kw):
                _FakeStripe.last = kw
                return _Sess()

    class Webhook:
        @staticmethod
        def construct_event(payload, sig, secret):
            return {"type": "checkout.session.completed"}


def _en(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(settings, "stripe_price_pro", "price_pro")
    monkeypatch.setattr(billing, "_client", lambda: _FakeStripe)


def test_checkout_ok(monkeypatch):
    _en(monkeypatch)
    r = billing.create_checkout("pro", "a@b.it")
    assert r["url"].startswith("https://checkout.stripe.com") and r["id"] == "cs_test_123"
    assert _FakeStripe.last["metadata"] == {"tier": "pro"}
    assert _FakeStripe.last["customer_email"] == "a@b.it"


def test_checkout_tier_sconosciuto(monkeypatch):
    _en(monkeypatch)
    assert "error" in billing.create_checkout("boh")


def test_checkout_disabilitato(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    assert billing.create_checkout("pro")["error"]


def test_endpoint_checkout(monkeypatch):
    _en(monkeypatch)
    r = client.post("/billing/checkout", json={"tier": "pro", "email": "a@b.it"})
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout")
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    assert client.post("/billing/checkout", json={"tier": "pro"}).status_code == 400


def test_webhook(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec")
    monkeypatch.setattr(billing, "_client", lambda: _FakeStripe)
    ev = billing.verify_event(b"{}", "sig")
    assert ev["type"] == "checkout.session.completed"
    r = client.post("/billing/webhook", content=b"{}", headers={"Stripe-Signature": "sig"})
    assert r.status_code == 200 and r.json()["received"] is True


def test_webhook_senza_secret(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    assert billing.verify_event(b"{}", "sig") is None
