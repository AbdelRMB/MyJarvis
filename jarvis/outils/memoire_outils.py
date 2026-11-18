from . import outil
from .. import memoire


@outil
def memoriser(fait: str, categorie: str = "general"):
    """Enregistre durablement un fait sur l'utilisateur (identité, goûts, projets, habitudes, contacts, préférences). À utiliser dès que tu apprends quelque chose d'utile.
    fait: le fait, en une phrase
    categorie: identite | preference | projet | contact | habitude | general"""
    return memoire.ajouter(fait, categorie)


@outil
def oublier(texte: str):
    """Supprime de la mémoire les faits contenant ce texte.
    texte: texte à rechercher dans les faits à supprimer"""
    return memoire.supprimer(texte)


@outil
def chercher_memoire(requete: str):
    """Cherche dans la mémoire et dans l'historique des conversations passées.
    requete: mots-clés"""
    return memoire.chercher(requete)
