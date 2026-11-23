"""Compte en ligne Wesley : chaque utilisateur a sa mémoire, son historique, ses réglages et ses secrets.

Sécurité :
- Le mot de passe ne quitte jamais l'appareil. On en dérive (scrypt) une clé d'authentification, envoyée au
  serveur, et une clé de coffre, gardée dans le trousseau de l'appareil.
- Le coffre (clé API Claude, mots de passe des connecteurs, jeton GitHub) est chiffré en AES-GCM avec la clé
  de coffre AVANT l'envoi : le serveur ne stocke que du chiffré qu'il ne peut pas lire.

Fonctionnement hors ligne : tout est aussi gardé dans un cache local (RACINE/comptes/<id>/, mêmes fichiers
qu'avant : memoire/faits.json, memoire/historique/*.md, connecteurs.json, profil.json). Les écritures partent
au serveur tout de suite ; si le réseau manque, elles attendent dans attente.json et repartent plus tard.
"""
import base64
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import requests
import urllib3.util.connection

from . import config

# Beaucoup de box ont un IPv6 cassé : la connexion part en IPv6 et attend jusqu'à l'expiration avant de
# basculer en IPv4 (créer un compte prenait plusieurs minutes). Wesley passe donc directement par l'IPv4.
urllib3.util.connection.HAS_IPV6 = False
_http = requests.Session()   # connexion réutilisée entre les appels (plus rapide)
_http_attente = requests.Session()   # connexion dédiée à l'attente des changements (temps réel)
ecouteurs: list = []   # fonctions appelées quand la synchro rapporte des changements (web.py : prompt + interface)
from .config import CONFIG, MACHINE, RACINE, ecrire_trousseau, lire_trousseau

SERVEUR_DEFAUT = "https://wesley.abdelrahimriche.com"
# Le serveur (Apache + API) ne répond qu'aux requêtes portant cette clé : le navigateur et les robots ne voient
# qu'un 404. Ce n'est qu'un filtre : la vraie protection, ce sont le mot de passe du compte et le chiffrement.
CLE_APPLI_DEFAUT = "5l4xUaEzf2zcv9N56ZrvDH6Lo8MGCGgwqtTcnzeiK-w"   # serveur officiel ; autre serveur : "cle_appli" dans config.json
ETAT_FICHIER = RACINE / "compte.json"
# Version de la politique de confidentialité acceptée en créant un compte (même valeur que POLITIQUE dans serveur/app.py)
POLITIQUE = "2026-11-21"
_verrou = threading.RLock()
_coffre: dict = {}            # secrets déchiffrés (en mémoire seulement)
_synchro_lancee = False


# ---------- état local ----------
def etat() -> dict:
    try:
        return json.loads(ETAT_FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _sauver_etat(e: dict):
    ETAT_FICHIER.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def serveur() -> str:
    return (CONFIG.get("serveur_comptes") or SERVEUR_DEFAUT).rstrip("/")


def mode() -> str:
    """« en_ligne » (compte, données sur tous les appareils), « local » (rien ne sort de cet appareil), ou « »
    tant que l'utilisateur n'a pas choisi."""
    e = etat()
    return e.get("mode") or ("en_ligne" if e.get("id") else "")


def connecte() -> bool:
    return mode() == "en_ligne" and bool(etat().get("id")) and bool(_secret_local("compte:jeton"))


def dossier(uid=None) -> Path:
    if not uid and mode() == "local":
        return RACINE / "comptes" / "local"
    uid = uid or etat().get("id")
    return RACINE / "comptes" / (str(uid) if uid else "_sans_compte")


def choisir_local():
    """Mode local : pas de compte, rien n'est envoyé au serveur. Les données restent sur cet appareil."""
    _sauver_etat({"mode": "local", "importe": etat().get("importe", [])})
    activer_dossiers()


def changer_de_mode():
    """Revient à l'écran de choix (ex : passer du local au compte en ligne). Les données locales sont gardées :
    elles seront envoyées dans le compte à la connexion."""
    e = etat()
    _sauver_etat({"importe": e.get("importe", []), "mode_precedent": mode()})


# ---------- trousseau de l'appareil ----------
_cache_trousseau: dict = {}   # lire le trousseau macOS peut prendre plusieurs secondes : une fois suffit


def _secret_local(nom: str) -> str:
    if nom not in _cache_trousseau:
        try:
            _cache_trousseau[nom] = lire_trousseau(nom)
        except Exception:
            # accès refusé (« Deny ») : on retient la réponse pour ne pas reposer la question à chaque appel
            _cache_trousseau[nom] = ""
    return _cache_trousseau[nom]


def _definir_secret_local(nom: str, valeur: str):
    _cache_trousseau[nom] = valeur or ""
    ecrire_trousseau(nom, valeur)


# ---------- cryptographie ----------
SEL, CONTEXTE_COFFRE = b"wesley-compte:", b"wesley-coffre"


def _deriver(email: str, mot_de_passe: str) -> tuple[str, bytes]:
    maitre = hashlib.scrypt(mot_de_passe.encode(), salt=SEL + email.strip().lower().encode(),
                            n=2 ** 15, r=8, p=1, dklen=64, maxmem=128 * 1024 * 1024)
    return maitre[:32].hex(), maitre[32:]


def _chiffrer(donnees: dict, cle: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(cle).encrypt(nonce, json.dumps(donnees).encode(), CONTEXTE_COFFRE)).decode()


def _dechiffrer(blob: str, cle: bytes) -> dict:
    if not blob:
        return {}
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    brut = base64.b64decode(blob)
    return json.loads(AESGCM(cle).decrypt(brut[:12], brut[12:], CONTEXTE_COFFRE))


# ---------- HTTP ----------
class ErreurCompte(Exception):
    def __init__(self, message="", statut=0):
        super().__init__(message)
        self.statut = statut   # code HTTP renvoyé par le serveur (0 = pas de réponse)


class SessionRevoquee(ErreurCompte):
    """La session de cet appareil a été supprimée (déconnecté depuis un autre appareil, ou expirée)."""


def _appel(methode, chemin, jeton=None, http=None, **kw):
    h = {"Authorization": f"Bearer {jeton or _secret_local('compte:jeton')}", "X-Wesley-Appli": CONFIG.get("cle_appli") or CLE_APPLI_DEFAUT,
         "User-Agent": "Wesley"}
    try:
        r = (http or _http).request(methode, serveur() + chemin, headers=h, timeout=(8, kw.pop("timeout", 20)), **kw)
    except requests.RequestException as e:
        raise ErreurCompte(f"Serveur Wesley injoignable ({type(e).__name__}).") from e
    if r.status_code == 401 and chemin not in ("/v1/connexion", "/v1/inscription"):
        raise SessionRevoquee("Session expirée : reconnecte-toi.")
    if not r.ok:
        try:
            msg = r.json().get("detail")
        except ValueError:
            msg = None
        # pas de « detail » JSON : la réponse vient du proxy (Apache, Cloudflare), pas de l'API → on dit quelle requête
        raise ErreurCompte(msg if isinstance(msg, str) else f"Erreur du serveur ({r.status_code}) sur {methode} {chemin}.",
                           r.status_code)
    return r.json()


# ---------- bascule des dossiers vers le compte actif ----------
def activer_dossiers():
    """Pointe mémoire, connecteurs et profil vers le cache local du compte connecté."""
    from . import connecteurs, memoire
    d = dossier()
    (d / "memoire" / "historique").mkdir(parents=True, exist_ok=True)
    config.PARTAGE = d
    config.PROFIL = d / "profil.json"
    memoire.DOSSIER = d / "memoire"
    memoire.FAITS = memoire.DOSSIER / "faits.json"
    memoire.HIST = memoire.DOSSIER / "historique"
    connecteurs.FICHIER = d / "connecteurs.json"


# ---------- connexion / inscription ----------
def _ouvrir(reponse: dict, email: str, cle_coffre: bytes, nouveau: bool) -> dict:
    global _coffre
    _definir_secret_local("compte:jeton", reponse["jeton"])
    _definir_secret_local("compte:cle_coffre", base64.b64encode(cle_coffre).decode())
    venait_du_local = etat().get("mode_precedent") == "local"
    e = {"mode": "en_ligne", "id": reponse["id"], "email": reponse["email"], "prenom": reponse.get("prenom", ""),
         "serveur": serveur(), "admin": bool(reponse.get("admin")),   # sans attendre la 1re synchro "politique": reponse.get("politique", ""),
         "politique_actuelle": reponse.get("politique_actuelle", "")}
    importe = [] if venait_du_local else etat().get("importe", [])   # du local vers le compte : tout part
    e["importe"] = importe
    _sauver_etat(e)
    try:
        _coffre = _dechiffrer(reponse.get("coffre", ""), cle_coffre)
    except Exception:
        _coffre = {}
    activer_dossiers()
    if nouveau or venait_du_local:
        _pousser_coffre_depuis_appareil()   # la clé API et les secrets déjà sur cet appareil rejoignent le coffre
    if not nouveau:
        _appliquer_coffre()
    if e["prenom"]:
        CONFIG["nom_utilisateur"] = e["prenom"]
    resultat = {"import": None}
    # L'ancienne mémoire de cet appareil (avant les comptes) rejoint UNE seule fois le PREMIER compte connecté ici :
    # un autre utilisateur qui se connecterait ensuite sur cet appareil ne la récupère pas.
    # (Bouton « Envoyer la mémoire de cet appareil » pour le faire volontairement.)
    if not importe:
        try:
            resultat["import"] = importer_appareil()
            e["importe"] = [str(e["id"])]
            _sauver_etat(e)
        except ErreurCompte as x:
            resultat["import"] = {"erreur": str(x)}
    threading.Thread(target=synchroniser, daemon=True).start()   # l'écran n'attend pas la 1re synchro
    demarrer_synchro()
    return resultat


def inscrire(email: str, mot_de_passe: str, prenom: str, politique_acceptee: bool = False) -> dict:
    if not politique_acceptee:
        raise ErreurCompte("Accepte la politique de confidentialité pour créer ton compte.")
    if len(mot_de_passe) < 8:
        raise ErreurCompte("Mot de passe trop court (8 caractères minimum).")
    cle_auth, cle_coffre = _deriver(email, mot_de_passe)
    r = _appel("POST", "/v1/inscription", json={"email": email, "cle_auth": cle_auth, "prenom": prenom,
                                                "appareil": MACHINE, "politique": POLITIQUE})
    return _ouvrir(r, email, cle_coffre, nouveau=True)


def connecter(email: str, mot_de_passe: str) -> dict:
    cle_auth, cle_coffre = _deriver(email, mot_de_passe)
    r = _appel("POST", "/v1/connexion", json={"email": email, "cle_auth": cle_auth, "appareil": MACHINE})
    return _ouvrir(r, email, cle_coffre, nouveau=False)


def deconnecter():
    """Ferme la session sur cet appareil et retire les secrets du compte de cet appareil."""
    global _coffre
    try:
        _appel("POST", "/v1/deconnexion", timeout=5)
    except ErreurCompte:
        pass
    from . import claude, connecteurs
    for nom in _coffre.get("trousseau", {}):
        _definir_secret_local(nom, "")
    if _coffre.get("ANTHROPIC_API_KEY"):
        claude.definir_cle("", synchro=False)
    for nom in ("compte:jeton", "compte:cle_coffre", "github:jeton"):
        _definir_secret_local(nom, "")
    for cid in list(connecteurs.INSTANCES):
        connecteurs.arreter(cid)
    _coffre = {}
    e = etat()
    _sauver_etat({"importe": e.get("importe", [])})   # retour à l'écran de choix (en ligne ou local)
    activer_dossiers()


# ---------- confidentialité : politique, export, suppression du compte ----------
def politique_a_accepter() -> bool:
    """Vrai si le serveur a une politique plus récente que celle acceptée par ce compte."""
    e = etat()
    return connecte() and bool(e.get("politique_actuelle")) and e.get("politique") != e.get("politique_actuelle")


def accepter_politique():
    p = _appel("POST", "/v1/moi/politique")
    e = etat()
    e.update(politique=p.get("politique", ""), politique_actuelle=p.get("politique_actuelle", ""))
    _sauver_etat(e)


def exporter_donnees() -> Path:
    """Écrit toutes les données du compte dans un fichier JSON (Téléchargements) et renvoie son chemin."""
    from datetime import datetime
    donnees = _appel("GET", "/v1/moi/export", timeout=120)
    dossier_dl = Path.home() / "Downloads"
    if not dossier_dl.is_dir():
        dossier_dl = Path.home()
    f = dossier_dl / f"wesley-mes-donnees-{datetime.now():%Y-%m-%d-%H%M}.json"
    f.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    return f


def supprimer_compte(mot_de_passe: str):
    """Supprime définitivement le compte et toutes ses données sur le serveur, puis sur cet appareil."""
    import shutil
    e = etat()
    if not connecte():
        raise ErreurCompte("Aucun compte connecté.")
    cle_auth, _ = _deriver(e.get("email", ""), mot_de_passe)
    try:
        _appel("POST", "/v1/moi/supprimer", json={"cle_auth": cle_auth})
    except ErreurCompte as x:
        if x.statut == 403:
            raise ErreurCompte("Mot de passe incorrect.") from x
        raise
    cache = dossier(e.get("id"))
    deconnecter()   # la session n'existe déjà plus : retire les secrets de cet appareil
    shutil.rmtree(cache, ignore_errors=True)   # copie locale de la mémoire et de l'historique de ce compte


# ---------- coffre ----------
def _cle_coffre() -> bytes:
    b = _secret_local("compte:cle_coffre")
    return base64.b64decode(b) if b else b""


def charger_coffre():
    """Au démarrage : relit le coffre du serveur (secrets ajoutés depuis un autre appareil)."""
    global _coffre
    try:
        _coffre = _dechiffrer(_appel("GET", "/v1/moi")["coffre"], _cle_coffre())
        _appliquer_coffre()
    except Exception:
        pass


def _appliquer_coffre():
    from . import claude
    for nom, valeur in _coffre.get("trousseau", {}).items():
        if _secret_local(nom) != valeur:   # n'écrit que ce qui a changé (chaque écriture peut demander le mot de passe)
            _definir_secret_local(nom, valeur)
    if _coffre.get("ANTHROPIC_API_KEY") and _coffre["ANTHROPIC_API_KEY"] != os.environ.get("ANTHROPIC_API_KEY"):
        claude.definir_cle(_coffre["ANTHROPIC_API_KEY"], synchro=False)
    from .fournisseurs import FOURNISSEURS
    for f in FOURNISSEURS:   # clés des autres IA (OpenAI, Gemini, Mistral…)
        env = f.get("env")
        if env and _coffre.get(env) and _coffre[env] != os.environ.get(env):
            from . import openai_cerveau
            openai_cerveau.definir_cle(_coffre[env], synchro=False, fid=f["id"])


def _pousser_coffre_depuis_appareil():
    """Rassemble les secrets déjà présents sur cet appareil (clé API, connecteurs) dans le coffre."""
    from . import connecteurs
    from .fournisseurs import ENV_CLES
    for nom in ("ANTHROPIC_API_KEY", *ENV_CLES):
        if os.environ.get(nom):
            _coffre[nom] = os.environ[nom]
    trousseau = _coffre.setdefault("trousseau", {})
    for cid, d in connecteurs._lire().items():
        t = connecteurs.TYPES.get(d.get("type"))
        for champ in (t.champs if t else []):
            if champ.get("type") == "secret":
                v = connecteurs.secret(cid, champ["nom"])
                if v:
                    trousseau[f"{cid}:{champ['nom']}"] = v
    if _secret_local("github:jeton"):
        trousseau["github:jeton"] = _secret_local("github:jeton")
    _envoyer_coffre()


def _modifier_coffre(modif):
    """Relit le coffre du serveur, applique la modification, renvoie le tout chiffré (un autre appareil a pu
    ajouter des secrets entre-temps : on fusionne au lieu d'écraser)."""
    global _coffre
    if not connecte():
        return
    with _verrou:
        try:
            serveur_coffre = _dechiffrer(_appel("GET", "/v1/moi")["coffre"], _cle_coffre())
        except ErreurCompte as e:
            print(f"  ! Coffre non synchronisé : {e}")
            return
        except Exception:
            serveur_coffre = {}
        serveur_coffre.setdefault("trousseau", {})
        modif(serveur_coffre)
        _coffre = serveur_coffre
        try:
            _appel("PUT", "/v1/coffre", json={"coffre": _chiffrer(_coffre, _cle_coffre())})
        except ErreurCompte as e:
            print(f"  ! Coffre non synchronisé : {e}")


def _envoyer_coffre():
    local = dict(_coffre)
    _modifier_coffre(lambda c: (c["trousseau"].update(local.get("trousseau", {})),
                                c.update({k: v for k, v in local.items() if k != "trousseau"})))


def secret_modifie(nom: str, valeur: str):
    """Appelé quand un secret du trousseau change sur cet appareil (connecteur, jeton GitHub)."""
    if not connecte():
        return
    def modif(c):
        if valeur:
            c["trousseau"][nom] = valeur
        else:
            c["trousseau"].pop(nom, None)
    threading.Thread(target=_modifier_coffre, args=(modif,), daemon=True).start()


def cle_api_modifiee(cle: str, nom: str = "ANTHROPIC_API_KEY"):
    if not connecte():
        return
    def modif(c):
        if cle:
            c[nom] = cle
        else:
            c.pop(nom, None)
    threading.Thread(target=_modifier_coffre, args=(modif,), daemon=True).start()


# ---------- file d'attente des écritures (hors ligne) ----------
def _fichier_attente() -> Path:
    return dossier() / "attente.json"


def _lire_attente() -> list:
    try:
        return json.loads(_fichier_attente().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _mettre_en_attente(op: dict):
    with _verrou:
        a = _lire_attente()
        a.append(op)
        _fichier_attente().write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    threading.Thread(target=vider_attente, daemon=True).start()


def vider_attente():
    if not connecte():
        return
    with _verrou:
        a = _lire_attente()
        if not a:
            return
        reste = []
        lignes = [op["ligne"] for op in a if op["type"] == "ligne"]
        try:
            for op in a:
                if op["type"] == "fait":
                    _appel("POST", "/v1/faits", json=op["fait"])
                elif op["type"] == "oubli":   # file d'attente laissée par une version précédente
                    _appel("POST", "/v1/faits/oublier", json={"texte": op["texte"]})
                elif op["type"] == "suppression":
                    _appel("POST", "/v1/faits/supprimer", json={"fid": op["fid"], "texte": op["texte"],
                                                              "ts": op["ts"], "appareil": MACHINE})
                elif op["type"] == "doc":
                    try:
                        _appel("PUT", f"/v1/documents/{op['nom']}", json={"contenu": op["contenu"]})
                    except ErreurCompte as e:
                        if e.statut != 404:   # document inconnu d'un serveur plus ancien : ne bloque pas la file
                            raise
            if lignes:
                _appel("POST", "/v1/historique", json={"lignes": lignes})
        except ErreurCompte:
            reste = a   # on réessaiera (les envois sont idempotents : pas de doublon)
        _fichier_attente().write_text(json.dumps(reste, ensure_ascii=False), encoding="utf-8")


# appelés par memoire.py / connecteurs.py / config.py
def fait_ajoute(f: dict):
    """Ajout, modification, utilisation ou restauration d'un souvenir (avec la date de l'action)."""
    if connecte():
        _mettre_en_attente({"type": "fait", "fait": {
            "fait": f["fait"], "categorie": f.get("categorie", "general"), "date": f.get("date", ""),
            "fid": f.get("fid", ""), "ts": f.get("modifie") or time.time(), "appareil": MACHINE,
            "action": f.get("action", "")}})


def fait_supprime(fid: str, texte: str, ts: float):
    if connecte():
        _mettre_en_attente({"type": "suppression", "fid": fid, "texte": texte if not fid else "", "ts": ts})


def journal_memoire() -> list:
    return _appel("GET", "/v1/memoire/journal")


def ligne_ajoutee(jour: str, ligne: str):
    if connecte():
        _mettre_en_attente({"type": "ligne", "ligne": {"jour": jour, "machine": MACHINE, "ligne": ligne}})


def document_modifie(nom: str, contenu):
    if connecte():
        _mettre_en_attente({"type": "doc", "nom": nom, "contenu": contenu})


# ---------- synchronisation descendante ----------
_dernier_coffre = {"blob": None}


def synchroniser() -> dict:
    """Récupère du serveur l'état du compte : souvenirs ajoutés, modifiés ou supprimés sur un autre appareil,
    nouvel historique, réglages, connecteurs, secrets. Renvoie ce qui a changé ici."""
    changements = {"faits": False, "faits_texte": False, "historique": 0, "reglages": False, "connecteurs": False,
                   "coffre": False, "automatisations": False, "afaire": False}
    if not connecte():
        return changements
    from . import memoire
    vider_attente()
    if _lire_attente():
        return changements   # hors ligne : on garde le cache tel quel
    try:
        faits = [{k: x[k] for k in ("fait", "categorie", "date", "fid", "modifie") if k in x}
                 for x in _appel("GET", "/v1/faits")]
        with _verrou:   # une modification faite ici pendant l'appel n'est pas écrasée : on la laisse partir d'abord
            avant = memoire._charger()
            if not _lire_attente() and faits != avant:
                memoire._sauver(faits)   # ajout, suppression ou modification : le serveur fait foi
                changements["faits"] = True
                # le TEXTE a-t-il changé (et pas seulement la date d'utilisation) ? Seulement alors Wesley relit sa mémoire
                changements["faits_texte"] = sorted((x["fait"], x.get("categorie")) for x in faits) != \
                    sorted((x["fait"], x.get("categorie")) for x in avant)
        d = dossier()
        curseur_f = d / "historique.curseur"
        depuis = int(curseur_f.read_text()) if curseur_f.exists() else 0
        nouvelles = _appel("GET", f"/v1/historique?depuis={depuis}", timeout=60)
        par_fichier: dict = {}
        for l in nouvelles:
            par_fichier.setdefault(f"{l['jour']}__{l['machine']}.md", []).append(l["ligne"])
            depuis = max(depuis, l["id"])
        for nom, lignes in par_fichier.items():
            f = memoire.HIST / nom
            deja = set(f.read_text(encoding="utf-8").splitlines()) if f.exists() else set()
            ajout = [l for l in lignes if l not in deja]
            if ajout:
                with open(f, "a", encoding="utf-8") as h:
                    h.write("\n".join(ajout) + "\n")
                changements["historique"] += len(ajout)
        curseur_f.write_text(str(depuis))
        for nom in ("profil", "connecteurs", "automatisations"):
            doc = _appel("GET", f"/v1/documents/{nom}")["contenu"]
            if doc is None:
                continue
            if nom == "automatisations":
                from . import automatisations
                if doc != automatisations.lister():
                    automatisations._ecrire(doc, synchro=False)
                    changements["automatisations"] = True
                continue
            if nom == "profil":
                cles = [k for k in config.CLES_PARTAGEES if k != "nom_utilisateur"]   # le prénom vient du compte
                ancien = {k: CONFIG.get(k) for k in cles}
                config.PROFIL.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
                CONFIG.update({k: v for k, v in doc.items() if k in cles and v})
                changements["reglages"] = ancien != {k: CONFIG.get(k) for k in cles}
            else:
                from . import connecteurs
                if doc != connecteurs._lire():
                    connecteurs._ecrire(doc, synchro=False)
                    changements["connecteurs"] = True
        try:
            doc = _appel("GET", "/v1/documents/afaire")["contenu"]
            from . import afaire
            if doc is not None and doc != afaire.lister():
                afaire._ecrire(doc, synchro=False)
                changements["afaire"] = True
        except ErreurCompte as e:
            if e.statut != 404:
                raise
        moi = _appel("GET", "/v1/moi")
        e = etat()
        nouveau = {"admin": bool(moi.get("admin")), "politique": moi.get("politique", ""),
                   "politique_actuelle": moi.get("politique_actuelle", "")}
        if any(e.get(k) != v for k, v in nouveau.items()):
            e.update(nouveau)
            _sauver_etat(e)
        _surveiller_tickets(bool(moi.get("admin")))
        if moi.get("prenom") and moi["prenom"] != CONFIG.get("nom_utilisateur"):
            CONFIG["nom_utilisateur"] = moi["prenom"]
            changements["reglages"] = True
        if moi.get("coffre") != _dernier_coffre["blob"]:   # clé API / mot de passe changé sur un autre appareil
            if _dernier_coffre["blob"] is not None:
                global _coffre
                try:
                    _coffre = _dechiffrer(moi["coffre"], _cle_coffre())
                    _appliquer_coffre()
                    changements["coffre"] = True
                except Exception:
                    pass
            _dernier_coffre["blob"] = moi.get("coffre")
    except ErreurCompte as e:
        print(f"  ! Synchro du compte : {e}")
    if any(changements.values()):
        for f in ecouteurs:
            try:
                f(changements)
            except Exception as e:
                print(f"  ! Après synchro : {e}")
    return changements


# ---------- tickets (bugs, améliorations, idées) ----------
def est_admin() -> bool:
    return connecte() and bool(etat().get("admin"))


def creer_ticket(genre: str, titre: str, description: str = "") -> dict:
    from .version import VERSION
    from .plateforme import MAC
    if not connecte():
        raise ErreurCompte("Il faut être connecté à un compte Wesley pour envoyer un ticket.")
    return _appel("POST", "/v1/tickets", json={"genre": genre, "titre": titre, "description": description,
                                               "version": VERSION, "plateforme": "mac" if MAC else "windows",
                                               "appareil": MACHINE})


def mes_tickets() -> list:
    return _appel("GET", "/v1/tickets") if connecte() else []


def tous_les_tickets() -> list:
    return _appel("GET", "/v1/admin/tickets")


def traiter_ticket(tid: int, statut: str = "", reponse=None):
    corps = {"statut": statut}
    if reponse is not None:
        corps["reponse"] = reponse
    # POST et non PATCH : le proxy du serveur de comptes ne laisse passer que GET, POST et PUT (sinon 404)
    return _appel("POST", f"/v1/admin/tickets/{int(tid)}", json=corps)


def statistiques(jours: int = 30) -> dict:
    """(Administrateur) Statistiques d'utilisation de l'appli : comptes, activité, appareils, versions."""
    return _appel("GET", "/v1/admin/stats", params={"jours": int(jours)})


def corriger_ticket(tid: int, projet: str = "", outil: str = "claude_code") -> dict:
    """Administrateur : lance une tâche de code qui corrige le ticket, et prévient son auteur que c'est en cours."""
    from . import taches
    from .config import GELE, sauver_config
    t = next((x for x in tous_les_tickets() if x["id"] == int(tid)), None)
    if not t:
        raise ErreurCompte(f"Ticket n°{tid} introuvable.")
    projet = (projet or CONFIG.get("depot_wesley") or ("" if GELE else str(RACINE))).strip()
    if not projet:
        raise ErreurCompte("Indique le dossier du code de Wesley (ex : ~/Desktop/wesley-real) : il sera retenu pour la suite.")
    if projet != CONFIG.get("depot_wesley"):
        CONFIG["depot_wesley"] = projet
        sauver_config(["depot_wesley"])
    genre = {"bug": "un bug", "amelioration": "une amélioration", "idee": "une idée", "question": "une question"}.get(t["genre"], "une demande")
    consigne = (f"Traite ce ticket envoyé par un utilisateur de Wesley ({genre}).\n\nTicket n°{t['id']} : {t['titre']}\n"
                f"{t.get('description') or '(pas de description)'}\n\nInfos : version {t.get('version') or '?'}, {t.get('plateforme') or '?'}.\n\n"
                "Trouve la cause dans le code, corrige-la proprement et vérifie (tests, `cd interface && npx tsc -p .` si "
                "l'interface change). Respecte CLAUDE.md : nouvelle version dans wesley/version.py et section CHANGELOG en "
                "français écrite pour l'utilisateur. Ne publie pas et ne pousse pas : je relirai.")
    tache = taches.creer(consigne, projet, outil, f"Ticket n°{t['id']} : {t['titre']}"[:80], ticket=t["id"])
    try:
        traiter_ticket(t["id"], "en_cours", t.get("reponse") or "Merci ! Un correctif est en préparation.")
    except ErreurCompte:
        pass
    return tache


def supprimer_ticket(tid: int):
    return _appel("POST", f"/v1/admin/tickets/{int(tid)}/supprimer")


def _surveiller_tickets(admin: bool):
    """Notifie les nouveaux tickets (admin) et les réponses / changements de statut (auteur)."""
    from . import notifications
    f = dossier() / "tickets_vus.json"
    try:
        vus = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        vus = None   # premier passage : on mémorise l'état sans tout notifier
    nouveau = dict(vus or {})
    try:
        if admin:
            for t in tous_les_tickets():
                cle = f"a{t['id']}"
                if vus is not None and cle not in vus:
                    notifications.ajouter(f"Nouveau ticket : {t['titre']}", f"{t.get('prenom') or t.get('email')} · {t['genre']}",
                                          genre="info", vue="tickets", systeme=True)
                nouveau[cle] = t["modifie"]
        for t in _appel("GET", "/v1/tickets"):
            cle, etat_t = f"m{t['id']}", f"{t['statut']}|{t['reponse']}"
            if vus is not None and cle in vus and vus[cle] != etat_t:
                notifications.ajouter(f"Ton ticket « {t['titre']} » a été mis à jour",
                                      (t["reponse"] or "") + f" (statut : {t['statut'].replace('_', ' ')})",
                                      genre="info", vue="tickets", systeme=True)
            nouveau[cle] = etat_t
    except ErreurCompte as e:
        if e.statut in (404, 403):
            return   # serveur plus ancien sans tickets
        raise
    if nouveau != vus:
        f.write_text(json.dumps(nouveau), encoding="utf-8")
    if vus is not None and nouveau != vus:
        try:
            from . import web
            web.diffuser(type="tickets_maj")
        except Exception:
            pass


def _session_revoquee():
    """Cet appareil a été déconnecté (depuis un autre appareil) : on retire ses secrets et on revient à la connexion."""
    e = etat()
    try:
        deconnecter()   # retire aussi la clé API et les mots de passe venus du coffre (appareil perdu, prêté…)
    except Exception:
        pass
    _sauver_etat({"mode": "en_ligne", "email": e.get("email", ""), "importe": e.get("importe", [])})
    activer_dossiers()
    try:
        from . import notifications, web
        notifications.ajouter("Appareil déconnecté", "Cet appareil a été déconnecté de ton compte. Reconnecte-toi pour retrouver ta mémoire.",
                              genre="alerte", systeme=True)
        web.diffuser(type="compte_deconnecte")
    except Exception:
        pass


def demarrer_synchro():
    """Temps réel : le serveur répond dès qu'un appareil change quelque chose dans le compte (attente longue).
    Chaque ajout, suppression ou modification arrive sur tous tes appareils en ~1 seconde."""
    global _synchro_lancee
    if _synchro_lancee:
        return
    _synchro_lancee = True

    def boucle():
        from . import appareils
        revision, derniere_presence = 0, 0.0
        while True:
            if not connecte():
                time.sleep(5)
                revision = 0
                continue
            try:
                if time.time() - derniere_presence > 20:   # « je suis en ligne » (onglet Appareils)
                    derniere_presence = time.time()
                    threading.Thread(target=appareils.presence, daemon=True).start()
                vider_attente()   # écritures faites hors ligne : elles repartent dès que le réseau revient
                r = _appel("GET", f"/v1/attendre?depuis={revision}", http=_http_attente, timeout=45)
                if r.get("ordres"):   # un de tes autres appareils demande quelque chose à celui-ci
                    appareils.traiter(r["ordres"])
                if r["change"]:
                    synchroniser()
                revision = r["revision"]
            except SessionRevoquee:
                _session_revoquee()
            except ErreurCompte:
                time.sleep(10)   # pas de réseau ou serveur indisponible : on réessaie
            except Exception as e:
                print(f"  ! Synchro temps réel : {e}")
                time.sleep(10)
    threading.Thread(target=boucle, daemon=True, name="synchro-compte").start()


# ---------- import de la mémoire déjà présente sur cet appareil ----------
def _sources_appareil() -> list[Path]:
    """Tous les endroits où une ancienne version de Wesley a pu ranger sa mémoire sur cet appareil."""
    candidats = [RACINE / "comptes" / "local" / "memoire", RACINE / "memoire", RACINE / "partage" / "memoire"]
    od = config._onedrive()
    if od:
        candidats.append(od / "Wesley" / "memoire")
    if CONFIG.get("dossier_partage"):
        candidats.append(Path(CONFIG["dossier_partage"]) / "memoire")
    cache = dossier().resolve()
    vus, res = set(), []
    for c in candidats:
        try:
            r = c.resolve()
        except OSError:
            continue
        if c.exists() and r not in vus and cache not in r.parents:
            vus.add(r)
            res.append(c)
    return res


def importer_appareil() -> dict:
    """Envoie au compte la mémoire de cet appareil (souvenirs, historique, connecteurs, réglages). Fusion :
    le serveur ignore les doublons, rien n'est écrasé."""
    faits, lignes = [], []
    sources = _sources_appareil()
    for s in sources:
        try:
            for x in json.loads((s / "faits.json").read_text(encoding="utf-8")):
                if x.get("fait"):
                    faits.append({"fait": x["fait"], "categorie": x.get("categorie", "general"), "date": x.get("date", "")})
        except (OSError, ValueError):
            pass
        for f in (s / "historique").glob("*.md") if (s / "historique").exists() else []:
            jour, _, machine = f.stem.partition("__")
            for l in f.read_text(encoding="utf-8").splitlines():
                if l.strip() and len(jour) == 10:
                    lignes.append({"jour": jour, "machine": machine or MACHINE, "ligne": l})
    vues, uniques = set(), []
    for l in lignes:   # la même ancienne mémoire peut être trouvée à deux endroits (dossier local + OneDrive)
        if (l["jour"], l["ligne"]) not in vues:
            vues.add((l["jour"], l["ligne"]))
            uniques.append(l)
    r = _appel("POST", "/v1/import", json={"faits": faits, "lignes": uniques}, timeout=120)
    # connecteurs et réglages communs : seulement si le compte n'en a pas encore
    for s in sources:
        for nom, fichier in (("connecteurs", s.parent / "connecteurs.json"), ("profil", s.parent / "profil.json"),
                             ("automatisations", s.parent / "automatisations.json")):
            try:
                contenu = json.loads(fichier.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if contenu and _appel("GET", f"/v1/documents/{nom}")["contenu"] is None:
                _appel("PUT", f"/v1/documents/{nom}", json={"contenu": contenu})
    return {"faits": r["faits"], "lignes": r["lignes"], "sources": [str(s) for s in sources]}


# ---------- au démarrage de Wesley ----------
def au_demarrage():
    activer_dossiers()
    if connecte():
        threading.Thread(target=lambda: (charger_coffre(), synchroniser()), daemon=True).start()
        demarrer_synchro()
