"""Outils de Jarvis pour créer et gérer les automatisations (« quand je reçois un mail de X, préviens-moi »)."""
from . import outil


@outil
def creer_automatisation(description: str, declencheur: str = "mail", heure: str = "", jours: str = "", minutes: int = 0,
                         expediteur: str = "", sujet: str = "", contient: str = "", compte_mail: str = "",
                         action: str = "jarvis", consigne: str = "", message: str = "", tous_les_appareils: bool = False):
    """Crée une automatisation (règle permanente) : « tous les matins à 8 h lis-moi mon agenda », « toutes les heures vérifie mon serveur », « quand je reçois un mail de papa préviens-moi », « au démarrage donne-moi la météo »…
    description: nom court de la règle (ex : « Agenda du matin »)
    declencheur: « horaire » (à heure fixe), « intervalle » (toutes les X minutes), « demarrage » (quand Jarvis démarre) ou « mail » (arrivée d'un e-mail)
    heure: pour horaire, au format HH:MM (ex : 08:00)
    jours: pour horaire, jours séparés par des virgules (0=lundi … 6=dimanche ; vide = tous les jours ; « 0,1,2,3,4 » = en semaine)
    minutes: pour intervalle, toutes les combien de minutes
    expediteur: pour mail, adresse ou nom de l'expéditeur. « Mon père », « ma femme »… : utilise l'adresse connue dans sa mémoire, sinon demande-la
    sujet: pour mail, mot à trouver dans le sujet
    contient: pour mail, mot à trouver dans le texte
    compte_mail: pour mail, identifiant du connecteur à surveiller (vide = toutes ses boîtes)
    action: « jarvis » (tu exécutes la consigne avec tous tes outils et tu lis le résultat à voix haute) ou « prevenir » (dire simplement le message)
    consigne: pour action jarvis, ce que tu dois faire (ex : « lis mon agenda du jour et résume-le »)
    message: pour action prevenir, la phrase à dire (vide = annonce par défaut)
    tous_les_appareils: true pour l'exécuter sur tous ses ordinateurs allumés (par défaut : seulement celui-ci, sauf pour les mails)"""
    from .. import automatisations
    if declencheur == "mail" and not (expediteur or sujet or contient):
        return "Pour un mail, précise au moins un expéditeur, un mot du sujet ou un mot du texte."
    if declencheur == "horaire" and not heure:
        return "Précise l'heure (HH:MM)."
    if declencheur == "intervalle" and not minutes:
        return "Précise l'intervalle en minutes."
    liste_jours = [int(x) for x in jours.replace(" ", "").split(",") if x.isdigit()] if jours else []
    r = automatisations.creer(description, expediteur, sujet, contient, compte_mail, action, consigne, declencheur,
                              heure, liste_jours, minutes, "" if tous_les_appareils else None, message)
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
