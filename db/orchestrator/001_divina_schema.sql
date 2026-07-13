-- ═══════════════════════════════════════════════════════════════════════════
-- DIVINA (ovy-orchestrator) — FASE 1: SCHEMA DATI · PROPOSTA, NON APPLICARE
-- ═══════════════════════════════════════════════════════════════════════════
-- Stato: BOZZA da rivedere con Andrea. Si applica A MANO sul progetto Supabase
-- (SQL editor) SOLO dopo revisione, insieme a 002_divina_role.sql.
--
-- Principi (dalla ricognizione approvata + decisioni 2026-07-11):
--   · SOLO ADDITIVO: nessuna modifica alle tabelle esistenti di Divina.
--   · Ogni tabella-dati porta org_code/tenant_code e riusa il pattern RLS
--     esistente (ovyon.can_read + GUC di sessione) → isolamento identico a Divina.
--   · REGOLA FERREA DIVINA: il tier (Dante/Virgilio/Beatrice) NON amplia mai lo
--     scope dei DATI. I campi tier esistono SOLO sulle tabelle di capability
--     (skills, doc_templates), MAI sulle tabelle di contenuto (raw_sources,
--     wiki_nodes, node_links, contradictions).
--   · Le contraddizioni NON si risolvono mai in automatico (resolved_by = umano).
--   · wiki_nodes vive SOLO qui (Q7): il vault resta la fonte di verità FORMA;
--     la promozione bozza→nota del vault è manuale.
-- Prerequisiti: ovyon_schema.sql già applicato (funzioni ovyon.grants/is_master/
-- can_read/touch_updated_at, tabelle organizations/tenants, RLS attiva).
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. raw_sources — materiale grezzo in ingresso (web, upload, connettori) ──
create table if not exists raw_sources (
    source_id    uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references tenants(tenant_id) on delete cascade,
    org_code     text not null,
    tenant_code  text not null,
    kind         text not null check (kind in ('web','upload','connector','manual')),
    url          text,                            -- se kind=web/connector
    title        text,
    content      text,                            -- testo grezzo (MAI contratti/PII qui)
    content_hash text,                            -- sha256 per dedup
    status       text not null default 'pending'
                 check (status in ('pending','processed','discarded','error')),
    error        text,
    fetched_by   text,                            -- skill/agente che l'ha raccolta (audit)
    created_at   timestamptz not null default now(),
    processed_at timestamptz
);
create index if not exists idx_raw_sources_tenant  on raw_sources(tenant_code, status);
create unique index if not exists idx_raw_sources_dedup
    on raw_sources(tenant_code, content_hash) where content_hash is not null;

-- ── 2. wiki_nodes — conoscenza strutturata per-tenant (l'output dell'ingest) ──
create table if not exists wiki_nodes (
    node_id      uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references tenants(tenant_id) on delete cascade,
    org_code     text not null,
    tenant_code  text not null,
    kind         text not null check (kind in ('entita','concetto','fonte','faq','evento')),
    slug         text not null,                   -- stabile, per link e dedup
    title        text not null,
    summary      text,
    content      text,
    tags         text[] not null default '{}',
    -- ciclo di vita con conferma umana: nasce 'bozza', diventa 'verificato' solo
    -- dopo revisione; 'promosso' = portato a mano nel vault (solo FORMA).
    status       text not null default 'bozza'
                 check (status in ('bozza','verificato','promosso','archiviato')),
    source_id    uuid references raw_sources(source_id) on delete set null,  -- provenienza (verifica fonti)
    confidence   numeric(3,2) check (confidence between 0 and 1),  -- fiducia del compilatore
    created_by   text,                            -- agente/skill (audit)
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (tenant_code, slug)
);
create index if not exists idx_wiki_nodes_tenant on wiki_nodes(tenant_code, status);
create index if not exists idx_wiki_nodes_tags   on wiki_nodes using gin(tags);
drop trigger if exists trg_wiki_nodes_updated on wiki_nodes;
create trigger trg_wiki_nodes_updated before update on wiki_nodes
    for each row execute function ovyon.touch_updated_at();

-- ── 3. node_links — relazioni tra nodi (il "grafo" per-tenant) ───────────────
create table if not exists node_links (
    link_id      uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references tenants(tenant_id) on delete cascade,
    org_code     text not null,
    tenant_code  text not null,
    node_a       uuid not null references wiki_nodes(node_id) on delete cascade,
    node_b       uuid not null references wiki_nodes(node_id) on delete cascade,
    relation     text not null default 'correlato'
                 check (relation in ('correlato','parte_di','fonte_di','contraddice','aggiorna')),
    created_by   text,                            -- agente/skill (audit)
    created_at   timestamptz not null default now(),
    check (node_a <> node_b),
    unique (node_a, node_b, relation)
);
create index if not exists idx_node_links_tenant on node_links(tenant_code);

-- ── 4. contradictions — coda di revisione UMANA (mai auto-risoluzione) ───────
create table if not exists contradictions (
    contradiction_id uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references tenants(tenant_id) on delete cascade,
    org_code     text not null,
    tenant_code  text not null,
    node_a       uuid references wiki_nodes(node_id) on delete set null,
    node_b       uuid references wiki_nodes(node_id) on delete set null,
    description  text not null,                   -- cosa confligge, citazioni incluse
    status       text not null default 'irrisolto'
                 check (status in ('irrisolto','risolto','ignorato')),
    detected_by  text,                            -- agente che l'ha rilevata
    resolved_by  text,                            -- SEMPRE un umano (mai un agente)
    resolution   text,                            -- come è stata risolta
    created_at   timestamptz not null default now(),
    resolved_at  timestamptz
);
create index if not exists idx_contradictions_tenant on contradictions(tenant_code, status);

-- ── 5. agents — agenti di sistema e di dominio ───────────────────────────────
-- tenant_id NULL = agente di sistema (Ricercatore, Ingest, Cross-referencer,
-- Manutentore). Gli agenti di dominio hanno tenant e vincoli macchina-leggibili.
create table if not exists agents (
    agent_id     uuid primary key default gen_random_uuid(),
    tenant_id    uuid references tenants(tenant_id) on delete cascade,   -- null = sistema
    org_code     text,
    tenant_code  text,
    name         text unique not null,            -- 'ricercatore','ingest',... | 'forma','ovyon','hrh','ats'
    role         text not null check (role in ('system','dominio')),
    -- Profilo narrativo Divina di DEFAULT per l'output (solo agenti di dominio).
    -- Il tier effettivo della richiesta resta quello della chiave (api_keys.branding.tier):
    -- l'archetype qui NON scavalca il gating e NON tocca lo scope dei dati.
    archetype    text check (archetype in ('dante','virgilio','beatrice')),
    prompt       text not null,
    constraints  jsonb not null default '{}',     -- es. {"anonymize_clients":true,"prices":"range_only"}
    tools        text[] not null default '{}',    -- nomi skill assegnate
    active       boolean not null default true,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    -- dominio ⇒ tenant_code obbligatorio (tenant_id si valorizza all'applicazione,
    -- vedi UPDATE nel seed: i code sono la chiave portabile, le uuid sono del DB live)
    check (role = 'system' or tenant_code is not null)
);
drop trigger if exists trg_agents_updated on agents;
create trigger trg_agents_updated before update on agents
    for each row execute function ovyon.touch_updated_at();

-- ── 6. skills — libreria funzioni richiamabili (globale) ─────────────────────
create table if not exists skills (
    skill_id     uuid primary key default gen_random_uuid(),
    name         text unique not null,            -- 'web-research','ingest-document',...
    description  text,
    input_schema  jsonb not null default '{}',    -- JSON Schema dell'input
    output_schema jsonb not null default '{}',
    handler      text not null,                   -- route interna del servizio Divina
    -- Gating Divina: tier minimo della CHIAVE per invocarla dall'esterno.
    -- (capability, non dati: le skill interne di pipeline restano min_tier='starter'
    --  perché girano per conto del sistema, non del cliente)
    min_tier     text not null default 'starter'
                 check (min_tier in ('starter','pro','enterprise')),
    active       boolean not null default true,
    created_at   timestamptz not null default now()
);

-- ── 7. doc_templates — template documenti per area business ─────────────────
-- tenant_id NULL = template di sistema (Virgilio); i template su misura di un
-- cliente (Beatrice) hanno tenant_id valorizzato.
create table if not exists doc_templates (
    template_id  uuid primary key default gen_random_uuid(),
    tenant_id    uuid references tenants(tenant_id) on delete cascade,   -- null = sistema
    org_code     text,
    tenant_code  text,
    name         text not null,
    business_area text not null,                  -- 'proposta-commerciale','report','brief','documentazione'
    format       text not null default 'markdown' check (format in ('markdown','docx','pdf')),
    min_tier     text not null default 'pro'
                 check (min_tier in ('starter','pro','enterprise')),
    content_template text not null,               -- markdown con {placeholder}
    constraints  jsonb not null default '{}',     -- eredita/estende i vincoli dell'agente di dominio
    active       boolean not null default true,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
create unique index if not exists idx_doc_templates_name
    on doc_templates((coalesce(tenant_code, '~sistema')), name);
drop trigger if exists trg_doc_templates_updated on doc_templates;
create trigger trg_doc_templates_updated before update on doc_templates
    for each row execute function ovyon.touch_updated_at();

-- ── 8. client_connectors — fondamenta Fase 5 (webhook + sync di fallback) ────
create table if not exists client_connectors (
    connector_id uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references tenants(tenant_id) on delete cascade,
    org_code     text not null,
    tenant_code  text not null,
    platform     text not null check (platform in ('sito','crm','social','ecommerce','altro')),
    mode         text not null default 'webhook' check (mode in ('webhook','poll')),
    -- MAI credenziali in chiaro: solo il NOME del secret (env Railway / Supabase Vault)
    credentials_ref text,
    config       jsonb not null default '{}',     -- url, frequenza poll, mapping campi
    status       text not null default 'inattivo' check (status in ('inattivo','attivo','errore')),
    error        text,
    last_sync    timestamptz,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
create index if not exists idx_client_connectors_tenant on client_connectors(tenant_code);
drop trigger if exists trg_client_connectors_updated on client_connectors;
create trigger trg_client_connectors_updated before update on client_connectors
    for each row execute function ovyon.touch_updated_at();

-- ═══ ROW LEVEL SECURITY — stesso pattern di documents/access_logs ════════════
alter table raw_sources       enable row level security;
alter table wiki_nodes        enable row level security;
alter table node_links        enable row level security;
alter table contradictions    enable row level security;
alter table agents            enable row level security;
alter table skills            enable row level security;
alter table doc_templates     enable row level security;
alter table client_connectors enable row level security;

-- Tabelle-dati per-tenant: lettura e scrittura solo nello scope concesso (o master).
drop policy if exists raw_sources_rw on raw_sources;
create policy raw_sources_rw on raw_sources
    for all using (ovyon.can_read(org_code, tenant_code, null))
             with check (ovyon.can_read(org_code, tenant_code, null));

drop policy if exists wiki_nodes_rw on wiki_nodes;
create policy wiki_nodes_rw on wiki_nodes
    for all using (ovyon.can_read(org_code, tenant_code, null))
             with check (ovyon.can_read(org_code, tenant_code, null));

drop policy if exists node_links_rw on node_links;
create policy node_links_rw on node_links
    for all using (ovyon.can_read(org_code, tenant_code, null))
             with check (ovyon.can_read(org_code, tenant_code, null));

drop policy if exists contradictions_rw on contradictions;
create policy contradictions_rw on contradictions
    for all using (ovyon.can_read(org_code, tenant_code, null))
             with check (ovyon.can_read(org_code, tenant_code, null));

drop policy if exists client_connectors_rw on client_connectors;
create policy client_connectors_rw on client_connectors
    for all using (ovyon.can_read(org_code, tenant_code, null))
             with check (ovyon.can_read(org_code, tenant_code, null));

-- agents: le righe di SISTEMA (tenant_code null) sono leggibili da tutti i
-- contesti autenticati; quelle di dominio solo nel proprio scope. Scrive solo master.
drop policy if exists agents_read on agents;
create policy agents_read on agents
    for select using (tenant_code is null or ovyon.can_read(org_code, tenant_code, null));
drop policy if exists agents_write on agents;
create policy agents_write on agents
    for all using (ovyon.is_master()) with check (ovyon.is_master());

-- skills: catalogo globale in sola lettura; scrive solo master.
drop policy if exists skills_read on skills;
create policy skills_read on skills for select using (true);
drop policy if exists skills_write on skills;
create policy skills_write on skills
    for all using (ovyon.is_master()) with check (ovyon.is_master());

-- doc_templates: sistema visibile a tutti; per-tenant solo nel proprio scope;
-- scrittura: master (sistema) o scope proprio (template su misura Beatrice).
drop policy if exists doc_templates_read on doc_templates;
create policy doc_templates_read on doc_templates
    for select using (tenant_code is null or ovyon.can_read(org_code, tenant_code, null));
drop policy if exists doc_templates_write on doc_templates;
create policy doc_templates_write on doc_templates
    for all using (ovyon.is_master() or ovyon.can_read(org_code, tenant_code, null))
             with check (ovyon.is_master() or ovyon.can_read(org_code, tenant_code, null));

-- ═══ SEED PROPOSTO (rivedere i prompt prima di applicare) ════════════════════
-- Agenti di SISTEMA (tenant null) — prompt sintetici, si affinano in Fase 2.
insert into agents (name, role, prompt, tools) values
 ('ricercatore','system','Cerca sul web (Tavily) materiale attinente al topic richiesto. Riporta SOLO fatti con URL di provenienza. Non inventare. Output → raw_sources.', '{web-research}'),
 ('ingest','system','Trasforma una raw_source in wiki_nodes strutturati (entita/concetto/fonte/faq): titolo, summary, contenuto, tag. Stato SEMPRE bozza. Cita source_id.', '{ingest-document,update-index}'),
 ('cross-referencer','system','Collega ogni nodo nuovo ai nodi esistenti del TENANT (node_links). Se due nodi si contraddicono: registra in contradictions e NON modificare i nodi.', '{cross-reference,contradiction-check}'),
 ('manutentore','system','Schedulato: segnala duplicati e nodi orfani portandoli a stato archiviato (mai delete), aggiorna gli indici. Ogni azione va in access_logs.', '{update-index}')
on conflict (name) do nothing;

-- Agenti di DOMINIO (vincoli decisi l'11/07 — workspace-decisioni-orchestrator).
-- NB: tenant_id va valorizzato al momento dell'applicazione con le uuid reali:
--   update agents set tenant_id = (select tenant_id from tenants where code = agents.tenant_code) where role='dominio';
insert into agents (name, role, org_code, tenant_code, archetype, prompt, constraints, tools) values
 ('forma','dominio','forma','forma-core','virgilio',
  'Agente del dominio FORMA. Produci contenuti e documenti pescando dai wiki_nodes del tenant forma-core.',
  '{"anonymize_clients": true, "prices": "range_only", "verify_sources": true}',
  '{generate-doc,summarize-thread,web-research}'),
 ('ovyon','dominio','ovyon','ovyon','beatrice',
  'Agente del dominio OVYON: prodotto e possibilità. Tono tecnico-visionario.',
  '{"tone": "tecnico-visionario", "no_release_dates": true, "internal_secret": true, "internal_access": "solo Andrea via chiave FORMA master"}',
  '{generate-doc,summarize-thread}'),
 ('hrh','dominio','forma','hrh','virgilio',
  'Agente del dominio HRH. Libero sui contenuti HRH del tenant hrh.',
  '{"data_visibility": "solo tenant hrh", "client_data_secret": true}',
  '{generate-doc,summarize-thread}'),
 ('ats','dominio','forma','ats','virgilio',
  'Agente del dominio ATS. Libero sui contenuti ATS del tenant ats.',
  '{"data_visibility": "solo tenant ats", "client_data_secret": true}',
  '{generate-doc,summarize-thread}')
on conflict (name) do nothing;

-- Skill library (handler = route del servizio Divina, Fase 2).
insert into skills (name, description, handler, min_tier) values
 ('web-research','Ricerca web via Tavily; ritorna fonti {url,titolo,estratto}','/skills/web-research','starter'),
 ('ingest-document','raw_source → wiki_nodes strutturati (stato bozza)','/skills/ingest-document','starter'),
 ('cross-reference','Collega un nodo ai nodi esistenti del tenant','/skills/cross-reference','starter'),
 ('contradiction-check','Rileva conflitti tra nodi → coda contradictions','/skills/contradiction-check','starter'),
 ('generate-doc','Template + wiki_nodes del tenant + vincoli dominio → documento','/skills/generate-doc','pro'),
 ('summarize-thread','Riassume una conversazione/thread nel formato del tier','/skills/summarize-thread','pro'),
 ('update-index','Ricalcola indici/contatori dopo le scritture','/skills/update-index','starter')
on conflict (name) do nothing;

-- Template documenti di sistema (bozze — contenuti da rifinire in Fase 4).
insert into doc_templates (name, business_area, min_tier, content_template) values
 ('proposta-commerciale-forma','proposta-commerciale','pro',
  '# Proposta — {cliente_anonimo}\n\n## Contesto\n{contesto}\n\n## Soluzione proposta\n{soluzione}\n\n## Investimento (range)\n{prezzo_range}\n\n## Fonti\n{fonti_verificate}'),
 ('report-ovyon','report','pro',
  '# Report OVYON — {titolo}\n\n{corpo}\n\n> Visione: {visione}\n\n*(niente date di rilascio)*'),
 ('brief-hrh','brief','pro','# Brief HRH — {titolo}\n\n{corpo}'),
 ('documentazione-ats','documentazione','pro','# Documentazione ATS — {titolo}\n\n{corpo}')
on conflict do nothing;
