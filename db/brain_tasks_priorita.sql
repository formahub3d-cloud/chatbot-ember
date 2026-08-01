-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · brain_tasks — la PRIORITÀ (migrazione additiva e idempotente,
-- stesso stile della migrazione del kind 'audit' del 31/07).
--
-- Il default 'media' non è pigrizia: è onestà. Una task senza priorità
-- dichiarata non è «bassa», è «non ancora giudicata». I tre seed già
-- eseguiti in produzione restano validi (prendono il default); le priorità
-- delle task audit esistenti si assegnano per CHIAVE con
-- scripts/set_priorita_audit_2026_07_31.py — mai a mano.
-- ═════════════════════════════════════════════════════════════════════════

alter table brain_tasks add column if not exists priorita text default 'media';
alter table brain_tasks drop constraint if exists brain_tasks_priorita_chk;
alter table brain_tasks add constraint brain_tasks_priorita_chk
    check (priorita in ('alta','media','bassa'));
