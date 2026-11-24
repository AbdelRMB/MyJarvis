"""Rapports de bug automatiques : quand Wesley plante ou qu'une demande échoue sur une erreur interne, il garde un
rapport prêt (version, système, erreur, fin du journal) et propose de l'envoyer au développeur sous forme de ticket.
Rien ne part sans l'accord de l'utilisateur : il voit le contenu exact avant d'envoyer (écran Tickets).
"""
import json
import re
import sys
import threading
import time
import traceback

from .config import RACINE

FICHIER = RACINE / "logs" / "rapport_en_attente.json"
_verrou = threading.Lock()
# erreurs qui viennent de la configuration de l'utilisateur ou du réseau, pas d'un bug de Wesley
_PAS_UN_BUG = re.compile(r"api[_ -]?key|clé api|401|403|429|credit|crédit|quota|rate.?limit|overloaded|surcharg|"
                         r"connection|connexion|injoignable|timed? ?out|délai|getaddrinfo|network|réseau|"
                         r"annul|interrompu|stop", re.I)


def en_attente() -> dict | None:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ignorer():
    FICHIER.unlink(missing_ok=True)


def _fin_journal(n=60) -> str:
    try:
        lignes = (RACINE / "logs" / "wesley.log").read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lignes[-n:])
    except OSError:
        return ""


def diagnostic() -> str:
    from .plateforme import MAC
    from .version import VERSION
    import platform
    sante = ""
    try:   # outils qui échouent, cerveaux (compté sur cet appareil ; joint seulement si l'utilisateur l'accepte)
        from . import sante as s
        sante = "\n" + s.texte(7)
    except Exception:
        pass
    return (f"Version : {VERSION} — {'macOS' if MAC else 'Windows'} {platform.release()} ({platform.machine()})\n"
            f"Date : {time.strftime('%Y-%m-%d %H:%M:%S')}" + sante)


def noter(erreur: str, contexte: str = "", plantage: bool = False):
    """Garde un rapport prêt à envoyer et prévient l'utilisateur (une fois par heure au plus pour la même erreur)."""
    if not plantage and _PAS_UN_BUG.search(erreur):
        return
    try:
        with _verrou:
            avant = en_attente()
            lignes = [l for l in erreur.strip().splitlines() if l.strip()]
            # une trace Python finit par l'erreur elle-même (« KeyError: 'x' ») : c'est elle qui sert de titre
            premiere = (lignes[-1] if lignes and lignes[0].startswith("Traceback") else (lignes or ["Erreur"])[0]).strip()[:150]
            if avant and avant.get("titre") == premiere and time.time() - avant.get("ts", 0) < 3600:
                return
            FICHIER.parent.mkdir(exist_ok=True)
            FICHIER.write_text(json.dumps({"ts": time.time(), "titre": premiere, "erreur": erreur[-4000:],
                                           "contexte": contexte[:500], "plantage": plantage,
                                           "diagnostic": diagnostic(), "journal": _fin_journal()},
                                          ensure_ascii=False), encoding="utf-8")
        if plantage:
            return   # l'appli s'arrête : la notification sera affichée au prochain démarrage
        _prevenir()
    except Exception:
        pass


def _prevenir():
    try:
        from . import notifications, web
        notifications.ajouter("Wesley a rencontré une erreur", "Tu peux envoyer un rapport au développeur pour qu'il la corrige "
                              "(écran Tickets : tu vois tout ce qui sera envoyé).", genre="alerte", vue="tickets")
        web.diffuser(type="tickets_maj")
    except Exception:
        pass


def au_demarrage():
    """Plantage lors de la dernière session : on le signale maintenant."""
    r = en_attente()
    if r and r.get("plantage") and not r.get("signale"):
        r["signale"] = True
        FICHIER.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        _prevenir()


def contenu(r: dict, commentaire: str = "") -> str:
    texte = (commentaire.strip() + "\n\n" if commentaire.strip() else "") + "--- Rapport automatique ---\n" + r["diagnostic"]
    if r.get("contexte"):
        texte += f"\nDemande en cours : {r['contexte']}"
    texte += f"\n\nErreur :\n{r['erreur']}"
    if r.get("journal"):
        texte += f"\n\nFin du journal :\n{r['journal']}"
    return texte[:9800]


def envoyer(commentaire: str = "") -> dict:
    from . import compte
    r = en_attente()
    if not r:
        raise compte.ErreurCompte("Aucun rapport en attente.")
    res = compte.creer_ticket("bug", f"Erreur : {r['titre']}"[:200], contenu(r, commentaire))
    ignorer()
    return res


def installer_crochets():
    """Toute exception non rattrapée (fil principal ou fil secondaire) devient un rapport."""
    ancien = sys.excepthook

    def crochet(typ, val, tb):
        if not issubclass(typ, (KeyboardInterrupt, SystemExit)):
            noter("".join(traceback.format_exception(typ, val, tb)), plantage=True)
        ancien(typ, val, tb)

    def crochet_fil(args):
        if not issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
            noter("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
                  contexte=f"fil « {args.thread.name if args.thread else '?'} »")
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = crochet
    threading.excepthook = crochet_fil
