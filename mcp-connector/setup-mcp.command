#!/bin/zsh
# Doppio-click: prepara il connettore MCP "OVY Brain" per Claude Desktop.
cd "$(dirname "$0")"
echo "──────────────────────────────────────────────"
echo "  OVY Brain Connector (MCP) — setup"
echo "──────────────────────────────────────────────"
if [ ! -d .venv ]; then echo "→ creo l'ambiente…"; python3 -m venv .venv; fi
source .venv/bin/activate
echo "→ installo le dipendenze…"
pip install -q -r requirements.txt || { echo "✗ pip fallito"; read; exit 1; }
echo ""
echo "✅ Connettore pronto."
echo ""
echo "ORA apri questo file:"
echo "   ~/Library/Application Support/Claude/claude_desktop_config.json"
echo "e incolla il blocco qui sotto (sostituisci INCOLLA_LA_CHIAVE_FORMA con la tua chiave FORMA)."
echo "Se il file ha già altri mcpServers, aggiungi solo la voce \"ovy-brain\"."
echo "──────────────────────────────────────────────"
cat claude-desktop-config.json
echo "──────────────────────────────────────────────"
echo "Poi RIAVVIA Claude Desktop. In chat comparirà lo strumento ovy_brain."
echo ""
echo "Premi Invio per chiudere."
read
