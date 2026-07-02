# Ember — Widget di chat embeddable

Widget di chat che si collega al servizio Ember (`/chat`) con isolamento per **tenant/scope**.
Due versioni incluse, stessa UI (palette FORMA, bolla flottante):

| File | Per chi | Come si usa |
|---|---|---|
| `embed.js` | Qualsiasi sito (ATS, landing, WordPress…) | un solo tag `<script>` |
| `EmberWidget.jsx` | App **Next.js / React** (FORMA v4) | componente client |
| `demo.html` | Test locale | apri nel browser col servizio attivo |

## 1) Test in locale (30 secondi)

```bash
# Terminale 1 — servizio
cd chatbot-ember && source .venv/bin/activate
uvicorn app.main:app --port 8000
```

Poi apri `widget/demo.html` nel browser: in basso a destra compare la bolla 💬.

## 2) Sito generico (ATS) — embed.js

Incolla **un** tag prima di `</body>`:

```html
<script src="https://ember.tuodominio.it/embed.js"
        data-api="https://ember.tuodominio.it"
        data-key="CHIAVE_ATS"
        data-title="Assistente ATS"
        data-accent="#F8693C"></script>
```

## 3) FORMA (Next.js) — componente

Copia `EmberWidget.jsx` in `components/` e montalo nel layout:

```jsx
import EmberWidget from "@/components/EmberWidget";

export default function Layout({ children }) {
  return (<>{children}
    <EmberWidget
      api="https://ember.tuodominio.it"
      tenantKey="CHIAVE_FORMA_INTERNO"
      title="Assistente FORMA" />
  </>);
}
```

## Scope = isolamento per cliente

La chiave determina cosa vede il bot:

| Chiave | Vede |
|---|---|
| `CHIAVE_FORMA_INTERNO` | FORMA core + Andrea |
| `CHIAVE_ATS` | solo note del cliente ATS |
| `CHIAVE_HRH` | solo note del cliente HRH |

Il bot ATS **non** può rispondere su FORMA (verificato).

## ⚠️ Nota di sicurezza (pilota → produzione)

La chiave tenant è visibile nel browser. È accettabile in **pilota** perché è di sola
lettura e ristretta allo scope. Per **produzione**:

1. Non esporre la chiave: instradare le richieste da un **proxy server** (es. route `/api/chat` di Next.js che aggiunge l'header lato server).
2. Spostare le chiavi in **DB** + **rate limiting** per chiave/IP (vedi roadmap audit).
3. Restringere `allow_origins` del CORS ai domini di FORMA/ATS (ora `*` per il pilota).
