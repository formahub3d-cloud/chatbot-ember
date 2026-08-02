-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · client_report — «questa cosa su di noi è sbagliata» (V8/B2).
--
-- La terza persona del sistema è il CLIENTE (ATS come azienda), e finora non
-- esisteva: c'erano l'owner, che vede tutto, e i visitatori del sito del
-- cliente, che vedono solo risposte. Il cliente può adesso guardare la propria
-- knowledge base e dire che una cosa è sbagliata.
--
-- Quello che NON fa, ed è il punto: non modifica niente. Una segnalazione è
-- una PROPOSTA che arriva nella coda dell'owner. La governance non cambia —
-- nel vault scrive una persona sola, dopo aver guardato. Il cliente ottiene la
-- cosa che gli serve davvero (essere ascoltato su ciò che lo riguarda) senza
-- che nessuno gli dia una penna sul cervello di qualcun altro.
--
-- `tenant_code` è il confine: una segnalazione nasce con lo scope della
-- sessione cliente, letto SERVER-SIDE dal cookie. Non arriva dalla richiesta,
-- quindi non si può falsificare cambiando un campo nel browser.
--
-- NON è un prerequisito (regola 1 del V7): senza tabella le segnalazioni
-- vivono in RAM, l'API non fallisce, e `app/dbcheck.py` dichiara che manca.
--
-- Additiva e idempotente.
-- ═════════════════════════════════════════════════════════════════════════

create table if not exists client_report (
    rep_id      uuid primary key default gen_random_uuid(),
    tenant_code text        not null,
    slug        text        not null default '',
    titolo      text        not null default '',
    cosa        text        not null,
    stato       text        not null default 'aperta'
                check (stato in ('aperta', 'accolta', 'respinta')),
    da          text        not null default '',
    created_at  timestamptz not null default now(),
    chiusa_at   timestamptz,
    chiusa_da   text        not null default '',
    risposta    text        not null default ''
);

create index if not exists client_report_aperte_idx
    on client_report (tenant_code, created_at desc)
    where stato = 'aperta';
