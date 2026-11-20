"""Liste « À faire » : ce que l'utilisateur a prévu de faire (« souviens-toi que je dois appeler le garage »).

Chaque tâche passe par trois étapes : à faire → en cours → fait. La liste est rangée dans le compte (document
« afaire », même mécanisme que les automatisations) : elle est la même sur tous les appareils.
"""
import json
import threading
import uuid
from datetime import datetime

from . import config

STATUTS = ("a_faire", "en_cours", "fait")
LIBELLES = {"a_faire": "à faire", "en_cours": "en cours", "fait": "fait"}
PRIORITES = ("basse", "normale", "haute")
_verrou = threading.RLock()


def _fichier():
    return config.PARTAGE / "afaire.json"


def lister() -> list:
    try:
        return json.loads(_fichier().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _ecrire(liste: list, synchro=True):
    _fichier().write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    if synchro:
        from . import compte
        compte.document_modifie("afaire", liste)
    try:
        from . import web
        web.diffuser(type="afaire_maj")
    except Exception:
        pass


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ajouter(titre: str, note: str = "", echeance: str = "", priorite: str = "normale", statut: str = "a_faire") -> dict:
    t = {"id": uuid.uuid4().hex[:8], "titre": titre.strip(), "note": note.strip(), "echeance": echeance.strip(),
         "priorite": priorite if priorite in PRIORITES else "normale",
         "statut": statut if statut in STATUTS else "a_faire", "cree": _maintenant(), "modifie": _maintenant(),
         "fait_le": _maintenant() if statut == "fait" else ""}
    with _verrou:
        _ecrire(lister() + [t])
    return t


def trouver(cle: str) -> list:
    """Par identifiant (début) ou par un morceau du titre."""
    cle = cle.strip("[] ").lower()
    liste = lister()
    return [t for t in liste if t["id"].startswith(cle)] or [t for t in liste if cle in t["titre"].lower()]


def modifier(tid: str, **champs) -> dict | None:
    with _verrou:
        liste = lister()
        t = next((t for t in liste if t["id"] == tid), None)
        if not t:
            return None
        for k in ("titre", "note", "echeance"):
            if champs.get(k) is not None:
                t[k] = str(champs[k]).strip()
        if champs.get("priorite") in PRIORITES:
            t["priorite"] = champs["priorite"]
        if champs.get("statut") in STATUTS and champs["statut"] != t["statut"]:
            t["statut"] = champs["statut"]
            t["fait_le"] = _maintenant() if t["statut"] == "fait" else ""
        t["modifie"] = _maintenant()
        _ecrire(liste)
        return t


def supprimer(tid: str) -> bool:
    with _verrou:
        liste = lister()
        reste = [t for t in liste if t["id"] != tid]
        if len(reste) == len(liste):
            return False
        _ecrire(reste)
        return True


def vider_faits() -> int:
    with _verrou:
        liste = lister()
        reste = [t for t in liste if t["statut"] != "fait"]
        if len(reste) != len(liste):
            _ecrire(reste)
        return len(liste) - len(reste)


def decrire(t: dict) -> str:
    extra = []
    if t.get("echeance"):
        extra.append(f"pour le {t['echeance']}")
    if t.get("priorite") == "haute":
        extra.append("prioritaire")
    if t.get("note"):
        extra.append(t["note"])
    return f"[{t['id']}] ({LIBELLES.get(t['statut'], t['statut'])}) {t['titre']}" + (f" — {', '.join(extra)}" if extra else "")

