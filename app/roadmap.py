"""Roadmap del cervello — le task che portano Divina a essere un "AI Operating System".

Benchmark di prodotto: Zoey OS (zoeyos.com) — un "personal AI operating system"
con companion persistenti, memoria che si accumula conversazione dopo
conversazione, voce continua, skill che eseguono interi workflow, task
programmati e 1.000+ integrazioni. Qui ogni capacità di Zoey è tradotta in una
task concreta sull'architettura Divina (motore + orchestratore), con priorità,
stato e aggancio ai file/tabelle già esistenti.

A differenza delle task di apprendimento (metrics.py, generate a runtime dai
gap e dai 👎), questa roadmap è STATICA e versionata nel repo: si aggiorna con
una PR, così ogni cambiamento di rotta resta tracciato. Esposta su
GET /admin/roadmap e mostrata nella tab "Roadmap" della console /panel/.
Analisi completa del confronto: docs/confronto-divina-zoey.md.
"""

BENCHMARK = {
    "name": "Zoey OS",
    "url": "https://zoeyos.com/what-is-zoey-os/",
    "summary": ("Team di companion AI persistenti (fino a ~20, con ruolo/personalità/"
                "tool definiti dall'utente), memoria che si accumula, voce+testo in "
                "un'unica conversazione, workspace visivo col dispatch in tempo reale, "
                "skill che eseguono interi workflow, 1.000+ integrazioni. Piani: "
                "Explorer $45 · Builder $90 · Architect $170 · BYO Architect $109/mese."),
}

# Dove Divina è GIÀ avanti rispetto a quanto Zoey dichiara: sono i pilastri da
# proteggere mentre si colmano i gap (mai barattarli per una feature).
STRENGTHS = [
    "RAG su cervello proprietario (vault Obsidian) con fonti citate",
    "Scope server-side sul retrieval: il permesso è un filtro Qdrant, non un prompt",
    "Multi-tenancy reale con RLS Postgres e audit su ogni azione",
    "Contraddizioni mai auto-risolte: chiude solo un umano",
    "Nessun DELETE: si archivia sempre",
    "Write-back nel vault solo dopo conferma umana",
    "GDPR: region UE, retention configurabile, quote e costi per tenant",
]

# priority: alta|media|bassa · status: da-fare|parziale|in-corso|fatto ·
# effort: S|M|L · repo: motore|orchestratore|entrambi
TASKS = [
    # ── memoria ──────────────────────────────────────────────────────────
    {"id": "memoria-persistente", "area": "memoria", "priority": "alta",
     "status": "parziale", "effort": "M", "repo": "entrambi",
     "title": "Memoria che si accumula (per tenant)",
     "description": ("Ogni conversazione deve costruire sulla precedente: salvare "
                     "riassunti episodici per tenant/utente e richiamarli nel "
                     "contesto della chat, così Divina non riparte mai da zero."),
     "zoey_ref": ("«Every conversation builds on the last» — il contesto si "
                  "accumula invece di azzerarsi, e i companion si affinano nel tempo."),
     "divina_note": ("Lato orchestratore esiste già agent_memory (db/003); manca la "
                     "memoria episodica delle chat del motore: nuova tabella RLS + "
                     "richiamo dei ricordi pertinenti in rag.py.")},
    {"id": "preferenze-apprese", "area": "memoria", "priority": "media",
     "status": "da-fare", "effort": "S", "repo": "motore",
     "title": "Preferenze apprese, non dichiarate",
     "description": ("Registrare come l'utente lavora (tono, formato, lingua, temi "
                     "ricorrenti) e adattare le risposte senza doverlo ripetere."),
     "zoey_ref": "«Zoey and your companions adapt to you over time.»",
     "divina_note": ("Il jsonb branding dei tenant già pilota lo stile (tier_style); "
                     "estenderlo con preferenze per utente aggiornate dai feedback 👍/👎.")},

    # ── companions ───────────────────────────────────────────────────────
    {"id": "companion-personalizzati", "area": "companions", "priority": "alta",
     "status": "da-fare", "effort": "L", "repo": "orchestratore",
     "title": "Companion personalizzati per tenant",
     "description": ("Oltre a Dante/Virgilio/Beatrice, permettere al cliente di "
                     "definire nuovi agenti con ruolo, personalità, skill e strumenti "
                     "consentiti — il suo team AI su misura."),
     "zoey_ref": ("Fino a ~20 companion per world: «you define their role, their "
                  "personality, their skills, and the tools they're allowed to act on»."),
     "divina_note": ("Le tabelle agents/skills esistono già nello schema Divina: "
                     "servono CRUD via API + editor nel pannello. Regola tassativa: "
                     "il tier non amplia MAI lo scope dei dati.")},
    {"id": "chat-regista", "area": "companions", "priority": "alta",
     "status": "parziale", "effort": "M", "repo": "entrambi",
     "title": "Divina regista: un solo punto d'ingresso",
     "description": ("La chat della console capisce da sola quando una richiesta è "
                     "una task operativa e la smista all'agente giusto, mostrando "
                     "in chat chi se ne occupa e con quale esito."),
     "zoey_ref": ("«Tell Zoey what you need. She understands the intent and "
                  "decides who handles it.»"),
     "divina_note": ("agents_bridge.py già riconosce i messaggi «task-like» e chiama "
                     "/agents/route: completare il giro con esito visibile in chat "
                     "e fallback esplicito quando la confidenza è bassa.")},

    # ── automazioni ──────────────────────────────────────────────────────
    {"id": "coda-task-persistente", "area": "automazioni", "priority": "alta",
     "status": "da-fare", "effort": "M", "repo": "entrambi",
     "title": "Coda task persistente del cervello",
     "description": ("Oggi le task di apprendimento sono in-memory e si azzerano al "
                     "redeploy. Serve una tabella tasks con stato (aperta/in-corso/"
                     "fatta), origine (gap, 👎, manuale, agente) e assegnatario "
                     "(umano o companion)."),
     "zoey_ref": ("«Every task, companion, and action in one place» — il task "
                  "tracking è il cuore del workspace di Zoey."),
     "divina_note": ("Migrazione additiva sul modello di contradictions "
                     "(001_divina_schema.sql: RLS ovyon.can_read + trigger touch_"
                     "updated_at); endpoint GET/POST /admin/tasks accanto a "
                     "/admin/learning.")},
    {"id": "skill-workflow", "area": "automazioni", "priority": "media",
     "status": "da-fare", "effort": "L", "repo": "orchestratore",
     "title": "Skill = interi workflow (playbook)",
     "description": ("Una skill deve poter concatenare più passi (ricerca → bozza → "
                     "aggiorna gestionale → prepara invio) mantenendo la conferma "
                     "umana sui passi critici."),
     "zoey_ref": ("«Give a companion a skill and it runs the whole workflow — send "
                  "the email, update the CRM, book the meeting.»"),
     "divina_note": ("pipeline.py concatena già 3 skill nell'ingest (Ricercatore → "
                     "Ingest → Cross-referencer): generalizzare in playbook "
                     "dichiarativi riusabili dalle skill di business.")},
    {"id": "task-programmati", "area": "automazioni", "priority": "media",
     "status": "parziale", "effort": "M", "repo": "orchestratore",
     "title": "Task programmati per tenant",
     "description": ("Schedulare task ricorrenti dal pannello (rassegna fonti ogni "
                     "mattina, solleciti ogni lunedì, report mensile) con esiti "
                     "tracciati e notificati."),
     "zoey_ref": "«Scheduling, task tracking, and workflow automation» integrati.",
     "divina_note": ("Oggi esiste solo nightly_learning.py su GitHub Actions: serve "
                     "uno scheduler applicativo per tenant, con audit su ogni run.")},

    # ── integrazioni ─────────────────────────────────────────────────────
    {"id": "connettori-azioni", "area": "integrazioni", "priority": "alta",
     "status": "parziale", "effort": "L", "repo": "orchestratore",
     "title": "Connettori che eseguono azioni reali",
     "description": ("I companion non devono solo rispondere: eseguono (email, "
                     "calendario, Notion, Slack, Drive) con conferma umana sulle "
                     "azioni verso l'esterno."),
     "zoey_ref": ("«Connected to the platforms your work already lives in, they "
                  "carry out real actions» — 1.000+ integrazioni."),
     "divina_note": ("Fase 5 già in design (docs/fase5-connettori-realtime.md); "
                     "client_connectors + webhook esistono, il connettore MCP ha 5 "
                     "tool. Priorità: Gmail/Calendar/Notion, e write-back Notion "
                     "già in roadmap (Fase 2b).")},
    {"id": "mcp-marketplace", "area": "integrazioni", "priority": "bassa",
     "status": "da-fare", "effort": "M", "repo": "orchestratore",
     "title": "Catalogo connettori nel pannello",
     "description": ("Una pagina della console dove attivare/disattivare i "
                     "connettori del tenant e vedere lo stato dei sync, senza "
                     "toccare configurazioni a mano."),
     "zoey_ref": "Le integrazioni in Zoey si attivano dall'interfaccia, per companion.",
     "divina_note": ("La tab Documenti ha già il bottone «Sync connettori»: "
                     "promuoverlo a vista dedicata sopra client_connectors.")},

    # ── voce ─────────────────────────────────────────────────────────────
    {"id": "voce-continua", "area": "voce", "priority": "media",
     "status": "parziale", "effort": "M", "repo": "motore",
     "title": "Voce e testo in un'unica conversazione",
     "description": ("Parlare con Divina nella console e passare da voce a testo "
                     "senza interrompere il filo (STT + TTS in streaming)."),
     "zoey_ref": ("«Switch between voice and text anytime in one continuous "
                  "conversation» — Zoey è voice-first."),
     "divina_note": ("Il provider voce è già previsto (voice_provider in "
                     "/admin/status, app/voice.py): manca il round-trip completo "
                     "nella chat della console e nel widget.")},

    # ── workspace ────────────────────────────────────────────────────────
    {"id": "dispatch-live", "area": "workspace", "priority": "media",
     "status": "da-fare", "effort": "M", "repo": "orchestratore",
     "title": "Regia live: vedere il lavoro accadere",
     "description": ("Una vista «regia» nella console che mostra in tempo reale "
                     "richiesta → agente scelto → skill → esito, mentre succede."),
     "zoey_ref": ("«She fires a task to the right companion. You see the dispatch "
                  "happen in real time» (nel workspace 3D)."),
     "divina_note": ("/agents/route già decide agente+skill; aggiungere lo streaming "
                     "di stato (il motore fa già SSE su /chat). Niente 3D: prima "
                     "la sostanza, poi la scena.")},
    {"id": "console-quotidiana", "area": "workspace", "priority": "bassa",
     "status": "da-fare", "effort": "S", "repo": "entrambi",
     "title": "Console come workspace quotidiano",
     "description": ("Far vivere l'utente nella console: notifiche sugli esiti dei "
                     "task, badge e contatori live, scorciatoie — l'equivalente "
                     "sobrio del «world» di Zoey."),
     "zoey_ref": ("«A living workspace where you and your companions build "
                  "together», senza perdersi nei tab."),
     "divina_note": ("La SPA /panel/ è già il punto unico delle due facce: "
                     "aggiungere refresh dei badge e notifiche (toast → web push).")},

    # ── business ─────────────────────────────────────────────────────────
    {"id": "multi-utente", "area": "business", "priority": "media",
     "status": "da-fare", "effort": "L", "repo": "motore",
     "title": "Più utenti per tenant (seat e ruoli)",
     "description": ("Ogni membro del team del cliente ha il suo accesso con ruolo "
                     "(admin/operatore), sulla conoscenza condivisa del tenant."),
     "zoey_ref": ("Business: «every team member gets their own world, shared "
                  "knowledge stays connected, admins control who sees what»."),
     "divina_note": ("Oggi una chiave = un tenant: aggiungere i seat sopra api_keys "
                     "(Supabase). RLS, audit e cifratura ci sono già — su questo "
                     "siamo avanti a Zoey, non indietro.")},
    {"id": "listino-tier", "area": "business", "priority": "bassa",
     "status": "parziale", "effort": "S", "repo": "motore",
     "title": "Listino a pacchetti + BYO key",
     "description": ("Pacchetti chiari sul modello Explorer/Builder/Architect e "
                     "opzione «porta la tua chiave» (Mistral/Anthropic) per i "
                     "clienti tecnici."),
     "zoey_ref": ("Explorer $45 · Builder $90 · Architect $170 · BYO Architect $109 "
                  "con chiave Anthropic propria."),
     "divina_note": ("I tier esistono già (starter/pro/enterprise nei template, "
                     "billing in Fase 4): aggiungere la chiave provider per-tenant "
                     "in providers.py/config, mai nel repo (regola 6).")},
]


def roadmap() -> dict:
    """Payload per GET /admin/roadmap: benchmark, punti di forza, task e conteggi.
    Sola lettura, nessuno stato: la fonte di verità è questo file."""
    aperte = sum(1 for t in TASKS if t["status"] in ("da-fare", "in-corso"))
    parziali = sum(1 for t in TASKS if t["status"] == "parziale")
    fatte = sum(1 for t in TASKS if t["status"] == "fatto")
    return {
        "benchmark": BENCHMARK,
        "strengths": STRENGTHS,
        "tasks": TASKS,
        "counts": {"totale": len(TASKS), "aperte": aperte,
                   "parziali": parziali, "fatte": fatte},
    }
