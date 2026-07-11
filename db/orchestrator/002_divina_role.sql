-- ═══════════════════════════════════════════════════════════════════════════
-- DIVINA — FASE 1: RUOLO POSTGRES DEDICATO · PROPOSTA, NON APPLICARE
-- ═══════════════════════════════════════════════════════════════════════════
-- Da eseguire A MANO (SQL editor Supabase, come postgres) DOPO 001_divina_schema.sql
-- e dopo revisione. Sostituire la password col valore generato (poi in env Railway
-- del servizio Divina come DIVINA_DATABASE_URL: postgresql://divina:<pwd>@<pooler>/postgres).
--
-- Principio del minimo privilegio (rischio R3 della ricognizione):
--   · accesso SOLO alle 8 tabelle nuove + INSERT sull'audit (access_logs)
--   · lettura anagrafica (organizations/tenants/sub_tenants) per risolvere i code
--   · NESSUN accesso a: api_keys, documents, key_usage, analytics_events
--     (i gap si leggono via API Ember /admin/learning, non dal DB)
--   · niente DELETE da nessuna parte: si archivia (status), non si cancella
--   · il ruolo NON bypassa la RLS: come Ember, imposta i GUC ovyon.* per ogni
--     transazione (SET LOCAL ovyon.allowed_orgs/... ) → isolamento identico.
-- ═══════════════════════════════════════════════════════════════════════════

create role divina login password 'CAMBIAMI-password-forte'
    nosuperuser nocreatedb nocreaterole noreplication;

grant usage on schema public to divina;
grant usage on schema ovyon  to divina;

-- funzioni RLS (SECURITY DEFINER, sola lettura dei GUC)
grant execute on all functions in schema ovyon to divina;

-- anagrafica in sola lettura (risoluzione code → uuid)
grant select on organizations, tenants, sub_tenants to divina;

-- tabelle Divina: lettura/scrittura senza delete
grant select, insert, update on raw_sources, wiki_nodes, node_links,
    contradictions, client_connectors to divina;

-- configurazione: gli agenti/skill/template si leggono; si scrivono via master
-- (pannello/CLI con GUC master), quindi al ruolo basta select + insert/update
-- per i soli template per-tenant (Beatrice) e lo stato dei connettori.
grant select on agents, skills to divina;
grant select, insert, update on doc_templates to divina;

-- audit: append-only (mai select — l'audit si legge da Ember /admin/access-logs)
grant insert on access_logs to divina;

-- ── Verifiche post-applicazione (da eseguire e conservare l'esito) ───────────
-- 1) Il ruolo NON vede le chiavi:      set role divina; select * from api_keys;        -- deve fallire
-- 2) La RLS isola: come divina, con    set local ovyon.allowed_tenants='ats';
--    select count(*) from wiki_nodes;                                                  -- solo nodi ats
-- 3) Niente delete:                    delete from wiki_nodes;                          -- deve fallire
-- 4) Audit scrivibile ma non leggibile: insert ok in access_logs, select negato.
