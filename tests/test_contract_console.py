"""CT — test di contratto console ↔ backend (sintesi architettura 29-07).

Ogni chiamata di rete del pannello verso QUESTO servizio deve corrispondere a
una rotta registrata nell'app FastAPI. Se una vista chiama una rotta che non
esiste, la CI diventa rossa QUI — non un fallimento silenzioso in produzione.

Le eccezioni legittime (es. una rotta servita da un edge esterno) vanno
dichiarate in tests/contract_exceptions.json con motivazione OBBLIGATORIA:
una eccezione senza motivazione fa fallire il test."""
import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "contract_console", _ROOT / "scripts" / "contract_console.py")
contract = importlib.util.module_from_spec(_spec)
sys.modules["contract_console"] = contract
_spec.loader.exec_module(contract)

EXC = Path(__file__).parent / "contract_exceptions.json"
SERVICE = "engine"


def _exceptions() -> dict:
    data = json.loads(EXC.read_text("utf-8")) if EXC.exists() else {}
    for key, why in data.items():
        assert isinstance(why, str) and why.strip(), \
            f"eccezione senza motivazione (vietato silenziare): {key}"
    return data


def test_contratto_console_backend():
    exc = _exceptions()
    missing = []
    for r in contract.check(SERVICE):
        key = f"{r['method']} {r['path']}"
        if r["found"] is False and key not in exc:
            missing.append(f"{key} (pannello riga {r['line']}) — {r['note']}")
    assert not missing, ("Chiamate del pannello SENZA rotta nel backend "
                         "(implementare, ripuntare o rimuovere):\n  "
                         + "\n  ".join(missing))


def test_estrazione_copre_le_famiglie_chiave():
    """Guardia sull'ESTRATTORE: se queste famiglie spariscono dall'elenco è
    l'analisi statica a essersi rotta, non il pannello a essere diventato sano.
    (Criterio d'accettazione del prompt CT.)"""
    paths = {r["path"] for r in contract.check(SERVICE)}
    for fam in ("/admin/brain", "/admin/tasks", "/admin/proposals",
                "/admin/roadmap", "/admin/clients", "/client/login", "/chat"):
        assert any(p == fam or p.startswith(fam + "/") or p.startswith(fam)
                   for p in paths), f"famiglia non estratta dal pannello: {fam}"


def test_nessun_path_dinamico_non_dichiarato():
    """I path non determinabili staticamente non si indovinano: devono essere
    zero, o dichiarati come eccezione con motivazione."""
    exc = _exceptions()
    dyn = [f"{r['method']} {r['path']} (riga {r['line']})"
           for r in contract.check(SERVICE)
           if r["found"] is None and f"{r['method']} {r['path']}" not in exc]
    assert not dyn, "path dinamici da giudicare a mano:\n  " + "\n  ".join(dyn)


# ── V11/A4 · Il contratto al contrario: chi chiama questa rotta? ─────────────
def test_nessuna_rotta_senza_chiamante_dichiarato():
    """Andrea, il 2/08 sera: «più cose aggiungiamo, più c'è vulnerabilità».

    Un endpoint che nessuna schermata chiama è superficie d'attacco che nessuno
    guarda, e che nessuno noterà quando smetterà di funzionare. Non tutti sono
    un difetto — alcuni hanno un chiamante fuori dal repo — ma il chiamante va
    DICHIARATO con un nome. È la differenza fra tenere una cosa e
    dimenticarsela, ed è l'unica versione della disciplina che sopravvive a un
    giro in cui si ha fretta."""
    orfane = contract.orfane()
    assert not orfane, (
        "Rotte che non chiama nessuno e che nessuno ha dichiarato. O si "
        "cancellano, o si aggiunge il chiamante a CHIAMANTI_FUORI in "
        "scripts/contract_console.py — con un nome, non con un «serve»:\n  "
        + "\n  ".join(orfane))


def test_ogni_dichiarazione_dice_CHI_chiama():
    """Una dichiarazione vuota o generica rimetterebbe le rotte esattamente
    dov'erano, con in più la sensazione che qualcuno ci abbia guardato."""
    for rotta, chi in contract.CHIAMANTI_FUORI.items():
        assert len(chi.strip()) >= 20, f"{rotta}: dichiarazione troppo vaga"


def test_le_dichiarazioni_non_invecchiano_in_silenzio():
    """Una rotta cancellata deve sparire anche dall'elenco: un elenco di
    fantasmi è la stessa malattia, spostata di un file."""
    routes, _ = contract.backend_routes()
    vere = {f"{me} {p}" for me, p in routes}
    morte = [k for k in contract.CHIAMANTI_FUORI if k not in vere]
    assert not morte, ("Dichiarate ma non più esistenti: " + ", ".join(morte))
