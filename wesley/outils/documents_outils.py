"""Outils de Wesley pour lire les documents de l'utilisateur (PDF, Word, textes) et y retrouver une information."""
import os

from . import outil


@outil
def chercher_dans_documents(question: str):
    """Cherche la réponse dans les documents de l'utilisateur (contrats, factures, devis, règlements, cours, notes… en PDF, Word ou texte), PAR LE SENS, et renvoie les passages avec le fichier et la page. À utiliser pour « qu'est-ce que dit mon bail sur… », « combien coûtait le devis… », « retrouve dans mes documents… ». Cite toujours le fichier (et la page) dans ta réponse.
    question: la question ou le sujet cherché, en langage naturel"""
    from .. import documents
    if not documents.dossiers():
        return ("Aucun dossier de documents n'est indexé. Demande à l'utilisateur quel dossier lire, puis utilise "
                "ajouter_dossier_documents.")
    res = documents.chercher(question)
    if not res:
        return "Rien trouvé de pertinent dans les documents indexés."
    return "\n\n".join(f"[{os.path.basename(r['fichier'])}{', page ' + str(r['page']) if r['page'] else ''}] "
                       f"({r['fichier']})\n{r['texte'][:1500]}" for r in res)


@outil
def ajouter_dossier_documents(chemin: str):
    """Ajoute un dossier aux documents que Wesley sait lire (PDF, Word, textes ; sous-dossiers compris). L'indexation se fait en fond, en local.
    chemin: le dossier (ex : ~/Documents/Administratif)"""
    from .. import documents
    try:
        p = documents.ajouter_dossier(chemin)
    except ValueError as e:
        return str(e)
    return f"Dossier ajouté : {p}. Je le lis en arrière-plan (quelques minutes pour beaucoup de fichiers)."


@outil
def etat_documents():
    """Dossiers de documents lus par Wesley, nombre de fichiers et de passages indexés."""
    from .. import documents
    e = documents.etat()
    if not e["dossiers"]:
        return "Aucun dossier de documents."
    return (f"Dossiers : {', '.join(e['dossiers'])}. {e['fichiers']} fichier(s), {e['passages']} passage(s)"
            + (" — indexation en cours." if e["indexation"] else ".")
            + (f" Illisibles : {', '.join(os.path.basename(x) for x in e['illisibles'])}." if e["illisibles"] else ""))
