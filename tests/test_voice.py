"""Test della logica voce (enabled/disabled), senza rete."""
from app.config import settings
from app import voice


def test_voce_disabilitata_di_default(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "")
    assert voice.stt_enabled() is False
    assert voice.tts_enabled() is False


def test_elevenlabs_abilitata_con_chiave(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", " sk_test \n")  # con spazi
    assert voice.stt_enabled() is True
    assert voice.tts_enabled() is True
    # la chiave viene ripulita da spazi/virgolette
    assert voice._el_key() == "sk_test"


def test_deepgram_abilitata_con_chiave(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "deepgram")
    monkeypatch.setattr(settings, "deepgram_api_key", '"dg_test"')  # con virgolette
    assert voice.stt_enabled() is True
    assert voice._dg_key() == "dg_test"


def test_provider_senza_chiave(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    assert voice.tts_enabled() is False
