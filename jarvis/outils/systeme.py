import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import psutil

from . import ajouter_fonction, outil
from ..plateforme import CACHE_FENETRE, MAC, WIN, applications, echapper_as, osascript, ouvrir_chemin, shell


def _run(cmd, shell_exe=None, cwd=None, timeout=120):
    """Exécute une commande dans le shell du système (PowerShell / zsh) et renvoie code + sortie."""
    argv = shell_exe + [cmd] if shell_exe else shell(cmd)
    r = subprocess.run(argv, capture_output=True, text=True, cwd=cwd or str(Path.home()),
                       timeout=timeout, encoding="utf-8", errors="replace", **CACHE_FENETRE)
    out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
    return f"(code {r.returncode})\n{out.strip()}" if out.strip() else f"(code {r.returncode}) aucune sortie"


def powershell(commande: str, dossier: str = "", timeout: int = 120):
    """Exécute une commande PowerShell sur le PC et renvoie la sortie. Pour tout ce qui n'a pas d'outil dédié (git, npm, winget, réseau, registre...).
    commande: la commande PowerShell
    dossier: dossier de travail (optionnel)
    timeout: secondes max (défaut 120)"""
    return _run(commande, cwd=dossier or None, timeout=timeout)


def terminal(commande: str, dossier: str = "", timeout: int = 120):
    """Exécute une commande dans le terminal du Mac (zsh) et renvoie la sortie. Pour tout ce qui n'a pas d'outil dédié (git, npm, brew, réseau, defaults...).
    commande: la commande shell
    dossier: dossier de travail (optionnel)
    timeout: secondes max (défaut 120)"""
    return _run(commande, cwd=dossier or None, timeout=timeout)


# l'outil de commandes porte le nom que le modèle connaît pour ce système
ajouter_fonction(terminal if MAC else powershell, "terminal" if MAC else "powershell")


@outil
def lancer_en_arriere_plan(commande: str, dossier: str = ""):
    """Lance une commande longue (serveur dev, script) dans une nouvelle fenêtre de terminal visible, sans attendre la fin.
    commande: la commande à lancer
    dossier: dossier de travail"""
    dossier = dossier or str(Path.home())
    if WIN:
        subprocess.Popen(["powershell", "-NoExit", "-Command", commande], cwd=dossier,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif MAC:
        osascript(f'tell application "Terminal" to do script "cd {echapper_as(repr(dossier))} && {echapper_as(commande)}"')
        osascript('tell application "Terminal" to activate')
    else:
        subprocess.Popen(shell(commande), cwd=dossier, start_new_session=True)
    return f"Lancé dans une nouvelle fenêtre : {commande}"


@outil
def executer_python(code: str):
    """Exécute un script Python et renvoie sa sortie (calculs, traitement de données, automatisations).
    code: le code Python complet"""
    f = Path(tempfile.gettempdir()) / "jarvis_script.py"
    f.write_text(code, encoding="utf-8")
    # dans l'appli installée, sys.executable est Jarvis lui-même : on prend le Python du système
    py = sys.executable if not getattr(sys, "frozen", False) else (shutil.which("python3") or shutil.which("python") or shutil.which("py"))
    if not py:
        return "Erreur : aucun Python installé sur cette machine pour exécuter le script."
    r = subprocess.run([py, str(f)], capture_output=True, text=True, timeout=300,
                       encoding="utf-8", errors="replace", **CACHE_FENETRE)
    return (r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr else "")).strip() or "(aucune sortie)"


def _raccourcis():
    yield from applications()


ALIAS_WIN = {"calculatrice": "calc", "bloc-notes": "notepad", "notepad": "notepad", "explorateur": "explorer",
             "paramètres": "ms-settings:", "parametres": "ms-settings:", "terminal": "wt", "cmd": "cmd",
             "gestionnaire des tâches": "taskmgr", "vscode": "code", "vs code": "code"}
ALIAS_MAC = {"calculatrice": "Calculator", "notes": "Notes", "bloc-notes": "TextEdit", "finder": "Finder",
             "explorateur": "Finder", "paramètres": "System Settings", "parametres": "System Settings",
             "réglages": "System Settings", "terminal": "Terminal", "moniteur d'activité": "Activity Monitor",
             "gestionnaire des tâches": "Activity Monitor", "vscode": "Visual Studio Code",
             "vs code": "Visual Studio Code", "navigateur": "Safari", "musique": "Music", "mail": "Mail",
             "calendrier": "Calendar", "photos": "Photos", "messages": "Messages"}


@outil
def ouvrir_application(nom: str):
    """Ouvre une application installée par son nom (ex: Discord, Spotify, Chrome, Steam, Word, Calculatrice).
    nom: nom de l'application"""
    n = nom.lower().strip()
    if MAC:
        cible = ALIAS_MAC.get(n)
        if not cible:
            cands = [p for p in _raccourcis() if n in p.stem.lower()]
            cands.sort(key=lambda p: (p.stem.lower() != n, len(p.stem)))
            cible = str(cands[0]) if cands else nom
        r = subprocess.run(["open", "-a", cible], capture_output=True, text=True)
        return f"{Path(cible).stem} ouvert." if r.returncode == 0 else f"Introuvable : {nom}"
    if n in ALIAS_WIN:
        subprocess.Popen(ALIAS_WIN[n], shell=True)
        return f"{nom} ouvert."
    cands = [p for p in _raccourcis() if n in p.stem.lower()]
    if cands:
        cands.sort(key=lambda p: (p.stem.lower() != n, "uninstall" in p.stem.lower(), len(p.stem)))
        ouvrir_chemin(str(cands[0]))
        return f"Ouvert : {cands[0].stem}"
    try:
        subprocess.Popen(nom, shell=True)
        return f"Tentative de lancement direct de '{nom}'."
    except Exception as e:
        return f"Introuvable : {nom} ({e})"


@outil
def lister_applications(filtre: str = ""):
    """Liste les applications installées.
    filtre: texte à filtrer (optionnel)"""
    noms = sorted({p.stem for p in _raccourcis() if filtre.lower() in p.stem.lower()})
    return "\n".join(noms[:300]) or "Aucune."


@outil
def ouvrir(cible: str):
    """Ouvre un fichier, un dossier ou une URL avec le programme par défaut.
    cible: chemin ou URL"""
    ouvrir_chemin(cible)
    return f"Ouvert : {cible}"


@outil
def infos_systeme():
    """Donne l'état de l'ordinateur : CPU, RAM, disques, batterie, GPU, uptime."""
    import time
    l = [f"CPU : {psutil.cpu_percent(interval=0.5)}% ({psutil.cpu_count()} threads)"]
    m = psutil.virtual_memory()
    l.append(f"RAM : {m.used/1e9:.1f}/{m.total/1e9:.1f} Go ({m.percent}%)")
    for p in psutil.disk_partitions():
        if MAC and not (p.mountpoint == "/" or p.mountpoint.startswith("/Volumes/")):
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
            l.append(f"Disque {p.mountpoint} : {u.free/1e9:.0f} Go libres / {u.total/1e9:.0f} Go")
        except Exception:
            pass
    b = psutil.sensors_battery()
    if b:
        l.append(f"Batterie : {b.percent}% {'(secteur)' if b.power_plugged else ''}")
    if shutil.which("nvidia-smi"):
        try:
            g = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                                "--format=csv,noheader"], capture_output=True, text=True, timeout=5, **CACHE_FENETRE).stdout.strip()
            l.append(f"GPU : {g}")
        except Exception:
            pass
    elif MAC:
        try:
            puce = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=5).stdout.strip()
            l.append(f"Puce : {puce}")
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
    """Ferme (kill) un processus par nom (ex: chrome.exe, Spotify) ou PID.
    nom_ou_pid: nom du processus ou PID"""
    tues = []
    for p in psutil.process_iter(["pid", "name"]):
        if str(p.info["pid"]) == nom_ou_pid or (p.info["name"] or "").lower() in (nom_ou_pid.lower(), nom_ou_pid.lower() + ".exe"):
            try:
                p.kill(); tues.append(f"{p.info['name']}({p.info['pid']})")
            except Exception:
                pass
    return f"Fermés : {', '.join(tues)}" if tues else "Aucun processus correspondant."


_minuteur_alim = None


@outil
def alimentation(action: str):
    """Verrouille, met en veille, redémarre ou éteint l'ordinateur.
    action: verrouiller | veille | redemarrer | eteindre | annuler"""
    global _minuteur_alim
    if action not in ("verrouiller", "veille", "redemarrer", "eteindre", "annuler"):
        return "Action inconnue."
    if WIN:
        cmds = {"verrouiller": "rundll32.exe user32.dll,LockWorkStation",
                "veille": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                "redemarrer": "shutdown /r /t 15", "eteindre": "shutdown /s /t 15", "annuler": "shutdown /a"}
        subprocess.Popen(cmds[action], shell=True)
    elif MAC:
        if action == "annuler":
            if _minuteur_alim:
                _minuteur_alim.cancel()
                _minuteur_alim = None
                return "Annulé."
            return "Rien à annuler."
        if action == "verrouiller":   # Ctrl+Cmd+Q
            osascript('tell application "System Events" to keystroke "q" using {control down, command down}')
        elif action == "veille":
            subprocess.Popen(["pmset", "sleepnow"])
        else:   # 15 s pour pouvoir annuler, comme sous Windows
            ordre = "restart" if action == "redemarrer" else "shut down"
            _minuteur_alim = threading.Timer(15, lambda: osascript(f'tell application "System Events" to {ordre}'))
            _minuteur_alim.daemon = True
            _minuteur_alim.start()
    return f"{action} lancé" + (" (15 s, 'annuler' possible)" if action in ("redemarrer", "eteindre") else "")
