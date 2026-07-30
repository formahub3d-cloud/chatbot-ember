"""Proxy voce (STT/TTS) — le chiavi restano SUL SERVER, mai nel browser.

Provider selezionabile da .env con VOICE_PROVIDER:
  - "deepgram"    → STT nova-3 · TTS aura-2
  - "elevenlabs"  → STT scribe_v1 · TTS eleven_flash_v2_5
  - ""  (vuoto)   → disabilitato: gli endpoint rispondono 501 e il widget
                    usa la voce gratuita del browser (Web Speech API).

Così la "voce PRO" è un upsell attivabile senza toccare il widget:
basta impostare le chiavi come variabili d'ambiente del servizio.

ATTENZIONE (voce italiana): se ELEVENLABS_VOICE_ID è vuoto si ripiega su una
voce di libreria dal timbro INGLESE (il modello è multilingua ma l'accento
resta straniero). La configurazione mancante è visibile in /admin/status
(voice_id_set) e nei log a ogni sintesi: va impostata una voce italiana.
"""
import logging

import httpx

from .config import settings

log = logging.getLogger("ember")

# Voce di riserva della libreria ElevenLabs ("Rachel"): parla italiano perché il
# modello è multilingua, ma con timbro/accent INGLESE. Serve solo a non lasciare
# muto il servizio se ELEVENLABS_VOICE_ID manca: NON è la voce del prodotto.
_EL_FALLBACK_VOICE = "21m00Tcm4TlvDq8ikWAM"


def _clean(v: str) -> str:
    # Tollera spazi, ritorni a capo o virgolette incollati per errore con la chiave.
    return (v or "").strip().strip('"').strip("'").strip()


def _dg_key() -> str:
    return _clean(settings.deepgram_api_key)


def _el_key() -> str:
    return _clean(settings.elevenlabs_api_key)


def stt_enabled() -> bool:
    p = settings.voice_provider
    return (p == "deepgram" and bool(_dg_key())) or \
           (p == "elevenlabs" and bool(_el_key()))


def tts_enabled() -> bool:
    return stt_enabled()  # stessa chiave provider abilita entrambi


def status() -> dict:
    """Fotografia NON sensibile della configurazione voce, per /admin/status:
    da qui si vede a colpo d'occhio se manca la voce italiana (voice_id_set)."""
    p = settings.voice_provider
    out = {"voice_provider": p or "", "voice_lang": settings.voice_lang}
    if p == "elevenlabs":
        out["voice_id_set"] = bool(_clean(settings.elevenlabs_voice_id))
        out["voice_tts_model"] = settings.elevenlabs_model
        out["voice_stt_model"] = settings.elevenlabs_stt_model
    elif p == "deepgram":
        out["voice_id_set"] = True   # la voce è nel nome del modello TTS
        out["voice_tts_model"] = settings.deepgram_tts_model
        out["voice_stt_model"] = "nova-3"
    return out


def transcribe(audio: bytes, mime: str = "audio/webm") -> str:
    """Audio → testo. Solleva RuntimeError se il provider non è configurato."""
    p = settings.voice_provider
    if p == "deepgram":
        r = httpx.post(
            "https://api.deepgram.com/v1/listen",
            params={"model": "nova-3", "smart_format": "true", "language": settings.voice_lang},
            headers={"Authorization": f"Token {_dg_key()}", "Content-Type": mime},
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
            headers={"xi-api-key": _el_key()},
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
        vid = _clean(settings.elevenlabs_voice_id)
        if not vid:
            vid = _EL_FALLBACK_VOICE
            log.warning("ELEVENLABS_VOICE_ID vuoto: uso la voce di riserva %s "
                        "(timbro INGLESE). Imposta una voce italiana su Railway.", vid)
        r = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": _el_key(), "accept": "audio/mpeg"},
            json={"text": text, "model_id": settings.elevenlabs_model}, timeout=60,
        )
        r.raise_for_status()
        return r.content, "audio/mpeg"
    if p == "deepgram":
        r = httpx.post(
            "https://api.deepgram.com/v1/speak",
            params={"model": settings.deepgram_tts_model},
            headers={"Authorization": f"Token {_dg_key()}",
                     "Content-Type": "application/json"},
            json={"text": text}, timeout=60,
        )
        r.raise_for_status()
        return r.content, "audio/mpeg"
    raise RuntimeError("VOICE_PROVIDER non configurato per TTS")
