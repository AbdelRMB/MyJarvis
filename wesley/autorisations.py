"""Autorisations du système (micro, écran, accessibilité, fichiers, contrôle des applis).

macOS ne permet à AUCUNE appli de s'accorder ces accès elle-même : c'est toujours l'utilisateur qui accepte.
Wesley les demande donc une seule fois (bandeau au premier lancement), retient ce qui a été demandé, et
l'écran Réglages › Autorisations permet de tout voir, accorder ou retirer.
Les accès restent acquis d'une version à l'autre parce que l'appli est signée avec un certificat stable
(construire-mac.sh) : avec une signature « ad hoc », macOS oubliait tout à chaque mise à jour.

Windows : les applis de bureau ont déjà accès aux fichiers, à l'écran et au clavier/souris ; seul le micro
peut être coupé dans Paramètres › Confidentialité.
"""
import os
import subprocess
import sys
import threading
from pathlib import Path

from .config import CONFIG, sauver_config

MAC = sys.platform == "darwin"
BUNDLE = "com.abdel.wesley"
REGLAGES_MAC = "x-apple.systempreferences:com.apple.preference.security?Privacy_"

# id -> (nom, à quoi ça sert, panneau des Réglages Système, service TCC pour « retirer »)
LISTE_MAC = {
    "micro": ("Micro", "T'entendre quand tu dis « Wesley », transcrire ta voix et tes réunions.", "Microphone", "Microphone"),
    "accessibilite": ("Accessibilité", "Raccourcis clavier globaux, souris et clavier pilotés par Wesley.", "Accessibility", "Accessibility"),
    "ecran": ("Enregistrement de l'écran", "Regarder ton écran quand tu lui demandes ce qui s'y trouve, et capter le son du Mac pour transcrire tes réunions en ligne.", "ScreenCapture", "ScreenCapture"),
    "fichiers": ("Accès complet au disque", "Lire et ranger tes fichiers partout (Bureau, Documents, Téléchargements…) sans autre question.", "AllFiles", "SystemPolicyAllFiles"),
    "automatisation": ("Contrôle des applications", "Ouvrir, fermer et piloter tes applis (Finder, Musique, navigateur…).", "Automation", "AppleEvents"),
}


# ---------- lecture de l'état (sans jamais déclencher de fenêtre de demande) ----------
def _micro_mac():
    try:
        import objc
        g = {}
        objc.loadBundle("AVFoundation", g, bundle_path="/System/Library/Frameworks/AVFoundation.framework")
        return {0: "a_demander", 1: "refuse", 2: "refuse", 3: "accorde"}.get(
            int(g["AVCaptureDevice"].authorizationStatusForMediaType_("soun")), "inconnu")
    except Exception:
        return "inconnu"


def _accessibilite_mac():
    try:
        import ApplicationServices
        return "accorde" if ApplicationServices.AXIsProcessTrusted() else "a_demander"
    except Exception:
        return "inconnu"


def _ecran_mac():
    try:
        import Quartz
        return "accorde" if Quartz.CGPreflightScreenCaptureAccess() else "a_demander"
    except Exception:
        return "inconnu"


def _fichiers_mac():
    # la base des autorisations n'est lisible qu'avec l'accès complet au disque (et la lire ne demande rien)
    base = Path.home() / "Library" / "Application Support" / "com.apple.TCC" / "TCC.db"
    try:
        with open(base, "rb"):
            return "accorde"
    except PermissionError:
        return "a_demander"
    except OSError:
        return "inconnu"


def _micro_windows():
    try:
        import winreg
        cle = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
        valeurs = []
        for sous in (cle, cle + r"\NonPackaged"):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sous) as k:
                    valeurs.append(winreg.QueryValueEx(k, "Value")[0])
            except OSError:
                pass
        return "refuse" if "Deny" in valeurs else "accorde"
    except Exception:
        return "inconnu"


def _automatisation_mac():
    """macOS ne permet pas de lire cette autorisation sans la redemander : on retient la réponse obtenue."""
    return CONFIG.get("autorisation_automatisation") or "inconnu"


_accessibilite_avant = {"etat": None}


def _surveiller_accessibilite(etat_actuel: str):
    """Accessibilité accordée pendant que Wesley tourne : on relance les raccourcis clavier globaux
    (sinon ils ne marchaient qu'après un redémarrage de Wesley)."""
    if etat_actuel == "accorde" and _accessibilite_avant["etat"] not in (None, "accorde"):
        from . import web
        if web.APPLI.get("relancer_raccourcis"):
            web.APPLI["relancer_raccourcis"]()
    _accessibilite_avant["etat"] = etat_actuel


def etat() -> dict:
    deja = set(CONFIG.get("autorisations_demandees") or [])
    if MAC:
        lecteurs = {"micro": _micro_mac, "accessibilite": _accessibilite_mac, "ecran": _ecran_mac,
                    "fichiers": _fichiers_mac, "automatisation": _automatisation_mac}
        liste = [{"id": i, "nom": n, "role": r, "etat": lecteurs[i](), "demande_faite": i in deja}
                 for i, (n, r, _, _) in LISTE_MAC.items()]
        _surveiller_accessibilite(next(a["etat"] for a in liste if a["id"] == "accessibilite"))
    else:
        liste = [
            {"id": "micro", "nom": "Micro", "role": "T'entendre quand tu dis « Wesley » et transcrire tes réunions.", "etat": _micro_windows(),
             "demande_faite": True},
            {"id": "systeme", "nom": "Fichiers, écran, clavier et souris",
             "role": "Accordés d'office aux applis de bureau sous Windows.", "etat": "accorde", "demande_faite": True},
        ]
    # à proposer au démarrage : jamais demandé ET pas déjà accordé (une seule demande, puis plus jamais)
    a_proposer = [a["id"] for a in liste if not a["demande_faite"] and a["etat"] != "accorde"]
    return {"plateforme": "mac" if MAC else "windows", "autorisations": liste, "a_proposer": a_proposer}


def etat_un(i: str) -> str:
    return {"micro": _micro_mac, "accessibilite": _accessibilite_mac, "ecran": _ecran_mac, "fichiers": _fichiers_mac,
            "automatisation": _automatisation_mac}[i]() if MAC else "accorde"


def _noter_demande(i: str):
    deja = list(CONFIG.get("autorisations_demandees") or [])
    if i not in deja:
        CONFIG["autorisations_demandees"] = deja + [i]
        sauver_config(["autorisations_demandees"])


def ignorer(ids: list):
    """« Plus tard / non merci » : on ne les redemandera plus (restent gérables dans les Réglages)."""
    for i in ids:
        _noter_demande(i)


# ---------- demander / ouvrir les réglages / retirer ----------
def ouvrir_reglages(i: str):
    if MAC:
        subprocess.Popen(["open", REGLAGES_MAC + LISTE_MAC.get(i, ("", "", "Microphone", ""))[2]])
    else:
        os.startfile("ms-settings:privacy-microphone")   # noqa: S606


def demander(i: str) -> str:
    """Affiche la demande du système (une seule fois). Renvoie ce que l'appli doit faire ensuite."""
    _noter_demande(i)
    if not MAC:
        ouvrir_reglages(i)
        return "reglages"
    if i in ("accessibilite", "automatisation") and etat_un(i) != "accorde":
        # une ancienne version de Wesley (autre signature) peut avoir laissé une entrée « activée » qui ne
        # s'applique plus : on l'efface pour que la demande concerne bien cette version
        subprocess.run(["tccutil", "reset", LISTE_MAC[i][3], BUNDLE], capture_output=True)
    try:
        if i == "micro":
            import objc
            g = {}
            objc.loadBundle("AVFoundation", g, bundle_path="/System/Library/Frameworks/AVFoundation.framework")
            if _micro_mac() == "a_demander":
                g["AVCaptureDevice"].requestAccessForMediaType_completionHandler_("soun", lambda ok: None)
                return "demande"
        elif i == "accessibilite":
            import ApplicationServices
            if not ApplicationServices.AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}):
                return "demande"
        elif i == "ecran":
            import Quartz
            if not Quartz.CGPreflightScreenCaptureAccess():
                Quartz.CGRequestScreenCaptureAccess()
                return "demande"
        elif i == "automatisation":
            # une commande AppleScript vers « System Events » déclenche la demande au nom de Wesley ;
            # on retient la réponse (macOS ne permet pas de la relire ensuite sans redemander)
            def essayer():
                try:
                    r = subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of first process'],
                                       capture_output=True, text=True, timeout=180)
                    resultat = "accorde" if r.returncode == 0 else "refuse" if "-1743" in r.stderr else "inconnu"
                except subprocess.TimeoutExpired:
                    resultat = "inconnu"
                CONFIG["autorisation_automatisation"] = resultat
                sauver_config(["autorisation_automatisation"])
            threading.Thread(target=essayer, daemon=True).start()
            return "demande"
    except Exception as e:
        print(f"  ! Autorisation {i} : {e}")
    # déjà refusé une fois (macOS ne redemande plus) ou réglage manuel (accès complet au disque)
    ouvrir_reglages(i)
    return "reglages"


def retirer(i: str) -> str:
    """Retire l'accès accordé à Wesley. macOS le redemandera la prochaine fois qu'il en aura besoin."""
    if not MAC:
        ouvrir_reglages(i)
        return "reglages"
    service = LISTE_MAC[i][3]
    if i == "automatisation":
        CONFIG["autorisation_automatisation"] = ""
        sauver_config(["autorisation_automatisation"])
    r = subprocess.run(["tccutil", "reset", service, BUNDLE], capture_output=True, text=True)
    if r.returncode != 0:
        ouvrir_reglages(i)
        return "reglages"
    return "retire"
