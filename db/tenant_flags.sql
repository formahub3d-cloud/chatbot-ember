-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · tenant_flags — i permessi per-tenant che il SERVER conosce e applica
-- (V5, 01-08). Primo inquilino: liv3 («cancellare e agire fuori»).
--
-- Prima viveva in localStorage: una riga di JavaScript nella console del
-- browser e il guardrail spariva. Regola già scritta e ora rispettata anche
-- qui: «il flag sta sul record del tenant, mai nella richiesta».
-- Default SPENTO: la riga assente È il freno.
-- Additiva e idempotente, come le altre migrazioni.
-- ═════════════════════════════════════════════════════════════════════════

create table if not exists tenant_flags (
    tenant_code  text primary key,
    liv3         boolean not null default false,
    updated_by   text,
    updated_at   timestamptz not null default now()
);
