"""Lancement automatique de Jarvis à l'ouverture de session.

- Windows : clé Run de l'utilisateur (sans droits admin).
- macOS : LaunchAgent dans ~/Library/LaunchAgents.
"""
import sys
from pathlib import Path

from .config import GELE

NOM = "Jarvis"
ETIQUETTE_MAC = "com.abdel.jarvis"
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
