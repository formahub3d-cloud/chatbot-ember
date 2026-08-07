#!/usr/bin/env python3
"""S5.1c · Quante volte NON abbiamo saputo misurare un consumo.

È il numero da cui nascerà la soglia del secondo freno, e serve a sorvegliare
una cosa che il 7/08 si è già rivelata diversa da come la immaginavamo:
**`usage` arriva anche senza `MISTRAL_STREAM_USAGE`**. Le prime tre chat vere
sono uscite `misurato` col flag spento, quindi il flag resta spento e questo
rapporto non serve più a verificarne l'accensione — serve a **accorgersi se un
giorno smette di arrivare**, che è il caso in cui il conto si sfalsa in
silenzio.

Legge e basta: nessuna scrittura, nessuna decisione. Si connette con la
`DATABASE_URL_LEDGER` (ruolo `divina`), che ha `select` e `insert` — quindi
anche sbagliando non può rovinare niente.

**Il GUC va impostato, altrimenti il rapporto è cieco e non lo dice.** Il ruolo
`divina` ha la RLS attiva: la policy chiama `ovyon.can_read`, che legge
`ovyon.allowed_tenants` dalla sessione. Senza quel GUC la `SELECT` non dà
errore — **restituisce zero righe**, e lo script stampava «nessun addebito nel
periodo» a registro pieno. Trovato da Kimi in produzione il 7/08, con la query
manuale che le righe le vedeva: è la RLS che fa il suo lavoro, non un guasto.

Da qui la regola: `--tenant` è OBBLIGATORIO. `--tenant '*'` dà la vista
completa (è il carattere che `ovyon.can_read` tratta come «tutti», lo stesso
che l'orchestratore usa per l'anagrafica); un codice singolo dà quel cliente.
Non c'è un default, apposta: un default silenzioso qui vuol dire un rapporto
che sembra vuoto invece di uno che chiede una cosa.

Uso:
    DATABASE_URL_LEDGER='postgresql://…' python3 scripts/rapporto_misura.py --tenant '*'
    DATABASE_URL_LEDGER='…' python3 scripts/rapporto_misura.py --tenant forma-core --giorni 7

Gira col Python di sistema: l'unica dipendenza è psycopg2, che il motore ha già.
"""
import os
import sys

QUERY_TOTALI = """
select coalesce(misura, 'senza-colonna') as misura,
       count(*) as righe,
       sum(token) as token
from token_ledger
where direzione = 'addebito'
  and created_at >= now() - make_interval(days => %s)
group by 1
order by 2 desc
"""

QUERY_PER_GIORNO = """
select date_trunc('day', created_at)::date as giorno,
       count(*) filter (where misura = 'ignoto') as ignote,
       count(*) as totali
from token_ledger
where direzione = 'addebito'
  and created_at >= now() - make_interval(days => %s)
group by 1
order by 1
"""


def main() -> int:
    dsn = (os.environ.get("DATABASE_URL_LEDGER") or "").strip()
    if not dsn:
        print("manca DATABASE_URL_LEDGER (la stringa del ruolo `divina`)", file=sys.stderr)
        return 2
    giorni = 30
    if "--giorni" in sys.argv:
        giorni = int(sys.argv[sys.argv.index("--giorni") + 1])
    if "--tenant" not in sys.argv:
        print("manca --tenant: usa `--tenant '*'` per la vista completa, oppure "
              "un codice singolo (es. --tenant forma-core).\n"
              "Senza, la RLS del ruolo `divina` nasconde tutto e il rapporto "
              "esce vuoto invece di dire che non ha potuto guardare.",
              file=sys.stderr)
        return 2
    tenant = sys.argv[sys.argv.index("--tenant") + 1]

    import psycopg2
    with psycopg2.connect(dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            # I GUC della RLS, per la sola transazione. Senza, ogni SELECT
            # torna vuota — in silenzio.
            for nome in ("ovyon.allowed_tenants", "ovyon.allowed_orgs",
                         "ovyon.allowed_sub_tenants"):
                cur.execute("SELECT set_config(%s, %s, true)",
                            (nome, tenant if nome.endswith("tenants") else "", True))
            try:
                cur.execute(QUERY_TOTALI, (giorni,))
            except psycopg2.errors.UndefinedColumn:
                # db/005 non applicata: lo si dice invece di stampare zero.
                print("la colonna `misura` non esiste (db/005 non applicata): "
                      "il rapporto non può distinguere misurato da ignoto")
                return 1
            righe = cur.fetchall()
            cur.execute(QUERY_PER_GIORNO, (giorni,))
            per_giorno = cur.fetchall()

    totale = sum(r[1] for r in righe) or 0
    print(f"\nAddebiti degli ultimi {giorni} giorni (tenant {tenant}): {totale}")
    if not totale:
        # Zero righe non è «tutto bene»: è «non è passato traffico», e sono due
        # cose diverse da dire a chi legge un rapporto. Terza possibilità, la
        # più insidiosa: la RLS non ci fa vedere niente — per questo il tenant
        # visto è scritto qui sopra, e non è un dettaglio di cortesia.
        print("nessun addebito nel periodo — niente da misurare, non «tutto a posto».\n"
              f"Se il registro NON è vuoto, controlla il tenant: con --tenant {tenant!r} "
              "la RLS mostra solo quello (usa '*' per la vista completa).")
        return 0

    for misura, n, token in righe:
        print(f"  {misura:<12} {n:>7} righe  {(n / totale * 100):5.1f}%  "
              f"{int(token or 0):>12} token")

    ignote = next((r[1] for r in righe if r[0] == "ignoto"), 0)
    print(f"\nTasso di NON misurato: {ignote / totale * 100:.2f}%")
    print("(misurato il 7/08: `usage` arriva anche col flag spento, quindi qui ci\n"
          " si aspetta ~0%. Se risale, qualcosa ha smesso di dirci quanto è costato\n"
          " — e il conto si sfalsa in silenzio.)\n")

    if per_giorno:
        print("Per giorno:")
        for giorno, ign, tot in per_giorno:
            quota = (ign / tot * 100) if tot else 0
            print(f"  {giorno}  {ign:>5}/{tot:<5} ignote  {quota:5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
