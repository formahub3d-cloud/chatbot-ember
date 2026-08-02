# CLAUDE.md — Contesto progetto per Claude Code

> Leggi questo file prima di lavorare. Aggiornato al 02-08-2026, sera (V10: il
> clone del vault come dipendenza dichiarata, la voce dell'agente misurata invece
> che indovinata, le cinque prove della conversazione). Prodotto: **Divina** — dominio
> `divina.formahub.it`. Nomi storici («Ember», «Jarvis», «OVY») rimossi da ciò che
> una persona legge; restano SOLO dove sono contratti (vedi sotto).

## Cos'è

**Divina** è il prodotto AI di FORMA, due facce sotto lo stesso brand:
- **questo repo (`chatbot-ember`) = il motore**: chatbot RAG multi-tenant + il cervello (retrieval, ingest, admin, voce);
- **`ovy-orchestrator` = l'orchestratore**: i 3 companion (Dante/Virgilio/Beatrice), che parlano col motore SOLO via API.

La **console unica** (`/panel/`, servita da entrambi i servizi come copia byte-identica)
unisce le due facce. Il cervello è un vault Obsidian (repo `ovy-cervello`) di
Andrea Aloia / FORMA. FORMA lo usa internamente (tenant 0), **ATS** è il pilota,
poi si vende ai clienti. Regola d'oro: **un solo motore, molte chiavi** — ogni
cliente è un *tenant* con una chiave che limita le aree del cervello che legge.

> **Identificatori-contratto col vecchio nome — NON rinominarli** (li leggono
> clienti, database, segreti o il calcolo dei permessi): DB Mongo `MONGO_DB=ember`,
> prefisso chiavi tenant `ember_…`/`ovy_…` (formato storico del generatore — **NESSUNA
> chiave è installata presso clienti**: verificato con Andrea l'1/08, erano emesse in
> previsione di vendite non avvenute; regola: una chiave esiste solo se qualcuno la sta
> usando — reset con `scripts/reset_chiavi.py`, la FORMA si riemette PRIMA), logger
> `ember`, segreti/variabili `EMBER_URL`/`EMBER_ADMIN_TOKEN` (CI + Railway, si
> cambiano solo in coppia), nomi tool MCP `ovy_*`, cartella `ovyon/` del vault
> (= scope: rinominarla fa SPARIRE le note ai tenant), schema/GUC SQL `ovyon.*`,
> alias `ember-*`/`jarvis-production-e680.up.railway.app`. Dettagli e piani di
> migrazione: prompt «Togliere Ember e OVY» del 31-07.

## Architettura

```
note .md del vault ──ingest──> Qdrant (vettori + scope/org/tenant/sub_tenant/links)
                                    │ retrieval filtrato per scope (+ focus orbita)
     domanda + chiave tenant ──────►│
                                    ▼
                       LLM (Mistral/Claude) ──> risposta + fonti (+ ⟦fuori⟧ owner/libera)
upload ──OCR──► estrazione ──(conferma umana)──► write-back vault (marcato se da conversazione)
```

**Scope = permesso**, calcolato dal path: `forma/clienti/<X>/…` → `<X>`;
`forma/…` → `forma-core`; `andrea-aloia/…` → `andrea`; `ovyon/…` → `ovyon`.
Tre livelli additivi nel payload (org/tenant/sub_tenant); `rag.build_filter`
accetta grant come lista storica o dict per livello. Il **focus** (orbita scelta
in console) è un filtro slug in `must`: restringe soltanto, mai allarga.
**Owner** (`branding.owner=true`, server-side): conversazione libera con
provenienza obbligatoria ⟦fuori⟧…⟦/fuori⟧, resa come blocchi «fuori dal
cervello · non verificato»; i tenant clienti restano vincolati al vault.

**V6 · La distinzione da non perdere.** Il **tono** della conversazione (saluti,
chiacchiera, tornare indietro, ammettere il buco con una frase umana e offrire di
colmarlo) vale per **tutti**: è uno strato del system prompt (`rag._TONO_IT`), non
un permesso. Il **contenuto fuori dal vault** no: solo owner, o tenant con la
spunta `libera` (tenant_flags, stessa famiglia di `liv3` — server-side, mai nella
richiesta). Il motivo: il widget sul sito di un cliente non può inventare sul
cliente. Quando il cervello non sa, la risposta porta `gap` e la console ci
attacca l'offerta di scrivere la nota, nella bolla.

## Mappa file

- `app/config.py` — settings da `.env` (incl. `VAULT_GIT_REF=main`, guardie ingest, espressività voce `ELEVENLABS_*`)
- `app/providers.py` — embeddings + chat (switch Mistral/Claude)
- `app/ingest.py` — vault→Qdrant: sync git deterministico (fetch+reset, clone-swap che preserva i dati cliente, MAI riuso silenzioso), guard anti-stantio (`INGEST_MAX_VAULT_AGE_H`), guard min-note, perimetro unico `is_note_included`, `vault_info()` (commit+data in /ingest e /admin/brain)
- `app/rag.py` — retrieval filtrato + risposta vincolata; V9/C `vettore()` (il vettore della domanda si calcola UNA volta: retrieval + riconoscimento capacità) e `_capacita_block` (offrire, mai eseguire); focus_slugs (O2); free/owner con marcatori (O4); tono per tutti + `gap` nella risposta (V6/B1-B2); tier=solo stile; web additivo; aggancio systemq PRIMA del retrieval
- `app/conversa.py` — V10/C: **le cinque prove della conversazione**. Una mossa (correzione · ambiguo · abbandono · dubbio · ripresa) cambia **cosa si va a cercare**, non il tono: è la differenza fra sei funzioni e una conversazione, ed è l'unica parte verificabile senza LLM. Due casi non arrivano al modello (il chiarimento «quale dei due?» si compone dai nomi già nel filo — non PUÒ indovinare; «lascia stare» senza seguito è una riga). `generica()` (C2): le domande sul mondo ricevono risposta (owner/`libera`) ma **niente offerta di annotarle nel vault**, e il discrimine sono gli scope del tenant, non i nomi propri
- `app/filo.py` — V7/A1: il filo della conversazione. Finestra a CARATTERI (non 6 turni: a voce si parla per frasi corte), espansione lessicale della domanda di seguito PRIMA del retrieval (nessuna chiamata LLM: a 55 ms di prima sillaba un round-trip in più si sente), memoria server-side in RAM **opt-in** (solo con `conversazione`, TTL 30', tetto duro, mai su disco). Il filo NON allarga i permessi: c'è un test che lo dimostra
- `app/dbcheck.py` — V7/B1: le migrazioni ATTESE contro quelle applicate (tabelle, colonne e CHECK), con «cosa smette di funzionare» per ognuna. Riga `[db]` all'avvio + `/admin/status`. Nessuna tabella nuova: legge `information_schema`
- `app/learned.py` — V6/B3: da 0 a 3 «cose imparate» da una conversazione, ognuna con la CITAZIONE verificata nel testo (una citazione non ritrovata fa cadere la proposta), PII scartate (mai redatte), `andrea-aloia/human/` sempre fuori. Non scrive: propone
- `app/degrado.py` — V9/A: **una funzione spenta lo dice DOVE si usa.** Registro funzione→dipendenze (tabelle via `dbcheck`, variabili via `settings`, V10/A1 il **clone del vault** via `clone_del_vault()` — `dbcheck` non può vederlo, non è una tabella) con tre esiti mai confusi: acceso · spento · non-so. Il «cosa smette di funzionare» si legge da `dbcheck.ATTESE`, mai riscritto. La console lo disegna con `boxDegrado()`/`vuotoOnesto()` — al cliente niente riga tecnica
- `app/sitokb.py` — V9/B: la KB di un cliente dal suo SITO, come proposta. Citazione verificata letteralmente (`learned._cita_vera`), niente persone in NESSUNA sezione (deroga solo per i recapiti aziendali nei contatti), nessuna scrittura automatica. Il sito lo legge Tavily, non il motore (SSRF)
- `app/riassunti.py` — V9/D: la conversazione che dura. Un promemoria compresso per conversazione, scritto UNA volta a fine conversazione (`POST /chat/chiudi`, lo dice il client). Non allarga i permessi (test) · retention 30 giorni applicata anche in LETTURA · raggiunto dal «Dimentica». Nessuna spazzatura periodica: buco dichiarato
- `app/memoria.py` — V8/A: «Cosa so di te». Quello che il sistema ha imparato di chi gli parla, con la FRASE da cui viene e quante volte è stato ridetto — **nessuna percentuale**: senza un criterio la fonte batte il numero (in Zoey sono tutte al 70%). Le voci con una `chiave` nota (lingua, lunghezza) diventano COMPORTAMENTO: `do_chat` le applica prima di rispondere. `dimentica()` cancella davvero (art. 17) e lascia solo la lapide
- `app/clientkb.py` — V8/B: la terza persona del sistema. Il cliente vede la propria KB, segnala un errore (proposta nella coda, mai una scrittura nel vault) e — dietro `flags.buchi`, spento di default — le domande rimaste senza risposta. Lo scope arriva dalla SESSIONE, mai dalla richiesta
- `app/flags.py` — permessi per-tenant sul server: `liv3` (agire fuori), `libera` (conoscenza generale) e `buchi` (V8: il cliente vede i buchi — sono domande dei suoi utenti finali, è un accordo). Default SPENTI
- `app/systemq.py` — saluti e domande SUL sistema («dimmi cosa sai» → metadati dell'indice, coi buchi); riconoscitori prudenti, fallback esplicito al retrieval
- `app/voice.py` — proxy STT/TTS (chiavi SUL SERVER): ElevenLabs con `voice_settings` da env + `language_code`, TTS in streaming (0 byte → 502, mai un 200 muto), `status()` per /admin/status (`voice_id_set` = spia voce italiana). V8/C1: **una voce per agente** (`ELEVENLABS_VOICE_ID_DANTE`…) — dal client arriva il NOME, mai un voice_id; variabile vuota = voce di Divina
- `widget/voce.js` — **MOTORE VOCALE UNICO** (U1): frasi (emSentenze, marcatori testati), coda TTS ordinata, barge-in con soglia RELATIVA all'eco (K appreso, marcatori EM_VAD testati, `setBarge` a caldo), invio automatico a fine parlato, parziali STT, ampiezza in/out per l'orb. Copia byte-identica in `panel/voce.js` (parità = test). La meccanica voce si tocca SOLO qui.
- `widget/embed.js` — widget embeddable (Shadow DOM); carica voce.js come fratello; fallback browser se il modulo manca
- `panel/index.html` — console SPA (file unico, no build; versione nel footer). V8: **solo il giro di navigazione corrente può dipingere** (`_giro`/`vivo(giro)` — D1, il menu che si illuminava e non cambiava pagina); pagina «Cosa so di te» (Squadra); le due porte del CLIENTE (`ckb`, `cbuchi`, in `CLIENTE_VIEWS`); delega e scheda-risultato DENTRO il filo; spunta `buchi` in Impostazioni. V6: HOME = L'ORBITA (grande, centrale, nessuna etichetta, colore/forma per stato, UNA riga di testo sotto — il colore da solo non basta); offerta di colmare il buco attaccata alla risposta; «Cosa abbiamo imparato»; spunta `libera` in Impostazioni. V2: SEI PORTE (Mondo · Cervello · Clienti · Squadra · Integrazioni · Impostazioni) + Diagnostica richiudibile; CHAT SEMPRE PRESENTE (pannello destro fuori da #content, tab agenti dinamiche, traccia tool, chip→nota); orb sfera unica colore-unico con fps adattivi; orbite+lenti (O2/O3), modo vocale (U2/U3), «Miglioramenti» con FATTE firmate, quadro potenziamento (X3), allarme cervello fermo (task 18), preboot+[boot] (P3), modalità cliente e demo
- `panel/manifest.webmanifest` `panel/sw.js` `panel/icon-*.png` — PWA (Fase 9): guscio offline prudente, navigazioni sempre prima in rete, API mai in cache
- `panel/brain3d.js` — renderer 3D del grafo (istanza, riusato da home e Cervello vivo). V6/A: `setAccent` (tinta unica o gradiente fra due agenti, transizione 600 ms) e `setMood` (riposo=respiro · pensa=contrazione · lavora=onda dal punto dell'agente · legge=cascata); `labels:'none'` = mai testo, mai hover
- `app/main.py` — API: `/health` `/ingest` `/chat` (SSE; `focus`; free per owner) `/upload` `/voice/*`; MCP: `/search` `/document` `/context` `/writeback` (con `origin=conversazione` → marcatura server-side «NON verificato»); admin: `/admin/status` (spie voce), `/admin/brain*`, `/admin/tasks` (brain_tasks, kind incl. `audit`), `/admin/roadmap`, `/admin/proposals` (incl. proposte `conversazione`: approvare = scrivere la nota marcata), `/admin/conversazione/imparato`, `/admin/tasks/da-merge` (V7/C), `/admin/tasks/nota`, `/admin/liv3`, `/admin/libera`, `/admin/memoria*` (V8/A), `/admin/segnalazioni*` + `/admin/buchi-cliente` (V8/B), `/admin/clients/kb-da-sito` (V9/B), `/chat/chiudi` (V9/D), `/admin/clients*`, `/admin/learning`; `/client/*` (accessi cliente via `app/clientauth.py`; V8: `/client/kb`, `/client/segnala`, `/client/buchi`)
- `app/braintasks.py` — coda task. V7/C: stato **`da-verificare`** (il merge muove, non chiude), `by_idempotency_key`, `annota()` (nota senza transizione). Senza la migrazione del CHECK degrada dichiarandolo, non fallisce
- `app/tenants.py` `app/rls.py` `app/docstore.py` `app/brain.py` `app/braintasks.py` `app/proposals.py` — chiavi/RLS/metadati/grafo/coda/proposte
- `db/` — DDL Supabase: `schema.sql`, `brain_tasks*.sql`, `brain_graph.sql`, `client_access.sql` (i nomi SQL interni, es. schema `ovyon`, sono contratti e restano)
- `scripts/` — `test_console_headless.js` (**il guardiano**: in CI a ogni push), `test_voce_sentenze.js` (17 casi chunker), `test_voce_vad.js` (7 casi barge-in), `contract_console.py` (console↔API, 0 endpoint fantasma), `count_notes.py` (parità perimetro col vault), `verify_ingest.py`, `seed_audit_2026_07_31*.py` (21 task audit come dati, idempotenti) · `seed_task_v6_2026_08_01.py` (11 task V6, chiavi 22-32, priorità inclusa) · `console_parita.py` (V7/B3: manifesto `panel/CONSOLE.sha256`, in CI di ENTRAMBI i repo) · `audit_da_merge.py` (V7/C: dal merge a «da verificare») · `unifica_voce_telefono.py` (il doppione -31/-20) · `close_audit_2026_07_31.py`/`close_audit_2026_08_01.py` (chiusure per idempotency_key, con nota) · `reset_chiavi.py` (reset chiavi: FORMA prima, poi revoca con freno) · `seed_task_allarme_commit.py` (punto 9) · `seed_task_v8_2026_08_02.py` (V8: 10 task, chiavi 33-42 — **da lanciare PRIMA del merge**, altrimenti `audit-merge` non trova le chiavi citate) · `correggi_case_study_2026_08_02.py` (V8/D2: la ‑21 era FALSA → archiviata, nasce la ‑43) · `da_verificare_arretrati_2026_08_02.py` (V8/E: le 10 task il cui lavoro è già in produzione, una volta sola) · `seed_task_v9_2026_08_02.py` (V9: 7 task, chiavi 44-50) · `seed_task_v10_2026_08_02.py` (V10: 6 task, chiavi 51-56) — **i seed si lanciano PRIMA del merge**. **Gli script di manutenzione usano `urllib`, MAI httpx**: girano col Python di sistema, senza venv (regola 1/08)
- `mcp-connector/` — server MCP (5 tool `ovy_*`) · `SETUP-PRODUZIONE.md` — runbook produzione

## Comandi

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q                      # ~524 test offline (DB/LLM/rete mockati)
node scripts/test_console_headless.js    # il guardiano: apre DAVVERO la console (serve Playwright)
python3 scripts/console_parita.py         # V7/B3: i tre file della console combaciano col manifesto
python3 scripts/console_parita.py --scrivi # dopo averli modificati: rigenera E copia nell'altro repo
uvicorn app.main:app --reload --port 8000
curl -X POST localhost:8000/ingest -H "Authorization: Bearer $ADMIN_TOKEN"   # indicizza
```

**V7 · Tre regole nate da errori veri (01-08).**
1. **Nessuna migrazione SQL come prerequisito.** Il codice funziona senza (a freno inserito), la migrazione si scrive, e il pannello DICHIARA cosa manca (`dbcheck`). Il 1/08 quattro migrazioni sono state applicate a mano, ognuna scoperta da un 500 ore dopo il merge.
2. **Il merge NON chiude le task: le mette «da verificare».** «Fatta» la scrive una persona, col suo nome, dopo aver guardato.
3. **Senza dato la spia dice «—», e dice QUALE dato manca.** Un ripiego generico («sync metadati note») è peggio di un errore: sembra normale.

**V8 · La regola nata dal difetto del V6 (02-08).**
4. **Ogni commit nomina le chiavi delle task che tocca — e SOLO quelle.** Il commit del V6 (`a2fd734`) ha costruito l'orbita, il colore, il muro-che-diventa-porta e le proposte da conversazione senza nominare nessuna di quelle chiavi: sono rimaste in DA FARE mentre il lavoro era in produzione. L'unica chiave che citava era `audit-2026-07-31-20`, che NON era stata fatta. Senza questa regola l'automazione del merge è un ornamento; con una chiave citata per il motivo sbagliato è peggio di niente.
5. **Nessuna percentuale senza un criterio dietro.** Se non c'è, si scrive la FONTE. (Zoey mostra ogni memoria al 70%: un numero costante travestito da misura.)

**V10 · Le due regole della sera (02-08).**
7. **Un allarme che non può guardare lo DICE.** Peggio di un allarme assente è un allarme che si spegne da solo: dopo ogni redeploy manca il clone del vault, l'allarme sui commit non ha due valori da confrontare e la fascia spariva — cioè diceva «va tutto bene». Il clone è una dipendenza come le tabelle (`degrado.vault()`), e il motore se lo riprende all'avvio (`ingest.procura_clone()`) **senza reindicizzare**: Qdrant sopravvive al redeploy, è il metro che si perde.
8. **Dove esiste un metro contabile, il punteggio si conta.** L'area «conversazione» non si giustifica più con quante funzioni sono state aggiunte ma con **quante delle cinque prove passano** (`tests/test_v10_conversazione.py`, dizionario `PROVE`). Una stima e un conteggio non stanno nella stessa casella.

**V9 · La regola nata da un difetto visto in produzione (02-08 pomeriggio).**
6. **Una funzione spenta lo dice DOVE si usa, non solo in `/admin/status`.** «Cosa so di te» diceva «non so niente di te» mentre la verità era «mi manca la tabella». Chi apre una schermata non legge lo stato tecnico: una funzione spenta che sembra inutile non chiede di essere riparata. Il registro è `app/degrado.py`, il disegno è `boxDegrado()`, e la frase viene da `dbcheck` — mai riscritta a mano in due posti.

## Regole tassative

1. **Mai committare** `.env`, `tenants.json`, PII, segreti (mai nemmeno in chat).
2. **Embeddings = Mistral** sempre; LLM Mistral o Claude via env; logica provider solo in `providers.py`.
3. **Accessi server-side**: lo scope è un filtro Qdrant, non un prompt. Il focus restringe soltanto. Il flag owner sta sul record del tenant, mai nella richiesta.
4. **Write-back solo con conferma umana**; contenuto nato da conversazione entra MARCATO «NON verificato» (lo marca il server).
5. **La console è UNA**: `panel/index.html` + `voce.js` + `brain3d.js` byte-identici nei due repo (sempre `cp` + commit su entrambi). La voce si modifica solo in `widget/voce.js`.
6. **GDPR**: Qdrant/region UE; contratti = dati personali → repo privato.
7. **Ogni consegna finisce in una PR aperta e VERIFICATA** (`list_pull_requests` dopo la creazione). Io non mergio mai: merge = Andrea. Se la PR del branch è già mergiata, si riparte da main (mai accodare a storia chiusa).
8. Prima di dire «fatto»: suite verde, guardiano headless verde, contract test verde.

## Stato (01-08-2026)

- ✅ In produzione: RAG multi-tenant, voce continua (frasi/barge-in a turni/mani libere/modo vocale; prima sillaba 55 ms), orbite+lenti+focus, conversazione libera owner, «Miglioramenti» (task audit 01-03, 09, 10 FATTE via `close_audit_*`; quadro di potenziamento collegato alla nota del vault), console che dichiara quando è pronta (riga `[boot]`; produzione 1265 ms), guardiano in CI, accessi cliente, ingest anti-stantio.
- ✅ V6 (01-08 notte, in PR): **l'orbita è la home** (grande e centrale, nessuna etichetta sui nodi, colore per agente — Divina gialla, Dante rosso —, respiro a riposo, onda quando un agente lavora, cascata durante l'ingest) con **una riga di testo** che dice sempre quello che dice il colore (accessibilità, non rifinitura); **settima area** del quadro «Estetica e resa visiva» (il radar è un ettagono); **il muro diventa una porta** (`gap` + offerta di scrivere la nota attaccata alla risposta); **tono per tutti / contenuto fuori dal vault solo con `libera`**; **le conversazioni propongono note** con la citazione, in coda Proposte, mai in automatico.
- ✅ V7 (01-08 notte, in PR): **il filo della conversazione** (`app/filo.py`) con la domanda di seguito espansa prima del retrieval e la memoria server-side opt-in; **le capacità raggiungibili dalla chat** (il catalogo si legge da `/agents`, mai duplicato); **il cerchio provato end-to-end** (gap → nota → ingest → risposta con la fonte nuova); **il motore dichiara le migrazioni** attese e mancanti; **la parità della console è un vincolo di CI**, non una disciplina; **il merge mette «da verificare»**.
- ✅ V8 (02-08, in PR): **«Cosa so di te»** (`app/memoria.py`) — elenco, fonte al posto della percentuale, DIMENTICA che cancella davvero, e la memoria che **cambia la risposta**; **il pannello del cliente** (`app/clientkb.py`) — la sua KB, la segnalazione che è una proposta, i buchi dietro un accordo (`flags.buchi`); **una voce per agente**, **la delega dentro il filo**, **il risultato come scheda**; **il menu che si illuminava e non cambiava pagina** (era una corsa fra render async, non il grafo).
- ✅ V10 (02-08 sera, in PR): **il clone del vault è una dipendenza dichiarata** e il motore se lo riprende all'avvio (l'allarme sui commit non si spegne più da solo a ogni redeploy); **la voce dell'agente misurata invece che indovinata** — la tubatura era giusta, la lettura ad alta voce nasce spenta e l'unico comando era un tooltip; **le cinque prove della conversazione** (`app/conversa.py`), da 0/5 a 5/5.
- ✅ V9 (02-08 pomeriggio, in PR): **il degrado dichiarato dove si vede** (`app/degrado.py`); **la KB del cliente dal suo sito** (`app/sitokb.py`) come proposta con la pagina e la frase; **le capacità raggiungibili parlando** (riconoscimento semantico col vettore che il retrieval calcola già — le parole non bastavano, e c'è il test che lo dimostra); **la conversazione che dura** (`app/riassunti.py`, retention e «Dimentica» inclusi).
- ⏳ Aperti: task audit 04-08 e 11-21, più le 22-32 del V6 (conversazione normale, sei sezioni, allarme cervello fermo, valore clienti, voce su telefono, case study Centioni, …), lente Temi (aspetta i tag `tema/*` decisi da Andrea — proposta in `docs/lenti-temi-proposta.md`), R2/R3 del piano nomi (migrazioni, non rename).

## Riferimenti

- Confronto e roadmap: `docs/confronto-divina-zoey.md` · voce: `docs/voce-continua.md`
- V10 (il clone come dipendenza + la voce misurata + le cinque prove): `docs/conversazione-e-cose-che-si-spengono.md`
- V9 (degrado dichiarato + KB dal sito + capacità dalla conversazione + riassunti): `docs/kb-dal-sito-e-conversazione-lunga.md`
- V8 (memoria visibile + pannello del cliente + il menu che non cambiava pagina): `docs/memoria-e-pannello-cliente.md`
- V6 (orbita della home + conversazione + knowledge base dalle conversazioni): `docs/orbita-e-conversazione.md`
- Audit in console: sezione «Miglioramenti» → «Gli audit» (`panel/audit-*.html`)
