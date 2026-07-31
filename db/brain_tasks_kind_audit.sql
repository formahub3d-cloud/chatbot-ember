-- M2 (31-07-2026): il vincolo sul kind di brain_tasks non ammetteva né
-- 'azione' (usato dal codice da Z3: inserti destinati a FALLIRE in silenzio
-- sul CHECK — buco latente trovato scrivendo il seed dell'audit) né 'audit'
-- (le task nate dagli audit del pannello). Migrazione additiva, idempotente.
alter table brain_tasks drop constraint if exists brain_tasks_kind_chk;
alter table brain_tasks add constraint brain_tasks_kind_chk
    check (kind in ('manuale','gap','feedback','agente','azione','audit'));
