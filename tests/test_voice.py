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


# ── V1 «voce naturale»: espressività e pronuncia italiana nella sintesi ──────
def _cattura_post(monkeypatch, seen):
    def fake_post(url, **kw):
        seen["url"] = url
        seen["json"] = kw.get("json")
        return _Resp()
    monkeypatch.setattr(voice.httpx, "post", fake_post)


def test_sintesi_manda_voice_settings_e_lingua(monkeypatch):
    """Senza voice_settings la voce recita coi default di fabbrica: il corpo
    deve portare i quattro valori di espressività E language_code=it."""
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "sk_test")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "VOCE_IT")
    seen = {}
    _cattura_post(monkeypatch, seen)
    voice.synthesize("Ciao, come va?")
    vs = seen["json"]["voice_settings"]
    assert vs == {"stability": 0.45, "similarity_boost": 0.80,
                  "style": 0.25, "use_speaker_boost": True}
    assert seen["json"]["language_code"] == "it"
    assert seen["json"]["model_id"] == "eleven_flash_v2_5"


def test_espressivita_regolabile_da_ambiente(monkeypatch):
    """Andrea prova un timbro cambiando una variabile su Railway: i valori
    del corpo seguono i settings, non costanti cablate."""
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "sk_test")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "VOCE_IT")
    monkeypatch.setattr(settings, "elevenlabs_stability", 0.7)
    monkeypatch.setattr(settings, "elevenlabs_style", 0.15)
    monkeypatch.setattr(settings, "elevenlabs_speaker_boost", False)
    seen = {}
    _cattura_post(monkeypatch, seen)
    voice.synthesize("Prova")
    vs = seen["json"]["voice_settings"]
    assert vs["stability"] == 0.7 and vs["style"] == 0.15
    assert vs["use_speaker_boost"] is False


def test_status_espone_l_espressivita(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    s = voice.status()
    assert s["voice_stability"] == 0.45
    assert s["voice_similarity"] == 0.80
    assert s["voice_style"] == 0.25
    assert s["voice_speaker_boost"] is True


def test_stream_gli_errori_esplodono_prima_dei_byte(monkeypatch):
    """Contratto del fallback: se ElevenLabs non risponde, synthesize_stream
    deve sollevare PRIMA di produrre byte → /voice/tts fa 502 → il widget
    ripiega sulla voce del browser, identico a prima dello streaming."""
    import httpx as _httpx
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "sk_test")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "VOCE_IT")

    class _BadStream:
        def __enter__(self):
            raise _httpx.ConnectError("giù")

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(voice.httpx, "stream", lambda *a, **k: _BadStream())
    import pytest as _pytest
    with _pytest.raises(_httpx.ConnectError):
        voice.synthesize_stream("Ciao")


def test_stream_restituisce_i_byte_in_ordine(monkeypatch):
    monkeypatch.setattr(settings, "voice_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "sk_test")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "VOCE_IT")
    seen = {}

    class _OkStream:
        def __enter__(self):
            class R:
                def raise_for_status(self):
                    pass

                def iter_bytes(self):
                    yield b"AB"
                    yield b"CD"
            return R()

        def __exit__(self, *a):
            return False

    def fake_stream(method, url, **kw):
        seen["url"] = url
        seen["json"] = kw.get("json")
        return _OkStream()
    monkeypatch.setattr(voice.httpx, "stream", fake_stream)
    gen, ctype = voice.synthesize_stream("Ciao")
    assert b"".join(gen) == b"ABCD" and ctype == "audio/mpeg"
    assert seen["url"].endswith("/VOCE_IT/stream")
    assert seen["json"]["voice_settings"]["stability"] == 0.45   # stesso corpo del non-stream
