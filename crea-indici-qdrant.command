#!/bin/zsh
# Doppio-click: crea gli indici di payload mancanti su Qdrant (slug, scope, org,
# tenant, sub_tenant) SENZA reindicizzare i contenuti (niente re-embed, pochi secondi).
# Serve a far funzionare /document (ovy_get_document), che filtra per slug.
cd "$(dirname "$0")"
echo "──────────────────────────────────────────────"
echo "  Qdrant · creo gli indici mancanti (slug…)"
echo "──────────────────────────────────────────────"
if [ ! -f .env ]; then echo "✗ Manca .env (le chiavi Qdrant). Fai prima l'ingest."; read; exit 1; fi
if grep -q "INCOLLA_DA_RAILWAY" .env; then echo "✗ .env non ancora compilato con le chiavi."; read; exit 1; fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt >/dev/null 2>&1
python3 -c "
from app.config import settings
from app.ingest import client, ensure_collection
c = client()
ensure_collection(c)   # idempotente: NON tocca i dati, crea solo gli indici mancanti (incluso slug)
print('OK - indici assicurati sulla collection:', settings.qdrant_collection)
" || { echo '✗ errore - controlla le chiavi in .env'; read; exit 1; }
echo ""
echo "✅ Fatto. Ora ovy_get_document funziona. Premi Invio per chiudere."
read
