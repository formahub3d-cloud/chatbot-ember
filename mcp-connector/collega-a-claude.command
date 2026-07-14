#!/bin/zsh
# Doppio-click: collega il connettore "OVY Brain" a Claude Desktop.
# Fa TUTTO: ambiente, dipendenze, e modifica in sicurezza il file di config di Claude.
cd "$(dirname "$0")"
CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
echo "──────────────────────────────────────────────"
echo "  OVY Brain → Claude Desktop"
echo "──────────────────────────────────────────────"

# 1) ambiente + dipendenze del connettore
if [ ! -d .venv ]; then echo "→ preparo l'ambiente…"; python3 -m venv .venv; fi
source .venv/bin/activate
echo "→ installo le dipendenze…"
pip install -q -r requirements.txt || { echo "✗ pip fallito"; read; exit 1; }

# 2) chiedo la chiave FORMA (incollala e premi Invio)
echo ""
echo "Incolla la tua CHIAVE FORMA (inizia con ember_forma_) e premi Invio:"
read -r KEY
if [ -z "$KEY" ]; then echo "✗ Nessuna chiave inserita. Esco."; read; exit 1; fi

# 3) scrivo/aggiorno il file di config di Claude (con backup)
PYBIN="$(pwd)/.venv/bin/python"
SERVER="$(pwd)/server.py"
mkdir -p "$(dirname "$CFG")"
CFG="$CFG" PYBIN="$PYBIN" SERVER="$SERVER" KEY="$KEY" python3 <<'PY'
import json, os, shutil
cfg = os.environ["CFG"]
data = {}
if os.path.exists(cfg):
    shutil.copy(cfg, cfg + ".backup")            # backup di sicurezza
    try: data = json.load(open(cfg))
    except Exception: data = {}
data.setdefault("mcpServers", {})
data["mcpServers"]["ovy-brain"] = {
    "command": os.environ["PYBIN"],
    "args": [os.environ["SERVER"]],
    "env": {"EMBER_API_URL": "https://divina.formahub.it",
            "EMBER_TENANT_KEY": os.environ["KEY"]},
}
json.dump(data, open(cfg, "w"), indent=2, ensure_ascii=False)
print("✓ Config aggiornata:", cfg)
PY

echo ""
echo "✅ FATTO. Ora CHIUDI e RIAPRI Claude Desktop (esci del tutto e riavvia)."
echo "   Poi in chat scrivi:  usa lo strumento ovy_list_context"
echo ""
echo "Premi Invio per chiudere."
read
