"""Billing Stripe (opzionale): sessioni di Checkout a livelli (starter/pro/enterprise)
e verifica del webhook. Inerte finché `STRIPE_SECRET_KEY` non è impostata — così il
resto di Ember funziona senza Stripe. La libreria `stripe` è importata in modo pigro.

Nessun segreto è cablato nel codice: chiavi e price-id arrivano dalla config (env).
Ember NON esegue pagamenti: crea solo la sessione di Checkout ospitata da Stripe.
"""
import logging

from .config import settings

log = logging.getLogger("ember.billing")


def enabled() -> bool:
    return bool(settings.stripe_secret_key.strip())


def _prices() -> dict:
    return {k: v for k, v in {
        "starter": settings.stripe_price_starter.strip(),
        "pro": settings.stripe_price_pro.strip(),
        "enterprise": settings.stripe_price_enterprise.strip(),
    }.items() if v}


def _client():
    import stripe   # import pigro: dipendenza opzionale, serve solo con Stripe attivo
    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_checkout(tier: str, email: str = "") -> dict:
    """Crea una sessione di Checkout Stripe per il piano `tier`. Ritorna {url, id}
    oppure {error} (billing off / piano sconosciuto). Non muove denaro: è Stripe a
    gestire il pagamento sulla pagina ospitata."""
    if not enabled():
        return {"error": "billing non configurato"}
    price = _prices().get((tier or "").strip().lower())
    if not price:
        return {"error": f"piano sconosciuto: {tier}"}
    try:
        s = _client()
        sess = s.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            success_url=settings.stripe_success_url or "https://ember.formahub.it/?checkout=ok",
            cancel_url=settings.stripe_cancel_url or "https://ember.formahub.it/?checkout=annullato",
            customer_email=email or None,
            metadata={"tier": tier},
        )
        return {"url": sess.url, "id": sess.id}
    except Exception as e:  # pragma: no cover - errore lato Stripe/rete
        log.warning("checkout Stripe fallito", exc_info=True)
        return {"error": "checkout non riuscito: " + str(e)[:120]}


def verify_event(payload: bytes, sig: str) -> dict | None:
    """Verifica la firma del webhook e ritorna l'evento; None se non verificabile.
    Richiede STRIPE_WEBHOOK_SECRET."""
    if not settings.stripe_webhook_secret.strip():
        return None
    try:
        return _client().Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except Exception:  # pragma: no cover - firma non valida
        log.warning("webhook Stripe non verificato", exc_info=True)
        return None
