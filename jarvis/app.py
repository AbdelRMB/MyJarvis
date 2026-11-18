"""Application de bureau Jarvis.

- Fenêtre native (pas d'onglet de navigateur), cachée au démarrage de Windows (--cache).
- Icône dans la zone de notification : Ouvrir / Écoute « Jarvis » / Quitter.
- Appel : dire « Jarvis, … » ou « Hey Jarvis » (écoute de fond) ou Ctrl+Alt+J (réglable) -> la fenêtre apparaît et il t'écoute.
- Fermer la fenêtre la cache seulement ; « Quitter » dans l'icône arrête vraiment Jarvis.
"""
import json
import sys
import threading
import time
import traceback
import urllib.request

from .config import CONFIG, GELE, RACINE


def _journaux():
    """Sans console (appli installée / pythonw), on écrit dans logs/jarvis.log."""
    if sys.stdout is None or GELE or "pythonw" in sys.executable.lower():
        (RACINE / "logs").mkdir(exist_ok=True)
        f = open(RACINE / "logs" / "jarvis.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
        print(f"\n===== Démarrage {time.strftime('%Y-%m-%d %H:%M:%S')} =====")


def _appeler_instance(url):
    """Une instance tourne déjà : on lui demande d'afficher sa fenêtre."""
    try:
        with urllib.request.urlopen(f"{url}/api/session", timeout=2) as r:
            jeton = json.load(r)["jeton"]
        req = urllib.request.Request(f"{url}/api/fenetre/afficher", method="POST", headers={"x-jeton": jeton})
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def _icone():
    """Icône du réacteur dessinée à la volée."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), outline=(60, 232, 255, 255), width=5)
    d.ellipse((16, 16, 48, 48), outline=(60, 232, 255, 160), width=4)
    d.ellipse((24, 24, 40, 40), fill=(168, 245, 255, 255))
    return img


def main():
    cache = "--cache" in sys.argv
    _journaux()
    from . import web
    from .agent import Jarvis
    from .ecoute import EcouteFond

    url = f"http://{web.HOTE}:{web.PORT}"
    if web._deja_lance(url):
        _appeler_instance(url)
        return

    web.preparer()
    import uvicorn
    serveur = uvicorn.Server(uvicorn.Config(web.app, host=web.HOTE, port=web.PORT, log_level="warning", log_config=None))
    threading.Thread(target=serveur.run, daemon=True, name="serveur").start()
    for _ in range(100):
        if serveur.started:
            break
        time.sleep(0.05)
    print(f"  Serveur prêt sur {url}")

    import webview
    fen = webview.create_window("J.A.R.V.I.S.", url, width=1320, height=860, min_size=(420, 560), hidden=cache,
                                background_color="#04090f", text_select=True)
    etat = {"quitter": False}

    def afficher():
        try:
            fen.show()
            fen.restore()
            fen.on_top = True     # passe devant les autres fenêtres…
            time.sleep(0.2)
            fen.on_top = False    # …sans rester toujours au premier plan
        except Exception:
            traceback.print_exc()

    def en_fermeture():
        if etat["quitter"]:
            return True
        threading.Thread(target=fen.hide, daemon=True).start()
        return False              # annule la fermeture : la fenêtre est seulement cachée

    fen.events.closing += en_fermeture
    # NB : on ne touche pas à WebView2 pour autoriser le micro (bloquait tout le processus) :
    # Windows le demande une fois, le choix est mémorisé (storage_path).

    # --- « Hey Jarvis » en arrière-plan
    def sur_eveil():
        afficher()
        web.diffuser(type="vocal", etat="eveil")

    ecoute = EcouteFond(sur_eveil, web.commande_vocale, web.transcrire_rapide)
    if CONFIG.get("ecoute_fond", True):
        ecoute.demarrer()
    web.APPLI.update(active=True, afficher=afficher, ecoute=ecoute)

    # --- raccourci clavier global
    try:
        from pynput import keyboard
        keyboard.GlobalHotKeys({CONFIG.get("raccourci") or "<ctrl>+<alt>+j": afficher}).start()
    except Exception as e:
        print(f"  ! Raccourci clavier : {e}")

    # --- icône dans la zone de notification
    import pystray

    def basculer_ecoute(icone, _):
        if ecoute.actif:
            ecoute.arreter()
        else:
            ecoute.demarrer()
        CONFIG["ecoute_fond"] = not CONFIG.get("ecoute_fond", True)
        from .config import sauver_config
        sauver_config(["ecoute_fond"])

    def quitter(icone, _):
        etat["quitter"] = True
        ecoute.arreter()
        icone.stop()
        fen.destroy()

    icone = pystray.Icon("Jarvis", _icone(), "J.A.R.V.I.S. — Ctrl+Alt+J ou dis « Jarvis »", menu=pystray.Menu(
        pystray.MenuItem("Ouvrir Jarvis", lambda i, _: afficher(), default=True),
        pystray.MenuItem("Écoute « Jarvis »", basculer_ecoute, checked=lambda _: ecoute.actif),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", quitter)))
    icone.run_detached()

    # boucle de l'interface (bloque jusqu'à « Quitter ») ; Jarvis peut parler sans clic préalable
    import os
    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required")
    webview.start(private_mode=False, storage_path=str(RACINE / "webview"))

    serveur.should_exit = True
    try:
        print("Je mémorise ce que j'ai appris...")
        for f in web.jarvis.extraire_souvenirs():
            print(" ", f)
    except Exception:
        traceback.print_exc()
    Jarvis.liberer()


if __name__ == "__main__":
    main()
