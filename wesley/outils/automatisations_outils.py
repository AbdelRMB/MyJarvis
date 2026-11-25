"""Outils de Wesley pour créer et gérer les automatisations (« quand je reçois un mail de X, préviens-moi »)."""
from . import outil


@outil
def creer_automatisation(description: str, declencheur: str = "mail", heure: str = "", jours: str = "", minutes: int = 0,
                         expediteur: str = "", sujet: str = "", contient: str = "", compte_mail: str = "",
                         action: str = "wesley", consigne: str = "", message: str = "", tous_les_appareils: bool = False,
                         phrase: str = "", avant: int = 15, dossier: str = "", motif: str = "", url: str = "",
                         condition: str = ""):
    """Crée une automatisation (règle permanente) : « tous les matins à 8 h lis-moi mon agenda », « toutes les heures vérifie mon serveur », « quand je reçois un mail de papa préviens-moi », « 15 min avant chaque rendez-vous prépare-moi le contexte », « quand une facture arrive dans Téléchargements range-la », « préviens-moi quand ma tâche de code est finie », « préviens-moi si mon site tombe »…
    description: nom court de la règle (ex : « Agenda du matin »)
    declencheur: « horaire » (à heure fixe), « intervalle » (toutes les X minutes), « demarrage » (quand Wesley démarre), « mail » (arrivée d'un e-mail), « commande » (ROUTINE lancée quand l'utilisateur dit sa phrase : « mode travail »… ; consigne = toutes les étapes), « rendez_vous » (X minutes avant un événement de l'agenda), « fichier » (un nouveau fichier arrive dans un dossier), « tache_finie » (une tâche de code se termine), « transcription_finie » (une transcription se termine ; son résumé est en contexte : « envoie-moi le compte rendu sur Telegram ») ou « site » (un site ou serveur ne répond plus)
    avant: pour rendez_vous, combien de minutes avant (15 par défaut)
    dossier: pour fichier, le dossier surveillé (vide = Téléchargements)
    motif: pour fichier, filtre sur le nom (ex : « *.pdf », « facture* » ; vide = tous)
    url: pour site, l'adresse à vérifier (minutes = fréquence, 5 par défaut)
    condition: facultatif, condition en français vérifiée avant d'agir (ex : « seulement si c'est une facture », « si le mail parle d'un paiement »)
    heure: pour horaire, au format HH:MM (ex : 08:00)
    jours: pour horaire, jours séparés par des virgules (0=lundi … 6=dimanche ; vide = tous les jours ; « 0,1,2,3,4 » = en semaine)
    minutes: pour intervalle, toutes les combien de minutes
    expediteur: pour mail, adresse ou nom de l'expéditeur. « Mon père », « ma femme »… : utilise l'adresse connue dans sa mémoire, sinon demande-la
    sujet: pour mail, mot à trouver dans le sujet
    contient: pour mail, mot à trouver dans le texte ; pour rendez_vous, tache_finie et transcription_finie, mot à trouver dans le titre
    compte_mail: pour mail, identifiant du connecteur à surveiller (vide = toutes ses boîtes)
    action: « wesley » (tu exécutes la consigne avec tous tes outils et tu lis le résultat à voix haute) ou « prevenir » (dire simplement le message)
    consigne: pour action wesley, ce que tu dois faire (ex : « lis mon agenda du jour et résume-le »)
    message: pour action prevenir, la phrase à dire (vide = annonce par défaut)
    tous_les_appareils: true pour l'exécuter sur tous ses ordinateurs allumés (par défaut : seulement celui-ci, sauf pour les mails)
    phrase: pour commande, la phrase qui lance la routine (ex : « mode travail »)"""
    from .. import automatisations
    if declencheur == "mail" and not (expediteur or sujet or contient):
        return "Pour un mail, précise au moins un expéditeur, un mot du sujet ou un mot du texte."
    if declencheur == "horaire" and not heure:
        return "Précise l'heure (HH:MM)."
    if declencheur == "intervalle" and not minutes:
        return "Précise l'intervalle en minutes."
    if declencheur == "site" and not url:
        return "Précise l'adresse du site ou du serveur à surveiller."
    liste_jours = [int(x) for x in jours.replace(" ", "").split(",") if x.isdigit()] if jours else []
    r = automatisations.creer(description, expediteur, sujet, contient, compte_mail, action, consigne, declencheur,
                              heure, liste_jours, minutes or (5 if declencheur == "site" else 0),
                              "" if tous_les_appareils else None, message, phrase, avant, dossier, motif, url, condition)
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


@outil
def lancer_routine(nom: str):
    """Lance une routine de l'utilisateur (« mode travail », « fin de journée »…) : renvoie les étapes à exécuter tout de suite avec tes outils.
    nom: la phrase ou le nom de la routine"""
    from .. import automatisations
    r = automatisations.trouver_routine(nom)
    if not r:
        noms = [x["declencheur"].get("phrase") or x["nom"] for x in automatisations.lister() if x["declencheur"].get("type") == "commande"]
        return "Routine introuvable." + (f" Routines existantes : {', '.join(noms)}." if noms else " Aucune routine : propose d'en créer une (creer_automatisation, declencheur=commande).")
    return automatisations.consigne_routine(r)
