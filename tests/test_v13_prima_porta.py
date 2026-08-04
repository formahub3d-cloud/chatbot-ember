"""V13/A · La prima porta, e la chiave che non passa più dagli appunti.

Il 3/08 il browser ha dimenticato le credenziali e la console si è aperta
chiedendo **sei campi, due dei quali segreti**, prima di mostrare qualunque
cosa. Per chi conosce il sistema è mezzo minuto; per «l'imprenditore appena
partito» del criterio del V11 è un muro — ed era l'unica porta che quel criterio
non aveva mai incontrato, oltre a essere la prima che si apre.

Qui si prova la metà server della correzione: **creare un accesso cliente non
chiede più di incollare una chiave.** Prima erano tre passaggi — emetti la
chiave, copiala al volo perché «si vede UNA sola volta», incollala in un altro
modulo — e in mezzo un segreto passava per gli appunti e per lo schermo.
"""
import pytest
from fastapi.testclient import TestClient

from app import clientauth, main, manage_apikeys
from app.config import settings

TOK = "tok-di-test-lungo-abbastanza-123456"
AUTH = {"Authorization": f"Bearer {TOK}"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    return TestClient(main.app)


@pytest.fixture()
def spia(monkeypatch):
    """La chiave coniata dal server, e l'account creato. Niente database."""
    visto = {}

    def finta_create_key(name, orgs=None, tenants_=None, subs=None, origins=None,
                         quota=0, branding=None):
        visto["nome"] = name
        visto["tenants"] = tenants_
        visto["branding"] = branding
        return "ovy_coniata_dal_server"

    def finto_account(email, display_name, tenant_key, password):
        visto["chiave_ricevuta"] = tenant_key
        return {"id": "c1", "email": email, "display_name": display_name}

    monkeypatch.setattr(manage_apikeys, "create_key", finta_create_key)
    monkeypatch.setattr(main.manage_apikeys, "create_key", finta_create_key)
    monkeypatch.setattr(clientauth, "create", finto_account)
    monkeypatch.setattr(main.clientauth, "create", finto_account)
    monkeypatch.setattr(main, "_require_apikeys", lambda: None)
    monkeypatch.setattr(main, "_client_feature_on", lambda: None)
    monkeypatch.setattr(main.tenants, "log_access", lambda *a, **k: None)
    return visto


def test_basta_il_cliente_la_chiave_la_conia_il_server(client, spia):
    """L'azione è UNA. Nessuna chiave nella richiesta, quindi nessuna chiave
    negli appunti, nello schermo o nella cronologia del browser."""
    r = client.post("/admin/clients", headers=AUTH,
                    json={"email": "reception@ats.it", "name": "ATS",
                          "scope": "ats", "password": "unapassword"})
    assert r.status_code == 200
    assert spia["chiave_ricevuta"] == "ovy_coniata_dal_server"
    assert spia["tenants"] == ["ats"]          # vede SOLO la sua cartella
    assert spia["branding"] == {"tenant_code": "ats"}


def test_la_chiave_coniata_non_torna_indietro(client, spia):
    """Non la vede nemmeno chi crea l'accesso: se comparisse nella risposta
    sarebbe di nuovo un segreto sullo schermo, con un passaggio in meno e lo
    stesso rischio."""
    r = client.post("/admin/clients", headers=AUTH,
                    json={"email": "x@ats.it", "scope": "ats", "password": "unapassword"})
    assert "ovy_coniata_dal_server" not in r.text
    assert "key" not in r.json()


def test_senza_cliente_e_senza_chiave_non_si_indovina(client, spia):
    """Coniare una chiave con uno scope vuoto darebbe un accesso che vede
    tutto: meglio un 422."""
    r = client.post("/admin/clients", headers=AUTH,
                    json={"email": "x@ats.it", "password": "unapassword"})
    assert r.status_code == 422
    assert "chiave_ricevuta" not in spia


def test_la_via_vecchia_resta_per_chi_una_chiave_ce_l_ha_gia(client, spia):
    """Chi ha già emesso una chiave non deve rifarla: `tenant_key` continua a
    funzionare, e in quel caso il server non ne conia una seconda."""
    r = client.post("/admin/clients", headers=AUTH,
                    json={"email": "x@ats.it", "tenant_key": "ovy_esistente",
                          "password": "unapassword"})
    assert r.status_code == 200
    assert spia["chiave_ricevuta"] == "ovy_esistente"
    assert "nome" not in spia                  # create_key non è stata chiamata
