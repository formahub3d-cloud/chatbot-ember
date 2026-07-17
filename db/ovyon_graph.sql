-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · brain_graph — il grafo REALE del cervello (additiva)
-- Da applicare DOPO ovyon_schema.sql. Tranche 2 della convergenza console:
-- nodi = note del vault, sinapsi = [[link]] tra note, ricostruito a ogni
-- ingest completa (app/ingest.py passo 5 → app/brain.save_graph) e mostrato
-- nella tab «Cervello vivo» della console (/admin/brain/graph).
--
-- Riga UNICA jsonb (id=1): il grafo si sostituisce in blocco a ogni ingest —
-- niente storico qui (la fonte di verità resta il vault). Senza questa
-- tabella il grafo vive solo in-memory e si azzera al redeploy.
-- ═════════════════════════════════════════════════════════════════════════

create table if not exists brain_graph (
    id           smallint primary key default 1,
    graph        jsonb not null,                  -- {nodes:[{slug,title,tenant}], links:[[i,j]], generated_at}
    generated_at timestamptz not null default now(),
    constraint brain_graph_singleton check (id = 1)
);
