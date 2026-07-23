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

    # ── Audit generale 21-07 (Code): gap emersi dal giro completo su motore,
    #    console e orchestratore — capacità già costruite ma non esposte,
    #    robustezza, sicurezza, prodotto. ──────────────────────────────────
    {"id": "chat-streaming-console", "area": "workspace", "priority": "alta",
     "status": "da-fare", "effort": "S", "repo": "entrambi",
     "title": "Risposta in streaming nella console",
     "description": ("La chat della console aspetta la risposta intera; il motore "
                     "sa già rispondere token-per-token (SSE). Collegare i due: "
                     "percezione di velocità radicalmente migliore, specie da "
                     "mobile."),
     "zoey_ref": "La chat di Zoey scrive mentre pensa: la latenza percepita è zero.",
     "divina_note": ("/chat con {stream:true} è già SSE collaudato (event sources → "
                     "delta → done): sendChat deve consumarlo con fetch+reader e "
                     "aggiornare la bolla in progress. L'orb «parlando» si aggancia "
                     "allo stream invece che al TTS.")},
    {"id": "conversazioni-persistenti", "area": "memoria", "priority": "alta",
     "status": "da-fare", "effort": "M", "repo": "motore",
     "title": "Conversazioni salvate (riprendi da dove eri)",
     "description": ("Oggi la chat della console vive in memoria: un refresh e "
                     "sparisce tutto. Salvare i thread per tenant (Supabase), "
                     "riaprirli, dare un titolo automatico — la memoria del "
                     "quotidiano, non solo del vault."),
     "zoey_ref": "«Your context accumulates» — le conversazioni SONO memoria.",
     "divina_note": ("Tabella conversations+messages con RLS per tenant; la "
                     "console lista i thread e ricarica history (già supportata "
                     "da /chat). Passo successivo naturale verso "
                     "memoria-persistente e preferenze-apprese.")},
    {"id": "upload-console", "area": "workspace", "priority": "alta",
     "status": "da-fare", "effort": "M", "repo": "motore",
     "title": "Upload documenti in console (OCR → conferma → vault)",
     "description": ("L'API /upload con OCR Mistral ed estrazione campi esiste da "
                     "Fase 2, ma la console non ha una vista per usarla: caricare "
                     "un PDF dal telefono, vedere i campi estratti, confermare, "
                     "write-back nel vault."),
     "zoey_ref": "In Zoey trascini un file nel world e diventa contesto.",
     "divina_note": ("Vista Upload: drag&drop/foto da mobile → /upload → anteprima "
                     "campi (UniLav + generico) → conferma umana (regola 5) → "
                     "writeback. Tutto già server-side, manca SOLO la UI.")},
    {"id": "notifiche-owner", "area": "automazioni", "priority": "alta",
     "status": "da-fare", "effort": "M", "repo": "entrambi",
     "title": "Notifiche all'owner (approvazioni e fallimenti)",
     "description": ("Quando un'azione entra in-approvazione o una task fallisce, "
                     "oggi bisogna accorgersene aprendo la console. Serve un "
                     "canale attivo: email o Telegram/WhatsApp all'owner con link "
                     "diretto alla decisione."),
     "zoey_ref": "Zoey ti raggiunge lei: «needs your approval» arriva, non si cerca.",
     "divina_note": ("Hook nel transition di braintasks (in-approvazione, fallita): "
                     "provider pluggabile (SMTP/Telegram bot), opt-in via env, "
                     "MAI contenuti sensibili nel messaggio — solo titolo+link. "
                     "Si sposa con le quote: alert soglia già calcolato in usage.")},
    {"id": "backup-programmato", "area": "memoria", "priority": "alta",
     "status": "parziale", "effort": "S", "repo": "motore",
     "title": "Backup programmato + prova di restore",
     "description": ("scripts/backup.py (snapshot Qdrant + export Supabase) esiste "
                     "ma nessuno lo lancia: schedularlo e documentare il restore. "
                     "Il cervello è l'asset: senza backup provato non è protetto."),
     "zoey_ref": "Un AI OS custodisce il world: la memoria non si perde.",
     "divina_note": ("Workflow schedulato (come eval del lunedì e retention "
                     "notturna già attivi) + runbook di restore in OVYON-SETUP; "
                     "esito nel pannello Stato & audit (ultima esecuzione, ok/ko).")},
    {"id": "csp-sessioni-owner", "area": "workspace", "priority": "alta",
     "status": "da-fare", "effort": "M", "repo": "entrambi",
     "title": "Hardening console: CSP + sessione owner",
     "description": ("La console tiene i token admin in localStorage e il motore "
                     "non manda Content-Security-Policy: un XSS ruberebbe le "
                     "chiavi del regno. CSP severa subito; poi login owner con "
                     "sessione breve al posto del token incollato."),
     "zoey_ref": "Prodotto vendibile = sicurezza da prodotto, non da prototipo.",
     "divina_note": ("Oggi ci sono solo nosniff+X-Frame-Options. CSP: "
                     "default-src 'self' + connect-src verso i due servizi (la "
                     "console è inline: serve nonce o hash). Sessione: cookie "
                     "HttpOnly+SameSite con scadenza, magic-link o passkey; "
                     "prerequisito sano per multi-utente.")},
    {"id": "azioni-estese-persona", "area": "integrazioni", "priority": "alta",
     "status": "in-corso", "effort": "M", "repo": "orchestratore",
     "title": "Azioni estese + identità Composio per-tenant",
     "description": ("Oltre la bozza Gmail: invio email vero, evento calendario, "
                     "messaggio Slack — sempre dietro approvazione. E ogni tenant "
                     "con la SUA identità Composio (user-id = tenant), mai account "
                     "condivisi."),
     "zoey_ref": "Le azioni di Zoey escono davvero (mail, calendar, CRM).",
     "divina_note": ("Catalogo Z1 già pronto (gmail/calendar/slack, param_map "
                     "collaudato); manca l'entity per-tenant in composio_exec "
                     "(user_id=tenant_code), la verifica scope gmail.compose/"
                     "modify sull'Auth Config, e le skill-azione «invio» gated "
                     "requires_approval=True (§4 del piano).")},
    {"id": "audit-trail-azioni", "area": "automazioni", "priority": "media",
     "status": "da-fare", "effort": "M", "repo": "entrambi",
     "title": "Timeline completa per ogni azione",
     "description": ("Per ogni azione fidata: chi l'ha proposta, chi ha approvato "
                     "e quando, quando è partita, esito, risposta del connettore. "
                     "Oggi i pezzi esistono sparsi (task, regia, access_logs) — "
                     "serve la vista unica che li cuce."),
     "zoey_ref": "Approval history per-azione: la fiducia si costruisce col registro.",
     "divina_note": ("Le fonti ci sono già tutte (brain_tasks con approved_by/"
                     "error, dispatches con esito, audit RLS): endpoint "
                     "/admin/actions/{id}/timeline che aggrega + drawer in "
                     "console dalla card della task.")},
    {"id": "eval-qualita-console", "area": "memoria", "priority": "media",
     "status": "parziale", "effort": "S", "repo": "motore",
     "title": "Qualità delle risposte nel pannello (eval RAG)",
     "description": ("L'eval RAG gira ogni lunedì in CI (eval_rag.py) ma il "
                     "punteggio non si vede: portarlo in console con lo storico — "
                     "il cervello dichiara quanto è affidabile, e si vede subito "
                     "se un ingest lo peggiora."),
     "zoey_ref": "Un AI OS misura sé stesso, non si autodichiara bravo.",
     "divina_note": ("Persistere l'esito dell'eval (Supabase o artifact→endpoint) "
                     "e mostrarlo in Dashboard/Stato: punteggio, trend, ultima "
                     "run. Gancio naturale con proposals: eval in calo → proposta "
                     "automatica all'owner.")},
    {"id": "pwa-installabile", "area": "workspace", "priority": "media",
     "status": "da-fare", "effort": "S", "repo": "entrambi",
     "title": "Console installabile (PWA)",
     "description": ("manifest + icone + service worker minimo: Divina si installa "
                     "sul telefono come app vera, a schermo intero, con la sua "
                     "icona — il passo finale dell'esperienza mobile."),
     "zoey_ref": "Zoey vive nel desktop: Divina vive in tasca.",
     "divina_note": ("La console è già un file solo con bottom bar da app: "
                     "manifest.json + icone FORMA + SW cache-first SOLO per lo "
                     "shell statico (mai per le API: il no-cache resta). Occhio "
                     "a non ricreare il problema cache appena risolto.")},
    {"id": "gdpr-console", "area": "business", "priority": "media",
     "status": "parziale", "effort": "S", "repo": "motore",
     "title": "Export e oblio GDPR dalla console",
     "description": ("gdpr.py (export + diritto all'oblio su Supabase+Qdrant) "
                     "esiste: esporlo in console per-tenant. Per vendere in UE è "
                     "un requisito, non un extra — e per ATS serve già."),
     "zoey_ref": "Zoey è US-centrica: il GDPR fatto bene è fossato UE di Divina.",
     "divina_note": ("Vista in Tenant: «Esporta dati» (zip) e «Cancella» con "
                     "doppia conferma + nome di chi decide (stesso pattern delle "
                     "contraddizioni). Audit dell'operazione in access_logs.")},
    {"id": "billing-live", "area": "business", "priority": "media",
     "status": "parziale", "effort": "M", "repo": "motore",
     "title": "Billing Stripe attivo per i primi clienti",
     "description": ("billing.py con Stripe è scritto e inerte (si attiva con la "
                     "chiave): checkout per i tier, webhook già verificato, stato "
                     "abbonamento visibile in Tenant. ATS pilota = primo test "
                     "reale."),
     "zoey_ref": "Zoey fattura dal giorno uno: $45-170/mese per world.",
     "divina_note": ("Il grosso c'è (webhook firmato, quota mensile per-tenant): "
                     "mancano i price ID nei tier, il link checkout in console e "
                     "il blocco morbido a quota scaduta (mai il duro: il "
                     "cervello non sparisce, si degrada).")},
    {"id": "onboarding-wizard", "area": "business", "priority": "media",
     "status": "da-fare", "effort": "M", "repo": "motore",
     "title": "Onboarding nuovo cliente in 5 minuti",
     "description": ("Wizard in console: nome cliente → scope (aree del cervello) "
                     "→ branding (colori, lingua, tier) → quota → chiave emessa + "
                     "snippet widget pronto da incollare. Oggi è un giro tra "
                     "tab e curl."),
     "zoey_ref": "Zoey: signup → world pronto. Divina: chiave → cliente attivo.",
     "divina_note": ("Le API ci sono tutte (manage_tenants/manage_apikeys, "
                     "branding jsonb): è orchestrazione UI in un flusso unico "
                     "con anteprima. Include il widget embeddabile (Fase 1) come "
                     "output finale: quello è il pezzo davvero nuovo.")},
    {"id": "test-console-ci", "area": "workspace", "priority": "media",
     "status": "da-fare", "effort": "M", "repo": "entrambi",
     "title": "Smoke test della console in CI",
     "description": ("La console è ~1.500 righe di JS senza un test: ogni tocco è "
                     "un atto di fede + screenshot manuale. Smoke Playwright in "
                     "CI (demo mode): le viste chiave si aprono, chat/selettore/"
                     "approvazione funzionano, zero errori console."),
     "zoey_ref": "La qualità percepita di un OS è che non si rompe mai.",
     "divina_note": ("Playwright su file:// in demo mode già collaudato a mano "
                     "(19-07): formalizzarlo in .github/workflows/ci.yml con "
                     "3-4 scenari + check console.error. Copre ANCHE la copia "
                     "orchestratore (diff byte-identico dei due panel).")},
    {"id": "accessi-clienti", "area": "business", "priority": "alta",
     "status": "fatto", "effort": "M", "repo": "motore",
     "title": "Accessi cliente gestiti da FORMA (password → codice a 6 cifre)",
     "description": ("Il cliente entra nel SUO pannello (solo chat) con email+"
                     "password al primo accesso, poi col codice a 6 cifre che "
                     "solo FORMA genera/rigenera. Chiavi e token restano sul "
                     "server: il cliente non li vede mai. FORMA aggiunge/"
                     "sospende/rimuove gli accessi e può entrare nel pannello "
                     "di ogni cliente (sessione breve, tracciata)."),
     "zoey_ref": "Ogni utente il suo world; da Divina: l'owner governa gli accessi.",
     "divina_note": ("21-07: app/clientauth.py + /client/* + tab Tenant in "
                     "console (crea, codice, sospendi, rimuovi=archivio, "
                     "«Entra» ghost 30min con banner). Sessioni HMAC in cookie "
                     "HttpOnly, lockout 5 tentativi, chiave tenant cifrata a "
                     "riposo con CONTENT_ENC_KEY, master vietata, fail-closed "
                     "senza CLIENT_SESSION_SECRET. Login cliente: "
                     "/panel/#cliente. DDL: db/ovyon_client_access.sql.")},
    {"id": "i18n-console", "area": "business", "priority": "bassa",
     "status": "da-fare", "effort": "M", "repo": "entrambi",
     "title": "Console bilingue (IT/EN)",
     "description": ("La console parla solo italiano; i tenant hanno già la "
                     "lingua nel branding e il motore risponde in lang. Per "
                     "vendere white-label fuori dall'Italia serve l'inglese "
                     "anche nell'interfaccia."),
     "zoey_ref": "Zoey è EN-only: Divina bilingue vende in due mercati.",
     "divina_note": ("Dizionario stringhe + lang dal branding del tenant (già in "
                     "/chat): partire dalle viste cliente (chat, home), le viste "
                     "owner possono restare IT. Dopo multi-utente ha più senso.")},
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
