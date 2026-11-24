"""Outils de Wesley pour la transcription de réunions (onglet Transcription, 100 % local)."""
from . import outil


def _lancer(reprendre: str = "", **options):
    """Passe par le serveur de l'interface quand il tourne (il coupe l'écoute « Wesley » pendant la réunion).
    reprendre : identifiant d'une transcription à continuer."""
    try:
        from .. import web
    except ImportError:          # Wesley en mode terminal, sans interface
        from .. import transcription
        return transcription.reprendre(reprendre, **options) if reprendre else transcription.demarrer(**options)
    try:
        return web._lancer_transcription(reprendre=reprendre, **options)
    except Exception as e:
        if e.__class__.__name__ == "HTTPException":
            raise ValueError(getattr(e, "detail", str(e)))
        raise


@outil
def demarrer_transcription(source: str = "micro", avec_micro: bool = True, titre: str = "", nb_locuteurs: int = 0,
                           langue: str = "", vocabulaire: str = ""):
    """Lance la transcription d'une réunion ou d'une conversation dans un fichier, avec reconnaissance des voix (Locuteur 1, Locuteur 2…) et horodatage. Tout reste sur l'ordinateur. À utiliser quand on te demande de transcrire, d'écrire ou de prendre en note une réunion / un appel / une conversation.
    source: « systeme » pour une réunion en ligne (Teams, Zoom, Meet… : le son de l'ordinateur) ou « micro » pour une réunion physique (Wesley écoute la pièce)
    avec_micro: source « systeme » seulement : ajouter le micro pour transcrire aussi la voix de l'utilisateur (oui par défaut)
    titre: titre de la réunion (facultatif)
    nb_locuteurs: nombre de personnes s'il est connu (0 = détection automatique)
    langue: langue parlée (« fr », « en »…) ; vide = celle de Wesley
    vocabulaire: mots techniques ou noms propres à bien orthographier, séparés par des virgules (ex. « PHP, getter, setter, $this ») ; facultatif"""
    from .. import transcription
    from ..config import CONFIG
    try:
        s = _lancer(source="systeme" if source == "systeme" else "micro", avec_micro=avec_micro, titre=titre,
                    nb_locuteurs=nb_locuteurs, langue=(langue or CONFIG.get("langue") or "fr").strip().lower()[:5],
                    vocabulaire=vocabulaire)
    except ValueError as e:
        return f"Impossible : {e}"
    quoi = "le son de l'ordinateur" + (" et ton micro" if avec_micro else "") if source == "systeme" else "le micro"
    return (f"Transcription « {s['titre']} » lancée ({quoi}). Elle s'écrit au fil de l'eau dans "
            f"{transcription.dossier_export()} ; suivi et renommage des locuteurs dans l'onglet Transcription. "
            "Dis « arrête la transcription » à la fin.")


def _partage():
    from .. import partage
    return partage


def _locale(tid: str):
    from .. import transcription
    try:
        return transcription.lire(tid)
    except ValueError:
        return None


def _toutes() -> list[dict]:
    """Transcriptions de cet appareil et des autres appareils du compte, les plus récentes d'abord."""
    from .. import transcription
    return sorted(transcription.lister() + _partage().distants("transcription"), key=lambda r: r.get("debut") or 0,
                  reverse=True)


@outil
def arreter_transcription():
    """Arrête la transcription de réunion en cours (la fin est transcrite et les voix sont regroupées une dernière fois). Si elle tourne sur un autre appareil, c'est lui qui l'arrête."""
    from .. import transcription
    s = transcription.arreter()
    if s is None:
        ailleurs = [r for r in _partage().distants("transcription") if r.get("etat") in ("preparation", "en_cours")]
        if len(ailleurs) == 1:
            try:
                return _partage().agir("transcription", ailleurs[0]["id"], "arreter")
            except ValueError as e:
                return str(e)
        return "Aucune transcription en cours."
    return (f"Transcription « {s['titre']} » arrêtée ({transcription.horodatage(s['duree'])}). Les dernières phrases "
            "sont en cours de transcription ; l'utilisateur peut nommer les locuteurs dans l'onglet Transcription.")


@outil
def reprendre_transcription(identifiant: str = "", source: str = "", avec_micro: bool = True):
    """Reprend une transcription de réunion déjà faite (terminée ou interrompue) : la suite s'écrit à la fin de la même transcription, avec les mêmes personnes (Locuteur 1, 2… et leurs noms) et l'horodatage qui continue. À utiliser quand on te demande de continuer, reprendre ou compléter une transcription (la réunion reprend après une pause, Wesley a été fermé…).
    identifiant: code de la transcription (lister_transcriptions) ; vide = la plus récente
    source: « systeme » (réunion en ligne) ou « micro » (réunion physique) ; vide = la même qu'avant
    avec_micro: source « systeme » seulement : ajouter le micro pour transcrire aussi la voix de l'utilisateur"""
    from .. import transcription
    tid = identifiant.strip("[] ")
    if not tid:
        liste = _toutes()
        if not liste:
            return "Aucune transcription à reprendre."
        tid = liste[0]["id"]
    s = _locale(tid)
    if s is None:
        if _partage().trouver("transcription", tid) is None:
            return "Transcription introuvable."
        # faite sur un autre appareil : c'est lui qui la reprend (son micro / le son de cet ordinateur-là)
        params = {"source": source} if source in ("micro", "systeme") else {}
        try:
            return _partage().agir("transcription", tid, "reprendre", params | {"avec_micro": bool(avec_micro)})
        except ValueError as e:
            return str(e)
    source = source if source in ("micro", "systeme") else (s.get("source") if s.get("source") in ("micro", "systeme") else "micro")
    try:
        r = _lancer(reprendre=tid, source=source, avec_micro=bool(avec_micro) and source == "systeme")
    except ValueError as e:
        return f"Impossible : {e}"
    return (f"Transcription « {r['titre']} » reprise à {transcription.horodatage(r.get('duree') or 0)} : la suite "
            "s'ajoute au même fichier, avec les mêmes locuteurs. Dis « arrête la transcription » à la fin.")


@outil
def lister_transcriptions():
    """Liste les transcriptions de réunions (titre, date, durée, nombre de personnes, identifiant), y compris celles faites sur tes autres appareils (« sur … »)."""
    from datetime import datetime
    from .. import transcription
    lignes = [f"[{r['id']}] {r['titre']} — {datetime.fromtimestamp(r['debut']).strftime('%d/%m/%Y %H:%M')}, "
              f"{transcription.horodatage(r.get('duree') or 0)}, {r['nb_locuteurs']} locuteur(s), {r['etat']}"
              + (f", sur {r['appareil']}" if r.get("distant") else "")
              for r in _toutes()[:30]]
    return "\n".join(lignes) or "Aucune transcription."


@outil
def lire_transcription(identifiant: str = "", debut: float = 0, fin: float = 0, partie: int = 1):
    """Renvoie le texte exact d'une transcription de réunion, mot pour mot avec l'heure et le locuteur de chaque prise de parole (pour la résumer, en faire un compte rendu, retrouver qui a dit quoi…). Une longue réunion est renvoyée par parties : si la réponse indique « Suite : partie=2 », rappelle l'outil avec partie=2, et ainsi de suite, avant de résumer.
    identifiant: code de la transcription (lister_transcriptions) ; vide = la plus récente
    debut: ne renvoyer qu'à partir de cette minute (0 = depuis le début)
    fin: ne renvoyer que jusqu'à cette minute (0 = jusqu'à la fin)
    partie: numéro de la partie à lire (1, 2…) quand le texte est long"""
    from .. import transcription
    tid = identifiant.strip("[] ")
    if not tid:
        liste = _toutes()
        if not liste:
            return "Aucune transcription."
        tid = liste[0]["id"]
    s = _locale(tid) or _partage().lire("transcription", tid)   # ou faite sur un autre appareil
    if s is None:
        return "Transcription introuvable."
    return transcription.extrait(s, debut, fin, partie)
