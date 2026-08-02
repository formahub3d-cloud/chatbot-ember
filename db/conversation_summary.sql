-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · conversation_summary — la conversazione che dura (V9/D).
--
-- Un riassunto compresso per conversazione, scritto UNA volta quando la
-- conversazione finisce. Serve a riprendere il filo il giorno dopo senza
-- ripetere tutto — soprattutto a voce, dove riformulare è innaturale.
--
-- Perché non si tengono i turni: tenerli tutti è la strada che non scala e che
-- moltiplica i dati personali conservati. Comprimere è insieme la scelta
-- tecnica migliore e quella che tiene meno roba in giro.
--
-- **Il riassunto è un dato personale**, e questa tabella lo tratta come tale:
--   · una riga per conversazione (nessuno storico di versioni);
--   · retention 30 giorni, applicata dal codice ANCHE in lettura, così una riga
--     scaduta non compare nemmeno se la pulizia non è ancora passata;
--   · si CANCELLA, non si archivia — è l'unica altra deroga alla regola
--     «nessun DELETE» insieme a `tenant_memory`, e per la stessa ragione:
--     l'art. 17 non si soddisfa tenendo il testo con una data accanto.
--
-- Quello che NON contiene: lo scope. Un riassunto non è un permesso — uno scope
-- toccato ieri non dà diritti oggi, e i grant si ricalcolano sempre dalla
-- chiave. Metterlo qui sarebbe stato il primo passo per usarlo come filtro.
--
-- NON è un prerequisito (regola 1 del V7): senza tabella i riassunti vivono in
-- RAM, l'API non fallisce, e `app/dbcheck.py` dichiara che manca.
--
-- Additiva e idempotente.
-- ═════════════════════════════════════════════════════════════════════════

create table if not exists conversation_summary (
    sum_id        uuid primary key default gen_random_uuid(),
    tenant_code   text        not null,
    conversazione text        not null,
    testo         text        not null,
    created_at    timestamptz not null default now(),
    unique (tenant_code, conversazione)
);

create index if not exists conversation_summary_recenti_idx
    on conversation_summary (tenant_code, created_at desc);

-- La pulizia oltre la retention. Il codice non si fida di questa riga (filtra
-- anche in lettura), ma tenerla scritta qui è il posto giusto per chi un giorno
-- collegherà un lavoro schedulato:
--   delete from conversation_summary where created_at < now() - interval '30 days';
