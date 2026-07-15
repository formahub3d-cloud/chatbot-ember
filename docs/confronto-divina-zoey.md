# Confronto — Divina (FORMA) vs Zoey OS

> Analisi di prodotto a supporto della tab **Roadmap** della console `/panel/`
> (endpoint `GET /admin/roadmap`, dati in `app/roadmap.py`). Aggiornata al 2026-07-15.
> Fonti: zoeyos.com (home, what-is-zoey-os, pricing, business) via ricerca web.

## Cos'è Zoey OS

Zoey OS si presenta come «il tuo AI operating system personale»: un'app desktop
(macOS/Windows) in cui vive **un team di companion AI persistenti** — Zoey coordina,
Atlas fa ricerca, altri companion creano e costruiscono — che lavorano insieme
per l'utente. I tratti distintivi dichiarati:

| Capacità | Come la racconta Zoey |
|---|---|
| **Team di companion** | Fino a ~20 companion per «world»; l'utente definisce ruolo, personalità, skill e strumenti consentiti di ciascuno. |
| **Coordinamento** | «Tell Zoey what you need. She understands the intent and decides who handles it» — smistamento automatico del task al companion giusto. |
| **Memoria composta** | «Every conversation builds on the last»: il contesto si accumula invece di azzerarsi; i companion si affinano nel tempo. |
| **Voce continua** | Voice-first: si passa da voce a testo in un'unica conversazione ininterrotta. |
| **Workspace visivo (3D)** | Un workspace «vivo» dove si vede ogni task, companion e azione, e il dispatch avviene in tempo reale. |
| **Skill = workflow** | «Give a companion a skill and it runs the whole workflow — send the email, update the CRM, book the meeting.» |
| **Esecuzione reale** | 1.000+ integrazioni: i companion non solo rispondono, eseguono azioni sulle piattaforme dove il lavoro già vive. |
| **Task programmati** | Scheduling, task tracking e workflow automation integrati. |
| **Privacy** | «Never trains on your data.» |

**Zoey OS for Business**: multi-seat per team («ogni membro ha il suo world, la
conoscenza condivisa resta connessa»), permessi per ruolo, row-level security su
ogni tabella, credenziali cifrate, audit log su ogni azione, SOC 2 in roadmap.
Integrazioni citate: Slack, Drive, Notion, GitHub, Microsoft (+ custom on demand).

**Prezzi** (USD/mese): Explorer $45 · Builder $90 · Architect $170 ·
**BYO Architect $109** (piattaforma completa, ma porti la tua chiave Anthropic
o ti colleghi via Claude Code bridge).

## Dove Divina è già avanti

Questi sono i pilastri da **proteggere** mentre si colmano i gap — non vanno
barattati per nessuna feature:

1. **RAG su cervello proprietario** (vault Obsidian) con fonti citate in risposta —
   Zoey non dichiara un retrieval su una base di conoscenza curata del cliente.
2. **Scope server-side**: il permesso è un filtro Qdrant calcolato dal path della
   nota, non un prompt. Un tenant non può «convincere» il modello a sconfinare.
3. **Multi-tenancy reale**: RLS Postgres (GUC `ovyon.*`), audit (`access_logs`)
   su ogni azione, cifratura contenuti — Zoey Business lo promette, Divina ce l'ha.
4. **Governance del sapere**: contraddizioni risolte solo da un umano, nessun
   DELETE (si archivia), write-back nel vault solo dopo conferma umana.
5. **GDPR**: region UE, retention configurabile, quote e costi per tenant.

## Dove Zoey è avanti (i gap → le task della roadmap)

| Gap | Zoey | Divina oggi | Task roadmap (`app/roadmap.py`) |
|---|---|---|---|
| Memoria conversazionale | si accumula per sempre | in-memory, si azzera al redeploy; `agent_memory` solo lato orchestratore | `memoria-persistente`, `preferenze-apprese` |
| Companion su misura | fino a ~20, definiti dall'utente | 3 agenti fissi (Dante/Virgilio/Beatrice) con catalogo skill fisso | `companion-personalizzati` |
| Punto d'ingresso unico | Zoey coordina e smista | `agents_bridge` riconosce i messaggi «task-like» ma il giro non è completo | `chat-regista` |
| Task tracking | ogni task visibile e tracciato | task di apprendimento effimere | `coda-task-persistente` |
| Skill multi-step | una skill = un intero workflow | skill singole; solo l'ingest è concatenato | `skill-workflow` |
| Scheduling | task ricorrenti integrati | solo `nightly_learning` su GitHub Actions | `task-programmati` |
| Esecuzione esterna | 1.000+ integrazioni | MCP 5 tool, Tavily, webhook; Fase 5 in design | `connettori-azioni`, `mcp-marketplace` |
| Voce | continua, voice-first | provider previsto, round-trip incompleto | `voce-continua` |
| Workspace vivo | 3D, dispatch in tempo reale | tab statiche con refresh | `dispatch-live`, `console-quotidiana` |
| Multi-seat | world per membro + ruoli | una chiave = un tenant | `multi-utente` |
| Packaging | 4 piani chiari + BYO key | tier presenti ma non «a listino» | `listino-tier` |

## Linea di prodotto

Divina non deve inseguire il «world 3D»: la sostanza di Zoey è
**memoria + companion su misura + esecuzione reale + tutto visibile in un posto solo**.
La console `/panel/` è già quel posto; le task della roadmap la portano da
«console di controllo» a «posto dove si lavora». L'ordine consigliato è quello
delle priorità nella tab Roadmap: prima memoria e coda task persistente (fondamenta),
poi companion personalizzati e connettori (valore visibile al cliente), infine
voce, regia live e packaging.
