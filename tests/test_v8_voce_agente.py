"""V8/C1 · Una voce per ogni agente.

Zoey ha 63 voci ricercabili, ognuna con una descrizione d'uso, scelte per
companion. Divina ne aveva UNA per tutti e quattro: Dante, Virgilio e Beatrice
hanno colori e forme diversi in tutta la console e parlavano con la stessa gola.
È un parametro, non un progetto — e questi test sorvegliano le due cose che
possono andare storte: che la voce cambi davvero, e che il browser non possa
scegliere quale voce far pagare.
"""
import pytest
from fastapi.testclient import TestClient

from app import main, voice
from app.config import settings

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _voce(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "k" * 20)
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "VOCE-DIVINA")
    monkeypatch.setattr(settings, "elevenlabs_voice_id_dante", "")
    monkeypatch.setattr(settings, "elevenlabs_voice_id_virgilio", "")
    monkeypatch.setattr(settings, "elevenlabs_voice_id_beatrice", "")
    yield


def test_senza_voci_per_agente_niente_cambia(monkeypatch):
    """La regressione da escludere per prima: chi non imposta le variabili nuove
    deve sentire esattamente quello che sentiva ieri."""
    for a in ("", "dante", "virgilio", "beatrice", "qualunque-cosa"):
        assert voice._el_voice(a) == "VOCE-DIVINA"


def test_la_voce_dell_agente_vince_quando_c_e(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_voice_id_dante", "VOCE-DANTE")
    assert voice._el_voice("dante") == "VOCE-DANTE"
    assert voice._el_voice("DANTE") == "VOCE-DANTE"      # il nome arriva da fuori: si normalizza
    assert voice._el_voice("virgilio") == "VOCE-DIVINA"  # non configurata: ricade
    assert voice._el_voice("") == "VOCE-DIVINA"


def test_un_agente_ignoto_non_rompe_la_frase(monkeypatch):
    """Un nome sbagliato deve dare la voce di Divina, non un errore: una voce
    sbagliata è un difetto estetico, un 500 a metà frase è una conversazione
    rotta."""
    monkeypatch.setattr(settings, "elevenlabs_voice_id_dante", "VOCE-DANTE")
    assert voice.agente_valido("marta") == ""
    assert voice._el_voice("marta") == "VOCE-DIVINA"


def test_la_spia_dice_chi_ha_una_voce_sua_e_chi_no(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_voice_id_dante", "VOCE-DANTE")
    v = voice.voci_per_agente()
    assert v == {"divina": True, "dante": True, "virgilio": False, "beatrice": False}
    assert voice.status()["voci_agente"] == v
    # e mai gli id: un voice_id è un identificatore di fatturazione
    assert "VOCE-DANTE" not in str(voice.status())


def test_senza_provider_elevenlabs_la_spia_non_inventa(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "deepgram")
    assert voice.voci_per_agente() == {}


def test_l_endpoint_passa_il_NOME_e_non_un_voice_id(monkeypatch):
    """Il contratto di sicurezza: dal browser arriva `agente`, la mappa
    nome→voce vive sul server. Se un giorno qualcuno accettasse un voice_id
    dalla richiesta, questo test lo troverebbe."""
    visti = {}

    def finto(text, agente=""):
        visti.update(text=text, agente=agente)
        return iter([b"audio"]), "audio/mpeg"

    monkeypatch.setattr(main.voice, "synthesize_stream", finto)
    monkeypatch.setattr(main, "tenant_or_401", lambda k: {"name": "t", "allowed_scopes": ["ats"]})
    monkeypatch.setattr(main, "_guard", lambda *a, **k: None)
    r = client.post("/voice/tts", json={"text": "ciao", "agente": "dante"},
                    headers={"X-Tenant-Key": "k"})
    assert r.status_code == 200 and visti["agente"] == "dante"
    assert "voice_id" not in main.TTSIn.model_fields
