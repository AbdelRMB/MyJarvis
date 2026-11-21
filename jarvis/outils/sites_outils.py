"""Outils de Jarvis : son navigateur (ouvrir, voir, cliquer, remplir) et les sites qu'il a appris par cœur."""
import re

from . import outil

# clics qui modifient vraiment quelque chose : Jarvis demande « Autoriser / Refuser » avant
_RISQUE = re.compile(r"supprim|delete|effacer|retirer|remove|payer|paiement|pay now|acheter|buy|commander|order|"
                     r"envoyer|send|valider|confirmer|confirm|soumettre|submit|publier|publish|transf[ée]rer|virement|"
                     r"signer|r[ée]silier|annuler la|d[ée]sactiver|enregistrer et|approuver|approve|rejeter|reject", re.I)


def _avec_page(fn):
    from .. import navigateur
    try:
        return navigateur.decrire(fn())
    except Exception as e:
        return f"Erreur navigateur : {e}"


@outil
def navigateur_ouvrir(url: str):
    """Ouvre une page dans le navigateur de Jarvis (où l'utilisateur est connecté à ses sites) et renvoie ce qu'elle contient : éléments numérotés (liens, boutons, champs). Pour un site appris, cherche d'abord avec site_chercher pour aller directement à la bonne page.
    url: adresse de la page"""
    from .. import navigateur
    return _avec_page(lambda: navigateur.ouvrir(url))


@outil
def navigateur_voir():
    """Regarde la page actuellement ouverte dans le navigateur de Jarvis : adresse, titres, éléments numérotés, début du texte."""
    from .. import navigateur
    return _avec_page(navigateur.instantane)


@outil
def navigateur_cliquer(element: str):
    """Clique sur un élément de la page (numéro entre crochets donné par navigateur_voir, ou son texte). Les clics qui modifient quelque chose (supprimer, envoyer, payer, valider…) demandent l'accord de l'utilisateur.
    element: numéro de l'élément (ex : 12) ou son texte (ex : « Nouvelle facture »)"""
    from .. import navigateur, web
    try:
        e = navigateur._element(element)
    except Exception as x:
        return f"Erreur navigateur : {x}"
    if _RISQUE.search(e.get("libelle", "")):
        if not web.demander_confirmation(f"Cliquer sur « {e['libelle']} » dans le navigateur ?",
                                         "Cette action peut modifier des données sur le site."):
            return "L'utilisateur a refusé ce clic. Ne le refais pas sans son accord."
    return _avec_page(lambda: navigateur.cliquer(element))


@outil
def navigateur_remplir(element: str, valeur: str):
    """Remplit un champ (ou choisit une option d'une liste) dans la page.
    element: numéro du champ (navigateur_voir) ou son libellé
    valeur: le texte à saisir, ou l'option à choisir"""
    from .. import navigateur
    return _avec_page(lambda: navigateur.remplir(element, valeur))


@outil
def navigateur_touche(touche: str):
    """Appuie sur une touche dans la page (après avoir rempli un champ de recherche, par exemple).
    touche: entree | tab | echap | bas | haut | retour"""
    from .. import navigateur
    return _avec_page(lambda: navigateur.touche(touche))


@outil
def navigateur_capture(question: str = "Décris précisément ce que montre cette page."):
    """Prend une capture de la page du navigateur et l'analyse (graphiques, tableaux, images, mise en page) quand le texte ne suffit pas.
    question: ce que tu veux savoir sur la page"""
    from .. import navigateur
    try:
        image = navigateur.capture()
    except Exception as e:
        return f"Erreur navigateur : {e}"
    from ..config import CONFIG
    if CONFIG.get("cerveau") == "claude":
        from .. import claude
        return claude.vision(question, image)
    from ..config import RACINE
    f = RACINE / "logs" / "capture_navigateur.png"
    f.write_bytes(image)
    from .ecran import analyser_image
    return analyser_image(str(f), question)


# ---------- sites appris ----------
@outil
def sites_appris():
    """Liste les sites que Jarvis a appris par cœur (pages explorées, procédures montrées, astuces)."""
    from .. import sites
    l = [sites.resume(s) for s in sites.lister()]
    return "\n".join(f"- {s['nom']} ({s['url']}) : {s['pages']} pages, {s['procedures']} procédures, {s['astuces']} astuces"
                     for s in l) or "Aucun site appris. L'utilisateur peut en ajouter dans l'écran Sites (ou te demander d'en explorer un)."


@outil
def site_chercher(question: str, site: str = ""):
    """À appeler EN PREMIER pour toute question ou tâche sur un site appris (« où je trouve les congés dans l'intranet ? », « crée une facture sur Sage »…) : renvoie les pages utiles avec le chemin pour y aller et leur adresse, les procédures montrées par l'utilisateur, les astuces et le guide du site.
    question: la question ou la tâche, en mots-clés
    site: (optionnel) nom ou adresse du site"""
    from .. import sites
    return sites.chercher(question, site)


@outil
def site_explorer(url: str, nom: str = "", max_pages: int = 80):
    """Apprend un site : l'ajoute et l'explore en lecture seule (il suit les liens sans rien modifier) pour en mémoriser les pages, menus, boutons et formulaires, puis rédige son guide. L'utilisateur doit d'abord être connecté au site dans le navigateur de Jarvis.
    url: adresse de départ (page d'accueil du site, une fois connecté)
    nom: nom court du site (ex : « Intranet », « Sage »)
    max_pages: nombre de pages à explorer au maximum (80 par défaut)"""
    from .. import sites
    s = sites.ajouter(nom, url)
    try:
        sites.explorer(s["id"], max(5, min(int(max_pages), 300)))
    except RuntimeError as e:
        return str(e)
    return f"Exploration de « {s['nom']} » lancée en arrière-plan (suivi dans l'écran Sites). Je te préviens à la fin."


@outil
def site_noter(site: str, astuce: str):
    """Retient une astuce sur un site appris, pour faire plus vite la prochaine fois (à faire après une tâche réussie sur le site, ou quand l'utilisateur t'explique quelque chose : « pour exporter, c'est Rapports > Export, bouton en haut à droite »).
    site: nom ou adresse du site
    astuce: l'astuce, concrète (où aller, sur quoi cliquer, quoi éviter)"""
    from .. import sites
    s = sites.trouver(site)
    if not s:
        s = sites.ajouter("", site) if "." in site else None
    if not s:
        return "Site inconnu : précise son adresse."
    sites.noter(s["id"], astuce)
    return f"Astuce retenue pour {s['nom']}."
