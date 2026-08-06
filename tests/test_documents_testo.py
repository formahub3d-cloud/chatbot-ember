"""S4.1 · `POST /documents/testo` — un documento, il suo testo, nient'altro.

Fratello generico di `/upload`, che è dei contratti UNILAV (OCR → campi da
confermare). Nell'area cliente il documento non diventa un modulo compilato: il
testo va all'orchestratore, che ne ricava nodi in bozza.

Le cose che questi test tengono ferme sono quelle che, sbagliate, costano soldi
o raccontano una bugia:

  · **i formati di testo non passano dall'OCR.** Leggere un .txt è decodificare
    dei byte: mandarlo a un modello sarebbe un giro di rete e una fattura per
    niente;
  · **i limiti stanno QUI**, non nel chiamante. Un tetto che vive solo nel
    client è un tetto che il secondo client non ha;
  · **un 200 non vuol dire documento leggibile.** Un PDF scansionato male torna
    con `testo` vuoto: l'estrazione è riuscita, il documento no — e chi chiama
    deve poterlo distinguere;
  · **501 ≠ 502.** «Non configurato su questo ambiente» non si riprova.
"""
import pytest
from fastapi.testclient import TestClient

from app import main, ocr, tenants
from app.config import settings

client = TestClient(main.app)

FAKE_TENANT = {"name": "ATS", "allowed_scopes": ["ats"], "allowed_origins": [],
               "branding": {}, "quota_day": 0}


@pytest.fixture(autouse=True)
def _mock_tenant(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: FAKE_TENANT if k == "K_ATS" else None)
    monkeypatch.setattr(settings, "mistral_api_key", "sk-finta")
    # Il limitatore è un singleton di modulo e conta per CHIAVE, non per test:
    # dieci richieste con `K_ATS` qui dentro esaurivano il budget di quella
    # chiave anche per i file dopo (`test_upload_confirm` andava in 429). Da
    # solo questo file passava; nella suite ne rompeva otto — è la regola di
    # review in testa al diario, e stavolta l'ho scoperta addosso a me.
    monkeypatch.setattr(main, "rate_ok", lambda k: True)


def _post(contenuto=b"ciao", nome="listino.txt", mime="text/plain", key="K_ATS"):
    return client.post("/documents/testo",
                       files={"file": (nome, contenuto, mime)},
                       headers={"X-Tenant-Key": key})


def test_un_txt_non_passa_dall_OCR(monkeypatch):
    def _mai(*a, **k):
        raise AssertionError("l'OCR non deve essere chiamato per un file di testo")
    monkeypatch.setattr(ocr, "ocr_document", _mai)

    r = _post(b"Il listino 2026 parte da 120 euro.")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["testo"] == "Il listino 2026 parte da 120 euro."
    assert d["caratteri"] == 34
    assert d["titolo"] == "listino.txt"


def test_un_pdf_passa_dall_OCR(monkeypatch):
    visti = {}

    def _finto(path, mime="application/pdf"):
        visti["mime"] = mime
        return "  Testo estratto dal PDF.  "

    monkeypatch.setattr(ocr, "ocr_document", _finto)
    r = _post(b"%PDF-1.4 finto", nome="listino.pdf", mime="application/pdf")
    assert r.status_code == 200, r.text
    assert r.json()["testo"] == "Testo estratto dal PDF."
    assert visti["mime"] == "application/pdf"


def test_un_documento_illeggibile_torna_200_con_testo_VUOTO(monkeypatch):
    """L'estrazione è riuscita, il documento no.

    La soglia di «troppo poco per farci qualcosa» la mette chi chiama, che sa
    cosa deve farci. Qui si dice quanti caratteri sono usciti, e basta.
    """
    monkeypatch.setattr(ocr, "ocr_document", lambda p, mime="": "   ")
    r = _post(b"%PDF scansione", nome="scansione.pdf", mime="application/pdf")
    assert r.status_code == 200
    assert r.json() == {"titolo": "scansione.pdf", "mime": "application/pdf",
                        "testo": "", "caratteri": 0}


def test_senza_chiave_mistral_e_501_non_502(monkeypatch):
    """«Non configurato» non si riprova; «rotto» sì. Confonderli fa riprovare
    all'infinito una cosa che su questo ambiente non esiste."""
    monkeypatch.setattr(settings, "mistral_api_key", "")
    r = _post(b"%PDF", nome="x.pdf", mime="application/pdf")
    assert r.status_code == 501
    # ma il testo semplice continua a funzionare: non gli serve nessuna chiave
    assert _post(b"ciao").status_code == 200


def test_un_OCR_che_esplode_e_502(monkeypatch):
    def _rotto(*a, **k):
        raise RuntimeError("rete")
    monkeypatch.setattr(ocr, "ocr_document", _rotto)
    assert _post(b"%PDF", nome="x.pdf", mime="application/pdf").status_code == 502


def test_formato_non_supportato(monkeypatch):
    for mime in ("application/zip", "application/x-msdownload", "video/mp4"):
        assert _post(b"x", nome="a.bin", mime=mime).status_code == 415, mime


def test_file_troppo_grande(monkeypatch):
    r = _post(b"x" * (main.DOC_MAX_BYTE + 1))
    assert r.status_code == 413


def test_file_vuoto(monkeypatch):
    assert _post(b"").status_code == 422


def test_senza_chiave_tenant_non_si_legge_niente(monkeypatch):
    def _mai(*a, **k):
        raise AssertionError("nessuna estrazione senza tenant")
    monkeypatch.setattr(ocr, "ocr_document", _mai)
    assert _post(key="SBAGLIATA").status_code == 401


def test_il_nome_del_file_non_porta_un_percorso(monkeypatch):
    """`../../etc/passwd` come nome file diventa il suffisso del temporaneo e il
    titolo del documento: si tiene solo l'ultimo pezzo."""
    monkeypatch.setattr(ocr, "ocr_document", lambda p, mime="": "x")
    r = _post(b"%PDF", nome="../../etc/passwd.pdf", mime="application/pdf")
    assert r.status_code == 200
    assert r.json()["titolo"] == "passwd.pdf"
