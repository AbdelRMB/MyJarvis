"""Lancement automatique de Wesley à l'ouverture de session.

- Windows : clé Run de l'utilisateur (sans droits admin).
- macOS : LaunchAgent dans ~/Library/LaunchAgents.
"""
import sys
from pathlib import Path

from .config import GELE

NOM = "Wesley"
ETIQUETTE_MAC = "com.abdel.wesley"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{ETIQUETTE_MAC}.plist"


def arguments() -> list[str]:
    if GELE:   # appli installée : l'exécutable lui-même
        return [sys.executable, "--cache"]
    racine = Path(__file__).resolve().parents[1]
    py = Path(sys.executable)
    if sys.platform == "win32":
        py = py.with_name("pythonw.exe")
    return [str(py), str(racine / "lanceur.pyw"), "--cache"]


def commande() -> str:
    return " ".join(f'"{a}"' if " " in a or a.endswith(".exe") else a for a in arguments())


# ---------- macOS ----------
def plist_mac() -> str:
    from xml.sax.saxutils import escape
    args = "\n".join(f"        <string>{escape(a)}</string>" for a in arguments())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{ETIQUETTE_MAC}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
"""


def est_actif() -> bool:
    if sys.platform == "darwin":
        return PLIST.exists()
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            return bool(winreg.QueryValueEx(k, NOM)[0])
    except OSError:
        return False


def activer(oui: bool = True):
    if sys.platform == "darwin":
        if oui:
            PLIST.parent.mkdir(parents=True, exist_ok=True)
            PLIST.write_text(plist_mac(), encoding="utf-8")
        elif PLIST.exists():
            PLIST.unlink()
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                        winreg.KEY_SET_VALUE) as k:
        if oui:
            winreg.SetValueEx(k, NOM, 0, winreg.REG_SZ, commande())
        else:
            try:
                winreg.DeleteValue(k, NOM)
            except OSError:
                pass


# ---------- passage de Jarvis à Wesley (2.0.0) ----------
ANCIEN_NOM = "Jarvis"
ANCIENNE_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.abdel.jarvis.plist"


def migrer_ancien_nom():
    """L'appli s'appelait Jarvis avant la 2.0.0. Le lancement automatique enregistré sous l'ancien nom est repris
    sous le nouveau, et pointe toujours vers l'exécutable actuel (son chemin change avec le nom de l'appli)."""
    if sys.platform == "darwin":
        if ANCIENNE_PLIST.exists():
            ANCIENNE_PLIST.unlink()
            activer(True)
        elif PLIST.exists() and plist_mac() != PLIST.read_text(encoding="utf-8"):
            activer(True)
        return
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                        winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
        try:
            winreg.QueryValueEx(k, ANCIEN_NOM)
            winreg.DeleteValue(k, ANCIEN_NOM)
            ancien = True
        except OSError:
            ancien = False
    if ancien or (est_actif() and GELE):
        activer(True)


def nettoyer_ancienne_appli_windows():
    """Après la mise à jour qui a renommé l'appli : l'ancien dossier d'installation (Programs/Jarvis, ~250 Mo)
    et ses raccourcis ne servent plus. Appelé un peu après le démarrage, quand l'ancienne version est bien fermée."""
    import os
    import shutil
    if not (GELE and sys.platform == "win32"):
        return
    ancien = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / ANCIEN_NOM
    actuel = Path(sys.executable).resolve().parent
    if ancien.is_dir() and (ancien / f"{ANCIEN_NOM}.exe").exists() and ancien.resolve() != actuel:
        shutil.rmtree(ancien, ignore_errors=True)
    menu = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs"
    for lien in (menu / f"{ANCIEN_NOM}.lnk", menu / f"Mettre à jour {ANCIEN_NOM}.lnk",
                 Path.home() / "Desktop" / f"{ANCIEN_NOM}.lnk"):
        lien.unlink(missing_ok=True)
