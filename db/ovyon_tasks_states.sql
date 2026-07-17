-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · brain_tasks — macchina a stati con APPROVAZIONE (additiva)
-- Da applicare DOPO ovyon_tasks.sql. Brief "Divina verso Zoey" (2026-07-17),
-- task Z2: le azioni dei companion con effetto esterno non partono mai senza
-- l'ok dell'owner — è il differenziatore di Divina ("azioni fidate").
--
-- Stati (nomi italiani, mapping col brief):
--   aperta (pending) → in-approvazione (awaiting_approval) → approvata
--   (approved) → in-esecuzione (executing) → fatta (done) | fallita (failed)
--   | archiviata (archived). Mai DELETE: si archivia. Ogni transizione umana
--   registra chi decide (approved_by / closed_by).
-- ═════════════════════════════════════════════════════════════════════════

alter table brain_tasks drop constraint if exists brain_tasks_status_chk;
alter table brain_tasks add constraint brain_tasks_status_chk
    check (status in ('aperta','in-approvazione','approvata','in-esecuzione',
                      'fatta','fallita','archiviata'));

alter table brain_tasks drop constraint if exists brain_tasks_kind_chk;
alter table brain_tasks add constraint brain_tasks_kind_chk
    check (kind in ('manuale','gap','feedback','agente','azione'));

alter table brain_tasks add column if not exists approved_by     text;
alter table brain_tasks add column if not exists approved_at     timestamptz;
alter table brain_tasks add column if not exists started_at      timestamptz;
alter table brain_tasks add column if not exists error           text;
alter table brain_tasks add column if not exists idempotency_key text;

-- Idempotenza (Z3): la stessa azione non può essere accodata due volte.
create unique index if not exists brain_tasks_idem_idx
    on brain_tasks (idempotency_key) where idempotency_key is not null;
