-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · tenant_memory — «Cosa so di te» (V8/A).
--
-- Quello che il sistema ha imparato di chi gli parla: preferenze dichiarate,
-- fatti stabili, uno per riga, con la FRASE da cui vengono e quante volte
-- sono stati ripetuti.
--
-- Due colonne meritano una riga di spiegazione, perché sono il disegno:
--
--   chiave/valore  Le preferenze che il motore SA APPLICARE (lingua,
--                  lunghezza). Un fatto senza chiave è contesto per il
--                  prompt; un fatto CON chiave cambia il comportamento. È la
--                  differenza fra ricordare e servirsene — il difetto di Zoey,
--                  che teneva «prefers Italian» e rispondeva in inglese.
--
--   conferme       Quante volte la persona l'ha ridetto. È l'unico criterio
--                  onesto che questa pagina possiede, e per questo qui NON
--                  c'è nessuna colonna `confidence`: una percentuale senza un
--                  criterio dietro è un numero costante travestito da misura.
--
-- Dimenticare: `dimenticato_at` NON è un archivio. Il codice, insieme alla
-- data, SVUOTA fatto/citazione/valore/chiave. La regola del progetto è
-- «nessun DELETE, si archivia», ma l'art. 17 GDPR non si soddisfa con una
-- riga archiviata e il testo ancora dentro. Resta la lapide: che qualcosa è
-- stato dimenticato, quando e da chi — non che cosa.
--
-- NON è un prerequisito (regola 1 del V7): senza questa tabella la memoria
-- vive in RAM finché vive il processo, l'API non fallisce, e `app/dbcheck.py`
-- dichiara che manca e cosa smette di funzionare.
--
-- Additiva e idempotente.
-- ═════════════════════════════════════════════════════════════════════════

create table if not exists tenant_memory (
    mem_id          uuid primary key default gen_random_uuid(),
    tenant_code     text        not null,
    agente          text        not null default 'divina',
    fatto           text        not null default '',
    chiave          text        not null default '',
    valore          text        not null default '',
    origine         text        not null default 'detto',
    citazione       text        not null default '',
    conferme        integer     not null default 1,
    created_at      timestamptz not null default now(),
    last_at         timestamptz not null default now(),
    dimenticato_at  timestamptz,
    dimenticato_da  text        not null default ''
);

-- La pagina legge SEMPRE per tenant, escludendo le lapidi.
create index if not exists tenant_memory_vive_idx
    on tenant_memory (tenant_code, last_at desc)
    where dimenticato_at is null;

-- Una preferenza per chiave e per agente: ridirla conferma, non duplica.
create unique index if not exists tenant_memory_chiave_idx
    on tenant_memory (tenant_code, agente, chiave)
    where chiave <> '' and dimenticato_at is null;
