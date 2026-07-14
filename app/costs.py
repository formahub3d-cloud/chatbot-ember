"""Stima costi per tenant + alert su spike (entrambi opzionali, OFF di default).

Non è contabilità: è una stima onesta basata sui conteggi di richieste (key_usage)
moltiplicati per una tariffa media per richiesta impostata dall'operatore
(COST_PER_REQUEST_EUR). Serve a dare un'idea della spesa per tenant nel pannello
admin e a lanciare un alert se un tenant "esplode". Nessun segreto, nessuna
chiamata esterna: inerte finché le tariffe restano a 0.

Nota: key_usage accumula i conteggi solo per i tenant che hanno una quota
(quota_day > 0); per gli altri l'uso non è tracciato e il costo risulta 0.
"""
import logging

from .config import settings
from . import obs

log = logging.getLogger("ember.costs")


def per_request_eur() -> float:
    """Tariffa media per richiesta in € (>= 0). 0 = costi non mostrati."""
    try:
        return max(0.0, float(settings.cost_per_request_eur or 0.0))
    except (TypeError, ValueError):
        return 0.0


def daily_threshold_eur() -> float:
    """Soglia di spesa giornaliera per tenant oltre cui scatta l'alert (0 = off)."""
    try:
        return max(0.0, float(settings.cost_alert_daily_eur or 0.0))
    except (TypeError, ValueError):
        return 0.0


def annotate(usage: list[dict]) -> dict:
    """Aggiunge una stima `cost_eur` a ogni riga d'uso e calcola il totale.
    Se la tariffa è 0 (default) non aggiunge i costi: restituisce solo i conteggi."""
    rate = per_request_eur()
    rows = [dict(r) for r in (usage or [])]
    total = 0.0
    if rate > 0:
        for r in rows:
            cost = round(int(r.get("count", 0) or 0) * rate, 4)
            r["cost_eur"] = cost
            total += cost
    return {
        "usage": rows,
        "cost_per_request_eur": rate,
        "total_eur": round(total, 4),
        "currency": "EUR",
    }


def spikes(rows: list[dict], threshold: float) -> list[dict]:
    """Righe la cui stima di costo giornaliera supera la soglia (threshold>0)."""
    if threshold <= 0:
        return []
    over = []
    for r in rows:
        cost = float(r.get("cost_eur", 0) or 0)
        if cost > threshold:
            over.append({"name": r.get("name"), "cost_eur": cost, "count": r.get("count")})
    return over


def check_and_alert(usage: list[dict]) -> dict:
    """Annota i costi e, se COST_ALERT_DAILY_EUR > 0, segnala i tenant oltre soglia
    (log WARNING + Sentry se attivo). Ritorna il payload completo per /admin/usage."""
    data = annotate(usage)
    threshold = daily_threshold_eur()
    over = spikes(data["usage"], threshold)
    if over:
        detail = ", ".join(f"{o['name']}=€{o['cost_eur']}" for o in over)
        log.warning("COST SPIKE (soglia €%.2f/giorno): %s", threshold, detail)
        obs.capture_message(f"Divina cost spike (soglia €{threshold}/giorno): {detail}")
    data["cost_alert_daily_eur"] = threshold
    data["alerts"] = over
    return data
