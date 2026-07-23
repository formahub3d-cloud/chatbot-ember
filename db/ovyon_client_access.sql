-- Accessi console cliente, gestiti da FORMA (app/clientauth.py).
-- La chiave tenant vive SOLO qui (cifrata se CONTENT_ENC_KEY è attiva):
-- il cliente non la vede mai. Nessun DELETE: la rimozione è status='rimosso'.
-- Da applicare sul progetto Supabase OVYON (SQL editor), come gli altri db/*.sql.

create table if not exists client_access (
  id               uuid primary key,
  email            text not null unique,
  display_name     text not null default '',
  tenant_key_enc   text not null,            -- 'enc:<b64 fernet>' | 'plain:<chiave>'
  password_hash    text not null default '', -- scrypt salt$hash — primo accesso
  pin_hash         text not null default '', -- scrypt salt$hash — vuoto = PIN non generato
  status           text not null default 'attivo'
                   check (status in ('attivo','sospeso','rimosso')),
  failed_attempts  int  not null default 0,
  locked           boolean not null default false,
  created_at       timestamptz not null default now(),
  last_login_at    timestamptz
);

create index if not exists client_access_email_idx on client_access (lower(email));

-- RLS: la tabella è raggiunta SOLO dal motore col suo ruolo di servizio;
-- nessun accesso anon/authenticated.
alter table client_access enable row level security;
