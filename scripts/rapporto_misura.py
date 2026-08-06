#!/usr/bin/env python3
"""S5.1c · Quante volte NON abbiamo saputo misurare un consumo.

È il numero da cui nascerà la soglia del secondo freno (S5.1c/2), e per adesso
serve a una cosa più semplice: **vedere se l'accensione di
`MISTRAL_STREAM_USAGE` ha funzionato**. Prima dell'accensione le righe della
chat sono tutte `ignoto`; dopo devono crollare. Se non crollano, il problema è
altrove e si vede subito invece che a fine mese.

Legge e basta: nessuna scrittura, nessuna decisione. Si connette con la
`DATABASE_URL_LEDGER` (ruolo `divina`), che ha `select` e `insert` — quindi
anche sbagliando non può rovinare niente.

Uso:
    DATABASE_URL_LEDGER='postgresql://…' python3 scripts/rapporto_misura.py
    DATABASE_URL_LEDGER='…' python3 scripts/rapporto_misura.py --giorni 7

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

    import psycopg2
    with psycopg2.connect(dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
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
    print(f"\nAddebiti degli ultimi {giorni} giorni: {totale}")
    if not totale:
        # Zero righe non è «tutto bene»: è «non è passato traffico», e sono due
        # cose diverse da dire a chi legge un rapporto.
        print("nessun addebito nel periodo — niente da misurare, non «tutto a posto»")
        return 0

    for misura, n, token in righe:
        print(f"  {misura:<12} {n:>7} righe  {(n / totale * 100):5.1f}%  "
              f"{int(token or 0):>12} token")

    ignote = next((r[1] for r in righe if r[0] == "ignoto"), 0)
    print(f"\nTasso di NON misurato: {ignote / totale * 100:.2f}%")
    print("(prima di MISTRAL_STREAM_USAGE=true ci si aspetta ~100% sulla chat;\n"
          " dopo l'accensione deve crollare. Se non crolla, il problema è altrove.)\n")

    if per_giorno:
        print("Per giorno:")
        for giorno, ign, tot in per_giorno:
            quota = (ign / tot * 100) if tot else 0
            print(f"  {giorno}  {ign:>5}/{tot:<5} ignote  {quota:5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
