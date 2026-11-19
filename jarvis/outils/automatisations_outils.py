"""Outils de Jarvis pour créer et gérer les automatisations (« quand je reçois un mail de X, préviens-moi »)."""
from . import outil


@outil
def creer_automatisation(description: str, expediteur: str = "", sujet: str = "", contient: str = "",
                         compte_mail: str = "", action: str = "prevenir", consigne: str = ""):
    """Crée une automatisation déclenchée par l'arrivée d'un e-mail (règle permanente, sur tous ses appareils).
    description: phrase courte qui décrit la règle (ex : « Mail de papa »)
    expediteur: adresse e-mail ou nom tel qu'il apparaît dans l'expéditeur. Si l'utilisateur dit « mon père », « ma femme »…, utilise l'adresse ou le nom connus dans sa mémoire ; sinon demande-lui l'adresse avant de créer la règle
    sujet: mot à trouver dans le sujet (optionnel)
    contient: mot à trouver dans le texte du mail (optionnel)
    compte_mail: identifiant du connecteur e-mail à surveiller (vide = toutes ses boîtes)
    action: « prevenir » (le dire à voix haute + notification) ou « jarvis » (exécuter la consigne avec le mail)
    consigne: si action = jarvis, ce que Jarvis doit faire du mail (ex : « résume-le-moi », « réponds que je rappelle »)"""
    from .. import automatisations
    if not (expediteur or sujet or contient):
        return "Précise au moins un expéditeur, un mot du sujet ou un mot du texte."
    r = automatisations.creer(description, expediteur, sujet, contient, compte_mail, action, consigne)
    return f"Automatisation créée : {automatisations.decrire(r)}"


@outil
def lister_automatisations():
    """Liste les automatisations de l'utilisateur (règles « quand… alors… »)."""
    from .. import automatisations
    regles = automatisations.lister()
    return "\n".join(f"[{r['id']}] {'' if r['actif'] else '(en pause) '}{r['nom']} : {automatisations.decrire(r)}"
                     for r in regles) or "Aucune automatisation."


@outil
def supprimer_automatisation(identifiant: str):
    """Supprime une automatisation.
    identifiant: le code entre crochets donné par lister_automatisations"""
    from .. import automatisations
    return "Supprimée." if automatisations.supprimer(identifiant.strip("[] ")) else "Introuvable."
