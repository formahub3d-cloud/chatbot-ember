"""API del servizio Divina.

Endpoint:
  GET  /health            stato e provider attivi
  POST /ingest            (admin) reindicizza il cervello su Qdrant
  POST /chat              (tenant) domanda → risposta limitata allo scope del tenant
                          con {"stream": true} risposta SSE token per token
  POST /upload            (tenant) carica un contratto → OCR + estrazione → ANTEPRIMA
                          dei campi (NON consolida: richiede conferma umana)
"""
import base64
import contextvars
import csv
import io
import logging
import secrets
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
from . import ingest, rag, ocr, extract, tenants, security, voice, writeback, metrics, events, gdpr, billing, manage_apikeys, obs, crypto, costs, contracts, esign, agents_bridge, roadmap, braintasks, proposals, brain, clientauth

obs.init_sentry()   # osservabilità errori (inerte senza SENTRY_DSN)

# Token placeholder/deboli: con uno di questi (o vuoto) gli endpoint admin restano
# CHIUSI (503) — un deploy con config sbagliata non diventa mai un pannello aperto.
# Fix sicurezza (collaudo 17-07): un Bearer debole dava accesso a /admin/*.
_WEAK_ADMIN_TOKENS = {"change-me", "changeme", "password", "admin", "token",
                      "secret", "test", "123456", "admin123"}

_tok_boot = (settings.admin_token or "").strip()
if not _tok_boot or _tok_boot.lower() in _WEAK_ADMIN_TOKENS or len(_tok_boot) < 16:
    log.critical("ADMIN_TOKEN assente, debole o troppo corto: gli endpoint /admin/* "
                 "risponderanno 503 finché non viene impostato un token forte "
                 "(consigliato: >= 32 caratteri casuali). RUOTARE SUBITO.")

app = FastAPI(title="Divina — Cervello OVY", version="0.3.0")

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
    # La console /panel/ è una SPA statica che cambia a ogni deploy: no-cache
    # (con ETag → 304 se invariata) così il MOBILE non resta sulla versione
    # vecchia dopo un aggiornamento (collaudo 19-07).
    if request.url.path.startswith("/panel"):
        resp.headers["Cache-Control"] = "no-cache"
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

# Console operativa (admin UI) servita same-origin dal backend stesso, così le
# chiamate ad /admin/* usano l'ADMIN_TOKEN senza problemi di CORS. Montata su
# /panel (NON /admin, per non oscurare le rotte API /admin/*). Lo shell HTML non
# contiene segreti: il token si inserisce nell'interfaccia e resta nel browser.
# → https://<dominio>/panel/
app.mount("/panel", StaticFiles(directory="panel", html=True), name="panel")


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


def _tenant_code(tenant: dict) -> str:
    """Codice tenant da passare a Divina per la sua RLS (ponte agenti). Preferisce
    branding.tenant_code (esplicito), altrimenti il primo allowed_scope (livello
    tenant). Vuoto = niente instradamento (il ponte resta inerte). SICUREZZA: è l'UNICA
    informazione di scope passata a Divina; i grant/il filtro Qdrant del RAG non cambiano."""
    brand = tenant.get("branding") or {}
    code = str(brand.get("tenant_code") or "").strip()
    if code:
        return code
    scopes = tenant.get("allowed_scopes") or []
    return scopes[0] if scopes else ""


def _agent_response(routed: dict, grants: dict) -> dict:
    """Shape di /chat quando si instrada a un agente Divina: l'output dell'agente come
    `answer`, e in `sources` una voce di tipo `agent` (agente/skill/confidenza) seguita
    dalle eventuali `web_sources` di Divina. `scopes` = quelli del tenant, per parità di
    shape col RAG (nessun ampliamento: restano i grant del tenant)."""
    sources: list = [{"type": "agent",
                      "agent": routed.get("agent"),
                      "skill": routed.get("skill"),
                      "confidence": routed.get("confidence")}]
    web = routed.get("web_sources")
    if isinstance(web, list):
        sources.extend(web)
    return {"answer": routed.get("output") or "",
            "sources": sources,
            "scopes": rag.scopes_of(grants)}


class ChatIn(BaseModel):
    message: str
    stream: bool = False  # true → risposta SSE (text/event-stream) token per token
    history: list = []     # turni precedenti [{role, content}] dal client, per i follow-up
    lang: str = ""         # "it" | "en" — se vuota: branding del tenant → default_lang
    web: bool = False      # richiesta esplicita di ricerca web (agente); effettiva solo se
    #                        la capability web è abilitata (WEB_SEARCH o branding.web_search)
    agent: bool = False    # richiesta esplicita di instradare a un agente Divina (COMPITO);
    #                        effettiva solo col ponte attivo (AGENTS_BRIDGE + DIVINA_URL/token)
    companion: str = ""    # companion scelto ESPLICITAMENTE (selettore console):
    #                        dante/virgilio/beatrice → implica agent:true e Divina smista
    #                        tra le skill di QUEL companion. Valore ignoto → ignorato.


class SearchIn(BaseModel):
    message: str
    k: int = 6


class IngestIn(BaseModel):
    # Re-ingest INCREMENTALE: se valorizzato, re-indicizza SOLO queste note (path
    # relativi al vault, es. "forma/clienti/ats/kb-ats.md"). Vuoto/assente → ingest
    # completo (comportamento storico, retro-compatibile col dispatch vault-updated).
    paths: list[str] | None = None


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
        "title": brand.get("title", tenant.get("name", "Divina · Assistente")),
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
def do_ingest(body: IngestIn | None = None, authorization: str = Header(default="")):
    """Indicizza il cervello. Body vuoto → ingest COMPLETO (storico). Con
    {"paths": [...]} → re-ingest INCREMENTALE solo di quelle note (realtime:
    aggiorna il cervello man mano senza reindicizzare tutto)."""
    _require_admin(authorization)
    try:
        if body and body.paths:
            return ingest.reindex_paths(body.paths)
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
    # Tier/archetipo OVYON (dante/virgilio/beatrice) dal branding del tenant.
    # SICUREZZA: il tier modula SOLO lo stile della risposta (vedi rag.style_directive);
    # NON entra nei grant e NON tocca il filtro Qdrant → lo scope dei dati resta identico.
    tier = (tenant.get("branding") or {}).get("tier")
    # Capability ricerca web (OPT-IN, OFF di default): abilitata se WEB_SEARCH globale
    # OPPURE branding.web_search del tenant. SICUREZZA: è ADDITIVA — non tocca i grant né
    # il filtro Qdrant (lo scope del vault resta identico), e il contenuto web è trattato
    # come dato non fidato in rag. Con capability OFF /chat è identico a oggi (nessuna
    # chiamata web, nessun costo). Inerte comunque senza TAVILY_API_KEY (websearch.search).
    web_enabled = settings.web_search or bool((tenant.get("branding") or {}).get("web_search"))
    log.info("chat tenant=%s q=%r", tenant.get("name", "?"), security.redact_pii(body.message)[:200])
    # Ponte agenti Divina (OPT-IN, OFF di default). Se la richiesta è un COMPITO — flag
    # esplicito agent:true, oppure euristico task-like con AGENTS_AUTO — e il ponte è
    # attivo e configurato, si instrada all'agente Divina giusto invece del RAG.
    # SICUREZZA: a Divina passa SOLO il tenant_code (lo scope lo applica Divina con la sua
    # RLS); i grant/il filtro Qdrant del RAG NON cambiano. Con ponte OFF o senza config il
    # blocco è saltato → /chat identico a oggi. Fallback pulito al RAG se Divina è inerte,
    # irraggiungibile o non instrada (routed:false) → mai un errore secco.
    # Companion scelto esplicitamente dal selettore in console: implica l'instradamento
    # agli agenti; un valore ignoto è ignorato (fail-open verso lo smistamento auto).
    companion = (body.companion or "").strip().lower()
    if companion not in ("dante", "virgilio", "beatrice"):
        companion = ""
    want_agent = bool(companion) or body.agent \
        or (settings.agents_auto and agents_bridge.is_task_like(body.message))
    if want_agent and agents_bridge.enabled():
        routed = agents_bridge.route(_tenant_code(tenant), body.message, body.history,
                                     agent=companion or None)
        if routed and routed.get("routed"):
            return _agent_response(routed, _grants(tenant))
        # Divina inerte/irraggiungibile o non ha instradato → si prosegue col RAG.
    if body.stream:
        try:
            gen = rag.answer_stream(body.message, _grants(tenant), history=body.history,
                                    lang=lang, tier=tier, web=body.web, web_enabled=web_enabled)
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
        return rag.answer(body.message, _grants(tenant), history=body.history, lang=lang,
                          tier=tier, web=body.web, web_enabled=web_enabled)
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
    """Bearer ADMIN_TOKEN con confronto timing-safe. FAIL-CLOSED: token non
    configurato o debole/placeholder → 503 (gli admin non si aprono mai per un
    errore di config); token errato → 401. Copre lettura E scrittura di tutti
    gli /admin/* (fix sicurezza, collaudo 17-07)."""
    tok = (settings.admin_token or "").strip()
    if not tok or tok.lower() in _WEAK_ADMIN_TOKENS:
        raise HTTPException(503, "ADMIN_TOKEN assente o debole: endpoint admin "
                                 "disabilitati finché non viene impostato un token forte.")
    if not secrets.compare_digest(authorization or "", f"Bearer {tok}"):
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


@app.get("/admin/roadmap")
def admin_roadmap(authorization: str = Header(default="")):
    """Roadmap del cervello verso la console "AI Operating System" (benchmark:
    Zoey OS): task curate con priorità, stato e aggancio all'architettura.
    Statica e versionata nel repo (app/roadmap.py): si aggiorna con una PR.
    Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    return roadmap.roadmap()


@app.get("/admin/brain")
def admin_brain(authorization: str = Header(default="")):
    """Il cervello vivo in console: KPI del vault (note, aree, ultimi 7 giorni,
    ultima ingest, dettaglio per area) + note più recenti, dai metadati che
    l'ingest sincronizza su Supabase (`documents`). Bearer ADMIN_TOKEN.
    `persist:false` (e dati vuoti) se il backend non è configurato."""
    _require_admin(authorization)
    return {"persist": brain.enabled(), "stats": brain.stats(),
            "recent": brain.notes(limit=10)}


@app.get("/admin/brain/graph")
def admin_brain_graph(authorization: str = Header(default="")):
    """Il grafo REALE del cervello: nodi = note, sinapsi = [[link]] tra note,
    ricostruito a ogni ingest completa (persistito su Supabase, db/ovyon_graph.sql).
    404 finché non è stata eseguita almeno una ingest. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    g = brain.graph()
    if not g:
        raise HTTPException(404, "Grafo non ancora generato: lancia una ingest completa.")
    return {"persist": brain.enabled(), **g}


@app.get("/admin/brain/notes")
def admin_brain_notes(q: str = "", limit: int = 50, authorization: str = Header(default="")):
    """Esploratore note del cervello (l'ex ⌘K del vecchio pannello): ricerca sui
    metadati (titolo/slug/path) o, senza query, le più recenti. Bearer ADMIN_TOKEN.
    La ricerca semantica sul CONTENUTO resta su POST /search (per-tenant)."""
    _require_admin(authorization)
    return {"notes": brain.notes(q, limit), "persist": brain.enabled()}


class TaskIn(BaseModel):
    title: str
    scope: str = ""
    note: str = ""
    kind: str = "manuale"        # manuale | gap | feedback | agente | azione
    status: str = "aperta"       # aperta | in-approvazione (azioni da approvare)
    idempotency_key: str = ""    # anti-duplicazione per le azioni (Z3)


class TaskCloseIn(BaseModel):
    id: str
    by: str                    # nome dell'UMANO che chiude (obbligatorio, come resolved_by)
    status: str = "fatta"      # fatta | archiviata


class TaskTransitionIn(BaseModel):
    id: str
    to: str                    # in-approvazione | approvata | in-esecuzione | fatta | fallita | archiviata
    by: str = ""               # obbligatorio per approvata/fatta/archiviata (decide un umano)
    error: str = ""            # per 'fallita'


@app.get("/admin/tasks")
def admin_tasks(limit: int = 100, status: str = "", authorization: str = Header(default="")):
    """Coda task PERSISTENTE del cervello (brain_tasks; fallback in-memory se
    Supabase è off — `persist` lo dice). Di default le ATTIVE (aperta,
    in-approvazione, approvata, in-esecuzione); con `status` filtra uno stato.
    Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    return {"tasks": braintasks.list_open(limit, status), "persist": braintasks.enabled()}


@app.post("/admin/tasks")
def admin_tasks_create(body: TaskIn, authorization: str = Header(default="")):
    """Crea una task operativa del cervello. Le AZIONI con effetto esterno nascono
    'in-approvazione' e non partono mai senza l'ok dell'owner (Z2). Titolo già
    redatto (niente PII). Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    t = braintasks.add(body.title, scope=body.scope, note=body.note, kind=body.kind,
                       status=body.status, idempotency_key=body.idempotency_key)
    if t is None:
        raise HTTPException(422, "Titolo obbligatorio e status iniziale valido "
                                 "(aperta | in-approvazione).")
    return {"ok": True, "task": t}


class TaskClaimIn(BaseModel):
    worker: str = ""           # nome del worker (per l'audit/regia)
    kind: str = ""             # es. 'azione' = solo payload strutturati eseguibili


@app.post("/admin/tasks/claim")
def admin_tasks_claim(body: TaskClaimIn, authorization: str = Header(default="")):
    """Z3: claim ATOMICO della prossima azione approvata (approvata →
    in-esecuzione, FOR UPDATE SKIP LOCKED su Supabase: mai doppioni tra worker
    concorrenti). Con kind='azione' il worker prende SOLO i payload strutturati
    (le proposte a esecuzione umana, kind 'agente', restano fuori).
    {"task": null} se non c'è nulla da eseguire. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    return {"task": braintasks.claim_next(body.worker, body.kind)}


@app.post("/admin/tasks/transition")
def admin_tasks_transition(body: TaskTransitionIn, authorization: str = Header(default="")):
    """Muove una task nella macchina a stati (Z2): approvata/fatta/archiviata
    richiedono `by` (decide un umano — mai automatico); 'fallita' registra
    l'errore. Transizioni fuori catalogo → 422. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    ok = braintasks.transition(body.id, body.to, by=body.by, error=body.error)
    if not ok:
        raise HTTPException(422, "Transizione non valida (stato di partenza, "
                                 "nome mancante o task inesistente).")
    return {"ok": True}


@app.post("/admin/tasks/close")
def admin_tasks_close(body: TaskCloseIn, authorization: str = Header(default="")):
    """Chiude una task ('fatta' | 'archiviata') col nome di chi decide: mai DELETE,
    chiude solo un umano — come le contraddizioni. Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    if not body.by.strip():
        raise HTTPException(422, "Indica chi chiude la task (by).")
    if body.status not in braintasks.CLOSE_STATUSES:
        raise HTTPException(422, "status deve essere 'fatta' o 'archiviata'.")
    ok = braintasks.close(body.id, body.by, body.status)
    if not ok:
        raise HTTPException(404, "Task non trovata o già chiusa.")
    return {"ok": True}


class ProposalIn(BaseModel):
    id: str


@app.get("/admin/proposals")
def admin_proposals(authorization: str = Header(default="")):
    """Proposte di auto-miglioramento (audit → owner). SEZIONE PRIVATA: solo
    Bearer ADMIN_TOKEN (owner) — mai chiave tenant, mai esposta per-tenant.
    Derivate dai segnali correnti (gap/👎/stato sistema), si rigenerano a ogni
    lettura; l'approvazione le trasforma in task della coda brain_tasks."""
    _require_admin(authorization)
    return {"proposals": proposals.generate()}


@app.post("/admin/proposals/approve")
def admin_proposals_approve(body: ProposalIn, authorization: str = Header(default="")):
    """L'owner approva una proposta → nasce una task operativa (brain_tasks).
    Niente è automatico: senza approvazione esplicita non si crea nulla."""
    _require_admin(authorization)
    t = proposals.approve(body.id)
    if t is None:
        raise HTTPException(404, "Proposta non trovata: ricarica la lista.")
    return {"ok": True, "task": t}


@app.post("/admin/proposals/dismiss")
def admin_proposals_dismiss(body: ProposalIn, authorization: str = Header(default="")):
    """L'owner ignora una proposta (non ricompare finché il processo vive)."""
    _require_admin(authorization)
    proposals.dismiss(body.id)
    return {"ok": True}


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
def retention_run(days: int = 0, dry_run: bool = False, authorization: str = Header(default="")):
    """GDPR retention: cancella gli eventi analytics oltre la soglia. Senza `days`
    usa RETENTION_DAYS. Con `dry_run=true` NON cancella: restituisce solo quante
    righe verrebbero eliminate (anteprima). Da richiamare a mano o da un cron.
    Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    if dry_run:
        return {"dry_run": True, "would_delete": events.preview_old(days or None),
                "retention_days": settings.retention_days}
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
    return {"name": "Divina", "version": settings.app_version, "commit": settings.git_sha[:12]}


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
        # Realtime (opt-in): re-indicizza SUBITO la nota appena scritta, così il cervello
        # la riflette man mano. Best-effort: un errore qui non deve far fallire il write-back.
        if settings.auto_reingest and res.get("path"):
            try:
                res["reingest"] = ingest.reindex_paths([res["path"]], sync=False)
            except Exception:
                log.exception("auto-reingest post write-back fallito (ignorato)")
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


class UploadConfirmIn(BaseModel):
    fields: dict
    cliente: str = "ats"
    vault: bool = True      # scrivi la nota contratto nel vault (se VAULT_PATH c'è)
    notion: bool = True     # inserisci la riga nel database Notion (se token c'è)


@app.post("/upload/confirm")
def upload_confirm(body: UploadConfirmIn, x_tenant_key: str = Header(default=""),
                   origin: str = Header(default="")):
    """Consolida un contratto DOPO la conferma umana dei campi (regola 5): scrive la
    nota nel vault (cartella privata del cliente) e/o la riga nel database Notion.
    Blocca gli errori formali (CF a 16 caratteri, campi obbligatori). Lo scope di
    destinazione (cliente) deve essere tra quelli concessi al tenant."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    grants = _grants(tenant)
    ctx = rag.list_context(grants)
    if not ctx["master"] and body.cliente not in (ctx["allowed_tenants"] or []):
        raise HTTPException(403, "Scope di destinazione non consentito per questo tenant.")
    fields = dict(body.fields or {})
    fields["codice_fiscale"] = (fields.get("codice_fiscale") or "").strip().upper()
    problems = extract.validate_unilav(fields)
    if problems:
        raise HTTPException(422, "Campi non validi: " + "; ".join(problems))
    out = {"vault": {"status": "skipped"}, "notion": {"status": "skipped"}}
    if body.vault:
        if not settings.vault_path.strip():
            out["vault"] = {"status": "skipped",
                            "reason": "VAULT_PATH non configurato su questo deploy"}
        else:
            try:
                path = writeback.save_contract_note(fields, cliente=body.cliente)
                out["vault"] = {"status": "ok", "path": path}
                fields.setdefault("slug", Path(path).stem)
            except Exception:
                log.exception("write-back vault fallito")
                out["vault"] = {"status": "error", "reason": "scrittura nel vault fallita"}
    if body.notion:
        out["notion"] = writeback.notion_upsert(fields)
    consolidato = out["vault"].get("status") == "ok" or out["notion"].get("status") == "ok"
    if consolidato:
        tenants.log_access(tenant.get("key_hash"), "create", tenant_code=body.cliente,
                           detail=f"upload/confirm {out['vault'].get('path', '')}".strip())
    return {"consolidato": consolidato, **out}


class ContractIn(BaseModel):
    template: str
    data: dict = {}


@app.get("/contracts/templates")
def contracts_templates(x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """Catalogo dei template contratto (id, titolo, campi con obbligatorietà)."""
    _guard(tenant_or_401(x_tenant_key), x_tenant_key, origin)
    return {"templates": contracts.list_templates()}


@app.post("/contracts/fill")
def contracts_fill(body: ContractIn, x_tenant_key: str = Header(default=""),
                   origin: str = Header(default="")):
    """Merge dei dati persona nel template scelto → TESTO del contratto da rivedere
    (conferma umana) + elenco dei campi obbligatori ancora mancanti."""
    _guard(tenant_or_401(x_tenant_key), x_tenant_key, origin)
    try:
        return contracts.fill(body.template, body.data)
    except KeyError:
        raise HTTPException(404, "Template sconosciuto. Vedi /contracts/templates.")


@app.post("/contracts/pdf")
def contracts_pdf(body: ContractIn, x_tenant_key: str = Header(default=""),
                  origin: str = Header(default="")):
    """Genera il PDF del contratto compilato. Rifiuta (422) se mancano campi
    obbligatori: prima si completa/conferma il testo con /contracts/fill.
    L'invio alla firma (e-sign) è un passo esterno."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    try:
        filled = contracts.fill(body.template, body.data)
    except KeyError:
        raise HTTPException(404, "Template sconosciuto. Vedi /contracts/templates.")
    if filled["missing"]:
        raise HTTPException(422, "Campi obbligatori mancanti: " + ", ".join(filled["missing"]))
    pdf = contracts.to_pdf(filled["text"], filled["titolo"])
    tenants.log_access(tenant.get("key_hash"), "create", detail=f"contracts/pdf {body.template}")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="contratto-{body.template}.pdf"'})


class SignIn(BaseModel):
    template: str
    data: dict = {}
    nome: str = ""
    ragione_sociale: str = ""
    company: str = ""          # alias EN di ragione_sociale
    email: str = ""


@app.post("/contracts/sign")
def contracts_sign(body: SignIn, request: Request, x_tenant_key: str = Header(default=""),
                   origin: str = Header(default="")):
    """Firma elettronica semplice (SES): il CLIENTE conferma l'accordo sul contratto.
    Rigenera il PDF del template compilato, ne calcola l'hash sha256 e produce un record
    di firma verificabile (chi/quando/cosa=hash/come=email·IP) + il PDF con il timbro di
    firma in coda (base64). Non è un write-back al vault; non logga PII (solo l'hash).
    Errore 422 se mancano nome/ragione_sociale o campi obbligatori del contratto."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    ragione = (body.ragione_sociale or body.company).strip()
    if not body.nome.strip() or not ragione:
        raise HTTPException(422, "Firma: 'nome' e 'ragione_sociale' sono obbligatori.")
    try:
        filled = contracts.fill(body.template, body.data)
    except KeyError:
        raise HTTPException(404, "Template sconosciuto. Vedi /contracts/templates.")
    if filled["missing"]:
        raise HTTPException(422, "Campi obbligatori mancanti: " + ", ".join(filled["missing"]))
    pdf = contracts.to_pdf(filled["text"], filled["titolo"])
    doc_hash = esign.pdf_hash(pdf)
    ip = request.client.host if request.client else ""
    try:
        record = esign.build_record(body.nome, ragione, doc_hash, email=body.email, ip=ip)
    except ValueError as e:
        raise HTTPException(422, str(e))
    signed_pdf = esign.stamp(filled["text"], record, filled["titolo"])
    # Audit senza PII: solo il template + l'impronta del documento (regola 6).
    tenants.log_access(tenant.get("key_hash"), "create",
                       detail=f"contracts/sign {body.template} sha256={doc_hash[:12]}")
    return {"signature": record,
            "pdf_sha256": doc_hash,
            "pdf_base64": base64.b64encode(signed_pdf).decode("ascii")}


# ── Accessi console CLIENTE, gestiti da FORMA (app/clientauth.py) ─────────────
# Modello: FORMA provisiona account + chiave tenant (server-side, mai al client);
# primo accesso email+password, poi SOLO codice a 6 cifre generato da FORMA.
# Sessione = cookie HttpOnly firmato (mai token in localStorage per i clienti).
_CLIENT_COOKIE = "dv_client"


class ClientLoginIn(BaseModel):
    email: str
    credential: str        # password al PRIMO accesso; poi il codice a 6 cifre


class ClientNewIn(BaseModel):
    email: str
    name: str = ""
    tenant_key: str        # resta server-side: il cliente non la vedrà mai
    password: str          # password del primo accesso (min 8)


class ClientIdIn(BaseModel):
    id: str


class ClientStatusIn(BaseModel):
    id: str
    status: str            # attivo | sospeso | rimosso (mai DELETE)


def _client_feature_on() -> None:
    """Fail-closed come gli /admin/*: senza segreto la feature non esiste."""
    if not clientauth.enabled():
        raise HTTPException(503, "Accessi cliente disabilitati: imposta CLIENT_SESSION_SECRET.")


def _client_session_or_401(request: Request) -> dict:
    _client_feature_on()
    sess = clientauth.check_session(request.cookies.get(_CLIENT_COOKIE, ""))
    if not sess:
        raise HTTPException(401, "Sessione cliente assente o scaduta.")
    return sess


def _set_client_cookie(response: Response, token: str, request: Request,
                       kind: str = "client") -> None:
    response.set_cookie(_CLIENT_COOKIE, token, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https",
                        max_age=clientauth.SESSION_TTL.get(kind, 3600), path="/")


@app.post("/client/login")
def client_login(body: ClientLoginIn, request: Request, response: Response):
    """Login del cliente. Un campo solo per le due fasi (password → codice);
    risposta identica per OGNI fallimento: niente oracoli su email/blocchi."""
    _client_feature_on()
    if not rate_ok("client-login:" + (body.email or "").strip().lower()):
        raise HTTPException(429, "Troppi tentativi. Riprova tra un minuto.",
                            headers={"Retry-After": "60"})
    acc = clientauth.login(body.email, body.credential)
    if not acc:
        raise HTTPException(401, "Credenziali non valide. Se l'accesso è bloccato, "
                                 "chiedi a FORMA un nuovo codice.")
    _set_client_cookie(response, clientauth.make_session(acc["id"]), request)
    tenants.log_access("client:" + acc["email"], "client-login")
    return {"ok": True, "account": acc}


@app.post("/client/logout")
def client_logout(response: Response):
    response.delete_cookie(_CLIENT_COOKIE, path="/")
    return {"ok": True}


@app.get("/client/me")
def client_me(request: Request):
    """Chi sono (per la console in modalità cliente). `kind` è 'ghost' quando
    dentro c'è FORMA: la console mostra il banner di cortesia."""
    sess = _client_session_or_401(request)
    return {"account": sess["account"], "kind": sess["kind"]}


class ClientChatIn(BaseModel):
    message: str
    history: list = []
    lang: str = ""
    agent: bool = False
    companion: str = ""


@app.post("/client/chat")
def client_chat(body: ClientChatIn, request: Request,
                origin: str = Header(default="")):
    """Chat del cliente autenticato: la chiave tenant è recuperata SERVER-SIDE
    (il browser non la conosce). Riusa il flusso COMPLETO di /chat: quote,
    rate limit, guardie origin/master, ponte agenti — nessuna scorciatoia."""
    sess = _client_session_or_401(request)
    try:
        key = clientauth.tenant_key_of(sess["account"]["id"])
    except KeyError:
        raise HTTPException(401, "Accesso cliente non più valido.")
    chat_body = ChatIn(message=body.message, history=body.history, lang=body.lang,
                       agent=body.agent, companion=body.companion)
    return do_chat(chat_body, x_tenant_key=key, origin=origin)


@app.get("/admin/clients")
def admin_clients(authorization: str = Header(default="")):
    """Elenco accessi cliente per il pannello FORMA — mai segreti né chiavi."""
    _require_admin(authorization)
    _client_feature_on()
    return {"clients": clientauth.list_accounts()}


@app.post("/admin/clients")
def admin_clients_new(body: ClientNewIn, authorization: str = Header(default="")):
    """FORMA crea l'accesso: email + nome + chiave tenant (server-side) +
    password del primo accesso. La chiave master è rifiutata."""
    _require_admin(authorization)
    _client_feature_on()
    try:
        acc = clientauth.create(body.email, body.name, body.tenant_key, body.password)
    except ValueError as e:
        raise HTTPException(422, str(e))
    tenants.log_access("client:" + acc["email"], "client-create")
    return {"ok": True, "account": acc}


@app.post("/admin/clients/pin")
def admin_clients_pin(body: ClientIdIn, authorization: str = Header(default="")):
    """Genera/RIGENERA il codice a 6 cifre — SOLO FORMA. Il codice appare UNA
    volta qui e non è recuperabile dopo: si rigenera. Sblocca anche l'account."""
    _require_admin(authorization)
    _client_feature_on()
    try:
        code = clientauth.set_pin(body.id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "code": code}


@app.post("/admin/clients/status")
def admin_clients_status(body: ClientStatusIn, authorization: str = Header(default="")):
    """Attiva/sospendi/rimuovi (status, mai DELETE). La sospensione taglia
    fuori anche le sessioni già emesse (check ad ogni richiesta)."""
    _require_admin(authorization)
    _client_feature_on()
    try:
        acc = clientauth.set_status(body.id, body.status)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "account": acc}


@app.post("/admin/clients/ghost")
def admin_clients_ghost(body: ClientIdIn, request: Request, response: Response,
                        authorization: str = Header(default="")):
    """FORMA entra nel pannello del cliente: sessione GHOST breve (30 min) con
    la STESSA vista del cliente, tracciata nell'audit. Dopo, aprire /panel/."""
    _require_admin(authorization)
    _client_feature_on()
    try:
        clientauth.tenant_key_of(body.id)          # esiste? (KeyError se no)
    except KeyError as e:
        raise HTTPException(404, str(e))
    _set_client_cookie(response, clientauth.make_session(body.id, "ghost"),
                       request, "ghost")
    tenants.log_access("admin", "client-ghost", detail=f"account={body.id}")
    return {"ok": True}
