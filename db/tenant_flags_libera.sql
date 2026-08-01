-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · tenant_flags.libera — «conoscenza generale fuori dal vault», V6/B2.
--
-- Il TONO della conversazione vale per tutti (saluti, chiacchiera, ammettere
-- il buco con una frase umana). Il CONTENUTO fuori dal vault no: il widget
-- sul sito di un cliente non può inventare sul cliente, perché la promessa
-- che si vende è che ciò che dice viene dal loro materiale.
--
-- Perciò è una spunta sul RECORD DEL TENANT — stessa famiglia di `owner` e
-- `liv3` — e mai una scelta nella richiesta. Default SPENTO: la colonna
-- assente o falsa È il freno.
--
-- Additiva e idempotente, come le altre migrazioni.
-- ═════════════════════════════════════════════════════════════════════════

alter table tenant_flags
    add column if not exists libera boolean not null default false;
