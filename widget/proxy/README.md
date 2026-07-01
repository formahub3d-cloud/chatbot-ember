# Proxy Jarvis — non esporre la chiave nell'HTML

In modalità "diretta" il widget mette la chiave tenant nell'HTML: chiunque legga il
sorgente la vede. Per i clienti paganti si usa un **proxy**: la chiave resta lato server,
il widget chiama un endpoint del sito che inoltra a Jarvis aggiungendo la chiave.

```
Browser ──(POST /api/jarvis, senza chiave)──▶  Proxy (ha la chiave)  ──(X-Tenant-Key)──▶  Jarvis
```

## Due implementazioni pronte

### A. Next.js (stack FORMA) — `nextjs-route.js`
1. Copia il file in `app/api/jarvis/route.js` del sito.
2. Imposta le variabili d'ambiente:
   - `JARVIS_API = https://jarvis-production-e680.up.railway.app`
   - `JARVIS_TENANT_KEY = <chiave del cliente>` (es. `CHIAVE_HRH`)
3. Nel widget usa: `data-proxy="/api/jarvis"` (niente `data-key`).

### B. Cloudflare Worker (universale) — `cloudflare-worker.js`
Ideale per siti non-Next.js. Un Worker per cliente.
1. Crea un Worker, incolla il codice.
2. Variables: `JARVIS_API` (variable), `JARVIS_TENANT_KEY` (**secret**), `ALLOW_ORIGIN` (dominio del cliente).
3. Nel widget: `data-proxy="https://jarvis-<cliente>.<sub>.workers.dev"`.

## Esempio widget (modalità proxy)
```html
<script src="https://.../embed.js"
        data-proxy="/api/jarvis"
        data-title="Assistente HRH"
        data-accent="#F8693C"></script>
```

## Note
- Il proxy non elimina la necessità di limitare gli abusi: tieni il rate-limiting di Jarvis
  attivo e, sul Worker, imposta `ALLOW_ORIGIN` al dominio del cliente.
- Ogni cliente = un proxy con la **sua** chiave → isolamento netto, chiave mai nel browser.
