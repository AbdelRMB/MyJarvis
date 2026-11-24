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


def _rappel_projet(p) -> str:
    """Fichier écrit dans un projet : rappel de lire / tenir à jour son WESLEY.md (une fois par projet)."""
    try:
        from ..wesley_md import rappel_apres_ecriture
        return rappel_apres_ecriture(p)
    except Exception:
        return ""


@outil
def ecrire_fichier(chemin: str, contenu: str):
    """Crée ou remplace entièrement un fichier (crée les dossiers parents). Pour coder un fichier complet.
    chemin: chemin du fichier
    contenu: contenu complet"""
    from .. import annulation
    p = _p(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    annulation.avant_ecriture(p)   # « annule » remettra le fichier comme avant
    p.write_text(contenu, encoding="utf-8")
    return f"Écrit : {p} ({len(contenu)} caractères)" + _rappel_projet(p)


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
    from .. import annulation
    annulation.avant_ecriture(p)
    p.write_text(t.replace(ancien, nouveau), encoding="utf-8")
    return f"Modifié : {p}" + _rappel_projet(p)


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
    from .. import annulation
    s, d = _p(source), _p(destination)
    arrivee = d / s.name if d.is_dir() else d
    shutil.move(str(s), str(d))
    annulation.apres_deplacement(s, arrivee)
    return f"Déplacé vers {destination}"


@outil
def copier(source: str, destination: str):
    """Copie un fichier ou un dossier.
    source: chemin source
    destination: chemin destination"""
    from .. import annulation
    s, d = _p(source), _p(destination)
    arrivee = d / s.name if d.is_dir() and not s.is_dir() else d
    existait = arrivee.exists()
    if existait and arrivee.is_file():
        annulation.avant_ecriture(arrivee)   # copie par-dessus un fichier : on garde l'ancien
    shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)
    annulation.apres_copie(arrivee, existait)
    return f"Copié vers {d}"


@outil
def creer_dossier(chemin: str):
    """Crée un dossier (et ses parents).
    chemin: chemin du dossier"""
    from .. import annulation
    p = _p(chemin)
    existait = p.exists()
    p.mkdir(parents=True, exist_ok=True)
    annulation.apres_dossier(p, existait)
    return "Créé."


@outil
def supprimer(chemin: str):
    """Supprime un fichier ou dossier (récupérable : « annule » le remet en place pendant 14 jours, puis il rejoint la corbeille du système).
    chemin: chemin"""
    from .. import annulation
    p = _p(chemin)
    if not p.exists():
        return f"Erreur : introuvable : {chemin}"
    try:
        annulation.supprimer(p)
    except OSError:
        send2trash(str(p))   # autre disque, droits… : corbeille du système directement
    return f"Supprimé (récupérable avec « annule ») : {chemin}"


@outil
def annuler(demandes: int = 1):
    """Annule ce que Wesley a fait sur les fichiers lors de la (ou des) dernière(s) demande(s) : fichiers écrits ou modifiés remis comme avant, créés ou copiés retirés, déplacés remis en place, supprimés restaurés. À utiliser pour « annule », « annule ce que tu viens de faire », « remets comme avant ».
    demandes: combien de demandes défaire (1 = la dernière)"""
    from .. import annulation
    res = annulation.annuler(max(1, int(demandes or 1)))
    return "\n".join(res) or "Rien à annuler : aucune action récente sur les fichiers."


@outil
def actions_recentes_fichiers():
    """Liste les dernières actions de Wesley sur les fichiers (celles qu'on peut encore annuler)."""
    from datetime import datetime
    from .. import annulation
    return "\n".join(f"{datetime.fromtimestamp(a['ts']):%d/%m %H:%M} — {a['type']} {a.get('chemin') or a.get('destination')}"
                     + (f" (demande : « {a['demande'][:60]} »)" if a.get("demande") else "")
                     for a in annulation.recentes()) or "Aucune action récente."
