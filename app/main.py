"""API del servizio Ember.

Endpoint:
  GET  /health            stato e provider attivi
  POST /ingest            (admin) reindicizza il cervello su Qdrant
  POST /chat              (tenant) domanda → risposta limitata allo scope del tenant
                          con {"stream": true} risposta SSE token per token
  POST /upload            (tenant) carica un contratto → OCR + estrazione → ANTEPRIMA
                          dei campi (NON consolida: richiede conferma umana)
"""
import contextvars
import csv
import io
import logging
import tempfile
import uuid
from pathlib import Path

# Osservabilità: un request_id per richiesta, propagato nei log (e nell'header
# X-Request-ID della risposta), così si segue un problema end-to-end.
_request_id: contextvars.ContextVar = contextvars.ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id.get()
        return True


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
for _h in logging.getLogger().handlers:
    _h.addFilter(_RequestIdFilter())
log = logging.getLogger("ember")

# Rate limiting: finestra scorrevole di 60s per chiave tenant, delegato a un
# limiter estraibile (app/ratelimit.py) così da poter passare a un backend Redis
# per il multi-istanza senza toccare gli endpoint.
from .ratelimit import limiter


def rate_ok(key: str) -> bool:
    return limiter.allow(key, settings.rate_limit_per_min)

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from . import ingest, rag, ocr, extract, tenants, security, voice, writeback, metrics, events, gdpr, billing, manage_apikeys, obs, crypto, costs

obs.init_sentry()   # osservabilità errori (inerte senza SENTRY_DSN)

app = FastAPI(title="Ember — Cervello OVY", version="0.3.0")

# CORS: consente al widget di chat (browser) di chiamare l'API.
# I domini autorizzati arrivano da settings.cors_origins (vedi config.py):
# "*" per il pilota, oppure lista separata da virgola per la produzione.
# Difesa aggiuntiva per-tenant: ogni tenant può avere "allowed_origins" e la
# richiesta viene rifiutata (403) se l'Origin non è consentito (vedi /chat).
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """request_id per richiesta + header di sicurezza + trasparenza AI (EU AI Act)."""
    rid = (request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12])[:64]
    _request_id.set(rid)
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = rid
    if settings.security_headers:
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=()")
        resp.headers.setdefault("X-AI-Generated", "true")
    return resp


# Widget servito dal backend stesso: un solo file da mantenere, stesso dominio
# dell'API, aggiornato a ogni deploy. → https://<dominio>/widget/embed.js
app.mount("/widget", StaticFiles(directory="widget"), name="widget")


@app.on_event("startup")
def _startup_seed_tenants():
    """Se è collegato un database, crea/popola la tabella tenants alla partenza."""
    try:
        tenants.ensure_seeded()
    except Exception:
        log.exception("ensure_seeded fallito: si userà il fallback statico")


def tenant_or_401(key: str) -> dict:
    tenant = tenants.get_tenant_by_key(key)
    if not tenant:
        raise HTTPException(401, "Chiave tenant non valida")
    return tenant


def _grants(tenant: dict) -> dict:
    """Grant del tenant per il retrieval. `allowed_scopes` (storico, livello tenant)
    resta il campo principale; `allowed_orgs` e `allowed_sub_tenants` sono opzionali
    e additivi (modello a tre livelli OVYON). Vedi rag.build_filter."""
    return {
        "allowed_scopes": tenant.get("allowed_scopes", []),
        "allowed_orgs": tenant.get("allowed_orgs", []),
        "allowed_sub_tenants": tenant.get("allowed_sub_tenants", []),
    }


class ChatIn(BaseModel):
    message: str
    stream: bool = False  # true → risposta SSE (text/event-stream) token per token
    history: list = []     # turni precedenti [{role, content}] dal client, per i follow-up
    lang: str = ""         # "it" | "en" — se vuota: branding del tenant → default_lang


class SearchIn(BaseModel):
    message: str
    k: int = 6


class WritebackIn(BaseModel):
    scope: str                 # tenant/scope di destinazione (deve essere concesso)
    title: str
    body: str
    summary: str = ""
    tags: list[str] = []
    confirm: bool = False      # false → solo ANTEPRIMA (regola 5: conferma umana)
    overwrite: bool = False


class FeedbackIn(BaseModel):
    vote: str                  # "up" | "down" (👍/👎 dal widget)
    question: str = ""
    answer: str = ""
    sources: list = []
    reason: str = ""           # motivo opzionale (soprattutto sul 👎)


class GdprEraseIn(BaseModel):
    tenant: str                # codice tenant (scope) di cui cancellare i dati
    confirm: bool = False      # senza confirm=true è solo un'anteprima (dry-run)


class CheckoutIn(BaseModel):
    tier: str                  # "starter" | "pro" | "enterprise"
    email: str = ""


class TenantCreateIn(BaseModel):
    name: str
    orgs: str = ""             # code separati da virgola
    tenants: str = ""
    subs: str = ""
    origins: str = ""
    quota: int = 0
    branding: dict | None = None


class TenantNameIn(BaseModel):
    name: str


class TenantBrandIn(BaseModel):
    name: str
    branding: dict


def _secs_to_midnight_utc() -> str:
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return str(max(1, int((nxt - now).total_seconds())))


def _reject_master_browser(tenant: dict, origin: str) -> None:
    """La chiave master ('*') vede TUTTI gli scope: è ammessa solo per uso admin
    server-side (MCP/CLI/curl, che non inviano Origin). Se arriva da un browser
    (Origin valorizzato, cioè il widget) → 403. Così 'master mai in widget pubblico'
    è imposto in codice, non lasciato alla convenzione."""
    if origin and rag.is_master(_grants(tenant)):
        raise HTTPException(403, "Chiave master non utilizzabile da un browser.")


def _guard(tenant: dict, key: str, origin: str) -> None:
    """Controlli comuni agli endpoint tenant: master-guard, origine, rate limit, quota."""
    _reject_master_browser(tenant, origin)
    if not security.origin_allowed(origin, tenant.get("allowed_origins")):
        raise HTTPException(403, "Origine non autorizzata per questo tenant.")
    if not rate_ok(key):
        raise HTTPException(429, "Troppe richieste. Riprova tra un minuto.", headers={"Retry-After": "60"})
    if not tenants.quota_ok(tenant):
        raise HTTPException(429, "Quota superata per questo tenant (giornaliera o mensile).",
                            headers={"Retry-After": _secs_to_midnight_utc()})


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_provider, "embed": settings.embed_provider,
            "voice": settings.voice_provider or "browser"}


@app.get("/config")
def config(x_tenant_key: str = Header(default="")):
    """Branding + capacità per il widget (titolo, accent, voce disponibile).
    Permette al widget di auto-configurarsi dal server senza ripetere i dati nell'HTML."""
    tenant = tenant_or_401(x_tenant_key)
    brand = tenant.get("branding", {}) or {}
    out = {
        "title": brand.get("title", tenant.get("name", "Ember · Assistente")),
        "subtitle": brand.get("subtitle", "Assistente AI"),
        "accent": brand.get("accent", "#0ED4E4"),
        "lang": brand.get("lang", settings.default_lang),   # lingua risposte (it|en)
        "voice_pro": voice.stt_enabled(),   # true → il widget può usare la voce PRO via proxy
    }
    # White-label per cliente: campi opzionali dal record del tenant. Inviati solo se
    # valorizzati, così il widget usa i default quando il brand non li specifica.
    for k in ("avatar", "logo", "greeting"):
        v = brand.get(k)
        if v:
            out[k] = v
    return out


class TTSIn(BaseModel):
    text: str


@app.post("/voice/stt")
async def do_stt(file: UploadFile = File(...), x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """Audio → testo (voce PRO). 501 se VOICE_PROVIDER non è configurato."""
    _guard(tenant_or_401(x_tenant_key), x_tenant_key, origin)
    if not voice.stt_enabled():
        raise HTTPException(501, "Voce PRO non attiva: usa la voce del browser.")
    audio = await file.read()
    try:
        return {"text": voice.transcribe(audio, mime=file.content_type or "audio/webm")}
    except Exception:
        log.exception("stt failed")
        raise HTTPException(502, "Trascrizione non riuscita.")


@app.post("/voice/tts")
def do_tts(body: TTSIn, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """Testo → audio (voce PRO). 501 se VOICE_PROVIDER non è configurato."""
    _guard(tenant_or_401(x_tenant_key), x_tenant_key, origin)
    if not voice.tts_enabled():
        raise HTTPException(501, "Voce PRO non attiva: usa la voce del browser.")
    text = security.cap_input(body.text, settings.max_message_chars)
    if not text:
        raise HTTPException(422, "Testo vuoto.")
    try:
        audio, ctype = voice.synthesize(text)
        return Response(content=audio, media_type=ctype)
    except Exception:
        log.exception("tts failed")
        raise HTTPException(502, "Sintesi vocale non riuscita.")


@app.post("/ingest")
def do_ingest(authorization: str = Header(default="")):
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(401, "Token admin non valido")
    try:
        return ingest.run()
    except HTTPException:
        raise
    except Exception:
        log.exception("ingest failed")
        raise HTTPException(500, "Errore interno durante l'indicizzazione.")


@app.post("/chat")
def do_chat(body: ChatIn, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """Risposta del chatbot. Con {"stream": true} nel body la risposta è SSE:
    `event: sources` (fonti+scope) → N × `data: {"delta": ...}` → `event: done`.
    Senza flag resta il JSON classico {answer, sources, scopes} (retro-compat)."""
    tenant = tenant_or_401(x_tenant_key)
    _reject_master_browser(tenant, origin)
    if not security.origin_allowed(origin, tenant.get("allowed_origins")):
        raise HTTPException(403, "Origine non autorizzata per questo tenant.")
    if not rate_ok(x_tenant_key):
        raise HTTPException(429, "Troppe richieste. Riprova tra un minuto.", headers={"Retry-After": "60"})
    if not tenants.quota_ok(tenant):
        raise HTTPException(429, "Quota superata per questo tenant (giornaliera o mensile).",
                            headers={"Retry-After": _secs_to_midnight_utc()})
    body.message = security.cap_input(body.message, settings.max_message_chars)
    if not body.message:
        raise HTTPException(422, "Messaggio vuoto.")
    lang = body.lang or (tenant.get("branding") or {}).get("lang") or settings.default_lang
    log.info("chat tenant=%s q=%r", tenant.get("name", "?"), security.redact_pii(body.message)[:200])
    if body.stream:
        try:
            gen = rag.answer_stream(body.message, _grants(tenant), history=body.history, lang=lang)
            first = next(gen)  # forza retrieval/validazione PRIMA degli header 200
        except HTTPException:
            raise
        except Exception:
            log.exception("chat stream failed")
            raise HTTPException(500, "Errore interno del chatbot.")

        def _stream():
            yield first
            try:
                yield from gen
            except Exception:
                log.exception("chat stream interrotto")
                yield 'event: error\ndata: {"message": "Stream interrotto."}\n\n'

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        return rag.answer(body.message, _grants(tenant), history=body.history, lang=lang)
    except HTTPException:
        raise
    except Exception:
        log.exception("chat failed")
        raise HTTPException(500, "Errore interno del chatbot.")


# ── Endpoint per il connettore MCP (ovy_search / get_document / list_context /
#    create|update_document). Stessa autenticazione e stessi filtri per grant del
#    /chat: l'isolamento è server-side, non delegato al connettore. ──────────────

@app.post("/search")
def do_search(body: SearchIn, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """ovy_search: risultati rilevanti (metadati + snippet) nello scope del tenant."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    q = security.cap_input(body.message, settings.max_message_chars)
    if not q:
        raise HTTPException(422, "Query vuota.")
    k = max(1, min(int(body.k or 6), 20))
    tenants.log_access(tenant.get("key_hash"), "read", detail="search")
    try:
        return rag.search(q, _grants(tenant), k)
    except Exception:
        log.exception("search failed")
        raise HTTPException(500, "Errore interno durante la ricerca.")


@app.get("/document")
def do_document(slug: str, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """ovy_get_document: contenuto completo di una nota per slug, se nello scope."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    try:
        doc = rag.get_document(slug, _grants(tenant))
    except Exception:
        log.exception("get_document failed")
        raise HTTPException(500, "Errore interno.")
    if not doc:
        raise HTTPException(404, "Nota non trovata o fuori dallo scope.")
    tenants.log_access(tenant.get("key_hash"), "read", detail=f"document:{slug}")
    return doc


@app.get("/context")
def do_context(x_tenant_key: str = Header(default="")):
    """ovy_list_context: livelli di permesso (org/tenant/sub) visibili al tenant."""
    tenant = tenant_or_401(x_tenant_key)
    return {"name": tenant.get("name", ""), **rag.list_context(_grants(tenant))}


@app.post("/feedback")
def do_feedback(body: FeedbackIn, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """Feedback 👍/👎 del widget su una risposta. Autenticato come il /chat (stesse
    guardie di origine/rate/quota). Aggiorna le metriche per scope e logga (redatto)
    la domanda: serve a capire dove il cervello è debole. Best-effort, mai bloccante."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    up = str(body.vote).strip().lower() in ("up", "1", "true", "positivo", "si", "sì", "👍")
    scopes = rag.scopes_of(_grants(tenant))
    qred = security.redact_pii(body.question or "")[:160]
    reason = security.redact_pii(body.reason or "")[:160] if not up else ""
    qlog = qred + (" · motivo: " + reason if reason else "")
    metrics.bump_feedback(scopes, up, qlog)
    events.record("feedback_up" if up else "feedback_down", scopes, qlog)
    log.info("feedback · scope=%s · voto=%s · q=%r", scopes, "up" if up else "down", qlog)
    return {"ok": True}


def _require_admin(authorization: str) -> None:
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(401, "Token admin non valido.")


@app.get("/admin/analytics")
def admin_analytics(authorization: str = Header(default="")):
    """Colpo d'occhio operativo (dal boot del processo): chat/gap/feedback per scope.
    Protetto dal Bearer ADMIN_TOKEN, come /ingest. In-memory: si azzera al redeploy."""
    _require_admin(authorization)
    return metrics.snapshot()


@app.get("/admin/insights")
def admin_insights(authorization: str = Header(default="")):
    """Segnali per arricchire il cervello: ultime domande senza risposta (gap) e
    ultimi feedback negativi (redatti). Protetto dal Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    return metrics.insights()


@app.get("/admin/learning")
def admin_learning(authorization: str = Header(default="")):
    """Auto-miglioramento del cervello: task di apprendimento azionabili generate
    dai gap (domande senza risposta) e dai feedback 👎 — raggruppate per scope e
    domanda, con conteggio e suggerimento concreto. Bearer ADMIN_TOKEN. In-memory."""
    _require_admin(authorization)
    return metrics.learning_tasks()


@app.get("/admin/events")
def admin_events(limit: int = 50, authorization: str = Header(default="")):
    """Storico eventi conversazione (chat/gap/feedback) da Supabase, più recenti
    prima. Protetto dal Bearer ADMIN_TOKEN. Vuoto se ANALYTICS_PERSIST è off."""
    _require_admin(authorization)
    return {"events": events.recent(limit), "persist": events.enabled()}


@app.get("/metrics")
def prometheus_metrics(authorization: str = Header(default="")):
    """Metriche in formato testo Prometheus (scraping/Grafana). Protetto dal Bearer
    ADMIN_TOKEN perché le serie per-scope rivelano i nomi tenant. In-memory."""
    _require_admin(authorization)
    return Response(metrics.prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.post("/admin/retention/run")
def retention_run(days: int = 0, authorization: str = Header(default="")):
    """GDPR retention: cancella gli eventi analytics oltre la soglia. Senza `days`
    usa RETENTION_DAYS. Da richiamare a mano o da un cron. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    deleted = events.purge_old(days or None)
    return {"deleted": deleted, "retention_days": settings.retention_days}


def _require_apikeys() -> None:
    if not tenants._apikeys_enabled():
        raise HTTPException(400, "Backend Supabase (api_keys) non attivo.")


@app.get("/admin/usage")
def admin_usage(authorization: str = Header(default="")):
    """Uso per tenant del giorno (conteggio richieste da key_usage) + stima di spesa
    in € (se COST_PER_REQUEST_EUR è impostata) e alert sui tenant oltre la soglia
    giornaliera (COST_ALERT_DAILY_EUR). Senza segreti. Bearer ADMIN_TOKEN. Vuoto se le
    quote non sono ancora attive (la tabella key_usage si popola coi tenant a quota)."""
    _require_admin(authorization)
    return costs.check_and_alert(tenants.usage_today())


@app.get("/admin/access-logs")
def admin_access_logs(limit: int = 100, authorization: str = Header(default="")):
    """Audit trail: ultime voci di access_logs (chi legge/scrive cosa). Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    return {"logs": tenants.recent_access_logs(limit)}


@app.get("/admin/status")
def admin_status(authorization: str = Header(default="")):
    """Snapshot operativo delle funzioni attive (solo booleani/valori non sensibili).
    Utile per verificare la configurazione a colpo d'occhio. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    return {
        "grants_backend": settings.grants_backend.strip() or "static",
        "supabase": tenants._apikeys_enabled(),
        "mongo": bool(settings.mongo_uri.strip()),
        "redis": bool(settings.redis_url.strip()),
        "sentry": obs.enabled(),
        "stripe": billing.enabled(),
        "voice_provider": settings.voice_provider.strip() or "",
        "analytics_persist": bool(settings.analytics_persist),
        "retention_days": settings.retention_days,
        "content_encryption": crypto.enabled(),
        "default_lang": settings.default_lang,
    }


@app.get("/version")
def version():
    """Build info pubbliche: versione app + commit. Utile per sapere cosa è in prod."""
    return {"name": "Ember", "version": settings.app_version, "commit": settings.git_sha[:12]}


def _to_csv(rows: list, fields: list) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


@app.get("/admin/access-logs.csv")
def admin_access_logs_csv(limit: int = 500, authorization: str = Header(default="")):
    """Audit trail in CSV (per compliance/archiviazione). Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    data = _to_csv(tenants.recent_access_logs(limit), ["at", "action", "tenant", "org", "detail"])
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=access-logs.csv"})


@app.get("/admin/events.csv")
def admin_events_csv(limit: int = 500, authorization: str = Header(default="")):
    """Eventi analytics in CSV. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    data = _to_csv(events.recent(limit), ["at", "kind", "scope", "question"])
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=events.csv"})


@app.get("/admin/tenants")
def admin_tenants(authorization: str = Header(default="")):
    """Elenco chiavi-tenant (senza segreti). Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    _require_apikeys()
    return {"tenants": manage_apikeys.list_keys()}


@app.post("/admin/tenants")
def admin_tenant_create(body: TenantCreateIn, authorization: str = Header(default="")):
    """Onboarding via API: crea una chiave-tenant e la restituisce IN CHIARO una sola
    volta (nel DB solo l'hash). Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    _require_apikeys()
    key = manage_apikeys.create_key(body.name, body.orgs, body.tenants, body.subs,
                                    body.origins, body.quota, body.branding)
    return {"name": body.name, "key": key, "nota": "chiave mostrata una sola volta"}


@app.post("/admin/tenants/revoke")
def admin_tenant_revoke(body: TenantNameIn, authorization: str = Header(default="")):
    """Disattiva (active=false) le chiavi con questo nome. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    _require_apikeys()
    return {"revoked": manage_apikeys.revoke(body.name)}


@app.post("/admin/tenants/brand")
def admin_tenant_brand(body: TenantBrandIn, authorization: str = Header(default="")):
    """Imposta/aggiorna il branding (white-label) di un tenant. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    _require_apikeys()
    return {"updated": manage_apikeys.set_branding(body.name, body.branding)}


@app.post("/billing/checkout")
def billing_checkout(body: CheckoutIn):
    """Crea una sessione di Checkout Stripe per un piano (customer-facing). Ritorna
    l'URL a cui reindirizzare il cliente. Inerte se Stripe non è configurato."""
    res = billing.create_checkout(body.tier, body.email)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@app.post("/billing/webhook")
async def billing_webhook(request: Request):
    """Webhook Stripe (firma verificata con STRIPE_WEBHOOK_SECRET). Registra l'evento;
    il provisioning del tenant resta manuale (python -m app.manage_apikeys add)."""
    ev = billing.verify_event(await request.body(), request.headers.get("Stripe-Signature", ""))
    if ev is None:
        raise HTTPException(400, "webhook non verificato")
    etype = ev.get("type") if isinstance(ev, dict) else getattr(ev, "type", "?")
    log.info("stripe webhook: %s", etype)
    return {"received": True, "type": etype}


@app.get("/admin/gdpr/export")
def gdpr_export(tenant: str, authorization: str = Header(default="")):
    """GDPR — diritto di accesso/portabilità: tutti i dati di un tenant (documenti
    con corpo DECIFRATO + eventi analytics). Protetto dal Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    return gdpr.export_tenant(tenant)


@app.post("/admin/gdpr/erase")
def gdpr_erase(body: GdprEraseIn, authorization: str = Header(default="")):
    """GDPR — diritto all'oblio: cancella i dati di un tenant da Qdrant e Supabase.
    Senza `confirm: true` restituisce solo l'anteprima (dry-run). Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    if not body.confirm:
        return {"dry_run": True, "would_erase": gdpr.erase_counts(body.tenant),
                "hint": "richiama con confirm=true per cancellare davvero"}
    return {"dry_run": False, "result": gdpr.erase_tenant(body.tenant)}


@app.get("/ready")
def ready():
    """Readiness per monitoraggio: verifica raggiungibilità di Qdrant e del backend
    tenant. 200 se tutto ok, 503 se un componente critico non risponde."""
    checks = {"qdrant": False, "tenants": False}
    try:
        ingest.client().get_collections()
        checks["qdrant"] = True
    except Exception:
        log.warning("readiness: Qdrant non raggiungibile")
    try:
        tenants.get_tenant_by_key("__readiness_probe__")  # None atteso, ma senza eccezioni
        checks["tenants"] = True
    except Exception:
        log.warning("readiness: backend tenant non raggiungibile")
    ok = all(checks.values())
    if not ok:
        raise HTTPException(503, {"ready": False, "checks": checks})
    return {"ready": True, "checks": checks}


@app.post("/writeback")
def do_writeback(body: WritebackIn, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """ovy_create_document / ovy_update_document: scrive una nota nel vault, MA solo
    dopo conferma umana (confirm=true). Senza conferma restituisce l'anteprima.
    Lo scope di destinazione deve essere tra quelli concessi al tenant."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    grants = _grants(tenant)
    ctx = rag.list_context(grants)
    if not ctx["master"] and body.scope not in (ctx["allowed_tenants"] or []):
        raise HTTPException(403, "Scope di destinazione non consentito per questo tenant.")
    title = security.cap_input(body.title, 200)
    if not title:
        raise HTTPException(422, "Titolo vuoto.")
    if not body.confirm:
        preview = writeback.render_note(body.scope, title, body.body, body.summary, body.tags)
        return {"consolidato": False, "preview": preview,
                "note": "Conferma con confirm=true per scrivere nel vault."}
    try:
        res = writeback.save_note(body.scope, title, body.body, body.summary,
                                  body.tags, overwrite=body.overwrite)
    except Exception:
        log.exception("writeback failed")
        raise HTTPException(500, "Errore durante la scrittura della nota.")
    if res.get("created"):
        tenants.log_access(tenant.get("key_hash"), "update" if body.overwrite else "create",
                           tenant_code=body.scope, detail=res.get("path"))
    return {"consolidato": res.get("created", False), **res}


@app.post("/upload")
async def do_upload(file: UploadFile = File(...), x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """Carica un documento → OCR → estrazione campi → ANTEPRIMA da confermare.
    Il consolidamento (write-back su vault/Notion) avviene solo dopo conferma umana.
    """
    _guard(tenant_or_401(x_tenant_key), x_tenant_key, origin)
    suffix = Path(file.filename or "doc.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    mime = file.content_type or "application/pdf"
    text = ocr.ocr_document(tmp_path, mime=mime)
    fields = extract.extract_unilav(text)
    return {"preview": fields, "note": "Conferma i campi prima del consolidamento.",
            "consolidato": False}
