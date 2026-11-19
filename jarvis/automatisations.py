"""Automatisations : « quand je reçois un mail de mon père, préviens-moi ».

Une règle = un déclencheur + une action, rangée dans ton compte (donc la même sur tous tes appareils) :
- déclencheur « mail » : un nouvel e-mail arrive sur une de tes boîtes (Gmail, IMAP), filtré par expéditeur,
  sujet et/ou mots du texte ;
- action « prévenir » : Jarvis te le dit à voix haute + notification ;
  action « jarvis » : Jarvis exécute une consigne avec le mail en contexte (« résume-le-moi », « réponds que… »).

Le moteur vérifie les boîtes toutes les minutes. Les e-mails déjà présents à la création de la règle ne
déclenchent rien : seuls les nouveaux comptent.
"""
import email
import email.policy
import json
import re
import threading
import time
import traceback
import uuid
from datetime import datetime

from . import config

INTERVALLE = 60   # secondes entre deux vérifications des boîtes mail
_lance = False
_verrou = threading.RLock()


# ---------- stockage (dans le compte, synchronisé entre appareils) ----------
def _fichier():
    return config.PARTAGE / "automatisations.json"


def lister() -> list:
    try:
        return json.loads(_fichier().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _ecrire(regles: list, synchro=True):
    _fichier().write_text(json.dumps(regles, ensure_ascii=False, indent=1), encoding="utf-8")
    if synchro:
        from . import compte
        compte.document_modifie("automatisations", regles)


def creer(nom: str, expediteur="", sujet="", contient="", connecteur="", action="prevenir", consigne="") -> dict:
    regle = {"id": uuid.uuid4().hex[:10], "nom": nom.strip() or "Automatisation", "actif": True,
             "declencheur": {"type": "mail", "expediteur": expediteur.strip(), "sujet": sujet.strip(),
                             "contient": contient.strip(), "connecteur": connecteur.strip()},
             "action": {"type": action if action in ("prevenir", "jarvis") else "prevenir", "consigne": consigne.strip()},
             "cree": datetime.now().isoformat(timespec="seconds")}
    with _verrou:
        _ecrire(lister() + [regle])
    return regle


def modifier(rid: str, **champs) -> bool:
    with _verrou:
        regles = lister()
        r = next((r for r in regles if r["id"] == rid), None)
        if not r:
            return False
        if "actif" in champs:
            r["actif"] = bool(champs["actif"])
        for k in ("nom",):
            if k in champs:
                r[k] = champs[k]
        _ecrire(regles)
        return True


def supprimer(rid: str) -> bool:
    with _verrou:
        regles = lister()
        reste = [r for r in regles if r["id"] != rid]
        _ecrire(reste)
        return len(reste) != len(regles)


def decrire(r: dict) -> str:
    d, a = r["declencheur"], r["action"]
    conditions = [f"de « {d['expediteur']} »" if d.get("expediteur") else "",
                  f"sujet contenant « {d['sujet']} »" if d.get("sujet") else "",
                  f"texte contenant « {d['contient']} »" if d.get("contient") else ""]
    quoi = "Quand un e-mail arrive " + (", ".join(c for c in conditions if c) or "(n'importe lequel)")
    faire = "te prévenir à voix haute" if a["type"] == "prevenir" else f"Jarvis : « {a['consigne']} »"
    return f"{quoi} → {faire}"


# ---------- moteur ----------
def _vus_fichier():
    from . import compte
    return compte.dossier() / "automatisations_vus.json"   # propre à cet appareil


def _boites():
    """Connecteurs e-mail démarrés : {cid: instance}."""
    from . import connecteurs
    return {cid: c for cid, c in list(connecteurs.INSTANCES.items())
            if isinstance(c, connecteurs.Mail) and not c.manquants() and not c.erreur}


def _correspond(r: dict, expediteur: str, sujet: str, texte_fn) -> bool:
    d = r["declencheur"]
    if d.get("expediteur") and d["expediteur"].lower() not in expediteur.lower():
        return False
    if d.get("sujet") and d["sujet"].lower() not in sujet.lower():
        return False
    if d.get("contient") and d["contient"].lower() not in texte_fn().lower():
        return False
    return True


def _declencher(r: dict, boite, expediteur: str, sujet: str, texte: str):
    from . import annonces, web
    nom_exp = re.sub(r"\s*<[^>]+>", "", expediteur).strip().strip('"') or expediteur
    if r["action"]["type"] == "jarvis" and r["action"].get("consigne"):
        consigne = (f"[Automatisation « {r['nom']} »] Nouvel e-mail reçu sur {boite.etiquette()}.\n"
                    f"De : {expediteur}\nSujet : {sujet}\n\n{texte[:3000]}\n\nConsigne : {r['action']['consigne']}")
        annonces.annoncer(f"Nouveau mail de {nom_exp} : {sujet}")
        threading.Thread(target=web.executer, args=(consigne,), daemon=True).start()
    else:
        annonces.annoncer(f"Tu as reçu un mail de {nom_exp}" + (f" : {sujet}" if sujet else "."))


def verifier():
    """Un passage : regarde les nouveaux e-mails de chaque boîte et applique les règles."""
    regles = [r for r in lister() if r.get("actif") and r["declencheur"]["type"] == "mail"]
    if not regles:
        return
    from .connecteurs import _dec, _texte
    try:
        vus = json.loads(_vus_fichier().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        vus = {}
    for cid, boite in _boites().items():
        concernees = [r for r in regles if not r["declencheur"].get("connecteur") or r["declencheur"]["connecteur"] == cid]
        if not concernees:
            continue
        try:
            m = boite._imap()
            try:
                m.select("INBOX", readonly=True)
                uids = [u.decode() for u in boite._chercher(m, "ALL")][-200:]
                deja = vus.get(cid)
                if deja is None:   # 1re fois : les e-mails déjà là ne comptent pas
                    vus[cid] = uids
                    continue
                nouveaux = [u for u in uids if u not in set(deja)]
                for uid in nouveaux:
                    t, d = m.uid("FETCH", uid, "(BODY.PEEK[])")
                    if t != "OK" or not d or not isinstance(d[0], tuple):
                        continue
                    try:   # « default » lit aussi les en-têtes accentués envoyés sans encodage
                        msg = email.message_from_bytes(d[0][1], policy=email.policy.default)
                    except Exception:
                        msg = email.message_from_bytes(d[0][1])
                    exp, suj = _dec(msg["From"]), _dec(msg["Subject"])
                    texte = {}

                    def lire_texte():
                        if "t" not in texte:
                            texte["t"] = _texte(msg)
                        return texte["t"]
                    for r in concernees:
                        if _correspond(r, exp, suj, lire_texte):
                            _declencher(r, boite, exp, suj, lire_texte())
                vus[cid] = uids
            finally:
                m.logout()
        except Exception as e:
            print(f"  ! Automatisations ({cid}) : {e}")
    _vus_fichier().write_text(json.dumps(vus), encoding="utf-8")


def demarrer():
    global _lance
    if _lance:
        return
    _lance = True

    def boucle():
        time.sleep(20)   # laisse les connecteurs démarrer
        while True:
            try:
                verifier()
            except Exception:
                traceback.print_exc()
            time.sleep(INTERVALLE)
    threading.Thread(target=boucle, daemon=True, name="automatisations").start()
