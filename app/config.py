"""Configurazione del servizio Ember. Legge le variabili da .env."""
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

    # sicurezza
    admin_token: str = "change-me"
    rate_limit_per_min: int = 30   # richieste/minuto per chiave tenant (0 = illimitato)
    max_message_chars: int = 2000  # lunghezza massima della domanda (anti-abuso/costi)
    security_headers: bool = True  # aggiunge header di sicurezza a ogni risposta

    # rate-limit condiviso tra repliche: se valorizzato, il limiter usa Redis
    # (finestra scorrevole su sorted-set) invece della memoria di processo.
    redis_url: str = ""            # es. redis://default:pwd@host:6379/0 (vuoto = in-memory)

    # analytics storiche: se True (e backend Supabase attivo), gli eventi
    # chat/gap/feedback vengono anche PERSISTITI su analytics_events (oltre ai
    # contatori in memoria). Off di default per non aggiungere latenza al pilota.
    analytics_persist: bool = False

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
