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
     "status": "in-corso", "effort": "M", "repo": "entrambi",
     "title": "Divina regista: un solo punto d'ingresso",
     "description": ("La chat della console capisce da sola quando una richiesta è "
                     "una task operativa e la smista all'agente giusto, mostrando "
                     "in chat chi se ne occupa e con quale esito."),
     "zoey_ref": ("«Tell Zoey what you need. She understands the intent and "
                  "decides who handles it.»"),
     "divina_note": ("agents_bridge.py riconosce i messaggi «task-like» e chiama "
                     "/agents/route; la chat mostra il chip agente·skill·confidenza "
                     "e, DURANTE l'attesa, il cervello vivo: chi sta lavorando "
                     "compare in tempo reale nella bolla (polling della regia). "
                     "Resta il fallback esplicito quando la confidenza è bassa. "
                     "19-07: SELETTORE companion in chat (Divina/Dante/Virgilio/"
                     "Beatrice) — la scelta umana forza l'agente, l'orb ne prende "
                     "il colore, il classificatore sceglie solo la skill.")},

    # ── automazioni ──────────────────────────────────────────────────────
    {"id": "coda-task-persistente", "area": "automazioni", "priority": "alta",
     "status": "in-corso", "effort": "M", "repo": "entrambi",
     "title": "Coda task persistente del cervello",
     "description": ("Le task di apprendimento sono in-memory e si azzerano al "
                     "redeploy. Serve una tabella tasks con stato (aperta/fatta/"
                     "archiviata), origine (gap, 👎, manuale, agente) e assegnatario "
                     "(umano o companion)."),
     "zoey_ref": ("«Every task, companion, and action in one place» — il task "
                  "tracking è il cuore del workspace di Zoey."),
     "divina_note": ("Z2 FATTO e COLLAUDATO end-to-end (17-07): Dante → «Accoda per "
                     "approvazione» → Proposte audit → approvata da Andrea, "
                     "migration stati applicata su Supabase. Claim atomico worker "
                     "pronto (POST /admin/tasks/claim, SKIP LOCKED). Resta Z3: il "
                     "worker pool sull'orchestratore con gli executor reali "
                     "(Composio) che esegue le approvate.")},
    {"id": "skill-workflow", "area": "automazioni", "priority": "media",
     "status": "da-fare", "effort": "L", "repo": "orchestratore",
     "title": "Skill = interi workflow (playbook)",
     "description": ("Una skill deve poter concatenare più passi (ricerca → bozza → "
                     "aggiorna gestionale → prepara invio) mantenendo la conferma "
                     "umana sui passi critici."),
     "zoey_ref": ("«Give a companion a skill and it runs the whole workflow — send "
                  "the email, update the CRM, book the meeting.»"),
     "divina_note": ("Z1 primo passo FATTO: dall'esito di un companion (Router) il "
                     "bottone «⚡ Accoda per approvazione» crea l'azione "
                     "in-approvazione (idempotente) → Proposte audit → ok owner → "
                     "claim atomico del worker (POST /admin/tasks/claim, SKIP "
                     "LOCKED). Restano: input_schema/executor_ref dichiarativi per "
                     "skill (con gli executor Z6) e il worker pool Z3 "
                     "sull'orchestratore che esegue davvero.")},
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
     "status": "in-corso", "effort": "L", "repo": "orchestratore",
     "title": "Connettori che eseguono azioni reali",
     "description": ("I companion non devono solo rispondere: eseguono (email, "
                     "calendario, Notion, Slack, Drive) con conferma umana sulle "
                     "azioni verso l'esterno."),
     "zoey_ref": ("«Connected to the platforms your work already lives in, they "
                  "carry out real actions» — 1.000+ integrazioni."),
     "divina_note": ("Z1+Z3+Z6 IMPLEMENTATI: catalogo azioni dichiarative "
                     "(GET /skills/spec), worker pool opt-in (WORKER_ENABLED, "
                     "claim SKIP LOCKED, solo kind 'azione' strutturate) ed "
                     "executor Composio. Per il collaudo live: collegare gli "
                     "account OAuth nel workspace Composio e attivare il worker "
                     "su Railway (runbook Cowork). Nango (Z7) rimandato alla "
                     "produzione (decisione owner).")},
    {"id": "crm-forma-sync", "area": "integrazioni", "priority": "alta",
     "status": "da-fare", "effort": "M", "repo": "orchestratore",
     "title": "Sincronizzazione col CRM FORMA (Railway)",
     "description": ("Il sito e il CRM FORMA (già su Railway) notificano clienti, "
                     "preventivi e ordini al cervello: le informazioni restano "
                     "sincronizzate e diventano conoscenza interrogabile, con "
                     "conferma umana prima di consolidare."),
     "zoey_ref": ("«Connected to the platforms your work already lives in» — le "
                  "integrazioni con gli strumenti dove il lavoro vive davvero."),
     "divina_note": ("Il funnel c'è già: registrare un connettore 'forma-crm' e "
                     "usare POST /connectors/webhook/forma-crm (X-Connector-Secret) "
                     "→ raw_sources → pipeline. Regola: tenant/scope dalla config "
                     "del connettore, MAI dal payload. FORMA è il tenant 0.")},
    {"id": "fossato-italia", "area": "integrazioni", "priority": "media",
     "status": "da-fare", "effort": "L", "repo": "orchestratore",
     "title": "Fossato Italia: SDI, PEC, WhatsApp Business (MCP nativi)",
     "description": ("I connettori che gli aggregatori USA non coprono: fatturazione "
                     "elettronica SDI, PEC, WhatsApp Business — il vantaggio "
                     "competitivo di Divina verso Zoey (US-centrica)."),
     "zoey_ref": ("Zoey compra l'ampiezza (1.000+ integrazioni claim): Divina "
                  "costruisce il fossato dove Zoey non arriva."),
     "divina_note": ("Brief 17-07 Z8. Server MCP nativi: SDI via Aruba/InfoCert API, "
                     "PEC, WhatsApp Business (Meta Cloud API). Pratiche avviate "
                     "lato owner (17-07): verifica Meta Business + numero dedicato, "
                     "credenziali SDI e PEC in raccolta. Non blocca le altre "
                     "tranche; parte appena arrivano le credenziali.")},
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
     "status": "in-corso", "effort": "M", "repo": "motore",
     "title": "Voce e testo in un'unica conversazione",
     "description": ("Parlare con Divina nella console e passare da voce a testo "
                     "senza interrompere il filo (STT + TTS in streaming)."),
     "zoey_ref": ("«Switch between voice and text anytime in one continuous "
                  "conversation» — Zoey è voice-first."),
     "divina_note": ("Tranche 1 FATTA (Web Speech). Tranche 2 FATTA (§2, spec "
                     "Brain Motion v2): orb nella Chat con stati Inattivo/ascolto/"
                     "parlando/ragionando/in-azione, ampiezza REALE dal microfono "
                     "(Web Audio), colori companion (Dante arancio · Virgilio "
                     "ciano · Beatrice magenta · Divina viola) e beat approvazione. "
                     "Resta §3: gateway divina-voice (Voxtral realtime, VAD + "
                     "barge-in). Nota owner: upgrade piano Mistral per la "
                     "produzione voce (B2, da decidere).")},

    # ── workspace ────────────────────────────────────────────────────────
    {"id": "dispatch-live", "area": "workspace", "priority": "media",
     "status": "in-corso", "effort": "M", "repo": "orchestratore",
     "title": "Regia live: vedere il lavoro accadere",
     "description": ("Una vista «regia» nella console che mostra in tempo reale "
                     "richiesta → agente scelto → skill → esito, mentre succede."),
     "zoey_ref": ("«She fires a task to the right companion. You see the dispatch "
                  "happen in real time» (nel workspace 3D)."),
     "divina_note": ("Prima tranche FATTA: registro dispatch (app/dispatches.py, "
                     "GET /agents/dispatches) e vista «Regia live» nella console "
                     "con aggiornamento ogni 5s. Resta lo streaming SSE al posto "
                     "del polling. Niente 3D: prima la sostanza, poi la scena.")},
    {"id": "cervello-vivo-console", "area": "workspace", "priority": "alta",
     "status": "fatto", "effort": "M", "repo": "motore",
     "title": "Cervello vivo nella console (convergenza portale)",
     "description": ("Portare nel pannello ciò che viveva solo sul vecchio portale: "
                     "il grafo animato dei neuroni, i KPI del vault, l'esploratore "
                     "note e le note recenti — per spegnere il portale a fine corsa."),
     "zoey_ref": ("Il «world» di Zoey: non solo vedere i companion lavorare, ma "
                  "vedere il cervello stesso pulsare mentre impara."),
     "divina_note": ("FATTO e COLLAUDATO (17-07): tab «Cervello vivo» con KPI vault, "
                     "ricerca, note recenti e sinapsi REALI dai [[link]] — 236 "
                     "collegamenti dal grafo rigenerato a ogni ingest (brain_graph "
                     "su Supabase, applicata). Mappe e audit visivi restano come "
                     "task dedicate.")},
    {"id": "audit-visivi-console", "area": "workspace", "priority": "media",
     "status": "da-fare", "effort": "M", "repo": "motore",
     "title": "Audit visivi di progetto in console",
     "description": ("I report di avanzamento (checklist per fasi, punteggi, % "
                     "completamento) oggi in audit-*.html sul portale: consultabili "
                     "dalla console, solo owner."),
     "zoey_ref": "Tutto in un posto solo: anche lo stato dei progetti.",
     "divina_note": ("Brief Cowork A5. Fonte: HTML statici generati dal vault — "
                     "decidere se servirli dal motore o rigenerarli come dati "
                     "(fasi/stati) per una vista nativa della console.")},
    {"id": "mappe-console", "area": "workspace", "priority": "media",
     "status": "da-fare", "effort": "L", "repo": "motore",
     "title": "Mappe del cervello in console (aree/progetti/clienti)",
     "description": ("Le 4 mappe .canvas di Obsidian ricreate come viste web nella "
                     "console, navigabili."),
     "zoey_ref": "Il workspace visivo: mappe e relazioni, non solo liste.",
     "divina_note": ("Brief Cowork A6. I .canvas sono JSON: parser + render web "
                     "(o embed della pagina generata). Dipende dalla stessa "
                     "pipeline dati di cervello-vivo (tranche 2).")},
    {"id": "console-quotidiana", "area": "workspace", "priority": "bassa",
     "status": "in-corso", "effort": "S", "repo": "entrambi",
     "title": "Console come workspace quotidiano",
     "description": ("Far vivere l'utente nella console: notifiche sugli esiti dei "
                     "task, badge e contatori live, scorciatoie — l'equivalente "
                     "sobrio del «world» di Zoey."),
     "zoey_ref": ("«A living workspace where you and your companions build "
                  "together», senza perdersi nei tab."),
     "divina_note": ("Prima tranche FATTA: home «Il tuo mondo» (hero FORMA, companion "
                     "card, stat vive) come vista d'ingresso e badge aggiornati "
                     "ogni 60s. Restano le notifiche web push.")},

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
                     "siamo avanti a Zoey, non indietro. Assorbe anche il pannello "
                     "cliente white-label /c/<cliente> del vecchio portale "
                     "(brief Cowork A8): login per-cliente, chat scoped, branding.")},
    {"id": "console-da-piattaforma", "area": "business", "priority": "media",
     "status": "da-fare", "effort": "M", "repo": "entrambi",
     "title": "Console raggiungibile dalla piattaforma FORMA",
     "description": ("Dal CRM/piattaforma FORMA si entra nella console Divina con "
                     "un click (prima link dedicato, poi SSO con seat e ruoli), "
                     "senza reinserire token a mano."),
     "zoey_ref": ("Business: un solo posto di lavoro per il team, con permessi "
                  "per ruolo dal primo giorno."),
     "divina_note": ("Prima tranche: bottone «Console Divina» nel CRM verso "
                     "https://divina.formahub.it/panel/. Poi SSO/seat: dipende "
                     "dalla task multi-utente (i token restano nel browser, mai "
                     "nel codice del CRM).")},
    {"id": "rebrand-forma-orchestrator", "area": "business", "priority": "media",
     "status": "in-corso", "effort": "S", "repo": "orchestratore",
     "title": "FORMA al centro: repo forma-orchestrator",
     "description": ("Rinominare ovy-orchestrator → forma-orchestrator: FORMA è il "
                     "cuore e il creatore della piattaforma, che poi si distribuisce "
                     "a partner e clienti (OVYON, ATS, hospitality, ristorazione…)."),
     "zoey_ref": ("Zoey OS è un prodotto che si vende a tier: prima l'identità "
                  "del creatore, poi la distribuzione."),
     "divina_note": ("Rename su GitHub FATTO (16-07, i vecchi URL redirigono). "
                     "Restano: verifica del collegamento Railway al nuovo nome, "
                     "git remote set-url sui cloni locali e aggiornamento dei "
                     "riferimenti nei docs/CI. EMBER_URL/DIVINA_URL restano uguali "
                     "finché non cambia il dominio.")},
    {"id": "spegnimento-portale", "area": "business", "priority": "media",
     "status": "da-fare", "effort": "M", "repo": "entrambi",
     "title": "Spegnere il vecchio portale (cervello.formahub.it)",
     "description": ("A convergenza completata, il portale web su Cloudflare Pages "
                     "si spegne e Divina resta l'unica faccia di FORMA. Il VAULT "
                     "Obsidian non si tocca MAI: è la fonte del cervello."),
     "zoey_ref": "Un solo posto dove vivere e lavorare: il world.",
     "divina_note": ("Checklist del brief Cowork (sez. C), ogni passo con "
                     "approvazione esplicita: prerequisiti in console (cervello "
                     "vivo, KPI, note, audit, mappe, pannello clienti), censimento "
                     "di chi consuma il portale (Custom Frames ?key=, clienti /c/, "
                     "link nelle note), poi CNAME via, progetto Pages ARCHIVIATO "
                     "(non eliminato), deploy.command e README aggiornati.")},
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
