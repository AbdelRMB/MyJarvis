"""Outils de Jarvis pour la liste « À faire » et les tickets (bugs, améliorations, idées)."""
from . import outil


def _une(tache: str):
    from .. import afaire
    trouves = afaire.trouver(tache)
    if not trouves:
        return None, "Aucune tâche ne correspond. Utilise lister_a_faire pour trouver la bonne."
    if len(trouves) > 1:
        return None, "Plusieurs tâches correspondent, précise avec l'identifiant :\n" + "\n".join(afaire.decrire(t) for t in trouves[:15])
    return trouves[0], ""


@outil
def ajouter_a_faire(titre: str, note: str = "", echeance: str = "", priorite: str = "normale", rappel: str = ""):
    """Ajoute une tâche à la liste « À faire » de l'utilisateur. À utiliser dès qu'il dit qu'il doit / veut / a prévu de faire quelque chose (« souviens-toi que je dois appeler le garage », « note que je dois finir le rapport », « ajoute à ma liste… ») : c'est une tâche, PAS un souvenir (n'utilise pas memoriser pour ça). Une demande avec plusieurs choses = un appel par tâche.
    titre: la tâche, courte et à l'infinitif (ex : « Appeler le garage »)
    note: (optionnel) détails utiles
    echeance: (optionnel) date limite au format AAAA-MM-JJ, éventuellement suivie de l'heure HH:MM (calcule-la si l'utilisateur dit « demain », « vendredi »…)
    priorite: basse | normale | haute
    rappel: (optionnel) moment où Jarvis doit le rappeler à voix haute, AAAA-MM-JJ HH:MM (« rappelle-moi de … à 18 h », « dans 2 heures » : calcule-le avec date_heure). Sans rappel mais avec une échéance qui a une heure, Jarvis prévient 1 h avant et à l'heure."""
    from .. import afaire
    t = afaire.ajouter(titre, note, echeance, priorite, rappel=rappel)
    return f"Ajouté à la liste : {afaire.decrire(t)}"


@outil
def lister_a_faire(statut: str = ""):
    """Liste ce que l'utilisateur a prévu de faire (sa liste « À faire »), avec l'étape de chaque tâche : à faire, en cours, fait. À utiliser pour « qu'est-ce que j'ai prévu ? », « qu'est-ce qu'il me reste à faire ? », « ma todo ».
    statut: (optionnel) a_faire | en_cours | fait | restant (à faire + en cours, par défaut tout)"""
    from .. import afaire
    liste = afaire.lister()
    if statut == "restant":
        liste = [t for t in liste if t["statut"] != "fait"]
    elif statut in afaire.STATUTS:
        liste = [t for t in liste if t["statut"] == statut]
    if not liste:
        return "Rien dans la liste." if not statut else "Aucune tâche avec ce statut."
    ordre = {"en_cours": 0, "a_faire": 1, "fait": 2}
    liste = sorted(liste, key=lambda t: (ordre.get(t["statut"], 3), t.get("echeance") or "9999", t["cree"]))
    return "\n".join(afaire.decrire(t) for t in liste)


@outil
def changer_etape_a_faire(tache: str, statut: str):
    """Fait passer une tâche de la liste « À faire » à une autre étape (« j'ai commencé… » → en_cours, « c'est fait », « j'ai appelé le garage » → fait).
    tache: identifiant entre crochets (via lister_a_faire) ou un morceau du titre
    statut: a_faire | en_cours | fait"""
    from .. import afaire
    if statut not in afaire.STATUTS:
        return "Statut inconnu : a_faire, en_cours ou fait."
    t, err = _une(tache)
    if not t:
        return err
    t = afaire.modifier(t["id"], statut=statut)
    return f"Mis à jour : {afaire.decrire(t)}"


@outil
def modifier_a_faire(tache: str, titre: str = "", note: str = "", echeance: str = "", priorite: str = "", rappel: str = ""):
    """Modifie une tâche de la liste « À faire » (titre, note, échéance, priorité).
    tache: identifiant entre crochets ou morceau du titre
    titre: (optionnel) nouveau titre
    note: (optionnel) nouvelle note
    echeance: (optionnel) nouvelle échéance AAAA-MM-JJ [HH:MM]
    priorite: (optionnel) basse | normale | haute
    rappel: (optionnel) nouveau rappel AAAA-MM-JJ HH:MM (« aucun » pour l'enlever)"""
    from .. import afaire
    t, err = _une(tache)
    if not t:
        return err
    t = afaire.modifier(t["id"], titre=titre or None, note=note or None, echeance=echeance or None, priorite=priorite or None,
                        rappel=("" if rappel.strip().lower() == "aucun" else rappel) or None)
    return f"Modifié : {afaire.decrire(t)}"


@outil
def supprimer_a_faire(tache: str = "", tout_ce_qui_est_fait: bool = False):
    """Retire une tâche de la liste « À faire » (abandonnée, ajoutée par erreur), ou vide toutes les tâches terminées.
    tache: identifiant entre crochets ou morceau du titre
    tout_ce_qui_est_fait: true pour retirer d'un coup toutes les tâches à l'étape « fait »"""
    from .. import afaire
    if tout_ce_qui_est_fait:
        return f"{afaire.vider_faits()} tâche(s) terminée(s) retirée(s)."
    t, err = _une(tache)
    if not t:
        return err
    afaire.supprimer(t["id"])
    return f"Retiré : {t['titre']}"


@outil
def briefing_du_jour():
    """Prépare le briefing : à appeler pour « fais-moi le briefing », « qu'est-ce que j'ai aujourd'hui ? », et au premier échange de la journée. Renvoie la liste « À faire » du jour et ce qu'il te reste à vérifier avec tes autres outils."""
    from datetime import datetime
    from .. import afaire
    from .. import taches
    n = datetime.now()
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    code = [t for t in taches.lister() if t.get("statut") == "en_cours"]
    parties = [f"Nous sommes {jours[n.weekday()]} {n:%d/%m/%Y}, il est {n:%H:%M}.", "", "# À faire", afaire.resume_du_jour()]
    if code:
        parties += ["", "# Tâches de code en cours", "\n".join(f"- {t['titre']}" for t in code)]
    parties += ["", "# À vérifier maintenant avec tes outils (seulement ceux disponibles, sans demander) :",
                "- mails importants ou non lus depuis hier (connecteurs mail) ;",
                "- agenda / rendez-vous du jour (connecteur agenda) ;",
                "- météo du jour pour la ville de l'utilisateur (mémoire ; recherche web) ;",
                "- état rapide des serveurs SSH s'il y en a (disque, services en panne) — seulement s'il y a un problème.",
                "Puis fais un briefing ORAL court (6 à 8 phrases), chaleureux, en commençant par l'essentiel."]
    return "\n".join(parties)


# ---------- tickets ----------
@outil
def envoyer_ticket(genre: str, titre: str, description: str = "", joindre_journal: bool = False):
    """Envoie un ticket au développeur de Jarvis : bug, amélioration, idée ou question (« signale un bug… », « envoie l'idée que… », « dis au développeur que… »). Le développeur répond dans l'écran Tickets.
    genre: bug | amelioration | idee | question | autre
    titre: résumé en une ligne
    description: détails (ce qui s'est passé, ce qui était attendu, comment le reproduire…)
    joindre_journal: true pour un bug : joint la version, le système et la fin du journal de Jarvis (aide le développeur)"""
    from .. import compte
    if joindre_journal:
        from .. import rapport
        description = (description + "\n\n--- Diagnostic ---\n" + rapport.diagnostic()
                       + "\n\nFin du journal :\n" + rapport._fin_journal(40))[:9800]
    try:
        r = compte.creer_ticket(genre, titre, description)
    except compte.ErreurCompte as e:
        return f"Impossible d'envoyer le ticket : {e}"
    return f"Ticket n°{r['id']} envoyé."


@outil
def lister_tickets(tous: bool = False, statut: str = ""):
    """Liste les tickets envoyés par l'utilisateur et leur réponse. Pour un administrateur, tous=true liste les tickets de TOUS les utilisateurs.
    tous: true pour voir les tickets de tous les utilisateurs (administrateur seulement)
    statut: (optionnel) ouvert | en_cours | resolu | ferme"""
    from .. import compte
    try:
        liste = compte.tous_les_tickets() if tous else compte.mes_tickets()
    except compte.ErreurCompte as e:
        return f"Impossible de lire les tickets : {e}"
    if statut:
        liste = [t for t in liste if t["statut"] == statut]
    if not liste:
        return "Aucun ticket."
    lignes = []
    for t in liste[:60]:
        qui = f" de {t.get('prenom') or t.get('email')}" if tous else ""
        l = f"[{t['id']}] ({t['genre']}, {t['statut'].replace('_', ' ')}){qui} {t['titre']}"
        if t.get("description"):
            l += f"\n    {t['description'][:400]}"
        if t.get("reponse"):
            l += f"\n    Réponse : {t['reponse'][:400]}"
        lignes.append(l)
    return "\n".join(lignes)


@outil
def traiter_ticket(numero: int, statut: str = "", reponse: str = ""):
    """(Administrateur) Change le statut d'un ticket et/ou répond à son auteur.
    numero: numéro du ticket (entre crochets dans lister_tickets)
    statut: (optionnel) ouvert | en_cours | resolu | ferme
    reponse: (optionnel) message pour l'auteur du ticket"""
    from .. import compte
    try:
        compte.traiter_ticket(numero, statut, reponse or None)
    except compte.ErreurCompte as e:
        return f"Impossible : {e}"
    return "Ticket mis à jour."


@outil
def corriger_ticket(numero: int, projet: str = "", outil: str = "claude_code"):
    """(Administrateur) « Corrige le ticket 12 » : lance une tâche de code de fond (Claude Code) sur le dépôt de Jarvis pour traiter ce ticket, et prévient l'auteur que c'est en cours. Le correctif arrive sur une branche à relire.
    numero: numéro du ticket
    projet: (optionnel) dossier du code de Jarvis ; retenu après la première fois
    outil: claude_code (défaut), codex ou jarvis"""
    from .. import compte
    try:
        t = compte.corriger_ticket(numero, projet, outil)
    except (compte.ErreurCompte, ValueError) as e:
        return f"Impossible : {e}"
    return f"Tâche [{t['id']}] lancée pour le ticket n°{numero} (suivi dans l'onglet Tâches). L'auteur est prévenu que c'est en cours."


@outil
def resoudre_ticket(numero: int, version: str = "", message: str = ""):
    """(Administrateur) Marque un ticket résolu et prévient son auteur (« marque le ticket 12 résolu », après publication du correctif).
    numero: numéro du ticket
    version: (optionnel) version qui contient le correctif (ex : 1.9.0)
    message: (optionnel) mot pour l'auteur"""
    from .. import compte
    texte = message.strip() or (f"Corrigé dans la version {version}. Mets Jarvis à jour (écran Mises à jour). Merci pour ton retour !"
                                if version else "C'est corrigé, merci pour ton retour !")
    try:
        compte.traiter_ticket(numero, "resolu", texte)
    except compte.ErreurCompte as e:
        return f"Impossible : {e}"
    return f"Ticket n°{numero} résolu ; l'auteur sera prévenu."
