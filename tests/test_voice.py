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


# ── voce italiana (P8 «la voce continua»): la config sbagliata deve VEDERSI ──
class _Resp:
    content = b"mp3"
    headers: dict = {}

    def raise_for_status(self):
        pass


def test_voice_id_vuoto_usa_riserva_ma_lo_dice(monkeypatch, caplog):
    """Senza ELEVENLABS_VOICE_ID si ripiega sulla voce di libreria (timbro
    inglese) ma MAI in silenzio: warning nei log a ogni sintesi."""
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "sk_test")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "")
    seen = {}

    def fake_post(url, **kw):
        seen["url"] = url
        return _Resp()
    monkeypatch.setattr(voice.httpx, "post", fake_post)
    with caplog.at_level("WARNING", logger="ember"):
        audio, ctype = voice.synthesize("Ciao")
    assert voice._EL_FALLBACK_VOICE in seen["url"]
    assert "ELEVENLABS_VOICE_ID vuoto" in caplog.text
    assert "INGLESE" in caplog.text


def test_voice_id_impostato_niente_warning(monkeypatch, caplog):
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "sk_test")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", " VOCE_ITALIANA ")
    seen = {}

    def fake_post(url, **kw):
        seen["url"] = url
        return _Resp()
    monkeypatch.setattr(voice.httpx, "post", fake_post)
    with caplog.at_level("WARNING", logger="ember"):
        voice.synthesize("Ciao")
    assert "/VOCE_ITALIANA" in seen["url"]        # ripulita da spazi
    assert "ELEVENLABS_VOICE_ID vuoto" not in caplog.text


def test_status_espone_voice_id_set(monkeypatch):
    """La spia per /admin/status: voice_id_set false = accento inglese in arrivo."""
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "")
    s = voice.status()
    assert s["voice_id_set"] is False
    assert s["voice_tts_model"] == "eleven_flash_v2_5"   # modello a bassa latenza
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "abc")
    assert voice.status()["voice_id_set"] is True


def test_status_senza_provider_minimale(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "")
    s = voice.status()
    assert s["voice_provider"] == ""
    assert "voice_id_set" not in s
