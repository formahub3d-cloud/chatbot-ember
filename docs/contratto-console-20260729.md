# Referto CT — contratto console ↔ backend

> 29 luglio 2026 · prodotto dal prompt CT della «Sintesi architettura Divina».
> Analisi statica: scripts/contract_console.py (estrattore chiamate + rotte FastAPI
> + confronto), test permanente in tests/test_contract_console.py — gira in CI su
> ogni PR in ENTRAMBI i repo (il pannello è copia identica nei due).

## Esito: NESSUN endpoint fantasma — 46 chiamate, 46 rotte trovate, 0 mancanti, 0 dinamiche

Verificato contro: chatbot-ember origin/main `be5d56b` · forma-orchestrator origin/main `3cf1b9`.

La tesi dei «cinque endpoint fantasma» del documento [B] nasce da un checkout di
chatbot-ember NON allineato (HEAD dichiarato `520041f`, che non corrisponde a
origin/main): il pannello aggiornato è stato confrontato con un motore vecchio.
Su origin/main le famiglie /admin/brain, /admin/tasks, /admin/proposals,
/admin/roadmap, /admin/clients esistono tutte — coi DDL (db/brain_graph.sql,
db/brain_tasks.sql, db/client_access.sql) e i relativi test.

## Contratto console → servizio `engine`
32 rotte trovate · 0 mancanti · 0 dinamiche

| Chiamata | Riga | Trovata | Nota |
|---|---|---|---|
| `GET /health` | 562 | ✅ |  |
| `GET /version` | 562 | ✅ |  |
| `GET /admin/analytics` | 591 | ✅ |  |
| `GET /admin/tasks` | 592 | ✅ |  |
| `GET /admin/roadmap` | 595 | ✅ |  |
| `GET /admin/status` | 675 | ✅ |  |
| `GET /admin/brain` | 675 | ✅ |  |
| `GET /admin/brain/notes` | 717 | ✅ |  |
| `GET /admin/brain/graph` | 721 | ✅ |  |
| `GET /admin/insights` | 738 | ✅ |  |
| `GET /admin/learning` | 746 | ✅ |  |
| `GET /admin/proposals` | 753 | ✅ |  |
| `POST /admin/proposals/approve` | 761 | ✅ |  |
| `POST /admin/proposals/dismiss` | 762 | ✅ |  |
| `POST /admin/tasks/transition` | 764 | ✅ |  |
| `POST /admin/tasks` | 792 | ✅ |  |
| `POST /admin/tasks/close` | 793 | ✅ |  |
| `GET /admin/usage` | 799 | ✅ |  |
| `GET /admin/events` | 808 | ✅ |  |
| `GET /admin/tenants` | 816 | ✅ |  |
| `GET /admin/clients` | 820 | ✅ |  |
| `POST /admin/clients/pin` | 829 | ✅ |  |
| `POST /admin/clients/status` | 833 | ✅ |  |
| `POST /chat` | 954 | ✅ |  |
| `POST /admin/tenants` | 1179 | ✅ |  |
| `POST /admin/tenants/revoke` | 1181 | ✅ |  |
| `POST /admin/clients` | 1200 | ✅ |  |
| `POST /admin/clients/ghost` | 837 | ✅ |  |
| `POST /client/chat` | 953 | ✅ |  |
| `GET /client/me` | 1245 | ✅ |  |
| `POST /client/logout` | 1266 | ✅ |  |
| `POST /client/login` | 1282 | ✅ |  |

## Contratto console → servizio `orch`
14 rotte trovate · 0 mancanti · 0 dinamiche

| Chiamata | Riga | Trovata | Nota |
|---|---|---|---|
| `GET /health` | 563 | ✅ |  |
| `GET /agents` | 593 | ✅ |  |
| `GET /contradictions` | 594 | ✅ |  |
| `GET /agents/dispatches` | 856 | ✅ |  |
| `POST /agents/route` | 866 | ✅ |  |
| `GET /nodes/recent` | 871 | ✅ |  |
| `GET /templates` | 887 | ✅ |  |
| `POST /docs/generate` | 889 | ✅ |  |
| `POST /maintenance/run` | 890 | ✅ |  |
| `POST /connectors/sync` | 891 | ✅ |  |
| `GET /version` | 899 | ✅ |  |
| `GET /ready` | 899 | ✅ |  |
| `POST /nodes/promote` | 1174 | ✅ |  |
| `POST /contradictions/resolve` | 1175 | ✅ |  |
## Eccezioni dichiarate

Nessuna: ogni chiamata del pannello ha la sua rotta. I file
tests/contract_exceptions.json di entrambi i repo sono vuoti. Una futura
eccezione richiede motivazione scritta, pena il fallimento del test.
