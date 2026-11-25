"""Résumé d'une transcription, quelle qu'elle soit : cours, réunion, discussion, appel, entretien, conférence,
note vocale…

Wesley reconnaît d'abord de quoi il s'agit, puis adapte le résumé : notions, définitions et devoirs pour un cours ;
décisions et « qui fait quoi » pour une réunion ; sujets abordés et avis de chacun pour une discussion… Il ne
fait que résumer ce qui a été dit (rien d'inventé) et garde l'heure des passages importants pour s'y retrouver.

- Fait automatiquement à la fin d'une transcription (réglage « transcription_resume_auto »), ou à la demande
  (bouton « Résumer », outil resumer_transcription).
- Les tâches dites à voix haute (« je t'envoie le devis vendredi », « pour lundi, exercices 3 et 4 ») partent dans
  la liste À faire au premier résumé automatique (réglage « transcription_actions_afaire »).
- Longue transcription : résumée par morceaux, puis les morceaux sont réunis (rien n'est coupé).
- Le résumé est rangé dans la transcription (session["resume"]) : il suit la transcription sur tous les appareils
  et en tête de l'export Markdown.
"""
import json
import re
import threading
import time

from .config import CONFIG

MIN_PHRASES = 4             # en dessous, rien à résumer
MIN_DUREE = 30.0            # s
TAILLE_MORCEAU = 40_000     # caractères de transcription par appel au cerveau
GENRES = {"cours": "Cours", "reunion": "Réunion", "discussion": "Discussion", "appel": "Appel", "entretien": "Entretien",
          "conference": "Conférence", "note": "Note vocale", "autre": "Transcription"}
_en_cours: set = set()
_verrou = threading.Lock()

CONSIGNES = """Tu résumes la transcription automatique d'un enregistrement. Ce n'est pas forcément une réunion : ça peut \
être un cours, une conférence, une discussion entre amis, un appel, un entretien, une note vocale…

1. Reconnais d'abord de quoi il s'agit, d'après le contenu.
2. Écris un résumé en Markdown, en {langue}, adapté à ce genre d'enregistrement :
   - cours / conférence : le sujet, les notions expliquées (avec les définitions et formules données), les exemples, \
ce qu'il faut retenir, et les devoirs ou consignes donnés ;
   - réunion : le contexte, les points abordés, les décisions prises, les questions restées ouvertes, qui fait quoi ;
   - discussion / appel : les sujets abordés, ce que chacun a dit ou proposé, ce qui a été convenu ;
   - entretien : les questions posées et l'essentiel des réponses ;
   - note vocale ou autre : l'essentiel, dans l'ordre.
   Commence par 2 ou 3 phrases qui disent l'essentiel, puis des titres « ### » et des listes à puces. Mets l'heure \
entre crochets pour les passages importants, comme dans la transcription : [12:34].
3. Ne résume QUE ce qui a été dit. N'invente rien, ne complète pas avec tes connaissances. La transcription peut \
contenir des erreurs de reconnaissance : si un mot est manifestement mal reconnu, ne le recopie pas. Désigne les \
personnes par le nom donné dans la transcription (« Locuteur 1 » si elle n'a pas de nom).
4. Longueur : proportionnelle au contenu (quelques lignes pour 5 minutes, plus pour une heure de cours).

Termine ta réponse par un bloc ```json, et rien après, de cette forme :
{{"genre": "cours|reunion|discussion|appel|entretien|conference|note|autre", "titre": "titre court et parlant", \
"actions": [{{"titre": "tâche à faire, à l'infinitif", "qui": "personne concernée ou vide", "echeance": "AAAA-MM-JJ ou vide"}}]}}
Dans "actions", mets SEULEMENT les tâches ou devoirs explicitement dits à voix haute (pas de conseils, pas d'idées \
en l'air) ; liste vide s'il n'y en a pas. Date de l'enregistrement : {date} (pour transformer « vendredi », \
« la semaine prochaine »… en date)."""


def texte_complet(session: dict) -> str:
    """La transcription en lignes « [hh:mm] Nom : texte » (tours de parole), comme lire_transcription."""
    from .transcription import horodatage, nom_locuteur, tours_de_parole
    return "\n".join(f"[{horodatage(t['debut'])}] {nom_locuteur(session, t['locuteur'])} : {t['texte']}"
                     for t in tours_de_parole(session))


def morceaux(texte: str, taille: int = TAILLE_MORCEAU) -> list[str]:
    """Coupe aux fins de ligne, jamais au milieu d'une prise de parole."""
    res, courant = [], []
    n = 0
    for ligne in texte.splitlines():
        if courant and n + len(ligne) > taille:
            res.append("\n".join(courant))
            courant, n = [], 0
        courant.append(ligne)
        n += len(ligne) + 1
    if courant:
        res.append("\n".join(courant))
    return res


def analyser(reponse: str) -> dict:
    """Sépare le résumé Markdown et le bloc JSON final (tolérant : un petit modèle local peut l'oublier)."""
    infos = {}
    m = list(re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", reponse, re.S))
    texte = reponse
    if m:
        try:
            infos = json.loads(m[-1].group(1))
        except ValueError:
            infos = {}
        texte = reponse[:m[-1].start()]
    else:   # JSON sans bloc, à la toute fin
        m2 = re.search(r"(\{[^{}]*\"genre\"[^{}]*(\[[^\]]*\])?[^{}]*\})\s*$", reponse, re.S)
        if m2:
            try:
                infos = json.loads(m2.group(1))
                texte = reponse[:m2.start()]
            except ValueError:
                pass
    genre = str(infos.get("genre") or "autre").lower()
    actions = []
    for a in infos.get("actions") or []:
        if isinstance(a, dict) and str(a.get("titre") or "").strip():
            ech = str(a.get("echeance") or "").strip()
            actions.append({"titre": str(a["titre"]).strip()[:200], "qui": str(a.get("qui") or "").strip()[:80],
                            "echeance": ech if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ech) else ""})
    return {"texte": texte.strip(), "genre": genre if genre in GENRES else "autre",
            "titre": str(infos.get("titre") or "").strip()[:120], "actions": actions[:20]}


def _langue() -> str:
    return "anglais" if (CONFIG.get("langue") or "fr") == "en" else "français"


def generer(session: dict, completer=None) -> dict:
    """Résumé d'une session (sans l'enregistrer). completer : fonction prompt -> réponse (cerveau de Wesley)."""
    from datetime import datetime
    if completer is None:
        from .agent import completer
    texte = texte_complet(session)
    if not texte.strip():
        raise ValueError("Rien n'a été transcrit : il n'y a rien à résumer.")
    date = datetime.fromtimestamp(session.get("debut") or time.time()).strftime("%A %d/%m/%Y")
    consignes = CONSIGNES.format(langue=_langue(), date=date)
    titre = session.get("titre") or ""
    parts = morceaux(texte, TAILLE_MORCEAU)
    if len(parts) == 1:
        rep = completer(f"{consignes}\n\nTitre donné à l'enregistrement : {titre or '(aucun)'}\n\nTRANSCRIPTION :\n{texte}")
    else:
        # longue transcription : notes détaillées par morceau, puis un seul résumé à partir des notes
        notes = []
        for i, p in enumerate(parts, 1):
            notes.append(completer(
                f"Voici la partie {i} sur {len(parts)} de la transcription automatique d'un enregistrement "
                f"(titre : {titre or 'aucun'}). Prends des notes détaillées en {_langue()} : tout ce qui est important, "
                "dans l'ordre, avec l'heure entre crochets [hh:mm], les noms des personnes, les définitions, chiffres, "
                "décisions, tâches et devoirs dits. N'invente rien, n'ajoute rien qui n'a pas été dit.\n\n"
                f"TRANSCRIPTION (partie {i}/{len(parts)}) :\n{p}"))
        rep = completer(f"{consignes}\n\nTitre donné à l'enregistrement : {titre or '(aucun)'}\n\n"
                        "L'enregistrement est long : voici les notes prises partie par partie, dans l'ordre. "
                        "Fais le résumé de l'ensemble à partir de ces notes.\n\n"
                        + "\n\n".join(f"--- NOTES, PARTIE {i} ---\n{n}" for i, n in enumerate(notes, 1)))
    r = analyser(rep or "")
    if not r["texte"]:
        raise ValueError("Le cerveau n'a pas renvoyé de résumé.")
    return r | {"date": time.time(), "nb_phrases": len(session.get("segments") or []), "cerveau": CONFIG.get("cerveau", "")}


def resumable(session: dict) -> bool:
    segs = session.get("segments") or []
    return len(segs) >= MIN_PHRASES and float(session.get("duree") or 0) >= MIN_DUREE


def resumer(tid: str, auto: bool = False, completer=None) -> dict:
    """Résume la transcription `tid` de cet appareil et range le résumé dedans. auto : à la fin d'une
    transcription (les tâches dites partent dans À faire si le réglage le permet). Renvoie le résumé."""
    from . import transcription
    with _verrou:
        if tid in _en_cours:
            raise ValueError("Le résumé de cette transcription est déjà en cours.")
        _en_cours.add(tid)
    try:
        s = transcription.lire(tid)
        if s is None:
            raise ValueError("Transcription introuvable.")
        if s.get("etat") in ("preparation", "en_cours", "finalisation"):
            raise ValueError("Attends la fin de la transcription pour la résumer.")
        transcription.marquer_resume(tid, {"en_cours": True, "erreur": ""})   # l'ancien résumé reste affiché
        try:
            r = generer(s, completer)
        except Exception as e:
            raison = str(e) if isinstance(e, ValueError) else \
                f"le cerveau de Wesley n'a pas répondu (vérifie l'IA choisie et sa clé dans Réglages › Cerveau). Détail : {e}"
            transcription.marquer_resume(tid, {"en_cours": False, "erreur": f"Résumé impossible : {raison}"[:500]})
            raise
        deja = (s.get("resume") or {}).get("afaire_ajoutees")
        if auto and r["actions"] and CONFIG.get("transcription_actions_afaire", True) and not deja:
            r["afaire_ajoutees"] = _vers_afaire(s, r["actions"])
        elif deja:
            r["afaire_ajoutees"] = deja
        transcription.marquer_resume(tid, r, remplacer=True)
        return r
    finally:
        with _verrou:
            _en_cours.discard(tid)


def _vers_afaire(session: dict, actions: list) -> int:
    from . import afaire
    n = 0
    for a in actions:
        note = f"Dit pendant « {session.get('titre') or 'la transcription'} »" + (f" (pour : {a['qui']})" if a.get("qui") else "")
        try:
            afaire.ajouter(a["titre"], note=note, echeance=a.get("echeance") or "")
            n += 1
        except Exception as e:
            print(f"  ! À faire depuis le résumé : {e}")
    return n


def au_terme(tid: str):
    """Appelé quand une transcription de cet appareil vient de se terminer : résumé automatique en fond."""
    from . import transcription
    s = transcription.lire(tid)
    if (not CONFIG.get("transcription_resume_auto", True) or not s or s.get("etat") != "terminee"
            or not resumable(s) or (s.get("resume") or {}).get("nb_phrases") == len(s.get("segments") or [])):
        _automatisations(tid)   # pas de nouveau résumé à attendre
        return

    def fond():
        try:
            r = resumer(tid, auto=True)
            from . import notifications
            plus = f" {r['afaire_ajoutees']} tâche(s) ajoutée(s) à À faire." if r.get("afaire_ajoutees") else ""
            notifications.ajouter(f"Résumé prêt : {s.get('titre') or 'transcription'}",
                                  (r["texte"].split("\n\n")[0][:300]) + plus, genre="succes", vue="transcription")
        except Exception as e:
            print(f"  ! Résumé automatique de {tid} : {e}")
        _automatisations(tid)   # avec le résumé s'il a réussi, sans sinon
    threading.Thread(target=fond, daemon=True, name=f"resume-{tid}").start()


def _automatisations(tid: str):
    """Règles « quand une transcription se termine » (ex : envoyer le compte rendu sur Telegram)."""
    try:
        from . import automatisations
        automatisations.transcription_finie(tid)
    except Exception as e:
        print(f"  ! Automatisations de fin de transcription ({tid}) : {e}")


def en_markdown(resume: dict) -> str:
    """Bloc « Résumé » placé en tête de l'export Markdown."""
    if not resume or not resume.get("texte"):
        return ""
    lignes = [f"## Résumé ({GENRES.get(resume.get('genre'), 'Transcription').lower()})", "", resume["texte"], ""]
    if resume.get("actions"):
        lignes += ["### À faire", ""] + [
            f"- [ ] {a['titre']}" + (f" ({a['qui']})" if a.get("qui") else "") + (f" — pour le {a['echeance']}" if a.get("echeance") else "")
            for a in resume["actions"]] + [""]
    return "\n".join(lignes)
