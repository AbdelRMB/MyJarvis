"""Outils de Wesley pour les WESLEY.md : les instructions propres à chaque projet (voir wesley/wesley_md.py)."""
from . import outil


@outil
def lire_wesley_md(projet: str, sous_dossier: str = ""):
    """Lit le WESLEY.md d'un projet (instructions, conventions, commandes et contexte du projet) : à appeler EN PREMIER avant de travailler sur un projet (coder, l'ouvrir, le modifier, répondre sur son code), puis le suivre avant ta mémoire et tes règles par défaut.
    projet: dossier du projet (ou n'importe quel fichier/dossier dedans)
    sous_dossier: sous-dossier concerné (optionnel) : ajoute ses WESLEY.md à celui de la racine"""
    from .. import wesley_md
    from pathlib import Path
    cible = str(Path(projet).expanduser() / sous_dossier) if sous_dossier else None
    racine = wesley_md.racine_projet(projet)
    contenu = wesley_md.lire(projet, cible)
    sous = [x.relative_to(racine).as_posix() for x in wesley_md.autres(projet) if x not in wesley_md.fichiers(projet, cible)]
    suite = ("\n\nAutres WESLEY.md dans des sous-dossiers (lis-les avant d'y travailler) : " + ", ".join(sous)) if sous else ""
    if not contenu:
        return (f"Pas de WESLEY.md dans le projet {racine.name} ({racine}). Si tu modifies ce projet, crée-le "
                "(creer_wesley_md) et consigne-y tes changements (noter_wesley_md)." + suite)
    return (f"Instructions du projet {racine.name} ({racine}) — à suivre en priorité :\n\n{contenu}{suite}\n\n"
            "Quand tu modifies ce projet, tiens ce fichier à jour avec noter_wesley_md.")


@outil
def creer_wesley_md(projet: str, contenu: str = "", remplacer: bool = False):
    """Crée le WESLEY.md à la racine d'un projet (« crée le WESLEY.md de ce projet ») : présentation, commandes utiles, conventions, décisions, journal des changements. Sans contenu, un modèle est rempli d'après le projet (README, package.json, pyproject…) : relis-le puis complète-le avec modifier_fichier.
    projet: dossier du projet
    contenu: texte Markdown complet (optionnel ; vide = modèle rempli automatiquement)
    remplacer: true pour écraser un WESLEY.md existant (seulement si l'utilisateur le demande)"""
    from .. import wesley_md
    f, cree = wesley_md.creer(projet, contenu, remplacer)
    if not cree:
        return f"Le projet a déjà un WESLEY.md : {f}. Lis-le (lire_wesley_md) et complète-le plutôt que de le remplacer."
    return f"WESLEY.md créé : {f}\n\n{f.read_text(encoding='utf-8')[:6000]}"


@outil
def noter_wesley_md(projet: str, note: str, rubrique: str = "changement"):
    """Consigne une information dans le WESLEY.md d'un projet (créé s'il n'existe pas). À faire après CHAQUE modification d'un projet : changement fait, décision prise, commande utile ou convention découverte.
    projet: dossier du projet (ou un fichier dedans)
    note: une phrase courte et précise (jamais de secret)
    rubrique: changement (journal daté, par défaut) | decision | commande | convention"""
    from .. import wesley_md
    f = wesley_md.noter(projet, note, rubrique)
    return f"Noté dans {f}."
