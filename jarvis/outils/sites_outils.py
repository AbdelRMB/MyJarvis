"""Outils de Jarvis : son navigateur (ouvrir, voir, cliquer, remplir) et les sites qu'il a appris par cœur."""
import re

from . import outil

# clics qui modifient vraiment quelque chose : Jarvis demande « Autoriser / Refuser » avant
_RISQUE = re.compile(r"supprim|delete|effacer|retirer|remove|payer|paiement|pay now|acheter|buy|commander|order|"
                     r"envoyer|send|valider|confirmer|confirm|soumettre|submit|publier|publish|transf[ée]rer|virement|"
                     r"signer|r[ée]silier|annuler la|d[ée]sactiver|enregistrer et|approuver|approve|rejeter|reject", re.I)


def _nav(dans: str):
    """« jarvis » : son navigateur à lui ; « mien » : le navigateur de l'utilisateur (Safari, Chrome…), sous ses yeux."""
    if str(dans).lower().strip() in ("mien", "utilisateur", "safari", "chrome", "le mien", "ton", "user"):
        from .. import navigateur_perso
        return navigateur_perso
    from .. import navigateur
    return navigateur


def _avec_page(fn):
    from .. import navigateur
    try:
        return navigateur.decrire(fn())
    except Exception as e:
        return f"Erreur navigateur : {e}"


_DANS = ("dans: « jarvis » (par défaut : ton navigateur à toi, où l'utilisateur s'est connecté à ses sites) ou « mien » "
         "(le navigateur de l'utilisateur — Safari, Chrome… — dans l'onglet ouvert à son écran : quand il dit « sur ma page », "
         "« dans Safari », « regarde ce que j'ai ouvert », ou veut te voir faire)")


def _doc(fn):
    fn.__doc__ = fn.__doc__.rstrip() + "\n    " + _DANS
    return fn


@outil
@_doc
def navigateur_ouvrir(url: str, dans: str = "jarvis"):
    """Ouvre une page dans le navigateur et renvoie ce qu'elle contient : éléments numérotés (liens, boutons, champs). Pour un site appris, cherche d'abord avec site_chercher pour aller directement à la bonne page.
    url: adresse de la page"""
    return _avec_page(lambda: _nav(dans).ouvrir(url))


@outil
@_doc
def navigateur_voir(dans: str = "jarvis"):
    """Regarde la page ouverte dans le navigateur : adresse, titres, éléments numérotés, début du texte."""
    return _avec_page(_nav(dans).instantane)


@outil
@_doc
def navigateur_cliquer(element: str, dans: str = "jarvis"):
    """Clique sur un élément de la page (numéro entre crochets donné par navigateur_voir, ou son texte) ; l'élément est entouré un instant pour que l'utilisateur voie. Les clics qui modifient quelque chose (supprimer, envoyer, payer, valider…) demandent son accord.
    element: numéro de l'élément (ex : 12) ou son texte (ex : « Nouvelle facture »)"""
    from .. import web
    nav = _nav(dans)
    try:
        lib = nav._element(element).get("libelle", "") if hasattr(nav, "_element") else nav.libelle(element)
    except Exception as x:
        return f"Erreur navigateur : {x}"
    if _RISQUE.search(lib or ""):
        if not web.demander_confirmation(f"Cliquer sur « {lib} » dans le navigateur ?",
                                         "Cette action peut modifier des données sur le site."):
            return "L'utilisateur a refusé ce clic. Ne le refais pas sans son accord."
    return _avec_page(lambda: nav.cliquer(element))


@outil
@_doc
def navigateur_remplir(element: str, valeur: str, dans: str = "jarvis"):
    """Remplit un champ (ou choisit une option d'une liste) dans la page.
    element: numéro du champ (navigateur_voir) ou son libellé
    valeur: le texte à saisir, ou l'option à choisir"""
    return _avec_page(lambda: _nav(dans).remplir(element, valeur))


@outil
@_doc
def navigateur_touche(touche: str, dans: str = "jarvis"):
    """Appuie sur une touche dans la page (après avoir rempli un champ de recherche, par exemple).
    touche: entree | tab | echap | bas | haut | retour"""
    return _avec_page(lambda: _nav(dans).touche(touche))


@outil
@_doc
def navigateur_capture(question: str = "Décris précisément ce que montre cette page.", dans: str = "jarvis"):
    """Prend une capture de la page du navigateur et l'analyse (graphiques, tableaux, images, mise en page) quand le texte ne suffit pas.
    question: ce que tu veux savoir sur la page"""
    try:
        image = _nav(dans).capture()
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


@outil
def site_se_connecter(site: str):
    """Se connecte tout seul à un site appris : identifiant, mot de passe, puis code de double authentification (calculé si la clé de l'appli d'authentification est enregistrée, sinon demandé à l'utilisateur), même quand la connexion se fait en plusieurs pages. Utilise-le aussi quand tu tombes sur une page de connexion pendant une tâche. Tu ne vois jamais les mots de passe.
    site: nom ou adresse du site"""
    from .. import sites, web
    s = sites.trouver(site)
    if not s:
        return "Site inconnu : il doit d'abord être ajouté dans l'écran Sites (avec ses identifiants)."
    try:
        return sites.se_connecter(s["id"], lambda q: web.demander_texte(q, "Saisis le code affiché par ton appli ou reçu par SMS."))
    except Exception as e:
        return f"Erreur de connexion : {e}"


@outil
def navigateur_capture_enregistrer(nom: str = "", element: str = "", pleine_page: bool = False, dans: str = "jarvis"):
    """Prend une capture d'écran de la page du navigateur et l'enregistre (dossier Images › Jarvis › Captures) : toute la partie visible, un élément précis (le tableau des interventions, un bloc…) ou toute la page déroulée. Renvoie le chemin du fichier (pour l'envoyer ensuite, par WhatsApp par exemple).
    nom: (optionnel) nom court ajouté au fichier (ex : interventions_karim)
    element: (optionnel) numéro ou texte d'un élément : capture seulement le tableau / bloc qui le contient
    pleine_page: true pour capturer toute la page, y compris ce qui dépasse en bas
    dans: « jarvis » (son navigateur : capture précise d'un élément ou de toute la page) ou « mien » (la fenêtre du navigateur de l'utilisateur, telle qu'il la voit)"""
    from .. import navigateur
    try:
        if _nav(dans) is not navigateur:
            import re as _re
            import time as _t
            propre = _re.sub(r"[^\w -]", "", nom).strip().replace(" ", "_")[:60]
            f = navigateur.dossier_captures() / f"{_t.strftime('%Y-%m-%d_%H-%M-%S')}{'_' + propre if propre else ''}.png"
            f.write_bytes(_nav(dans).capture())
        else:
            f = navigateur.enregistrer_capture(nom, element, pleine_page)
    except Exception as e:
        return f"Erreur navigateur : {e}"
    return f"Capture enregistrée : {f}"


@outil
def whatsapp_envoyer(contact: str, message: str = "", fichiers: list = None):
    """Envoie un message WhatsApp et/ou des fichiers (captures d'écran, photos) à un contact, par WhatsApp Web dans le navigateur de Jarvis (la 1re fois, l'utilisateur scanne un QR code avec son téléphone). Envoie seulement ce que l'utilisateur t'a demandé d'envoyer, à la personne qu'il a nommée.
    contact: nom du contact tel qu'enregistré dans son téléphone (ex : Karim Technicien)
    message: (optionnel) texte du message, ou légende de l'image
    fichiers: (optionnel) chemins des images à joindre (ex : ceux renvoyés par navigateur_capture_enregistrer)"""
    from .. import whatsapp
    if not message and not fichiers:
        return "Rien à envoyer : donne un message ou des fichiers."
    try:
        return whatsapp.envoyer(contact, message, fichiers or [])
    except Exception as e:
        return f"Erreur WhatsApp : {e}"
