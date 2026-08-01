-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · brain_tasks — lo stato «da-verificare» (V7/C, task audit-…-32)
--
-- Il merge di una PR NON chiude le task che nomina: le mette in uno stato
-- intermedio. Diventano «fatta» solo dopo che una persona le ha guardate.
-- Se il merge chiudesse da solo, il pannello direbbe «fatto» su cose che
-- nessuno ha aperto — ed è esattamente così che sono nate le tre affermazioni
-- sbagliate corrette l'1/08 (il case study, le chiavi «già nei siti», e
-- l'allarme che misurava le ore invece dei commit).
--
-- NON è un prerequisito per il merge (regola 1 del giro V7): senza questa
-- migrazione il motore lascia la task APERTA e le attacca una nota che dice
-- «da verificare» + il numero della PR, e /admin/status dichiara che manca.
-- Il degrado è dichiarato, non silenzioso.
--
-- Additiva e idempotente.
-- ═════════════════════════════════════════════════════════════════════════

alter table brain_tasks drop constraint if exists brain_tasks_status_chk;
alter table brain_tasks add constraint brain_tasks_status_chk
    check (status in ('aperta','in-approvazione','approvata','in-esecuzione',
                      'da-verificare','fatta','fallita','archiviata'));
