"""Outils de développement : VS Code, git, projets."""
import subprocess
from pathlib import Path

from . import outil
from .systeme import _run


def _code(*args):
    subprocess.Popen(["code", *args], shell=True)


@outil
def vscode_ouvrir(chemin: str, ligne: int = 0, nouvelle_fenetre: bool = False):
    """Ouvre un dossier ou un fichier dans VS Code (optionnellement à une ligne).
    chemin: fichier ou dossier
    ligne: numéro de ligne (optionnel)
    nouvelle_fenetre: ouvrir dans une nouvelle fenêtre"""
    args = ["-n"] if nouvelle_fenetre else []
    if ligne:
        args += ["-g", f"{chemin}:{ligne}"]
    else:
        args.append(chemin)
    _code(*args)
    return f"Ouvert dans VS Code : {chemin}"


@outil
def vscode_commande(commande: str):
    """Exécute une commande de la palette VS Code dans la fenêtre VS Code active (ex: 'Format Document', 'Toggle Terminal').
    commande: nom de la commande"""
    from .controle import gerer_fenetre, raccourci_clavier, taper_texte
    import time
    gerer_fenetre("Visual Studio Code", "activer"); time.sleep(0.4)
    raccourci_clavier("ctrl+shift+p"); time.sleep(0.4)
    taper_texte(commande); time.sleep(0.4)
    raccourci_clavier("enter")
    return f"Commande VS Code : {commande}"


@outil
def git(commande: str, depot: str):
    """Commande git dans un dépôt (ex: 'status', 'log --oneline -10', 'add -A', 'commit -m \"msg\"', 'push').
    commande: arguments git
    depot: dossier du dépôt"""
    return _run(f"git {commande}", ["powershell", "-NoProfile", "-Command"], depot)


@outil
def creer_projet(type_projet: str, nom: str, dossier: str = "~/Documents/Perso"):
    """Crée un nouveau projet et l'ouvre dans VS Code.
    type_projet: vite-react | next | node | python | vide
    nom: nom du projet
    dossier: dossier parent"""
    base = Path(dossier).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    cible = base / nom
    cmds = {
        "vite-react": f"npm create vite@latest {nom} -- --template react-ts; cd {nom}; npm install",
        "next": f"npx create-next-app@latest {nom} --ts --tailwind --eslint --app --use-npm --yes",
        "node": f"mkdir {nom}; cd {nom}; npm init -y; git init",
        "python": f"mkdir {nom}; cd {nom}; py -m venv .venv; git init; New-Item main.py",
        "vide": f"mkdir {nom}; cd {nom}; git init",
    }
    if type_projet not in cmds:
        return "Type inconnu."
    out = _run(cmds[type_projet], ["powershell", "-NoProfile", "-Command"], str(base), timeout=600)
    _code(str(cible))
    return f"{out[-1500:]}\nProjet ouvert dans VS Code : {cible}"
