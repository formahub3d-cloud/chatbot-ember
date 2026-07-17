"""Configurazione del servizio Divina. Legge le variabili da .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # provider
    llm_provider: str = "mistral"      # "mistral" | "claude"
    embed_provider: str = "mistral"    # "mistral" (Claude non ha embeddings)

    # chiavi
    mistral_api_key: str = ""
    anthropic_api_key: str = ""

    # modelli
    mistral_llm_model: str = "mistral-small-latest"
    mistral_embed_model: str = "mistral-embed"
    claude_llm_model: str = "claude-haiku-4-5"

    # qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "cervello"

    # retrieval: meno rumore = risposte più precise + "non lo so" più onesti.
    # Recupera un pool di candidati, poi tiene solo i chunk vicini al migliore.
    retrieval_pool: int = 12          # candidati recuperati prima del filtro (>= k)
    retrieval_rel_score: float = 0.5  # tieni i chunk con score >= questa frazione del top (0 = off)
    retrieval_min_score: float = 0.0  # soglia assoluta minima di score (0 = off)
    retrieval_per_note: int = 3       # max chunk dalla stessa nota nel contesto (0 = off):
    #   evita che più pezzi quasi identici della stessa nota saturino il contesto,
    #   lasciando spazio ad altre note → risposte più complete (diversità stile MMR).

    # cervello
    vault_path: str = ""
    # auto-ingest da git (opzionale): se valorizzato, PRIMA di indicizzare il vault
    # viene aggiornato dal repo (git pull --ff-only se già clonato, altrimenti git
    # clone --depth 1). Serve su Railway, dove il vault non si aggiorna da solo: il
    # flusso repository_dispatch vault-updated → POST /ingest riporta le note fresche.
    # Vuoto = comportamento storico (legge la cartella locale VAULT_PATH così com'è).
    vault_git_url: str = ""
    # token per repo PRIVATO (iniettato nell'URL come x-access-token, MAI loggato).
    # Vuoto = repo pubblico. È un segreto: solo segnaposto in .env.example.
    vault_git_token: str = ""
    # Realtime: dopo un write-back confermato, re-indicizza SUBITO (incrementale) la
    # nota appena scritta → il cervello la riflette "man mano", senza attendere un
    # ingest completo. OFF di default (opt-in). Best-effort: un errore non blocca mai
    # il write-back. Non fa git pull (indicizza la copia locale appena scritta).
    auto_reingest: bool = False

    # sicurezza — NESSUN default: senza un ADMIN_TOKEN forte gli endpoint
    # /admin/* restano chiusi (503, fail-closed). Il vecchio default "change-me"
    # rendeva gli admin di fatto pubblici su un deploy non configurato
    # (fix sicurezza collaudo 17-07).
    admin_token: str = ""
    rate_limit_per_min: int = 30   # richieste/minuto per chiave tenant (0 = illimitato)
    max_message_chars: int = 2000  # lunghezza massima della domanda (anti-abuso/costi)
    security_headers: bool = True  # aggiunge header di sicurezza a ogni risposta

    # lingua di default delle risposte del bot ("it" | "en"). Un tenant può forzarla
    # col campo branding.lang; il client può passarla per richiesta.
    default_lang: str = "it"

    # ricerca web (capability agente, OPT-IN, OFF di default). Divina può cercare su
    # internet via Tavily oltre a rispondere dal cervello. Gating: WEB_SEARCH globale
    # OPPURE branding.web_search del singolo tenant. INERTE finché TAVILY_API_KEY è vuota
    # (nessuna chiamata, nessun costo) — vedi app/websearch.py. Con capability OFF /chat
    # è identico a oggi. Il contenuto web è DATO NON FIDATO (mai istruzioni).
    tavily_api_key: str = ""
    web_search: bool = False

    # ── Ponte agenti Divina (ovy-orchestrator) — capability OPT-IN, OFF di default ──
    # Quando la chat riceve un COMPITO (non semplice Q&A), Divina può instradarlo
    # all'agente Divina giusto (Dante/Virgilio/Beatrice) via POST {DIVINA_URL}/agents/route,
    # invece di rispondere col RAG. GATING (non negoziabile): il ponte opera SOLO se
    # AGENTS_BRIDGE=true E DIVINA_URL + DIVINA_ADMIN_TOKEN sono configurati. Con OFF o
    # senza config /chat è identico a oggi (RAG), nessuna chiamata a Divina. A Divina si
    # passa SOLO il tenant_code (lo scope lo applica Divina con la sua RLS): i grant e il
    # filtro Qdrant del RAG NON cambiano. Fallback pulito al RAG se Divina è
    # irraggiungibile o non instrada. Vedi app/agents_bridge.py.
    agents_bridge: bool = False
    # Euristico opzionale: con AGENTS_AUTO=true i messaggi "task-like" (verbo imperativo
    # tipo scrivi/analizza/prepara/genera/crea) vengono auto-instradati anche senza il
    # flag agent nel body. OFF di default → serve il flag esplicito agent:true.
    agents_auto: bool = False
    # Endpoint del servizio Divina e token admin (Bearer). DIVINA_ADMIN_TOKEN è un
    # SEGRETO: solo segnaposto in .env.example, valore reale nelle env di deploy.
    divina_url: str = ""
    divina_admin_token: str = ""

    # osservabilità errori (opzionale): Sentry. Vuoto = disattivato.
    sentry_dsn: str = ""
    sentry_env: str = ""

    # build info (esposti da GET /version): utili per verificare cosa è in produzione.
    app_version: str = "0.3.0"
    git_sha: str = ""

    # rate-limit condiviso tra repliche: se valorizzato, il limiter usa Redis
    # (finestra scorrevole su sorted-set) invece della memoria di processo.
    redis_url: str = ""            # es. redis://default:pwd@host:6379/0 (vuoto = in-memory)

    # analytics storiche: se True (e backend Supabase attivo), gli eventi
    # chat/gap/feedback vengono anche PERSISTITI su analytics_events (oltre ai
    # contatori in memoria). Off di default per non aggiungere latenza al pilota.
    analytics_persist: bool = False

    # retention GDPR: cancella gli eventi analytics più vecchi di N giorni quando si
    # lancia POST /admin/retention/run. 0 = nessuna cancellazione automatica.
    retention_days: int = 0

    # stima costi (opzionale): tariffa media per richiesta in € — token medi per
    # conversazione × prezzo del modello (vedi doc-chatbot-cervello). Usata SOLO per
    # mostrare una stima di spesa per tenant in /admin/usage. 0 = non mostrare i costi.
    cost_per_request_eur: float = 0.0
    # alert spike costi (opzionale): se la stima di spesa giornaliera di un tenant
    # supera questa soglia in €, /admin/usage logga un WARNING (+ Sentry se attivo)
    # e la segnala nel campo "alerts". 0 = disattivato.
    cost_alert_daily_eur: float = 0.0

    # billing Stripe (opzionale): checkout a livelli + webhook. Inerte finché
    # STRIPE_SECRET_KEY è vuota. Gli ID prezzo si creano nel dashboard Stripe.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    stripe_price_enterprise: str = ""
    stripe_success_url: str = ""
    stripe_cancel_url: str = ""

    # setup fee una tantum al checkout (INERTE di default). Con BILLING_SETUP_FEE=true
    # il checkout di un tier aggiunge, oltre al canone ricorrente, un price ONE-TIME
    # (risolto per lookup_key) come line item aggiuntivo. Flag off → checkout identico
    # a oggi (nessun addebito extra). I lookup_key NON sono segreti: sono etichette dei
    # prezzi gia' creati su Stripe (Prodotti → Prezzi), uno per tier.
    billing_setup_fee: bool = False
    stripe_setup_lookup_starter: str = "setup_starter_dante"
    stripe_setup_lookup_pro: str = "setup_business_virgilio"
    stripe_setup_lookup_enterprise: str = "setup_enterprise_beatrice"

    # cifratura contenuti a riposo (GDPR) — per la colonna documents.content_encrypted.
    # Vuoto = disattivata. Una o più chiavi Fernet separate da virgola (la prima cifra,
    # tutte decifrano → rotazione). Genera una chiave con:  python -m app.crypto
    content_enc_key: str = ""

    # voce (opzionale) — proxy STT/TTS con chiavi lato server, mai nel browser.
    # VOICE_PROVIDER vuoto = disabilitato: il widget usa la voce gratuita del browser.
    voice_provider: str = ""            # "" | "deepgram" | "elevenlabs"
    voice_lang: str = "it"              # lingua STT (ISO 639-1)
    deepgram_api_key: str = ""
    deepgram_tts_model: str = "aura-2-thalia-en"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""       # vuoto = voce di default (multilingua)
    elevenlabs_model: str = "eleven_flash_v2_5"   # multilingua, bassa latenza (~75ms)
    elevenlabs_stt_model: str = "scribe_v1"

    # tenant: in cloud (Railway) il file tenants.json non c'è (gitignored).
    # Se valorizzata, questa variabile contiene la mappa tenant come stringa JSON
    # e ha la precedenza sul file locale. Vedi load_tenants() in main.py.
    tenants_json: str = ""

    # CORS: domini autorizzati a chiamare l'API dal browser (widget).
    # "*" = tutti (comodo per il pilota). In produzione metti i domini reali separati
    # da virgola, es: "https://www.formahub.it,https://altuoservizio.it".
    cors_origins: str = "*"

    # database (opzionale): se valorizzato, le chiavi tenant si leggono da Postgres
    # invece che da TENANTS_JSON. Railway inietta DATABASE_URL quando colleghi un
    # database al servizio. Vuoto = si usa TENANTS_JSON / tenants.json.
    database_url: str = ""

    # MongoDB (opzionale, consigliato in produzione): store tenant robusto con
    # chiavi HASHATE (mai in chiaro), quote giornaliere e revoca (campo active).
    # Ha la precedenza su Postgres/statico quando MONGO_URI è valorizzata.
    mongo_uri: str = ""
    mongo_db: str = "ember"
    tenants_collection: str = "tenants"
    usage_collection: str = "tenant_usage"

    # backend dei grant (opzionale): "supabase" = risolvi le chiavi dalla tabella
    # api_keys dello schema OVYON (db/ovyon_schema.sql), con grant a tre livelli
    # (allowed_orgs/tenants/sub_tenants) e audit su access_logs. Richiede DATABASE_URL.
    # Vuoto = comportamento storico (Mongo / Postgres-tenants / statico).
    grants_backend: str = ""

    # notion (write-back contratti) — inerte finché non compili questi campi
    notion_token: str = ""
    notion_contracts_db: str = ""


settings = Settings()
