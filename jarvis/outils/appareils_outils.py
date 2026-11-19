"""Outils de Jarvis pour piloter tes autres appareils (même compte) : « sur mon PC, lance Discord »."""
import base64
import os
from pathlib import Path

from . import outil


@outil
def lister_appareils():
    """Liste les appareils où Jarvis est connecté avec le même compte : en ligne ou non, occupé, accepte les ordres."""
    from .. import appareils
    import time
    lignes = []
    for a in appareils.lister():
        etat = ("en ligne" + (", occupé" if a["occupe"] else "")) if a["en_ligne"] else f"hors ligne (vu il y a {int((time.time() - (a['vu'] or 0)) // 60)} min)"
        lignes.append(f"- {a['nom']} ({a['plateforme'] or '?'}) : {etat}" + (" — CET APPAREIL" if a["moi"] else "")
                      + ("" if a["accepte"] or a["moi"] else " — refuse les ordres"))
    return "\n".join(lignes) or "Aucun appareil."


@outil
def demander_a_appareil(appareil: str, demande: str):
    """Fait exécuter une demande par Jarvis sur UN AUTRE de tes appareils (ex : « sur mon PC, lance Discord », « quel est l'espace disque du PC », « éteins le PC »). Le Jarvis de l'appareil cible l'exécute avec ses propres outils et renvoie le résultat.
    appareil: nom de l'appareil (ou « PC », « Mac »… voir lister_appareils)
    demande: ce qu'il doit faire, en une phrase claire et complète"""
    from .. import appareils
    r = appareils.envoyer(appareil, {"type": "demande", "texte": demande})
    return f"[{r['appareil']}] {r.get('resultat', '')}"


@outil
def recuperer_fichier_appareil(appareil: str, chemin_distant: str, chemin_local: str = ""):
    """Copie un fichier d'un autre de tes appareils vers celui-ci (10 Mo maximum).
    appareil: nom de l'appareil source
    chemin_distant: chemin du fichier sur l'appareil source (ex : ~/Desktop/rapport.pdf)
    chemin_local: où l'enregistrer ici (vide = dans Téléchargements)"""
    from .. import appareils
    r = appareils.envoyer(appareil, {"type": "lire_fichier", "chemin": chemin_distant})
    if not r.get("ok"):
        return r.get("resultat", "Échec.")
    cible = Path(os.path.expanduser(chemin_local or f"~/Downloads/{r['nom']}"))
    if cible.is_dir():
        cible = cible / r["nom"]
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(base64.b64decode(r["contenu"]))
    return f"Fichier récupéré depuis {r['appareil']} : {cible}"


@outil
def envoyer_fichier_appareil(appareil: str, chemin_local: str, chemin_distant: str):
    """Copie un fichier de cet appareil vers un autre de tes appareils (10 Mo maximum).
    appareil: nom de l'appareil de destination
    chemin_local: fichier à envoyer, sur cet appareil
    chemin_distant: où l'enregistrer là-bas (ex : ~/Desktop/rapport.pdf)"""
    from .. import appareils
    p = Path(os.path.expanduser(chemin_local))
    if not p.is_file():
        return f"Fichier introuvable : {p}"
    if p.stat().st_size > appareils.MAX_FICHIER:
        return "Fichier trop gros (maximum 10 Mo)."
    r = appareils.envoyer(appareil, {"type": "ecrire_fichier", "chemin": chemin_distant,
                                     "contenu": base64.b64encode(p.read_bytes()).decode()})
    return r.get("resultat", "")
