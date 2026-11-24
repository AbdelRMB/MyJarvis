"""« Annule ce que tu viens de faire » : chaque action de Wesley sur tes fichiers peut être défaite.

- Avant d'écrire ou de modifier un fichier, Wesley en garde une copie ; un fichier qu'il crée sera simplement retiré.
- Déplacer / renommer : remis à sa place. Copier : la copie est retirée. Créer un dossier : retiré s'il est vide.
- Supprimer : l'élément part d'abord dans la corbeille de Wesley (RACINE/annulation), restaurable tel quel ; au bout
  de 14 jours il rejoint la corbeille du système (toujours récupérable là).
- Les actions sont groupées par demande : « annule » défait tout ce que la dernière demande a fait sur les fichiers.
"""
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from .config import RACINE

DOSSIER = RACINE / "annulation"
JOURNAL = DOSSIER / "journal.json"
GARDE_JOURS = 14
MAX_COPIE = 200 * 1024 * 1024    # au-delà, pas de copie de sauvegarde avant écriture (fichier énorme)
_verrou = threading.RLock()
TOUR = {"id": "", "texte": ""}   # demande en cours (posé par Wesley.demander)


def nouvelle_demande(texte: str = ""):
    TOUR.update(id=uuid.uuid4().hex[:10], texte=texte[:200])


def _lire() -> list:
    try:
        return json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _ecrire(j: list):
    DOSSIER.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(j[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


def _noter(type_: str, **d):
    with _verrou:
        j = _lire()
        j.append({"id": uuid.uuid4().hex[:10], "tour": TOUR["id"] or "hors-demande", "demande": TOUR["texte"],
                  "ts": time.time(), "type": type_, "annule": False, **d})
        _ecrire(j)


def _copie(chemin: Path) -> str:
    """Copie de sauvegarde (fichier ou dossier) ; renvoie son chemin."""
    cible = DOSSIER / "copies" / uuid.uuid4().hex[:12] / chemin.name
    cible.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(chemin, cible) if chemin.is_dir() else shutil.copy2(chemin, cible)
    return str(cible)


# ---------- à appeler AVANT l'action ----------
def avant_ecriture(chemin: Path):
    """Fichier sur le point d'être écrit ou modifié."""
    try:
        if chemin.is_file():
            if chemin.stat().st_size > MAX_COPIE:
                return
            _noter("ecriture", chemin=str(chemin), copie=_copie(chemin))
        elif not chemin.exists():
            _noter("creation", chemin=str(chemin))
    except OSError as e:
        print(f"  (annulation : copie impossible de {chemin} : {e})")


def apres_deplacement(source: Path, destination: Path):
    _noter("deplacement", source=str(source), destination=str(destination))


def apres_copie(destination: Path, existait: bool):
    if not existait:
        _noter("copie", chemin=str(destination))


def apres_dossier(chemin: Path, existait: bool):
    if not existait:
        _noter("dossier", chemin=str(chemin))


def supprimer(chemin: Path) -> str:
    """Met l'élément dans la corbeille de Wesley (restaurable) au lieu de le supprimer."""
    cible = DOSSIER / "corbeille" / uuid.uuid4().hex[:12] / chemin.name
    cible.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(chemin), str(cible))
    _noter("suppression", chemin=str(chemin), copie=str(cible))
    return str(cible)


# ---------- annuler ----------
def _defaire(a: dict) -> str:
    t = a["type"]
    if t == "ecriture":
        shutil.copy2(a["copie"], a["chemin"])
        return f"Remis comme avant : {a['chemin']}"
    if t in ("creation", "copie"):
        p = Path(a["chemin"])
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink(missing_ok=True)
        return f"Retiré : {a['chemin']}"
    if t == "deplacement":
        if Path(a["source"]).exists():
            raise FileExistsError(f"{a['source']} existe de nouveau : je ne l'écrase pas.")
        shutil.move(a["destination"], a["source"])
        return f"Remis à sa place : {a['source']}"
    if t == "dossier":
        p = Path(a["chemin"])
        if p.is_dir() and not any(p.iterdir()):
            p.rmdir()
            return f"Dossier retiré : {a['chemin']}"
        return f"Dossier gardé (il n'est plus vide) : {a['chemin']}"
    if t == "suppression":
        if Path(a["chemin"]).exists():
            raise FileExistsError(f"{a['chemin']} existe de nouveau : je ne l'écrase pas.")
        Path(a["chemin"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(a["copie"], a["chemin"])
        return f"Restauré : {a['chemin']}"
    raise ValueError(f"Action inconnue : {t}")


def annuler(demandes: int = 1) -> list[str]:
    """Défait les actions sur fichiers des `demandes` dernières demandes (dans l'ordre inverse)."""
    with _verrou:
        j = _lire()
        tours = []
        for a in reversed(j):
            if not a["annule"] and a["tour"] not in tours:
                tours.append(a["tour"])
        cibles = set(tours[:max(1, demandes)])
        res = []
        for a in reversed(j):
            if a["annule"] or a["tour"] not in cibles:
                continue
            try:
                res.append(_defaire(a))
                a["annule"] = True
            except Exception as e:
                res.append(f"Impossible d'annuler ({a['type']} {a.get('chemin') or a.get('source')}) : {e}")
        _ecrire(j)
        return res


def recentes(n: int = 15) -> list[dict]:
    return [a for a in reversed(_lire()) if not a["annule"]][:n]


def menage():
    """Copies de plus de 14 jours : supprimées ; éléments supprimés : envoyés à la corbeille du système."""
    limite = time.time() - GARDE_JOURS * 86400
    with _verrou:
        j = _lire()
        garde = []
        for a in j:
            if a["ts"] >= limite:
                garde.append(a)
                continue
            try:
                if a["type"] == "suppression" and not a["annule"] and Path(a["copie"]).exists():
                    from send2trash import send2trash
                    send2trash(a["copie"])
                elif a.get("copie") and Path(a["copie"]).exists():
                    p = Path(a["copie"])
                    shutil.rmtree(p) if p.is_dir() else p.unlink()
            except Exception as e:
                print(f"  (annulation, ménage : {e})")
        _ecrire(garde)
    for d in ("copies", "corbeille"):
        for sous in (DOSSIER / d).glob("*") if (DOSSIER / d).exists() else []:
            try:
                if sous.is_dir() and not any(sous.iterdir()):
                    sous.rmdir()
            except OSError:
                pass
