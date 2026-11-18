import fnmatch
import os
import re
import shutil
from pathlib import Path

from send2trash import send2trash

from . import outil

IGNORE = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next", "AppData"}


def _p(chemin: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(chemin))).resolve()


@outil
def lire_fichier(chemin: str, debut: int = 1, fin: int = 400):
    """Lit un fichier texte (avec numéros de ligne).
    chemin: chemin du fichier
    debut: première ligne (défaut 1)
    fin: dernière ligne (défaut 400)"""
    lignes = _p(chemin).read_text(encoding="utf-8", errors="replace").splitlines()
    sel = lignes[debut - 1:fin]
    out = "\n".join(f"{i}\t{l}" for i, l in enumerate(sel, debut))
    return out + (f"\n[... {len(lignes)} lignes au total]" if len(lignes) > fin else "")


@outil
def ecrire_fichier(chemin: str, contenu: str):
    """Crée ou remplace entièrement un fichier (crée les dossiers parents). Pour coder un fichier complet.
    chemin: chemin du fichier
    contenu: contenu complet"""
    p = _p(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contenu, encoding="utf-8")
    return f"Écrit : {p} ({len(contenu)} caractères)"


@outil
def modifier_fichier(chemin: str, ancien: str, nouveau: str):
    """Remplace un extrait exact de texte dans un fichier (modification ciblée de code).
    chemin: chemin du fichier
    ancien: texte exact à remplacer (doit être unique)
    nouveau: texte de remplacement"""
    p = _p(chemin)
    t = p.read_text(encoding="utf-8")
    n = t.count(ancien)
    if n == 0:
        return "Erreur : texte 'ancien' introuvable. Relis le fichier avec lire_fichier."
    if n > 1:
        return f"Erreur : texte trouvé {n} fois, ajoute plus de contexte."
    p.write_text(t.replace(ancien, nouveau), encoding="utf-8")
    return f"Modifié : {p}"


@outil
def lister_dossier(chemin: str = "~", profondeur: int = 1):
    """Liste le contenu d'un dossier.
    chemin: dossier (défaut : dossier utilisateur)
    profondeur: niveaux de sous-dossiers (défaut 1)"""
    base = _p(chemin)
    out = []

    def rec(d: Path, niv: int):
        try:
            items = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            return
        for it in items:
            if it.name in IGNORE:
                continue
            ind = "  " * (profondeur - niv)
            if it.is_dir():
                out.append(f"{ind}{it.name}/")
                if niv > 1:
                    rec(it, niv - 1)
            else:
                try:
                    out.append(f"{ind}{it.name} ({it.stat().st_size//1024} Ko)")
                except OSError:
                    out.append(f"{ind}{it.name}")
            if len(out) > 400:
                return

    rec(base, profondeur)
    return f"{base}\n" + "\n".join(out)


@outil
def chercher_fichiers(motif: str, dossier: str = "~", max_resultats: int = 50):
    """Cherche des fichiers/dossiers par nom (motif glob comme *.pdf ou *facture*).
    motif: motif de nom
    dossier: dossier de départ (défaut : dossier utilisateur)
    max_resultats: nombre max"""
    res = []
    for racine, dirs, files in os.walk(_p(dossier)):
        dirs[:] = [d for d in dirs if d not in IGNORE and not d.startswith(".")]
        for n in dirs + files:
            if fnmatch.fnmatch(n.lower(), motif.lower()):
                res.append(os.path.join(racine, n))
                if len(res) >= max_resultats:
                    return "\n".join(res)
    return "\n".join(res) or "Aucun résultat."


@outil
def chercher_dans_fichiers(texte: str, dossier: str, extensions: str = ""):
    """Cherche un texte/regex à l'intérieur des fichiers d'un dossier (comme grep).
    texte: texte ou regex
    dossier: dossier
    extensions: ex '.py,.js' (optionnel)"""
    exts = tuple(e.strip() for e in extensions.split(",") if e.strip())
    rx = re.compile(texte, re.I)
    res = []
    for racine, dirs, files in os.walk(_p(dossier)):
        dirs[:] = [d for d in dirs if d not in IGNORE and not d.startswith(".")]
        for f in files:
            if exts and not f.endswith(exts):
                continue
            fp = os.path.join(racine, f)
            try:
                if os.path.getsize(fp) > 2_000_000:
                    continue
                with open(fp, encoding="utf-8", errors="ignore") as fh:
                    for i, l in enumerate(fh, 1):
                        if rx.search(l):
                            res.append(f"{fp}:{i}: {l.strip()[:200]}")
                            if len(res) >= 80:
                                return "\n".join(res)
            except Exception:
                pass
    return "\n".join(res) or "Aucun résultat."


@outil
def deplacer(source: str, destination: str):
    """Déplace ou renomme un fichier/dossier.
    source: chemin source
    destination: chemin destination"""
    shutil.move(str(_p(source)), str(_p(destination)))
    return f"Déplacé vers {destination}"


@outil
def copier(source: str, destination: str):
    """Copie un fichier ou un dossier.
    source: chemin source
    destination: chemin destination"""
    s, d = _p(source), _p(destination)
    shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)
    return f"Copié vers {d}"


@outil
def creer_dossier(chemin: str):
    """Crée un dossier (et ses parents).
    chemin: chemin du dossier"""
    _p(chemin).mkdir(parents=True, exist_ok=True)
    return "Créé."


@outil
def supprimer(chemin: str):
    """Supprime un fichier ou dossier (envoyé à la corbeille, récupérable).
    chemin: chemin"""
    send2trash(str(_p(chemin)))
    return f"Mis à la corbeille : {chemin}"
