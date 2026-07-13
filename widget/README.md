# Divina — Widget di chat embeddable

Widget di chat che si collega al servizio Divina (`/chat`) con isolamento per **tenant/scope**.
Due versioni incluse, stessa UI (palette FORMA, bolla flottante):

| File | Per chi | Come si usa |
|---|---|---|
| `embed.js` | Qualsiasi sito (ATS, landing, WordPress…) | un solo tag `<script>` |
| `DivinaWidget.jsx` | App **Next.js / React** (FORMA v4) | componente client |
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

Copia `DivinaWidget.jsx` in `components/` e montalo nel layout:

```jsx
import DivinaWidget from "@/components/DivinaWidget";

export default function Layout({ children }) {
  return (<>{children}
    <DivinaWidget
      api="https://ember.tuodominio.it"
      tenantKey="CHIAVE_FORMA_INTERNO"
      title="Assistente FORMA" />
  </>);
}
```

## Attributi disponibili (v2)

Tutti opzionali, con default. Si passano come `data-*` sul tag o via `window.EMBER_CONFIG`.

| Attributo | Default | Cosa fa |
|---|---|---|
| `data-proxy` / `data-api`+`data-key` | — | endpoint (proxy consigliato in produzione) |
| `data-title` | `Divina · Assistente` | titolo del pannello |
| `data-subtitle` | `Assistente AI` | sottotitolo (disclosure) |
| `data-accent` | `#0ED4E4` | colore brand |
| `data-avatar` / `data-logo` | — | URL immagine avatar / logo |
| `data-position` | `right` | angolo: `right` o `left` |
| `data-lang` | `it-IT` | lingua voce |
| `data-voice` | `true` | abilita microfono + lettura |
| `data-voice-auto` | `false` | legge in automatico ogni risposta |
| `data-voice-mode` | `browser` | `browser` (gratis) o `pro` (proxy → Deepgram/ElevenLabs) |
| `data-greeting` | — | messaggio di benvenuto personalizzato |

## Voce 🎤🔊

- **`browser` (default, gratis):** usa le Web Speech API del browser (STT + TTS). Nessuna chiave, nessun costo. Meglio su Chrome/Edge.
- **`pro`:** l'audio passa dal backend (`/voice/stt`, `/voice/tts`) che usa **Deepgram** o **ElevenLabs** — le chiavi restano sul server. Si attiva impostando `VOICE_PROVIDER` (+ chiave) nel `.env`; lato widget basta `data-voice-mode="pro"`. Se il backend risponde `501` (voce PRO non attiva) il widget **torna automaticamente** alla voce del browser.

Isolamento: il widget v2 gira in **Shadow DOM**, quindi non eredita né altera i CSS del sito ospite.
Trasparenza: al primo messaggio dichiara che è un assistente AI ed espone l'avviso "può commettere errori" (EU AI Act, art. 50).

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
3. Restringere gli Origin: oltre al CORS globale (`CORS_ORIGINS`), ogni tenant può avere `allowed_origins` in `tenants.json` — il backend rifiuta con `403` le richieste da domini non autorizzati (difesa per-tenant, già attiva).

Novità v0.3: header di sicurezza su ogni risposta, cap della lunghezza del messaggio, redazione PII nei log, sanitizzazione anti prompt-injection del contenuto recuperato, disclosure EU AI Act nel widget.
