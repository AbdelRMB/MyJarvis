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


def _appeler_instance(url, vue=None):
    """Une instance tourne déjà : on lui demande d'afficher sa fenêtre (sur une vue précise si besoin)."""
    try:
        with urllib.request.urlopen(f"{url}/api/session", timeout=2) as r:
            jeton = json.load(r)["jeton"]
        req = urllib.request.Request(f"{url}/api/fenetre/afficher", method="POST", data=json.dumps({"vue": vue}).encode(),
                                     headers={"x-jeton": jeton, "content-type": "application/json"})
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


def _relancer_jarvis():
    """Relance complète de Jarvis (le moteur d'affichage ne peut pas renaître dans la même fenêtre) :
    un petit script caché attend la fin de ce processus, puis relance Jarvis avec la fenêtre ouverte."""
    import os
    import subprocess
    from . import demarrage
    from .plateforme import CACHE_FENETRE
    args = [a for a in demarrage.arguments() if a != "--cache"]
    liste = ", ".join("'" + a.replace("'", "''") + "'" for a in args[1:])
    script = (f"Wait-Process -Id {os.getpid()} -Timeout 30 -ErrorAction SilentlyContinue; "
              f"Start-Process -FilePath '{args[0]}'" + (f" -ArgumentList {liste}" if liste else ""))
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                     creationflags=CACHE_FENETRE.get("creationflags", 0) | 0x00000008)   # DETACHED_PROCESS


def _proteger_affichage_windows(quitter):
    """Windows : si le moteur d'affichage (WebView2) plante, la fenêtre reste noire et ne répond plus.
    On note la cause dans le journal et on récupère tout seul : rechargement de la page, ou relance de Jarvis
    si c'est le moteur entier qui s'est arrêté."""
    try:
        from webview.platforms import edgechromium
    except Exception as e:
        print(f"  ! Surveillance de l'affichage : {e}")
        return
    origine = edgechromium.EdgeChrome.on_webview_ready
    etat = {"relance": False}

    def pret(self, sender, args):
        origine(self, sender, args)
        if not args.IsSuccess:
            return

        def echec(_expediteur, e):
            try:
                genre = str(e.ProcessFailedKind)
                details = f"raison {getattr(e, 'Reason', '?')}, code {getattr(e, 'ExitCode', '?')}, " \
                          f"{getattr(e, 'ProcessDescription', '') or ''}"
                print(f"  ! Affichage (WebView2) en échec : {genre} ({details.strip(', ')})")
                if "BrowserProcessExited" in genre:
                    if not etat["relance"]:
                        etat["relance"] = True
                        print("  Relance de Jarvis pour retrouver l'affichage.")
                        _relancer_jarvis()
                        threading.Thread(target=quitter, daemon=True).start()
                elif "GpuProcessExited" not in genre:   # le GPU repart tout seul ; le reste : on recharge
                    sender.CoreWebView2.Reload()
            except Exception:
                traceback.print_exc()

        try:
            sender.CoreWebView2.ProcessFailed += echec
        except Exception as e:
            print(f"  ! Surveillance de l'affichage : {e}")

    edgechromium.EdgeChrome.on_webview_ready = pret


def main():
    cache = "--cache" in sys.argv
    vue_maj = "majs" if "--maj" in sys.argv else None   # raccourci « Mettre à jour Jarvis »
    if vue_maj:
        cache = False
    _journaux()
    from . import rapport
    rapport.installer_crochets()   # une erreur non prévue devient un rapport de bug à envoyer (avec accord)
    from . import web
    from .agent import Jarvis
    from .ecoute import EcouteFond

    url = f"http://{web.HOTE}:{web.PORT}"
    if web._deja_lance(url):
        _appeler_instance(url, vue_maj)
        return
    from . import mises_a_jour
    if mises_a_jour.installer_au_demarrage(cache):   # version téléchargée en fond : installée, Jarvis se relance
        __import__("os")._exit(0)   # (« os » est importé plus bas dans main : variable locale)

    if GELE and sys.platform == "darwin" and sys.executable.startswith("/Applications/") \
            and not CONFIG.get("demarrage_auto_initialise"):
        from . import demarrage
        from .config import sauver_config
        demarrage.activer(True)
        CONFIG["demarrage_auto_initialise"] = True
        sauver_config(["demarrage_auto_initialise"])
    try:
        from .mises_a_jour import creer_raccourci_mac
        creer_raccourci_mac()   # « Mettre à jour Jarvis » trouvable dans Spotlight
    except Exception as e:
        print(f"  ! Raccourci de mise à jour : {e}")

    web.preparer()
    from . import rapport
    rapport.au_demarrage()
    mises_a_jour.demarrer_auto()   # plantage lors de la session précédente : propose d'envoyer le rapport
    import uvicorn
    serveur = uvicorn.Server(uvicorn.Config(web.app, host=web.HOTE, port=web.PORT, log_level="warning", log_config=None))
    threading.Thread(target=serveur.run, daemon=True, name="serveur").start()
    for _ in range(100):
        if serveur.started:
            break
        time.sleep(0.05)
    print(f"  Serveur prêt sur {url}")

    import webview
    # Au démarrage de l'ordinateur (--cache) : juste le processus (serveur + écoute de fond).
    # L'interface n'est chargée qu'au premier appel (« Jarvis », raccourci, icône).
    vide = "<html><body style='background:#04090f'></body></html>"
    from .version import VERSION
    # la version dans l'adresse : après une mise à jour, la page en cache de l'ancienne version n'est jamais réutilisée
    url_fenetre = f"{url}/?appli=1&v={VERSION}" + (f"&vue={vue_maj}" if vue_maj else "")
    fen = webview.create_window("J.A.R.V.I.S.", None if cache else url_fenetre, html=vide if cache else "",
                                width=1320, height=860, min_size=(420, 560), hidden=cache,
                                background_color="#04090f", text_select=True)
    etat = {"quitter": False, "charge": not cache}

    def afficher(vue=None):
        try:
            if not etat["charge"]:
                etat["charge"] = True
                fen.load_url(f"{url}/?appli=1&v={VERSION}" + (f"&vue={vue}" if vue else ""))
            elif vue:
                web.diffuser(type="naviguer", vue=vue)
            fen.show()
            fen.restore()
            fen.on_top = True     # passe devant les autres fenêtres…
            time.sleep(0.2)
            fen.on_top = False    # …sans rester toujours au premier plan
        except Exception:
            traceback.print_exc()

    def fermeture_systeme_mac() -> bool:
        """Mac : déconnexion, redémarrage ou extinction envoient l'Apple Event « quit » (un clic sur la croix,
        non). Dans ce cas Jarvis doit se fermer, sinon macOS affiche « Jarvis a interrompu la déconnexion »."""
        if sys.platform != "darwin":
            return False
        try:
            import Foundation
            ev = Foundation.NSAppleEventManager.sharedAppleEventManager().currentAppleEvent()
            return ev is not None and ev.eventClass() == 0x61657674 and ev.eventID() == 0x71756974   # 'aevt' 'quit'
        except Exception:
            return False

    def en_fermeture():
        if etat["quitter"]:
            return True
        if fermeture_systeme_mac():
            etat.update(quitter=True, fin_session=True)
            return True
        threading.Thread(target=fen.hide, daemon=True).start()
        return False              # annule la fermeture : la fenêtre est seulement cachée

    fen.events.closing += en_fermeture

    def surveiller_arret_windows():
        """Windows : à l'arrêt / redémarrage / déconnexion, la fenêtre reçoit une fermeture « WindowsShutDown ».
        On la laisse passer (sinon Jarvis bloque l'arrêt de Windows : « Cette application empêche l'arrêt »)."""
        try:
            from webview.platforms.winforms import BrowserView
            formulaire = BrowserView.instances[fen.uid]

            def sur_fermeture(_expediteur, args):
                if str(args.CloseReason) in ("WindowsShutDown", "TaskManagerClosing"):
                    etat.update(quitter=True, fin_session=True)
                    args.Cancel = False   # passe après le gestionnaire de pywebview, qui avait annulé
            formulaire.FormClosing += sur_fermeture
        except Exception as e:
            print(f"  ! Surveillance de l'arrêt de Windows : {e}")

    if sys.platform == "win32":
        fen.events.shown += surveiller_arret_windows
    # NB : on ne touche pas à WebView2 pour autoriser le micro (bloquait tout le processus) :
    # Windows le demande une fois, le choix est mémorisé (storage_path).

    # --- « Hey Jarvis » en arrière-plan
    def sur_eveil():
        afficher()
        web.diffuser(type="vocal", etat="eveil")

    ecoute = EcouteFond(sur_eveil, web.commande_vocale, web.transcrire_rapide,
                        sur_stop=web.stop_vocal, est_occupe=web.jarvis_occupe)
    if CONFIG.get("ecoute_fond", True):
        ecoute.demarrer()
    web.APPLI.update(active=True, afficher=afficher, ecoute=ecoute)

    # --- raccourci clavier global (relancé quand l'Accessibilité est accordée : macOS ne l'active qu'au démarrage)
    raccourcis = {"ecouteur": None}

    def demarrer_raccourcis():
        try:
            from pynput import keyboard
            if raccourcis["ecouteur"]:
                raccourcis["ecouteur"].stop()
            raccourcis["ecouteur"] = keyboard.GlobalHotKeys({CONFIG.get("raccourci") or "<ctrl>+<alt>+j": afficher,
                                                            "<ctrl>+<alt>+s": web.stop_vocal})   # arrêt d'urgence
            raccourcis["ecouteur"].start()
        except Exception as e:
            print(f"  ! Raccourci clavier : {e}")
    demarrer_raccourcis()
    web.APPLI["relancer_raccourcis"] = demarrer_raccourcis

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

    def quitter(icone=None, _=None):
        etat["quitter"] = True
        ecoute.arreter()
        try:
            (icone or etat.get("icone")).stop()
        except Exception:
            pass
        fen.destroy()

    web.APPLI["quitter"] = quitter   # utilisé par la mise à jour

    icone = pystray.Icon("Jarvis", _icone(), "J.A.R.V.I.S. — Ctrl+Alt+J ou dis « Jarvis »", menu=pystray.Menu(
        pystray.MenuItem("Ouvrir Jarvis", lambda i, _: afficher(), default=True),
        pystray.MenuItem("Écoute « Jarvis »", basculer_ecoute, checked=lambda _: ecoute.actif),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Mises à jour…", lambda i, _: afficher("majs")),
        pystray.MenuItem("Quitter", quitter)))
    etat["icone"] = icone
    web.APPLI["icone"] = icone   # notifications Windows des automatisations
    try:
        # sur Mac, l'icône vit dans la barre des menus, sur la boucle Cocoa de la fenêtre (d'où run_detached)
        icone.run_detached()
    except Exception as e:
        print(f"  ! Icône de notification indisponible ({e}) : appelle Jarvis à la voix ou au raccourci")

    # boucle de l'interface (bloque jusqu'à « Quitter ») ; Jarvis peut parler sans clic préalable
    import os
    if sys.platform == "win32":
        os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required")
        _proteger_affichage_windows(quitter)
    if cache:
        def precharger_interface():
            """Démarrage de l'ordinateur : l'interface se charge en arrière-plan, fenêtre cachée, quelques secondes
            après le lancement. Elle est ainsi prête à parler (avec la voix choisie) quand une automatisation se
            déclenche, et la fenêtre s'ouvre tout de suite quand on appelle Jarvis."""
            time.sleep(4)
            if not etat["charge"]:
                etat["charge"] = True
                try:
                    fen.load_url(url_fenetre)
                except Exception:
                    traceback.print_exc()
        threading.Thread(target=precharger_interface, daemon=True).start()
    webview.start(private_mode=False, storage_path=str(RACINE / "webview"))

    serveur.should_exit = True
    if etat.get("fin_session"):
        # l'ordinateur s'éteint : on part tout de suite (la mémoire est déjà synchronisée à chaque écriture)
        try:
            ecoute.arreter()
        except Exception:
            pass
        os._exit(0)
    from . import mises_a_jour
    if mises_a_jour.ETAT.get("quitter_pour_maj"):
        # mise à jour : on libère la place tout de suite (l'installateur attend notre fin pour remplacer l'appli)
        try:
            ecoute.arreter()
        except Exception:
            pass
        os._exit(0)
    try:
        print("Je mémorise ce que j'ai appris...")
        for f in web.jarvis.extraire_souvenirs():
            print(" ", f)
    except Exception:
        traceback.print_exc()
    Jarvis.liberer()


if __name__ == "__main__":
    main()
