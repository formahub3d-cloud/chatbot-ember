-- ============================================================================
-- OVYON — Schema Supabase/Postgres del cervello OVY
-- Sezione 4.1 (ER) + Sezione 9 (RLS multi-livello) del documento di architettura.
-- Modello a tre livelli: organizations > tenants > sub_tenants > documents.
--
-- Bridge con Ember: ogni riga porta anche il CODE testuale (org_code/tenant_code/
-- sub_code) = lo `scope`/segmento usato da Ember (es. 'forma','ats','docs'), così i
-- filtri per grant combaciano senza traduzioni. Vedi ovyon/docs/doc-ovyon-ember-scope.
--
-- Applicazione:  psql "$DATABASE_URL" -f db/ovyon_schema.sql
-- Idempotente:   usa IF NOT EXISTS / CREATE OR REPLACE.
-- ============================================================================

create extension if not exists "pgcrypto";   -- gen_random_uuid()

create schema if not exists ovyon;            -- funzioni helper per la RLS

-- ── Tabelle ER ──────────────────────────────────────────────────────────────

create table if not exists organizations (
    org_id       uuid primary key default gen_random_uuid(),
    code         text unique not null,          -- 'forma' | 'personal' | 'ovyon'
    name         text not null,
    owner_user_id uuid,
    created_at   timestamptz not null default now()
);

create table if not exists tenants (
    tenant_id    uuid primary key default gen_random_uuid(),
    org_id       uuid not null references organizations(org_id) on delete cascade,
    code         text unique not null,          -- 'ats' | 'forma-core' | 'andrea' | 'ovyon' | 'hrh'
    name         text not null,
    status       text not null default 'active',-- 'active' | 'archived'
    created_at   timestamptz not null default now()
);

create table if not exists sub_tenants (
    sub_tenant_id uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references tenants(tenant_id) on delete cascade,
    code         text not null,                 -- cartella intermedia: 'progetti','docs',...
    type         text,                          -- 'progetto' | 'dipendente' | 'collaboratore'
    name         text,
    created_at   timestamptz not null default now(),
    unique (tenant_id, code)
);

create table if not exists documents (
    content_id   uuid primary key default gen_random_uuid(),
    sub_tenant_id uuid references sub_tenants(sub_tenant_id) on delete set null,
    tenant_id    uuid not null references tenants(tenant_id) on delete cascade,
    org_id       uuid not null references organizations(org_id) on delete cascade,
    -- code denormalizzati (velocità RLS + bridge Ember): coincidono con lo scope Qdrant
    org_code     text not null,
    tenant_code  text not null,
    sub_code     text,
    slug         text,                           -- slug Obsidian / payload Qdrant
    title        text,
    path         text,                           -- path relativo nel vault
    type         text,                           -- pdf | markdown | html | codice
    tags         text[] default '{}',
    content_encrypted bytea,                     -- cifratura a livello di colonna (Sez. 9)
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create table if not exists access_logs (
    log_id       uuid primary key default gen_random_uuid(),
    user_id      uuid,
    key_hash     text,                           -- chiave-tenant che ha operato (hashata)
    content_id   uuid references documents(content_id) on delete set null,
    org_code     text,
    tenant_code  text,
    action       text not null,                  -- read | create | update | delete
    detail       text,
    created_at   timestamptz not null default now()
);

-- ── Analytics storiche (opzionale) ──────────────────────────────────────────
-- Eventi conversazione persistiti per lo storico (oltre ai contatori in memoria
-- di Ember). Popolata solo se ANALYTICS_PERSIST=true. La `question` è REDATTA
-- (PII rimosse) a monte da Ember; niente contenuto sensibile in chiaro qui.
create table if not exists analytics_events (
    event_id     bigserial primary key,
    kind         text not null,                  -- chat | gap | feedback_up | feedback_down
    scope        text not null,                  -- chiave scope (ordinata) o '∅'
    question     text,                            -- domanda redatta (può essere NULL)
    created_at   timestamptz not null default now()
);
create index if not exists analytics_events_created_idx on analytics_events (created_at desc);
create index if not exists analytics_events_kind_idx on analytics_events (kind);

-- ── Quota per chiave-tenant (contatore atomico per periodo, es. giorno UTC) ──
create table if not exists key_usage (
    key_hash  text not null,
    period    text not null,                       -- 'YYYY-MM-DD' (giorno UTC)
    count     integer not null default 0,
    primary key (key_hash, period)
);

-- ── Ponte con Ember: chiavi-tenant (hashate) e grant a tre livelli ──────────
-- Le liste di grant sono per CODE testuale = allowed_scopes/orgs/sub_tenants di
-- Ember. '*' in un qualunque array = chiave master (vede tutto).

create table if not exists api_keys (
    key_hash             text primary key,       -- sha256 della chiave in chiaro (mai in chiaro)
    name                 text,
    active               boolean not null default true,
    quota_day            integer not null default 0,   -- 0 = illimitato
    allowed_orgs         text[] not null default '{}',
    allowed_tenants      text[] not null default '{}',  -- storico: allowed_scopes
    allowed_sub_tenants  text[] not null default '{}',
    allowed_origins      text[] not null default '{}',
    branding             jsonb,                          -- white-label per tenant: {title, subtitle, accent, avatar, logo, greeting}
    created_at           timestamptz not null default now()
);

-- ── Indici ──────────────────────────────────────────────────────────────────
create index if not exists idx_tenants_org       on tenants(org_id);
create index if not exists idx_sub_tenants_tenant on sub_tenants(tenant_id);
create index if not exists idx_documents_codes    on documents(org_code, tenant_code, sub_code);
create index if not exists idx_documents_slug      on documents(slug);
create index if not exists idx_access_logs_created on access_logs(created_at);

-- ── updated_at automatico su documents ──────────────────────────────────────
create or replace function ovyon.touch_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists trg_documents_updated on documents;
create trigger trg_documents_updated before update on documents
    for each row execute function ovyon.touch_updated_at();

-- ── Helper RLS: i grant del richiedente arrivano da GUC di sessione ─────────
-- Ember (o il connettore) imposta per-transazione, es:
--   SET LOCAL ovyon.allowed_orgs = 'forma';
--   SET LOCAL ovyon.allowed_tenants = 'ats,forma-core';
--   SET LOCAL ovyon.allowed_sub_tenants = '';
-- Le funzioni sono SECURITY DEFINER e leggono i GUC come liste separate da virgola.

create or replace function ovyon.grants(name text) returns text[]
language sql stable as $$
    select coalesce(
        string_to_array(nullif(current_setting('ovyon.' || name, true), ''), ','),
        '{}'::text[]
    );
$$;

create or replace function ovyon.is_master() returns boolean
language sql stable as $$
    select '*' = any(ovyon.grants('allowed_orgs'))
        or '*' = any(ovyon.grants('allowed_tenants'))
        or '*' = any(ovyon.grants('allowed_sub_tenants'));
$$;

-- Un documento è visibile se master, oppure se soddisfa ALMENO UN livello
-- concesso (OR tra org/tenant/sub) — un grant su org copre i suoi tenant.
create or replace function ovyon.can_read(p_org text, p_tenant text, p_sub text)
returns boolean language sql stable as $$
    select ovyon.is_master()
        or p_org    = any(ovyon.grants('allowed_orgs'))
        or p_tenant = any(ovyon.grants('allowed_tenants'))
        or (p_sub is not null and p_sub = any(ovyon.grants('allowed_sub_tenants')));
$$;

-- ── Row Level Security ──────────────────────────────────────────────────────
alter table documents  enable row level security;
alter table access_logs enable row level security;

drop policy if exists documents_read on documents;
create policy documents_read on documents
    for select using (ovyon.can_read(org_code, tenant_code, sub_code));

drop policy if exists documents_write on documents;
create policy documents_write on documents
    for all using (ovyon.can_read(org_code, tenant_code, sub_code))
             with check (ovyon.can_read(org_code, tenant_code, sub_code));

-- Audit trail: un tenant può inserire solo voci nel PROPRIO scope e rileggere solo
-- le proprie (append-only + isolamento). Ember imposta i GUC ovyon.* via
-- rls.session_grants prima di scrivere (vedi app/tenants.log_access).
drop policy if exists access_logs_insert on access_logs;
create policy access_logs_insert on access_logs
    for insert with check (
        ovyon.is_master()
        or tenant_code = any(ovyon.grants('allowed_tenants'))
        or org_code    = any(ovyon.grants('allowed_orgs'))
        or (tenant_code is null and org_code is null)   -- voci di sistema
    );

drop policy if exists access_logs_read on access_logs;
create policy access_logs_read on access_logs
    for select using (
        ovyon.is_master()
        or tenant_code = any(ovyon.grants('allowed_tenants'))
        or org_code    = any(ovyon.grants('allowed_orgs'))
    );

-- Nota: il ruolo di servizio di Ember (service_role) bypassa la RLS; l'isolamento
-- effettivo si ottiene impostando i GUC ovyon.* per ogni richiesta tenant, oppure
-- connettendosi con un ruolo NON privilegiato su cui la RLS è attiva.

-- ── Vista comoda: grant di una chiave (ciò che Ember legge) ─────────────────
create or replace view ovyon.key_grants as
    select key_hash, name, active, quota_day,
           allowed_orgs, allowed_tenants, allowed_sub_tenants, allowed_origins
    from api_keys;
