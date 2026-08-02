-- ═════════════════════════════════════════════════════════════════════════
-- OVYON · tenant_flags.buchi — «il cliente vede le domande rimaste senza
-- risposta» (V8/B3).
--
-- Nel pannello del cliente c'è la pagina più utile del blocco: le domande a cui
-- il bot non ha saputo rispondere sui suoi dati, cioè l'elenco di cosa gli
-- conviene aggiungere. Il problema è da dove vengono quelle domande: le hanno
-- scritte i SUOI utenti finali, sul suo sito. Sono dati dei clienti del
-- cliente, e il motore gira ancora in US West.
--
-- Perciò non è un default ma un ACCORDO: una spunta sul record del tenant,
-- come `libera` e `liv3`, che si accende parlandone. Con la spunta spenta la
-- pagina esiste e DICE perché è spenta — «è una decisione da prendere, non un
-- dato che manca». Le domande sono comunque già redatte a monte (redact_pii in
-- metrics), ma la redazione non è il consenso.
--
-- Additiva e idempotente. Non è un prerequisito: colonna assente = spento,
-- che è il freno.
-- ═════════════════════════════════════════════════════════════════════════

alter table tenant_flags
    add column if not exists buchi boolean not null default false;
