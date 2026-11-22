"""Mes appareils : chaque Wesley connecté au même compte se déclare, et peut piloter les autres.

- Présence : toutes les ~25 s chaque appareil dit au serveur qu'il est en ligne (et s'il est occupé).
- Ordres : « sur mon PC, lance Discord » → le Wesley du Mac envoie la demande au Wesley du PC, qui l'exécute avec
  ses propres outils et renvoie le résultat. Fichiers aussi (lire / écrire à distance).
- Sécurité : chaque ordre est chiffré ET authentifié (AES-GCM) avec la clé du coffre, dérivée de ton mot de passe et
  présente seulement sur tes appareils. Le serveur relaie sans pouvoir lire ni fabriquer un ordre. Un ordre trop vieux
  ou déjà vu est rejeté. Chaque appareil choisit : accepter (libre ou avec confirmation) ou refuser les ordres.
- Journal des ordres envoyés et reçus (RACINE/ordres.json).
"""
import base64
import json
import os
import threading
import time
import uuid
from pathlib import Path

from .config import CONFIG, MACHINE, RACINE, sauver_config

JOURNAL = RACINE / "ordres.json"
MAX_FICHIER = 10 * 1024 * 1024   # 10 Mo par fichier transféré
_vus: set = set()
_verrou = threading.Lock()


def _compte():
    from . import compte
    return compte


def _plateforme():
    import sys
    return "mac" if sys.platform == "darwin" else "windows" if sys.platform == "win32" else "linux"


def reglages() -> dict:
    return {"accepte": CONFIG.get("ordres_accepte", True), "mode": CONFIG.get("ordres_mode") or "libre"}


def regler(accepte=None, mode=None):
    if accepte is not None:
        CONFIG["ordres_accepte"] = bool(accepte)
    if mode in ("libre", "confirmation"):
        CONFIG["ordres_mode"] = mode
    sauver_config(["ordres_accepte", "ordres_mode"])
    threading.Thread(target=presence, daemon=True).start()


# ---------- présence / liste / déconnexion ----------
def presence():
    c = _compte()
    if not c.connecte():
        return
    try:
        from . import web
        from .version import VERSION
        r = reglages()
        c._appel("POST", "/v1/appareils/presence", json={
            "nom": MACHINE, "plateforme": _plateforme(), "version": VERSION, "occupe": web.verrou_tache.locked(),
            "accepte": r["accepte"], "mode": r["mode"]}, timeout=10)
    except Exception:
        pass


def lister() -> list:
    return _compte()._appel("GET", "/v1/appareils")


def deconnecter(aid: str) -> dict:
    return _compte()._appel("POST", f"/v1/appareils/{aid}/deconnecter")


def trouver(nom_ou_id: str) -> dict:
    """Retrouve un appareil par son nom (même approximatif : « PC », « mac », « windows ») ou son identifiant."""
    cle = nom_ou_id.strip().lower()
    autres = [a for a in lister() if not a["moi"]]
    for test in (lambda a: a["id"] == cle, lambda a: a["nom"].lower() == cle, lambda a: cle in a["nom"].lower(),
                 lambda a: cle in a["plateforme"].lower() or (cle in ("pc", "windows") and a["plateforme"] == "windows")
                 or (cle in ("mac", "macbook") and a["plateforme"] == "mac")):
        trouves = [a for a in autres if test(a)]
        if len(trouves) == 1:
            return trouves[0]
        if len(trouves) > 1:
            en_ligne = [a for a in trouves if a["en_ligne"]]
            if len(en_ligne) == 1:
                return en_ligne[0]
            raise ValueError("Plusieurs appareils correspondent : " + ", ".join(a["nom"] for a in trouves))
    raise ValueError(f"Aucun autre appareil ne correspond à « {nom_ou_id} ». Appareils : "
                     + (", ".join(a["nom"] for a in autres) or "aucun"))


# ---------- chiffrement ----------
def _chiffrer(d: dict) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    n = os.urandom(12)
    return base64.b64encode(n + AESGCM(_compte()._cle_coffre()).encrypt(n, json.dumps(d).encode(), b"wesley-ordre")).decode()


def _dechiffrer(blob: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    brut = base64.b64decode(blob)
    return json.loads(AESGCM(_compte()._cle_coffre()).decrypt(brut[:12], brut[12:], b"wesley-ordre"))


# ---------- journal ----------
def journal() -> list:
    try:
        return json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _noter(sens: str, appareil: str, quoi: str, resultat: str = "", statut: str = ""):
    with _verrou:
        j = journal() + [{"ts": time.time(), "sens": sens, "appareil": appareil, "quoi": quoi[:1000],
                          "resultat": resultat[:3000], "statut": statut}]
        JOURNAL.write_text(json.dumps(j[-300:], ensure_ascii=False), encoding="utf-8")
    try:
        from . import web
        web.diffuser(type="appareils_maj")
    except Exception:
        pass


# ---------- envoyer un ordre ----------
def envoyer(cible: str, contenu: dict, delai: float = 600) -> dict:
    """Envoie un ordre chiffré à un autre appareil et attend sa réponse (déchiffrée)."""
    c = _compte()
    if not c.connecte():
        raise ValueError("Il faut être connecté à ton compte (pas en mode local) pour piloter tes autres appareils.")
    a = trouver(cible)
    if not a["en_ligne"]:
        raise ValueError(f"{a['nom']} est hors ligne (éteint, ou Wesley n'y tourne pas).")
    if not a["accepte"]:
        raise ValueError(f"{a['nom']} refuse les ordres à distance (réglage dans son onglet Appareils).")
    ordre = {**contenu, "nonce": uuid.uuid4().hex, "ts": time.time(), "de": MACHINE, "vers": a["id"]}
    quoi = contenu.get("texte") or f"{contenu.get('type')} {contenu.get('chemin', '')}".strip()
    oid = c._appel("POST", "/v1/ordres", json={"vers": a["id"], "blob": _chiffrer(ordre)}, timeout=120)["id"]
    debut, recu = time.time(), False
    while time.time() - debut < delai:
        r = c._appel("GET", f"/v1/ordres/{oid}/attendre", timeout=40)
        recu = recu or r.get("recu")
        if r.get("pret"):
            rep = _dechiffrer(r["blob"])
            _noter("envoye", a["nom"], quoi, rep.get("resultat", ""), "ok" if rep.get("ok") else "erreur")
            return {**rep, "appareil": a["nom"]}
        if not recu and time.time() - debut > 60:
            break
    _noter("envoye", a["nom"], quoi, "", "sans réponse")
    raise ValueError(f"{a['nom']} n'a pas répondu" + (" (il travaille peut-être encore)." if recu else " (hors ligne ?)."))


# ---------- recevoir un ordre ----------
def traiter(ordres: list):
    for o in ordres or []:
        threading.Thread(target=_executer, args=(o,), daemon=True, name=f"ordre-{o.get('id')}").start()


def _repondre(oid: str, rep: dict):
    try:
        _compte()._appel("POST", f"/v1/ordres/{oid}/reponse", json={"blob": _chiffrer(rep)}, timeout=120)
    except Exception as e:
        print(f"  ! Réponse à l'ordre {oid} : {e}")


def _executer(o: dict):
    try:
        d = _dechiffrer(o["blob"])
    except Exception:
        print("  ! Ordre rejeté : signature invalide (il ne vient pas d'un de tes appareils).")
        return
    if d.get("nonce") in _vus or abs(time.time() - float(d.get("ts", 0))) > 600:
        print("  ! Ordre rejeté : trop ancien ou déjà reçu.")
        return
    _vus.add(d.get("nonce"))
    de = d.get("de", "?")
    quoi = d.get("texte") or f"{d.get('type')} {d.get('chemin', '')}".strip()
    r = reglages()
    if not r["accepte"]:
        _repondre(o["id"], {"ok": False, "resultat": f"{MACHINE} refuse les ordres à distance."})
        _noter("recu", de, quoi, "refusé (réglage)", "refuse")
        return
    if r["mode"] == "confirmation":
        from . import web
        if not web.demander_confirmation(f"{de} demande d'exécuter sur cet appareil", quoi):
            _repondre(o["id"], {"ok": False, "resultat": "L'utilisateur a refusé sur l'appareil."})
            _noter("recu", de, quoi, "refusé par l'utilisateur", "refuse")
            return
    try:
        resultat, extra = _realiser(d)
        _repondre(o["id"], {"ok": True, "resultat": resultat, **extra})
        _noter("recu", de, quoi, resultat, "ok")
        from . import notifications
        notifications.ajouter(f"Ordre de {de}", f"{quoi}\n→ {resultat[:300]}", genre="info", vue="appareils")
    except Exception as e:
        _repondre(o["id"], {"ok": False, "resultat": f"Erreur sur {MACHINE} : {e}"})
        _noter("recu", de, quoi, str(e), "erreur")


def _mettre_a_jour() -> str:
    """Mise à jour demandée depuis un autre appareil : installe la dernière version puis redémarre."""
    from . import mises_a_jour, web
    from .version import VERSION
    r = mises_a_jour.lister()
    if r.get("erreur"):
        raise RuntimeError(r["erreur"])
    dispo = [m for m in r["majs"] if m["disponible"]]
    if not dispo:
        return f"{MACHINE} est déjà à jour (version {VERSION})."
    if not web.APPLI.get("quitter"):
        raise RuntimeError("Wesley tourne depuis le code source sur cet appareil : mise à jour avec « git pull ».")
    cible = dispo[0]["version"]
    mises_a_jour.installer(cible, lambda *a: None, web.APPLI["quitter"])
    from . import notifications
    notifications.ajouter("Mise à jour à distance", f"Mise à jour vers {cible} demandée depuis un autre appareil.", genre="info")
    return f"Mise à jour de {MACHINE} vers la version {cible} lancée : il redémarre tout seul dans une minute environ."


def _realiser(d: dict) -> tuple[str, dict]:
    t = d.get("type")
    if t == "demande":
        from .agent import Wesley
        j = Wesley()   # instance séparée : ta conversation sur cet appareil n'est pas dérangée
        rep = j.demander(f"[Demande envoyée depuis ton autre appareil « {d.get('de')} » : exécute-la ici, sur "
                         f"{MACHINE}, puis réponds en une ou deux phrases]\n{d.get('texte', '')}")
        return rep.strip() or "C'est fait.", {}
    if t == "lire_fichier":
        p = Path(os.path.expanduser(d["chemin"]))
        if not p.is_file():
            raise FileNotFoundError(f"Fichier introuvable sur {MACHINE} : {p}")
        if p.stat().st_size > MAX_FICHIER:
            raise ValueError(f"Fichier trop gros ({p.stat().st_size >> 20} Mo, maximum 10 Mo).")
        return f"Fichier {p.name} ({p.stat().st_size} octets).", {"nom": p.name, "contenu": base64.b64encode(p.read_bytes()).decode()}
    if t == "ecrire_fichier":
        p = Path(os.path.expanduser(d["chemin"]))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(base64.b64decode(d["contenu"]))
        return f"Fichier enregistré sur {MACHINE} : {p}", {}
    if t == "ping":
        return f"{MACHINE} est là.", {}
    if t == "mettre_a_jour":
        return _mettre_a_jour(), {}
    raise ValueError(f"Type d'ordre inconnu : {t}")
