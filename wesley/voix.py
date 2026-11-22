"""Voix optionnelle : reconnaissance (faster-whisper, local) et synthèse (voix Windows)."""
import threading

from .config import CONFIG

_moteur = None
_verrou = threading.Lock()
_whisper = None


def parler(texte):
    global _moteur
    if not CONFIG.get("voix_tts") or not texte.strip():
        return
    try:
        import pyttsx3
    except ImportError:
        return
    with _verrou:
        if _moteur is None:
            _moteur = pyttsx3.init()
            for v in _moteur.getProperty("voices"):
                if "fr" in (v.id + v.name).lower() or "french" in v.name.lower():
                    _moteur.setProperty("voice", v.id)
                    break
            _moteur.setProperty("rate", 185)
        _moteur.say(texte[:600])
        _moteur.runAndWait()


def ecouter():
    """Push-to-talk : enregistre jusqu'à ce que l'utilisateur appuie sur Entrée, puis transcrit."""
    global _whisper
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel
    if _whisper is None:
        from .modeles import charger_whisper
        _whisper = charger_whisper(CONFIG["whisper_modele"])
    morceaux = []
    flux = sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                          callback=lambda d, *_: morceaux.append(d.copy()))
    with flux:
        input("🎙️  Parle... (Entrée pour terminer) ")
    if not morceaux:
        return ""
    audio = np.concatenate(morceaux).flatten()
    segs, _ = _whisper.transcribe(audio, language="fr", vad_filter=True)
    return " ".join(s.text for s in segs).strip()
