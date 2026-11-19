"""Annonces : Jarvis te prévient de lui-même (automatisations), à voix haute et par une notification,
même si tu ne lui as pas parlé depuis longtemps et même si sa fenêtre est fermée.

- Interface ouverte : elle prononce l'annonce avec la voix choisie dans Réglages › Voix.
- Fenêtre jamais ouverte depuis le démarrage (interface non chargée) : Jarvis parle lui-même en fond
  (voix Microsoft Henri sur Mac, voix locale Piper sur Windows).
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import threading

from .plateforme import MAC, WIN


def _notification(texte: str, titre: str = "Jarvis"):
    try:
        if MAC:
            from .plateforme import echapper_as
            subprocess.Popen(["osascript", "-e", f'display notification "{echapper_as(texte[:240])}" '
                                                 f'with title "{echapper_as(titre)}" sound name "Glass"'])
        elif WIN:
            from . import web
            icone = web.APPLI.get("icone")
            if icone is not None:
                icone.notify(texte[:240], titre)
    except Exception as e:
        print(f"  ! Notification : {e}")


def _parler_en_fond(texte: str):
    """Synthèse vocale jouée directement par Jarvis (sans l'interface)."""
    from . import tts
    try:
        from .config import CONFIG
        en = CONFIG.get("langue") == "en"
        if MAC:
            audio, mime, _ = asyncio.run(tts.synthese(texte, "edge", "en-GB-RyanNeural" if en else "", 1.0))
            ext = ".mp3" if mime == "audio/mpeg" else ".wav"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(audio)
            subprocess.run(["afplay", f.name], timeout=120)
            os.unlink(f.name)
        elif WIN and en:   # la voix locale Piper est française : voix anglaise de Windows
            import pyttsx3
            moteur = pyttsx3.init()
            moteur.say(texte)
            moteur.runAndWait()
        elif WIN:
            import winsound
            voix = tts.voix_piper()
            if voix:
                winsound.PlaySound(tts._piper_synth(texte, voix[0], 1.0), winsound.SND_MEMORY)
    except Exception as e:
        print(f"  ! Voix de fond : {e}")
        if MAC:   # dernier recours : la voix du système
            from .config import CONFIG
            subprocess.run(["say", "-v", "Daniel" if CONFIG.get("langue") == "en" else "Thomas", texte], timeout=120)


def annoncer(texte: str, titre: str = "Jarvis", vue: str = "", genre: str = "info", detail: str = ""):
    """Prévient l'utilisateur : voix + notification du système + centre de notifications (cloche). Non bloquant."""
    from . import notifications, web
    _notification(texte, titre)
    notifications.ajouter(texte if titre == "Jarvis" else titre, detail or ("" if titre == "Jarvis" else texte), genre=genre, vue=vue)
    if web._clients:   # interface ouverte et branchée : elle parle avec la voix réglée par l'utilisateur
        web.diffuser(type="annonce", texte=texte)
    else:
        threading.Thread(target=_parler_en_fond, args=(texte,), daemon=True).start()
    print(f"  Annonce : {texte}")
    sys.stdout.flush()
