-- ============================================================================
-- OVYON — Seed di ESEMPIO (ambiente di prova). NON contiene chiavi reali.
-- Rispecchia tenants.example.json nel modello a tre livelli.
-- Le chiavi-tenant vanno inserite HASHATE (sha256 della chiave in chiaro):
--   select encode(digest('CHIAVE_ATS','sha256'),'hex');
-- ============================================================================

-- ── Organizzazioni ─────────────────────────────────────────────────────────
insert into organizations (code, name) values
    ('forma',    'FORMA Hub (Lock Light srl)'),
    ('personal', 'Personal Brand — Andrea Aloia'),
    ('ovyon',    'OVYON')
on conflict (code) do nothing;

-- ── Tenant (code = scope Divina) ────────────────────────────────────────────
insert into tenants (org_id, code, name)
select o.org_id, v.code, v.name
from (values
    ('forma', 'forma-core', 'FORMA (interno / dogfood)'),
    ('forma', 'ats',        'Al Tuo Servizio (ATS)'),
    ('forma', 'hrh',        'Home Restaurant Hotel'),
    ('personal', 'andrea',  'Andrea Aloia'),
    ('ovyon', 'ovyon',      'OVYON')
) as v(org_code, code, name)
join organizations o on o.code = v.org_code
on conflict (code) do nothing;

-- ── Chiavi-tenant (HASHATE) con grant a tre livelli ────────────────────────
-- Esempio: FORMA interno vede forma-core + andrea; ATS vede solo ats.
-- Sostituisci gli hash con quelli delle tue chiavi reali (mai in chiaro nel repo).
insert into api_keys (key_hash, name, allowed_tenants, allowed_orgs, allowed_origins) values
    (encode(digest('CHIAVE_FORMA_INTERNO','sha256'),'hex'),
     'FORMA (interno)', array['forma-core','andrea'], array[]::text[], array[]::text[]),
    (encode(digest('CHIAVE_ATS','sha256'),'hex'),
     'ATS', array['ats'], array[]::text[], array['https://www.altuoservizio.it']),
    (encode(digest('CHIAVE_HRH','sha256'),'hex'),
     'HRH', array['hrh'], array[]::text[], array['https://www.homerestauranthotel.it'])
on conflict (key_hash) do nothing;
