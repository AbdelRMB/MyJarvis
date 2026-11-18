"""Lancement automatique de Jarvis à l'ouverture de session Windows (clé Run de l'utilisateur, sans droits admin)."""
import sys
import winreg
from pathlib import Path

from .config import GELE

CLE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM = "Jarvis"


def commande() -> str:
    if GELE:   # appli installée : l'exécutable lui-même
        return f'"{sys.executable}" --cache'
    racine = Path(__file__).resolve().parents[1]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{racine / "lanceur.pyw"}" --cache'


def est_actif() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE) as k:
            return bool(winreg.QueryValueEx(k, NOM)[0])
    except OSError:
        return False


def activer(oui: bool = True):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE, 0, winreg.KEY_SET_VALUE) as k:
        if oui:
            winreg.SetValueEx(k, NOM, 0, winreg.REG_SZ, commande())
        else:
            try:
                winreg.DeleteValue(k, NOM)
            except OSError:
                pass
