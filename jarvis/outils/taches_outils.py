"""Outils de Jarvis pour les tâches de fond (coder avec Claude Code ou lui-même pendant qu'on continue à parler)."""
from . import outil


@outil
def lancer_tache_code(consigne: str, projet: str, outil: str = "claude_code", titre: str = ""):
    """Lance une tâche de code EN ARRIÈRE-PLAN : une branche est créée, Claude Code (ou Jarvis) code et tu le pilotes jusqu'au bout pendant que l'utilisateur continue à te parler. Utilise-le dès qu'on te demande de coder / développer / corriger quelque chose dans un projet.
    consigne: la demande complète et précise de l'utilisateur
    projet: chemin du dossier du projet (voir « Projets détectés » dans ta mémoire ; demande-le s'il est ambigu)
    outil: « claude_code » (par défaut) ou « jarvis » si l'utilisateur veut que tu codes toi-même
    titre: titre court de la tâche"""
    from .. import taches
    t = taches.creer(consigne, projet, outil, titre)
    return (f"Tâche [{t['id']}] lancée en arrière-plan ({'Claude Code' if t['outil'] == 'claude_code' else 'Jarvis'}). "
            "Elle crée sa branche et travaille ; suivi dans l'onglet Tâches.")


@outil
def lister_taches():
    """Liste les tâches de fond (en cours, terminées, arrêtées) avec leur état et leur dernier bilan."""
    from .. import taches
    return "\n".join(f"[{t['id']}] {t['statut']} — {t['titre']} ({t['projet']}, branche {t.get('branche') or '—'})"
                     + (f"\n   bilan : {t['bilan']}" if t.get("bilan") else "") for t in taches.lister()[:20]) or "Aucune tâche."


@outil
def mettre_a_jour_tache(identifiant: str, consigne: str):
    """Ajoute ou change une consigne d'une tâche de fond EN COURS (ou la relance si elle est finie) : prise en compte immédiatement. À utiliser quand l'utilisateur précise ou change ce qu'il veut pour une tâche déjà lancée.
    identifiant: code de la tâche (lister_taches)
    consigne: la nouvelle consigne / le changement demandé"""
    from .. import taches
    return taches.mettre_a_jour(identifiant.strip("[] "), consigne)


@outil
def arreter_tache(identifiant: str):
    """Arrête une tâche de fond (quand l'utilisateur ne veut plus qu'elle continue).
    identifiant: code de la tâche (lister_taches)"""
    from .. import taches
    return taches.arreter(identifiant.strip("[] "))


@outil
def suivre_tache(identifiant: str, dernieres: int = 15):
    """Donne l'état d'une tâche de fond et ses dernières étapes (ce que Claude Code a fait, ce que tu lui as répondu).
    identifiant: code de la tâche
    dernieres: nombre d'entrées du journal à afficher"""
    from .. import taches
    t = taches.lire(identifiant.strip("[] "))
    if not t:
        return "Tâche introuvable."
    j = "\n".join(f"- ({e['genre']}) {e['texte'][:300]}" for e in t.get("journal", [])[-max(1, int(dernieres)):])
    return f"[{t['id']}] {t['statut']} — {t['titre']}\nBranche : {t.get('branche') or '—'} ({t.get('dossier')})\nBilan : {t.get('bilan') or '—'}\n{j}"
