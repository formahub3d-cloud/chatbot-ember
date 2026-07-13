"""Verifica veloce della voce PRO: sintetizza una frase e salva un file audio.

Uso (dopo aver impostato VOICE_PROVIDER + la chiave del provider):
  railway run python -m app.voice_selftest      # in cloud
  python -m app.voice_selftest                   # in locale con .env valorizzato
"""
import sys

from .config import settings
from . import voice


def main():
    if not voice.tts_enabled():
        print(f"Voce PRO NON attiva (VOICE_PROVIDER='{settings.voice_provider or ''}').")
        print("→ Imposta VOICE_PROVIDER=elevenlabs e ELEVENLABS_API_KEY, poi rilancia.")
        return 1
    model = settings.elevenlabs_model if settings.voice_provider == "elevenlabs" else settings.deepgram_tts_model
    print(f"Provider: {settings.voice_provider} · modello TTS: {model} · lingua: {settings.voice_lang}")
    try:
        audio, ctype = voice.synthesize("Ciao, sono Divina. La voce funziona correttamente.")
    except Exception as e:
        print(f"ERRORE dal provider: {e}")
        print("→ Controlla che la chiave sia valida e che il piano copra il TTS.")
        return 2
    out = "ember_voice_test.mp3"
    with open(out, "wb") as f:
        f.write(audio)
    print(f"OK: {len(audio)} byte scritti in {out} ({ctype}). Aprilo per ascoltare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
