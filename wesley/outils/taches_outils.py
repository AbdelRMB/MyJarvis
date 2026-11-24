"""Outils de Wesley pour les tâches de fond (coder avec Claude Code ou lui-même pendant qu'on continue à parler)."""
from . import outil


@outil
def lancer_tache_code(consigne: str, projet: str, outil: str = "claude_code", titre: str = ""):
    """Lance une tâche de code EN ARRIÈRE-PLAN : une branche est créée, Claude Code (ou Wesley) code et tu le pilotes jusqu'au bout pendant que l'utilisateur continue à te parler. Utilise-le dès qu'on te demande de coder / développer / corriger quelque chose dans un projet. Le WESLEY.md du projet (instructions du projet) est transmis à l'agent, qui doit le tenir à jour.
    consigne: la demande complète et précise de l'utilisateur
    projet: chemin du dossier du projet (voir « Projets détectés » dans ta mémoire ; demande-le s'il est ambigu)
    outil: « claude_code » (par défaut), « codex » (agent de code d'OpenAI) ou « wesley » si l'utilisateur veut que tu codes toi-même
    titre: titre court de la tâche"""
    from .. import taches
    t = taches.creer(consigne, projet, outil, titre)
    nom = {"claude_code": "Claude Code", "codex": "Codex"}.get(t["outil"], "Wesley")
    return (f"Tâche [{t['id']}] lancée en arrière-plan ({nom}). "
            "Elle crée sa branche et travaille ; suivi dans l'onglet Tâches.")


def _distante(identifiant: str) -> bool:
    """La tâche a été lancée sur un autre appareil du compte (elle n'existe pas ici)."""
    from .. import taches
    return not taches.lire(identifiant) and _partage().trouver("tache", identifiant) is not None


def _partage():
    from .. import partage
    return partage


def _a_distance(identifiant: str, action: str, params: dict | None = None) -> str:
    try:
        return _partage().agir("tache", identifiant, action, params)
    except ValueError as e:
        return str(e)


@outil
def lister_taches():
    """Liste les tâches de fond (en cours, terminées, arrêtées) avec leur état et leur dernier bilan, celles de cet ordinateur puis celles lancées sur tes autres appareils (« sur … »)."""
    from .. import taches
    lignes = [f"[{t['id']}] {t['statut']} — {t['titre']} ({t['projet']}, branche {t.get('branche') or '—'})"
              + (f"\n   bilan : {t['bilan']}" if t.get("bilan") else "") for t in taches.lister()[:20]]
    for t in _partage().distants("tache")[:20]:
        lignes.append(f"[{t['id']}] {t['statut']} — {t['titre']} (sur {t['appareil']}"
                      + ("" if t.get("en_ligne") else ", hors ligne") + f", {t.get('projet')})"
                      + (f"\n   bilan : {t['bilan']}" if t.get("bilan") else ""))
    return "\n".join(lignes) or "Aucune tâche."


@outil
def mettre_a_jour_tache(identifiant: str, consigne: str):
    """Ajoute ou change une consigne d'une tâche de fond EN COURS (ou la relance si elle est finie) : prise en compte immédiatement. À utiliser quand l'utilisateur précise ou change ce qu'il veut pour une tâche déjà lancée.
    identifiant: code de la tâche (lister_taches)
    consigne: la nouvelle consigne / le changement demandé"""
    from .. import taches
    tid = identifiant.strip("[] ")
    if _distante(tid):   # lancée sur un autre appareil : c'est lui qui la change
        return _a_distance(tid, "consigne", {"texte": consigne})
    return taches.mettre_a_jour(tid, consigne)


@outil
def arreter_tache(identifiant: str):
    """Arrête une tâche de fond (quand l'utilisateur ne veut plus qu'elle continue).
    identifiant: code de la tâche (lister_taches)"""
    from .. import taches
    tid = identifiant.strip("[] ")
    if _distante(tid):
        return _a_distance(tid, "arreter")
    return taches.arreter(tid)


@outil
def reprendre_tache(identifiant: str):
    """Relance une tâche de fond arrêtée, interrompue, terminée ou en échec, là où elle en était. Une tâche lancée sur un autre appareil est relancée sur cet appareil-là (s'il est allumé avec Wesley ouvert ; sinon tu dis pourquoi ce n'est pas possible).
    identifiant: code de la tâche (lister_taches)"""
    from .. import taches
    tid = identifiant.strip("[] ")
    if _distante(tid):
        return _a_distance(tid, "reprendre")
    try:
        return taches.reprendre(tid)
    except ValueError as e:
        return str(e)


@outil
def suivre_tache(identifiant: str, dernieres: int = 15):
    """Donne l'état d'une tâche de fond et ses dernières étapes (ce que Claude Code a fait, ce que tu lui as répondu).
    identifiant: code de la tâche
    dernieres: nombre d'entrées du journal à afficher"""
    from .. import taches
    t = taches.lire(identifiant.strip("[] ")) or _partage().lire("tache", identifiant.strip("[] "))
    if not t:
        return "Tâche introuvable."
    j = "\n".join(f"- ({e['genre']}) {e['texte'][:300]}" for e in t.get("journal", [])[-max(1, int(dernieres)):])
    return f"[{t['id']}] {t['statut']} — {t['titre']}\nBranche : {t.get('branche') or '—'} ({t.get('dossier')})\nBilan : {t.get('bilan') or '—'}\n{j}"
