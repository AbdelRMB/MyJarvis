"""Outils de développement : VS Code, git, projets."""
import subprocess
from pathlib import Path

from . import outil
from ..plateforme import MAC, WIN, commande_vscode, touche_principale
from .systeme import _run


def _code(*args):
    subprocess.Popen([*commande_vscode(), *args], shell=WIN)


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
    return f"Ouvert dans VS Code : {chemin}" + _indice_wesley_md(chemin)


def _indice_wesley_md(chemin) -> str:
    """Projet ouvert : signale son WESLEY.md (instructions du projet) pour que Wesley le lise avant d'y travailler."""
    try:
        from .. import wesley_md
        if wesley_md.est_dans_un_projet(chemin) and wesley_md.fichiers(chemin):
            return " — ce projet a un WESLEY.md : lis-le (lire_wesley_md) avant d'y travailler."
    except Exception:
        pass
    return ""


@outil
def vscode_commande(commande: str):
    """Exécute une commande de la palette VS Code dans la fenêtre VS Code active (ex: 'Format Document', 'Toggle Terminal').
    commande: nom de la commande"""
    from .controle import gerer_fenetre, raccourci_clavier, taper_texte
    import time
    gerer_fenetre("Visual Studio Code" if not MAC else "Code", "activer"); time.sleep(0.4)
    raccourci_clavier(f"{touche_principale()}+shift+p"); time.sleep(0.4)
    taper_texte(commande); time.sleep(0.4)
    raccourci_clavier("enter")
    return f"Commande VS Code : {commande}"


@outil
def git(commande: str, depot: str):
    """Commande git dans un dépôt (ex: 'status', 'log --oneline -10', 'add -A', 'commit -m \"msg\"', 'push').
    commande: arguments git
    depot: dossier du dépôt"""
    return _run(f"git {commande}", cwd=depot)


@outil
def creer_projet(type_projet: str, nom: str, dossier: str = "~/Documents/Perso"):
    """Crée un nouveau projet et l'ouvre dans VS Code.
    type_projet: vite-react | next | node | python | vide
    nom: nom du projet
    dossier: dossier parent"""
    base = Path(dossier).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    cible = base / nom
    py, fichier = ("py", "New-Item main.py") if WIN else ("python3", "touch main.py")
    cmds = {
        "vite-react": f"npm create vite@latest {nom} -- --template react-ts; cd {nom}; npm install",
        "next": f"npx create-next-app@latest {nom} --ts --tailwind --eslint --app --use-npm --yes",
        "node": f"mkdir {nom}; cd {nom}; npm init -y; git init",
        "python": f"mkdir {nom}; cd {nom}; {py} -m venv .venv; git init; {fichier}",
        "vide": f"mkdir {nom}; cd {nom}; git init",
    }
    if type_projet not in cmds:
        return "Type inconnu."
    out = _run(cmds[type_projet], cwd=str(base), timeout=600)
    md = ""
    if cible.is_dir():
        try:
            from .. import wesley_md
            f, cree = wesley_md.creer(cible)
            md = f"\nWESLEY.md créé ({f}) : complète-le et tiens-le à jour." if cree else ""
        except Exception:
            pass
    _code(str(cible))
    return f"{out[-1500:]}\nProjet ouvert dans VS Code : {cible}{md}"
