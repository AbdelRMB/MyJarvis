"""Ce qui dépend du système (Windows / macOS), au même endroit."""
import os
import subprocess
import sys
from pathlib import Path

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"
NOM_OS = "Windows" if WIN else "macOS" if MAC else "Linux"
CACHE_FENETRE = {"creationflags": subprocess.CREATE_NO_WINDOW} if WIN else {}


def shell(commande: str):
    """Argv pour exécuter une commande dans le shell du système."""
    if WIN:
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", commande]
    return ["/bin/zsh" if Path("/bin/zsh").exists() else "/bin/sh", "-lc", commande]


def ouvrir_chemin(cible: str):
    """Ouvre un fichier, dossier ou URL avec le programme par défaut."""
    if WIN:
        os.startfile(cible)
    elif MAC:
        subprocess.Popen(["open", cible])
    else:
        subprocess.Popen(["xdg-open", cible])


def osascript(script: str, timeout=15) -> str:
    """Exécute un AppleScript (macOS) et renvoie sa sortie."""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "AppleScript a échoué")
    return r.stdout.strip()


def echapper_as(texte: str) -> str:
    return texte.replace("\\", "\\\\").replace('"', '\\"')


def alerte(message: str, titre="Jarvis"):
    """Fenêtre d'alerte bloquante (à appeler dans un fil séparé)."""
    if WIN:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, titre, 0x40 | 0x40000)
    elif MAC:
        osascript(f'display dialog "{echapper_as(message)}" with title "{echapper_as(titre)}" '
                  f'buttons {{"OK"}} default button 1 with icon note', timeout=3600)


def dossiers_applications():
    if WIN:
        return [Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
                Path(os.environ.get("PROGRAMDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
                Path.home() / "Desktop", Path(os.environ.get("PUBLIC", "")) / "Desktop"]
    if MAC:
        return [Path("/Applications"), Path("/Applications/Utilities"), Path("/System/Applications"),
                Path("/System/Applications/Utilities"), Path.home() / "Applications"]
    return [Path("/usr/share/applications"), Path.home() / ".local/share/applications"]


def applications():
    """Chemins des applications installées (raccourcis .lnk sous Windows, bundles .app sous macOS)."""
    for base in dossiers_applications():
        if not base.exists():
            continue
        if WIN:
            yield from base.rglob("*.lnk")
            yield from base.rglob("*.url")
        elif MAC:
            yield from (p for p in base.iterdir() if p.suffix == ".app")
        else:
            yield from base.glob("*.desktop")


def vscode_stockage() -> Path:
    if WIN:
        return Path(os.environ.get("APPDATA", "")) / "Code/User/globalStorage"
    if MAC:
        return Path.home() / "Library/Application Support/Code/User/globalStorage"
    return Path.home() / ".config/Code/User/globalStorage"


def commande_vscode():
    """Commande pour lancer VS Code (le CLI « code » n'est pas toujours dans le PATH sur Mac)."""
    import shutil
    if shutil.which("code"):
        return ["code"]
    if MAC:
        cli = Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code")
        if cli.exists():
            return [str(cli)]
        return ["open", "-a", "Visual Studio Code", "--args"]
    return ["code"]


def touche_principale() -> str:
    """Touche des raccourcis système : Ctrl sous Windows, Cmd sous macOS."""
    return "command" if MAC else "ctrl"
