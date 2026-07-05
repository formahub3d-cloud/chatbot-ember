"""Test dell'estrazione campi UniLav (regex). Puro, senza rete.

Copre l'output OCR reale: separatore con due punti, spazi variabili, casing,
e i falsi match evitati dall'ancoraggio a inizio riga (Nome vs Cognome).
"""
from app import extract as E

# Un modulo UniLav come lo restituisce l'OCR (con i due punti).
UNILAV = """\
Comunicazione obbligatoria

Codice comunicazione: 1234567890123456
Codice fiscale: RSSMRA85M01H501Z
Cognome: Rossi
Nome: Mario
Data inizio: 01/03/2026
Data fine: 31/12/2026
Denominazione: ACME S.r.l.
Tipologia contrattuale: Tempo determinato
"""


def test_estrae_tutti_i_campi_con_due_punti():
    f = E.extract_unilav(UNILAV)
    assert f["codice_comunicazione"] == "1234567890123456"
    assert f["codice_fiscale"] == "RSSMRA85M01H501Z"
    assert f["cognome"] == "Rossi"
    assert f["nome"] == "Mario"
    assert f["data_inizio"] == "01/03/2026"
    assert f["data_fine"] == "31/12/2026"
    assert f["datore"] == "ACME S.r.l."
    assert f["tipologia"] == "Tempo determinato"


def test_nome_non_matcha_cognome():
    """'Nome' non deve catturare il valore della riga 'Cognome' (ancoraggio a riga)."""
    txt = "Cognome: Bianchi\nNome: Anna\n"
    f = E.extract_unilav(txt)
    assert f["cognome"] == "Bianchi"
    assert f["nome"] == "Anna"


def test_separatore_a_spazi_e_casing():
    txt = "CODICE FISCALE   VRDLGU80A01F205X\n"
    assert E.extract_unilav(txt)["codice_fiscale"] == "VRDLGU80A01F205X"


def test_campo_assente_stringa_vuota():
    assert E.extract_unilav("Nessun campo utile qui")["codice_fiscale"] == ""
