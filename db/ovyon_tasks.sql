-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · brain_tasks — coda task PERSISTENTE del cervello (additiva)
-- Da applicare DOPO ovyon_schema.sql. Prima tranche della task di roadmap
-- «coda-task-persistente» (console /panel/ → tab "Task del cervello").
--
-- Filosofia: le task di apprendimento (in-memory) si rigenerano dai segnali;
-- queste sono le task OPERATIVE e sopravvivono al redeploy. Nessun DELETE:
-- una task si chiude ('fatta') o si archivia ('archiviata'), sempre con il
-- nome di chi decide (closed_by) — come resolved_by delle contraddizioni.
-- Titoli e note arrivano GIÀ REDATTI (niente PII) da Divina.
-- ═════════════════════════════════════════════════════════════════════════

create table if not exists brain_tasks (
    task_id      uuid primary key default gen_random_uuid(),
    kind         text not null default 'manuale',   -- manuale | gap | feedback | agente
    scope        text,                              -- area del cervello (informativo)
    title        text not null,
    note         text,
    status       text not null default 'aperta',    -- aperta | fatta | archiviata
    created_at   timestamptz not null default now(),
    closed_at    timestamptz,
    closed_by    text,                              -- umano che chiude (obbligatorio lato API)
    constraint brain_tasks_status_chk check (status in ('aperta','fatta','archiviata')),
    constraint brain_tasks_kind_chk   check (kind in ('manuale','gap','feedback','agente'))
);

create index if not exists brain_tasks_status_idx  on brain_tasks (status, created_at desc);
create index if not exists brain_tasks_created_idx on brain_tasks (created_at desc);
