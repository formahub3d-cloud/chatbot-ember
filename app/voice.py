"""Proxy voce (STT/TTS) — le chiavi restano SUL SERVER, mai nel browser.

Provider selezionabile da .env con VOICE_PROVIDER:
  - "deepgram"    → STT nova-3 · TTS aura-2
  - "elevenlabs"  → STT scribe_v1 · TTS eleven_flash_v2_5
  - ""  (vuoto)   → disabilitato: gli endpoint rispondono 501 e il widget
                    usa la voce gratuita del browser (Web Speech API).

Così la "voce PRO" è un upsell attivabile senza toccare il widget:
basta impostare le chiavi come variabili d'ambiente del servizio.
"""
import httpx

from .config import settings


def stt_enabled() -> bool:
    p = settings.voice_provider
    return (p == "deepgram" and bool(settings.deepgram_api_key)) or \
           (p == "elevenlabs" and bool(settings.elevenlabs_api_key))


def tts_enabled() -> bool:
    return stt_enabled()  # stessa chiave provider abilita entrambi


def transcribe(audio: bytes, mime: str = "audio/webm") -> str:
    """Audio → testo. Solleva RuntimeError se il provider non è configurato."""
    p = settings.voice_provider
    if p == "deepgram":
        r = httpx.post(
            "https://api.deepgram.com/v1/listen",
            params={"model": "nova-3", "smart_format": "true", "language": settings.voice_lang},
            headers={"Authorization": f"Token {settings.deepgram_api_key}", "Content-Type": mime},
            content=audio, timeout=60,
        )
        r.raise_for_status()
        alts = r.json()["results"]["channels"][0]["alternatives"]
        return alts[0]["transcript"] if alts else ""
    if p == "elevenlabs":
        data = {"model_id": settings.elevenlabs_stt_model}
        if settings.voice_lang:
            data["language_code"] = settings.voice_lang   # hint lingua (migliora l'accuratezza)
        r = httpx.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": settings.elevenlabs_api_key},
            data=data,
            files={"file": ("audio", audio, mime)}, timeout=60,
        )
        r.raise_for_status()
        return r.json().get("text", "")
    raise RuntimeError("VOICE_PROVIDER non configurato per STT")


def synthesize(text: str) -> tuple[bytes, str]:
    """Testo → (audio, content_type). Solleva RuntimeError se non configurato."""
    p = settings.voice_provider
    if p == "elevenlabs":
        vid = settings.elevenlabs_voice_id or "21m00Tcm4TlvDq8ikWAM"  # voce di default (multilingua)
        r = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": settings.elevenlabs_api_key, "accept": "audio/mpeg"},
            json={"text": text, "model_id": settings.elevenlabs_model}, timeout=60,
        )
        r.raise_for_status()
        return r.content, "audio/mpeg"
    if p == "deepgram":
        r = httpx.post(
            "https://api.deepgram.com/v1/speak",
            params={"model": settings.deepgram_tts_model},
            headers={"Authorization": f"Token {settings.deepgram_api_key}",
                     "Content-Type": "application/json"},
            json={"text": text}, timeout=60,
        )
        r.raise_for_status()
        return r.content, "audio/mpeg"
    raise RuntimeError("VOICE_PROVIDER non configurato per TTS")
