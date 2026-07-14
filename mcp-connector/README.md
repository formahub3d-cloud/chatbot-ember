# OVY Brain Connector (MCP)

Connettore **MCP** che espone a Claude il cervello OVY, come da Sezione 5 del
documento di architettura OVYON (`ovyon/docs/doc-ovyon-connettore-claude` nel
cervello). È un **adattatore sottile**: ogni tool chiama gli endpoint HTTP di
**Divina** (il chatbot integrato in OVYON), che applica server-side il filtro per
grant. Il connettore **non** contiene logica di permessi.

## I 5 tool

| Tool MCP | Endpoint Divina | Cosa fa |
|---|---|---|
| `ovy_search` | `POST /search` | cerca contenuti rilevanti (prima di generare) |
| `ovy_get_document` | `GET /document?slug=` | recupera una nota completa per slug |
| `ovy_list_context` | `GET /context` | elenca org/tenant/sotto-tenant visibili |
| `ovy_create_document` | `POST /writeback` | crea una nota (anteprima → conferma umana) |
| `ovy_update_document` | `POST /writeback` (overwrite) | aggiorna una nota (anteprima → conferma) |

> **Write-back solo dopo conferma umana**: i tool di scrittura, con `confirm=false`
> (default), restituiscono un'anteprima. Vanno richiamati con `confirm=true` solo
> dopo l'approvazione esplicita dell'utente.

## Setup

```bash
cd mcp-connector
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # imposta EMBER_API_URL e EMBER_TENANT_KEY
python server.py        # avvia il server MCP su stdio
```

## Collegamento a Claude (Claude Desktop / Claude Code)

Aggiungi il server alla configurazione MCP del client, es.:

```json
{
  "mcpServers": {
    "ovy-brain": {
      "command": "python",
      "args": ["/percorso/assoluto/mcp-connector/server.py"],
      "env": {
        "EMBER_API_URL": "https://divina.formahub.it",
        "EMBER_TENANT_KEY": "<chiave-tenant>"
      }
    }
  }
}
```

Lo **scoping per tenant** (Sezione 5.5 del doc) è determinato da `EMBER_TENANT_KEY`:
una chiave per tenant → un connettore che vede solo il proprio scope. Per un
Claude Project dedicato a un cliente, preconfigura la chiave del relativo tenant.

## Note

- Il connettore è disaccoppiato da Divina via HTTP: resta usabile con qualunque
  client compatibile MCP (mitigazione del rischio "dipendenza da Claude", Sez. 11).
- Nessun segreto nel codice: la chiave-tenant arriva dall'ambiente.
