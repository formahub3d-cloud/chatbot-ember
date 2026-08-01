-- V5b (01-08) · Punto 9: il commit che l'ultima ingest ha DAVVERO letto.
-- L'allarme del pannello confronta questo col commit del vault locale
-- (vault_info): il tempo è un'approssimazione della freschezza, il
-- confronto fra i due commit È la freschezza. Riga unica, come brain_graph.
create table if not exists ingest_meta (
  id           int primary key default 1,
  vault_commit text not null,
  at           timestamptz not null default now()
);
