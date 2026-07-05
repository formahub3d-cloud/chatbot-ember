#!/bin/zsh
# Doppio-click: reindicizza il vault OVY su Qdrant Cloud (ingest a 3 livelli org/tenant/sub).
cd "$(dirname "$0")"
echo "──────────────────────────────────────────────"
echo "  Ingest cervello OVY → Qdrant Cloud"
echo "──────────────────────────────────────────────"
if [ ! -f .env ]; then
  echo "✗ Manca il file .env."
  echo "  Fai:  cp .env.esempio .env   e incolla le chiavi da Railway (ember → Variables)."
  echo ""; echo "Premi Invio per chiudere."; read; exit 1
fi
if grep -q "INCOLLA_DA_RAILWAY" .env; then
  echo "✗ Il file .env ha ancora dei valori da riempire (INCOLLA_DA_RAILWAY)."
  echo "  Aprilo, incolla le 5 chiavi da Railway (ember → Variables) e salva, poi rilancia."
  echo "  Per aprirlo:  open -e .env"
  echo ""; echo "Premi Invio per chiudere."; read; exit 1
fi
if [ ! -d .venv ]; then echo "→ creo l'ambiente Python…"; python3 -m venv .venv; fi
source .venv/bin/activate
echo "→ installo le dipendenze…"
pip install -q -r requirements.txt || { echo "✗ pip fallito"; read; exit 1; }
echo "→ reindicizzo il vault (può volerci qualche minuto)…"
python3 -c "import json; from app import ingest; print(json.dumps(ingest.run(), ensure_ascii=False, indent=2))" \
  || { echo "✗ ingest fallito — controlla le chiavi in .env"; read; exit 1; }
echo "→ verifica payload org/tenant/sub…"
python3 scripts/verify_ingest.py || true
echo ""
echo "✅ Cervello aggiornato su Qdrant. Premi Invio per chiudere."
read
