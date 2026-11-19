"""Centre de notifications (cloche dans la barre du haut) : tout ce qui s'est passé pendant que tu n'étais pas là.

Tâches terminées ou échouées, automatisations, connexions à renouveler… Gardées sur cet appareil
(RACINE/notifications.json, 300 dernières), avec « lu / non lu ».
"""
import json
import os
import threading
import time
import uuid

from .config import RACINE

FICHIER = RACINE / "notifications.json"
_verrou = threading.Lock()


def lister() -> list:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _ecrire(liste):
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(liste[-300:], ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, FICHIER)
    try:
        from . import web
        web.diffuser(type="notifications", non_lues=sum(1 for n in liste if not n.get("lue")))
    except Exception:
        pass


def ajouter(titre: str, texte: str = "", genre: str = "info", vue: str = "", systeme: bool = False) -> dict:
    """genre : info | succes | alerte | erreur. vue : écran à ouvrir au clic. systeme : notification du système aussi."""
    n = {"id": uuid.uuid4().hex[:10], "ts": time.time(), "titre": titre[:200], "texte": texte[:4000], "genre": genre,
         "vue": vue, "lue": False}
    with _verrou:
        _ecrire(lister() + [n])
    if systeme:
        try:
            from .annonces import _notification
            _notification(texte or titre, titre if texte else "Jarvis")
        except Exception:
            pass
    return n


def marquer_lues(ids=None):
    with _verrou:
        liste = lister()
        for n in liste:
            if ids is None or n["id"] in ids:
                n["lue"] = True
        _ecrire(liste)


def effacer():
    with _verrou:
        _ecrire([])
