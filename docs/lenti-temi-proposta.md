# Lenti tematiche — proposta per Andrea (decisione SUA, non tecnica)

> 31-07-2026 · O3. La console ha le lenti che i dati reggono OGGI (le categorie
> reali dei path: Documenti, Workspace, Entità…). La lente che Andrea vuole —
> «dimmi *business* e vedi le note per ragionare di business» — oggi **non può
> esistere onestamente**: il vault ha i facet (forma|andrea|ovyon) e le
> categorie (cat/docs, cat/workspace…), ma NESSUNA classificazione tematica.
> Un classificatore automatico sbaglierebbe in silenzio, e una lente che
> seleziona le note sbagliate è peggio di nessuna lente: poi ci si fidano le
> decisioni. Il posto in console c'è, dichiaratamente vuoto («Temi · in attesa
> dei tag»): si accende da solo quando le note avranno i tag.

## La proposta minima (5 temi, non venti)

Da aggiungere al frontmatter delle note a cui si applicano, accanto ai tag
esistenti — forma `tema/<nome>`:

| Tag | Cosa copre | Esempi nel vault di oggi |
|---|---|---|
| `tema/business` | mercato, prezzi, offerta, trattative, crescita | listino, schede clienti, OKR |
| `tema/legale` | contratti, privacy/GDPR, compliance | area finance-legal, procedure |
| `tema/tecnico` | come funziona: stack, processi, macchine | doc Divina, aree sviluppo, stampa 3D |
| `tema/marketing` | contenuti, campagne, posizionamento, brand | aree marketing, campaign, community |
| `tema/persone` | chi fa cosa: ruoli, collaboratori, clienti come persone | self, aree, schede cliente |

Regole d'uso (per non far marcire la tassonomia):
- una nota può portare **più temi**, ma se ne servono più di due la nota
  probabilmente va spezzata;
- il tema si assegna **quando si scrive o si tocca** la nota, mai in blocco a
  ripetizione da uno script;
- se dopo un mese un tema ha meno di 3 note, si elimina il tema, non si
  forzano le note.

## Cosa succede quando decidi

1. Aggiungi i tag `tema/*` alle note (o dimmi la lista approvata e preparo io
   la modifica del frontmatter nota per nota, in PR sul vault, mai in blocco
   cieco).
2. L'ingest già indicizza i `tags` nel payload Qdrant: la lente tematica in
   console si collega a quelli — il posto vuoto si riempie, niente da
   ridisegnare.

**Niente di tutto questo parte senza il tuo sì**: è la tassonomia del tuo
cervello.
