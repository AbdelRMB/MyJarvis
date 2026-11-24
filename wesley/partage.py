"""Tâches de fond et transcriptions visibles sur tous les appareils du compte.

Chaque ordinateur publie ses tâches (onglet Tâches) et ses transcriptions (onglet Transcription) dans le compte,
chiffrées avec la clé du coffre (comme les ordres entre appareils) : le serveur ne voit ni les titres ni le texte.
Les autres appareils (ordinateurs et téléphone) les affichent à côté des leurs, avec le nom de l'appareil
d'origine.

Un élément reste à l'appareil qui l'a créé : c'est lui qui a le micro, le projet, la copie de travail et les
empreintes vocales. Depuis un autre appareil, « Reprendre », « Arrêter », renommer un locuteur… envoient un ordre
chiffré à l'appareil d'origine (wesley/appareils.py), qui le fait chez lui. S'il ne peut pas (éteint, Wesley
fermé, ordres refusés, autre transcription en cours…), la raison remonte telle quelle à l'utilisateur.
"""
import base64
import json
import threading
import time
import uuid
import zlib

from .config import MACHINE, RACINE

GENRES = ("tache", "transcription")
CONTEXTE = b"wesley-partage"
DELAI = {"tache": 2.0, "transcription": 2.0}
DELAI_EN_COURS = 10.0          # s : une transcription en cours est republiée au plus toutes les 10 s
JOURNAL_MAX = 400              # entrées du journal d'une tâche envoyées (les plus récentes)
_verrou = threading.RLock()
_sales: dict = {}              # (genre, id) -> instant à partir duquel publier
_publie: dict = {}             # (genre, id) -> instant de la dernière publication
_fil = {"lance": False}
_cache = {"liste": [], "lu": 0.0, "appareils": {}, "appareils_lu": 0.0}
_contenus: dict = {}           # (genre, id) -> (modifie, contenu déchiffré)
ecouteurs: list = []           # appelés quand la liste des éléments des autres appareils change


def _compte():
    from . import compte
    return compte


# ---------- identité stable de cette installation ----------
def identifiant_machine() -> str:
    """Ne change pas quand on se reconnecte (la session, elle, change) : permet de reconnaître ses propres
    éléments publiés depuis une ancienne session."""
    f = RACINE / "appareil.id"
    try:
        v = f.read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    v = uuid.uuid4().hex
    try:
        f.write_text(v, encoding="utf-8")
    except OSError:
        pass
    return v


def _plateforme():
    import sys
    return "mac" if sys.platform == "darwin" else "windows" if sys.platform == "win32" else "linux"


# ---------- chiffrement (zlib + AES-GCM, clé du coffre) ----------
def chiffrer(obj, cle: bytes | None = None) -> str:
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    n = os.urandom(12)
    brut = zlib.compress(json.dumps(obj, ensure_ascii=False).encode("utf-8"), 6)
    return base64.b64encode(n + AESGCM(cle or _compte()._cle_coffre()).encrypt(n, brut, CONTEXTE)).decode()


def dechiffrer(blob: str, cle: bytes | None = None):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    brut = base64.b64decode(blob)
    return json.loads(zlib.decompress(AESGCM(cle or _compte()._cle_coffre()).decrypt(brut[:12], brut[12:], CONTEXTE)))


# ---------- ce que cet appareil publie ----------
def _tache_locale(eid: str):
    from . import taches
    t = taches.lire(eid)
    if not t:
        return None
    journal = [dict(e, texte=str(e.get("texte", ""))[:3000]) for e in t.get("journal", [])[-JOURNAL_MAX:]]
    return taches.resume(t), dict(t, journal=journal, nb_journal=len(t.get("journal", [])))


def _transcription_locale(eid: str):
    from . import transcription
    try:
        s = transcription.lire(eid)
    except ValueError:
        return None
    if not s:
        return None
    return transcription.resume(s), dict(s, locuteurs=transcription.locuteurs(s))


def local(genre: str, eid: str):
    """(résumé, contenu) d'un élément de cet appareil, ou None s'il n'existe plus."""
    r = _tache_locale(eid) if genre == "tache" else _transcription_locale(eid) if genre == "transcription" else None
    if r is None:
        return None
    resume, contenu = r
    origine = {"appareil_nom": MACHINE, "plateforme": _plateforme(), "machine": identifiant_machine()}
    return resume | origine, contenu


def ids_locaux(genre: str) -> list[str]:
    if genre == "tache":
        from . import taches
        return [t["id"] for t in taches.lister()]
    from . import transcription
    return [s["id"] for s in transcription.lister()]


def signaler(genre: str, eid: str):
    """Un élément de cet appareil a changé (ou a été supprimé) : il part dans le compte peu après."""
    if genre not in GENRES or not eid:
        return
    try:
        if not _compte().connecte():
            return
    except Exception:
        return
    cle = (genre, eid)
    with _verrou:
        attente = DELAI[genre]
        if genre == "transcription":
            from . import transcription
            t = transcription.en_cours()
            if t is not None and t.session["id"] == eid and t.session.get("etat") == "en_cours":
                attente = max(attente, DELAI_EN_COURS - (time.time() - _publie.get(cle, 0)))
        _sales.setdefault(cle, time.time() + attente)
    _lancer_fil()


def _lancer_fil():
    with _verrou:
        if _fil["lance"]:
            return
        _fil["lance"] = True
    threading.Thread(target=_boucle, daemon=True, name="partage").start()


def _boucle():
    while True:
        time.sleep(1)
        with _verrou:
            # retirés AVANT l'envoi : un changement pendant l'envoi est de nouveau signalé (la fin d'une
            # transcription n'est jamais perdue)
            prets = [k for k, quand in _sales.items() if quand <= time.time()]
            for k in prets:
                _sales.pop(k, None)
        for cle in prets:
            try:
                publier(*cle)
            except Exception as e:
                print(f"  ! Partage de {cle[0]} {cle[1]} : {e}")
                with _verrou:
                    _sales.setdefault(cle, time.time() + 30)   # hors ligne : on réessaie plus tard


def publier(genre: str, eid: str):
    c = _compte()
    if not c.connecte():
        return
    el = local(genre, eid)
    if el is None:
        c._appel("POST", f"/v1/partages/{genre}/{eid}/supprimer", timeout=30)
        return
    resume, contenu = el
    cle = c._cle_coffre()
    c._appel("PUT", f"/v1/partages/{genre}/{eid}", json={"resume": chiffrer(resume, cle), "contenu": chiffrer(contenu, cle)},
             timeout=120)
    _publie[(genre, eid)] = time.time()


def reconcilier():
    """À la connexion : publie ce qui manque ou a changé pendant que Wesley était hors ligne, retire du compte ce
    qui a été supprimé ici, et récupère les éléments publiés par cet appareil depuis une ancienne session."""
    c = _compte()
    if not c.connecte():
        return
    serveur = c._appel("GET", "/v1/partages", timeout=60)
    moi = identifiant_machine()
    a_moi: dict = {}
    for x in serveur:
        if x["moi"]:
            a_moi[(x["genre"], x["id"])] = x["modifie"]
            continue
        try:
            if dechiffrer(x["resume"]).get("machine") == moi:   # publié par cet appareil avant une reconnexion
                a_moi[(x["genre"], x["id"])] = 0
        except Exception:
            pass
    for genre in GENRES:
        for eid in ids_locaux(genre):
            el = local(genre, eid)
            if el is None:
                continue
            maj = float(el[1].get("maj") or 0) if genre == "tache" else _date_fichier(eid)
            if (genre, eid) not in a_moi or maj > a_moi[(genre, eid)]:
                with _verrou:
                    _sales.setdefault((genre, eid), time.time())
    for (genre, eid) in a_moi:
        if eid not in ids_locaux(genre):
            with _verrou:
                _sales.setdefault((genre, eid), time.time())   # supprimé ici : publier() le retire du compte
    if _sales:
        _lancer_fil()


def _date_fichier(eid: str) -> float:
    from . import transcription
    try:
        return transcription._chemin(eid).stat().st_mtime
    except (OSError, ValueError):
        return time.time()


# ---------- ce que les autres appareils publient ----------
def _appareils(force=False) -> dict:
    if force or time.time() - _cache["appareils_lu"] > 20:
        try:
            from . import appareils
            _cache["appareils"] = {a["id"]: a for a in appareils.lister()}
            _cache["appareils_lu"] = time.time()
        except Exception:
            pass
    return _cache["appareils"]


def rafraichir():
    """Relit la liste du compte (appelé quand le serveur signale un changement)."""
    c = _compte()
    if not c.connecte():
        _cache["liste"] = []
        return
    liste = []
    moi = identifiant_machine()
    for x in c._appel("GET", "/v1/partages", timeout=60):
        if x["moi"]:
            continue
        try:
            r = dechiffrer(x["resume"])
        except Exception:
            continue   # chiffré avec une autre clé (ancien mot de passe) : illisible
        if r.get("machine") == moi:
            continue
        liste.append({"genre": x["genre"], "resume": r, "appareil_id": x["appareil"], "modifie": x["modifie"]})
    avant = [(e["genre"], e["resume"].get("id"), e["modifie"]) for e in _cache["liste"]]
    _cache["liste"], _cache["lu"] = liste, time.time()
    _appareils(force=True)
    if avant != [(e["genre"], e["resume"].get("id"), e["modifie"]) for e in liste]:
        for f in list(ecouteurs):
            try:
                f()
            except Exception as e:
                print(f"  ! Après partage : {e}")


def _decorer(e: dict) -> dict:
    a = _appareils().get(e["appareil_id"]) or {}
    return e["resume"] | {"distant": True, "appareil": e["resume"].get("appareil_nom") or a.get("nom") or "?",
                          "appareil_id": e["appareil_id"], "en_ligne": bool(a.get("en_ligne")),
                          "accepte": bool(a.get("accepte", True))}


def distants(genre: str) -> list[dict]:
    """Résumés des éléments des autres appareils (avec le nom de l'appareil et s'il est en ligne)."""
    try:
        if not _compte().connecte():
            return []
    except Exception:
        return []
    if not _cache["lu"]:
        try:
            rafraichir()
        except Exception:
            # serveur injoignable (ou pas encore à jour) : pas de nouvel essai à chaque affichage de la liste ;
            # la synchro temps réel relira la liste dès qu'un élément change
            _cache["lu"] = time.time()
            return []
    locaux = set(ids_locaux(genre))
    return [_decorer(e) for e in _cache["liste"] if e["genre"] == genre and e["resume"].get("id") not in locaux]


def trouver(genre: str, eid: str) -> dict | None:
    for e in _cache["liste"]:
        if e["genre"] == genre and e["resume"].get("id") == eid:
            return e
    return None


def lire(genre: str, eid: str) -> dict | None:
    """Contenu complet d'un élément d'un autre appareil (dernière version publiée)."""
    e = trouver(genre, eid)
    if e is None:
        try:
            rafraichir()
        except Exception:
            return None
        e = trouver(genre, eid)
        if e is None:
            return None
    deja = _contenus.get((genre, eid))
    if deja and deja[0] == e["modifie"]:
        contenu = deja[1]
    else:
        c = _compte()
        try:
            d = c._appel("GET", f"/v1/partages/{genre}/{eid}", timeout=120)
        except c.ErreurCompte:
            return None
        contenu = dechiffrer(d["contenu"])
        _contenus[(genre, eid)] = (d["modifie"], contenu)
    return contenu | {k: v for k, v in _decorer(e).items() if k in ("distant", "appareil", "appareil_id", "en_ligne", "accepte")}


# ---------- agir sur l'élément d'un autre appareil : on le lui demande ----------
VERBES = {"reprendre": "reprendre", "arreter": "arrêter", "consigne": "envoyer la consigne", "supprimer": "supprimer",
          "noms": "renommer les locuteurs", "fusionner": "fusionner les locuteurs", "locuteur": "changer le locuteur",
          "texte": "corriger le texte", "regrouper": "regrouper les voix", "titre": "changer le titre"}
NOMS = {"tache": "la tâche", "transcription": "la transcription"}


def agir(genre: str, eid: str, action: str, params: dict | None = None) -> str:
    """Demande à l'appareil d'origine de faire l'action. Renvoie son message ; ValueError avec la raison sinon."""
    from . import appareils
    e = trouver(genre, eid)
    if e is None:
        rafraichir()
        e = trouver(genre, eid)
    if e is None:
        raise ValueError(f"Impossible : {NOMS.get(genre, 'cet élément')} n'existe plus (supprimée sur son appareil ?).")
    d = _decorer(e)
    nom, titre = d["appareil"], d.get("titre") or eid
    verbe = VERBES.get(action, action)
    if not _compte().connecte():
        raise ValueError(f"Impossible de {verbe} sur {nom} : il faut être connecté à ton compte.")
    a = _appareils(force=True).get(e["appareil_id"])
    if a is None:
        raise ValueError(f"Impossible de {verbe} sur {nom} : cet appareil n'est plus connecté à ton compte "
                         f"(déconnecté, ou Wesley n'y a pas été rouvert depuis).")
    if not a.get("en_ligne"):
        raise ValueError(f"Impossible de {verbe} sur {nom} : il est hors ligne (éteint, en veille, ou Wesley n'y est "
                         "pas ouvert). Rallume-le ou ouvre Wesley dessus, puis réessaie.")
    if not a.get("accepte", True):
        raise ValueError(f"Impossible de {verbe} sur {nom} : il refuse les ordres à distance (réglage dans son onglet Appareils).")
    try:
        rep = appareils.envoyer(e["appareil_id"], {"type": "partage", "genre": genre, "id": eid, "action": action,
                                                   "params": params or {},
                                                   "texte": f"{verbe[:1].upper() + verbe[1:]} {NOMS.get(genre, '')} « {titre} »"},
                                delai=180)
    except ValueError as x:
        raise ValueError(f"Impossible de {verbe} sur {nom} : {x}")
    if not rep.get("ok"):
        raise ValueError(f"{nom} n'a pas pu {verbe} {NOMS.get(genre, '')} : {rep.get('resultat') or 'raison inconnue'}")
    _contenus.pop((genre, eid), None)
    return rep.get("resultat") or "C'est fait."


def executer(d: dict) -> str:
    """Sur l'appareil d'origine : réalise l'action demandée par un autre appareil (ordre « partage »)."""
    genre, eid, action, p = d.get("genre"), str(d.get("id") or ""), d.get("action"), d.get("params") or {}
    if genre == "transcription":
        return _executer_transcription(eid, action, p)
    if genre == "tache":
        return _executer_tache(eid, action, p)
    raise ValueError("Élément inconnu.")


def _executer_transcription(tid: str, action: str, p: dict) -> str:
    from . import transcription
    try:
        s = transcription.lire(tid)
    except ValueError:
        s = None
    if s is None:
        raise ValueError(f"cette transcription n'existe plus sur {MACHINE}.")
    titre = s.get("titre") or tid
    if action == "reprendre":
        from . import web
        etat = web.reprendre_transcription(tid, p)
        src = "le son de l'ordinateur" + (" et le micro" if etat.get("avec_micro") else "") if etat.get("source") == "systeme" else "le micro"
        return f"Transcription « {titre} » reprise sur {MACHINE} ({src}) : la suite s'y écrit."
    if action == "arreter":
        t = transcription.en_cours()
        if t is None or t.session["id"] != tid:
            raise ValueError(f"cette transcription n'est pas en cours sur {MACHINE}.")
        transcription.arreter()
        return f"Transcription « {titre} » arrêtée sur {MACHINE}."
    if action == "supprimer":
        transcription.supprimer(tid, bool(p.get("fichier")))
        return f"Transcription « {titre} » supprimée de {MACHINE}."
    if action in ("noms", "fusionner", "locuteur", "texte", "regrouper", "titre"):
        transcription.modifier(tid, action, p)
        return f"Transcription « {titre} » modifiée sur {MACHINE}."
    raise ValueError("Action inconnue.")


def _executer_tache(tid: str, action: str, p: dict) -> str:
    from . import taches
    t = taches.lire(tid)
    if not t:
        raise ValueError(f"cette tâche n'existe plus sur {MACHINE}.")
    if action == "reprendre":
        return taches.reprendre(tid).rstrip(".") + f" sur {MACHINE}."
    if action == "arreter":
        taches.arreter(tid)
        return f"Tâche « {t.get('titre')} » arrêtée sur {MACHINE}."
    if action == "consigne":
        texte = str(p.get("texte") or "").strip()
        if not texte:
            raise ValueError("consigne vide.")
        return taches.mettre_a_jour(tid, texte)
    if action == "supprimer":
        taches.supprimer(tid)
        return f"Tâche « {t.get('titre')} » supprimée de {MACHINE}."
    raise ValueError("Action inconnue.")


def demarrer():
    """Branche le partage : chaque changement local part dans le compte (appelé au lancement de l'interface)."""
    from . import transcription
    transcription.ecouteurs.append(lambda tid: signaler("transcription", tid))
