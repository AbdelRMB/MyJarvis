import os
import subprocess
import sys
import tempfile
from pathlib import Path

import psutil

from . import outil

START_MENU = [
    Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
]
DESKTOP = Path.home() / "Desktop"


def _run(cmd, shell_exe, cwd=None, timeout=120):
    r = subprocess.run(shell_exe + [cmd], capture_output=True, text=True, cwd=cwd or str(Path.home()),
                       timeout=timeout, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
    return f"(code {r.returncode})\n{out.strip()}" if out.strip() else f"(code {r.returncode}) aucune sortie"


@outil
def powershell(commande: str, dossier: str = "", timeout: int = 120):
    """Exécute une commande PowerShell sur le PC et renvoie la sortie. Pour tout ce qui n'a pas d'outil dédié (git, npm, winget, réseau, registre...).
    commande: la commande PowerShell
    dossier: dossier de travail (optionnel)
    timeout: secondes max (défaut 120)"""
    return _run(commande, ["powershell", "-NoProfile", "-NonInteractive", "-Command"], dossier or None, timeout)


@outil
def lancer_en_arriere_plan(commande: str, dossier: str = ""):
    """Lance une commande longue (serveur dev, script) dans une nouvelle fenêtre PowerShell visible sans attendre la fin.
    commande: la commande à lancer
    dossier: dossier de travail"""
    subprocess.Popen(["powershell", "-NoExit", "-Command", commande], cwd=dossier or str(Path.home()),
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
    return f"Lancé dans une nouvelle fenêtre : {commande}"


@outil
def executer_python(code: str):
    """Exécute un script Python et renvoie sa sortie (calculs, traitement de données, automatisations).
    code: le code Python complet"""
    f = Path(tempfile.gettempdir()) / "jarvis_script.py"
    f.write_text(code, encoding="utf-8")
    r = subprocess.run([sys.executable, str(f)], capture_output=True, text=True, timeout=300,
                       encoding="utf-8", errors="replace")
    return (r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr else "")).strip() or "(aucune sortie)"


def _raccourcis():
    for base in START_MENU + [DESKTOP, Path(os.environ.get("PUBLIC", "")) / "Desktop"]:
        if base.exists():
            yield from base.rglob("*.lnk")
            yield from base.rglob("*.url")


@outil
def ouvrir_application(nom: str):
    """Ouvre une application installée par son nom (ex: Discord, Spotify, Chrome, Steam, Word, Calculatrice).
    nom: nom de l'application"""
    n = nom.lower()
    alias = {"calculatrice": "calc", "bloc-notes": "notepad", "notepad": "notepad", "explorateur": "explorer",
             "paramètres": "ms-settings:", "parametres": "ms-settings:", "terminal": "wt", "cmd": "cmd",
             "gestionnaire des tâches": "taskmgr", "vscode": "code", "vs code": "code"}
    if n in alias:
        subprocess.Popen(alias[n], shell=True)
        return f"{nom} ouvert."
    cands = [p for p in _raccourcis() if n in p.stem.lower()]
    if cands:
        cands.sort(key=lambda p: (p.stem.lower() != n, "uninstall" in p.stem.lower(), len(p.stem)))
        os.startfile(str(cands[0]))
        return f"Ouvert : {cands[0].stem}"
    try:
        subprocess.Popen(nom, shell=True)
        return f"Tentative de lancement direct de '{nom}'."
    except Exception as e:
        return f"Introuvable : {nom} ({e})"


@outil
def lister_applications(filtre: str = ""):
    """Liste les applications installées (raccourcis du menu Démarrer).
    filtre: texte à filtrer (optionnel)"""
    noms = sorted({p.stem for p in _raccourcis() if filtre.lower() in p.stem.lower()})
    return "\n".join(noms[:300]) or "Aucune."


@outil
def ouvrir(cible: str):
    """Ouvre un fichier, un dossier ou une URL avec le programme par défaut.
    cible: chemin ou URL"""
    os.startfile(cible)
    return f"Ouvert : {cible}"


@outil
def infos_systeme():
    """Donne l'état du PC : CPU, RAM, disques, batterie, GPU, uptime."""
    import time
    l = [f"CPU : {psutil.cpu_percent(interval=0.5)}% ({psutil.cpu_count()} threads)"]
    m = psutil.virtual_memory()
    l.append(f"RAM : {m.used/1e9:.1f}/{m.total/1e9:.1f} Go ({m.percent}%)")
    for p in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(p.mountpoint)
            l.append(f"Disque {p.mountpoint} : {u.free/1e9:.0f} Go libres / {u.total/1e9:.0f} Go")
        except Exception:
            pass
    b = psutil.sensors_battery()
    if b:
        l.append(f"Batterie : {b.percent}% {'(secteur)' if b.power_plugged else ''}")
    try:
        g = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                            "--format=csv,noheader"], capture_output=True, text=True, timeout=5).stdout.strip()
        l.append(f"GPU : {g}")
    except Exception:
        pass
    l.append(f"Allumé depuis : {(time.time()-psutil.boot_time())/3600:.1f} h")
    return "\n".join(l)


@outil
def lister_processus(filtre: str = ""):
    """Liste les processus en cours (triés par RAM).
    filtre: nom à filtrer (optionnel)"""
    ps = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            if filtre.lower() in (p.info["name"] or "").lower():
                ps.append((p.info["memory_info"].rss, p.info["pid"], p.info["name"]))
        except Exception:
            pass
    ps.sort(reverse=True)
    return "\n".join(f"{pid}\t{n}\t{r/1e6:.0f} Mo" for r, pid, n in ps[:60])


@outil
def fermer_processus(nom_ou_pid: str):
    """Ferme (kill) un processus par nom (ex: chrome.exe) ou PID.
    nom_ou_pid: nom du processus ou PID"""
    tues = []
    for p in psutil.process_iter(["pid", "name"]):
        if str(p.info["pid"]) == nom_ou_pid or (p.info["name"] or "").lower() in (nom_ou_pid.lower(), nom_ou_pid.lower() + ".exe"):
            try:
                p.kill(); tues.append(f"{p.info['name']}({p.info['pid']})")
            except Exception:
                pass
    return f"Fermés : {', '.join(tues)}" if tues else "Aucun processus correspondant."


@outil
def alimentation(action: str):
    """Verrouille, met en veille, redémarre ou éteint le PC.
    action: verrouiller | veille | redemarrer | eteindre | annuler"""
    cmds = {"verrouiller": "rundll32.exe user32.dll,LockWorkStation",
            "veille": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
            "redemarrer": "shutdown /r /t 15", "eteindre": "shutdown /s /t 15", "annuler": "shutdown /a"}
    if action not in cmds:
        return "Action inconnue."
    subprocess.Popen(cmds[action], shell=True)
    return f"{action} lancé" + (" (15 s, 'annuler' possible)" if action in ("redemarrer", "eteindre") else "")
