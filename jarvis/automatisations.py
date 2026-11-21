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


TYPES = ("mail", "horaire", "intervalle", "demarrage", "commande")   # commande = routine lancée en la disant
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def creer(nom: str, expediteur="", sujet="", contient="", connecteur="", action="prevenir", consigne="",
          type_declencheur="mail", heure="", jours=None, minutes=0, appareil=None, message="", phrase="") -> dict:
    """type_declencheur : mail | horaire (heure HH:MM, jours 0=lundi…6=dimanche, vide = tous) | intervalle (minutes)
    | demarrage (à chaque lancement de Jarvis). appareil : nom de l'appareil qui l'exécute (« » = tous)."""
    from .config import MACHINE
    type_declencheur = type_declencheur if type_declencheur in TYPES else "mail"
    regle = {"id": uuid.uuid4().hex[:10], "nom": nom.strip() or "Automatisation", "actif": True,
             "declencheur": {"type": type_declencheur, "expediteur": expediteur.strip(), "sujet": sujet.strip(),
                             "contient": contient.strip(), "connecteur": connecteur.strip(), "heure": heure.strip(),
                             "jours": sorted({int(j) for j in (jours or []) if 0 <= int(j) <= 6}),
                             "minutes": max(1, int(minutes or 0)) if type_declencheur == "intervalle" else 0,
                             "phrase": (phrase or nom).strip() if type_declencheur == "commande" else ""},
             "action": {"type": action if action in ("prevenir", "jarvis") else "prevenir", "consigne": consigne.strip(),
                        "message": message.strip()},
             # les règles « à heure fixe » ne s'exécutent par défaut que sur l'appareil où elles ont été créées
             # (sinon chaque ordinateur allumé dirait la même chose) ; les règles mail aussi sur tous
             "appareil": (MACHINE if type_declencheur not in ("mail", "commande") else "") if appareil is None else appareil,
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


def trouver_routine(nom: str) -> dict | None:
    cle = nom.strip().strip("«»\"' ").lower()
    routines = [r for r in lister() if r.get("actif") and r["declencheur"].get("type") == "commande"]
    for r in routines:
        if cle in ((r["declencheur"].get("phrase") or "").lower(), r["nom"].lower(), r["id"]):
            return r
    return next((r for r in routines if cle and (cle in (r["declencheur"].get("phrase") or "").lower() or cle in r["nom"].lower())), None)


def consigne_routine(r: dict) -> str:
    return (f"[Routine « {r['declencheur'].get('phrase') or r['nom']} »] Fais maintenant, dans l'ordre et avec tes outils, ce qui "
            f"suit, puis résume en une phrase :\n{r['action'].get('consigne') or r['action'].get('message') or r['nom']}")


def supprimer(rid: str) -> bool:
    with _verrou:
        regles = lister()
        reste = [r for r in regles if r["id"] != rid]
        _ecrire(reste)
        return len(reste) != len(regles)


def decrire(r: dict) -> str:
    d, a = r["declencheur"], r["action"]
    t = d.get("type", "mail")
    if t == "horaire":
        jours = d.get("jours") or []
        quand = ("Tous les jours" if not jours or len(jours) == 7 else "Le " + ", ".join(JOURS[j] for j in jours)) + f" à {d.get('heure') or '?'}"
    elif t == "intervalle":
        quand = f"Toutes les {d.get('minutes')} min"
    elif t == "demarrage":
        quand = "Au démarrage de Jarvis"
    elif t == "commande":
        quand = f"Quand tu dis « {d.get('phrase') or r['nom']} »"
    else:
        conditions = [f"de « {d['expediteur']} »" if d.get("expediteur") else "",
                      f"sujet contenant « {d['sujet']} »" if d.get("sujet") else "",
                      f"texte contenant « {d['contient']} »" if d.get("contient") else ""]
        quand = "Quand un e-mail arrive " + (", ".join(c for c in conditions if c) or "(n'importe lequel)")
    if a["type"] == "jarvis":
        faire = f"Jarvis : « {a['consigne']} »"
    else:
        faire = f"te dire « {a['message']} »" if a.get("message") else "te prévenir à voix haute"
    ou = "" if t == "commande" else f" (sur {r['appareil']})" if r.get("appareil") else " (sur tous tes appareils)"
    return f"{quand} → {faire}{ou}"


def _pour_cet_appareil(r) -> bool:
    from .config import MACHINE
    return not r.get("appareil") or r["appareil"] == MACHINE


def _jarvis_execute(r: dict, contexte: str = ""):
    """Action « demander à Jarvis » : une instance séparée (ta conversation n'est pas dérangée) ; le résultat
    est dit à voix haute et rangé dans les notifications."""
    from . import annonces
    from .agent import Jarvis

    def travail():
        try:
            j = Jarvis()
            reponse = j.demander(f"[Automatisation « {r['nom']} » déclenchée automatiquement — réponds pour être "
                                 f"lu à voix haute à l'utilisateur]\n{contexte}\n\nConsigne : {r['action']['consigne']}")
            annonces.annoncer(reponse.strip() or "C'est fait.", titre=r["nom"], vue="automatisations", detail=reponse)
        except Exception as e:
            annonces.annoncer(f"L'automatisation « {r['nom']} » a échoué : {e}", titre=r["nom"], vue="automatisations",
                              genre="erreur")
    threading.Thread(target=travail, daemon=True, name=f"automatisation-{r['id']}").start()


def _executer_regle(r: dict, contexte: str = "", resume: str = ""):
    from . import annonces
    if r["action"]["type"] == "jarvis" and r["action"].get("consigne"):
        _jarvis_execute(r, contexte)
    else:
        annonces.annoncer(r["action"].get("message") or resume or r["nom"], titre=r["nom"], vue="automatisations")


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


def _en() -> bool:
    return config.CONFIG.get("langue") == "en"


def _declencher(r: dict, boite, expediteur: str, sujet: str, texte: str):
    from . import annonces, web
    nom_exp = re.sub(r"\s*<[^>]+>", "", expediteur).strip().strip('"') or expediteur
    if r["action"]["type"] == "jarvis" and r["action"].get("consigne"):
        contexte = f"Nouvel e-mail reçu sur {boite.etiquette()}.\nDe : {expediteur}\nSujet : {sujet}\n\n{texte[:3000]}"
        annonces.annoncer(f"New email from {nom_exp}: {sujet}" if _en() else f"Nouveau mail de {nom_exp} : {sujet}",
                          vue="automatisations")
        _jarvis_execute(r, contexte)
    elif r["action"].get("message"):
        annonces.annoncer(r["action"]["message"], titre=r["nom"], vue="automatisations", detail=f"{nom_exp} : {sujet}")
    else:
        if _en():
            annonces.annoncer(f"You've got an email from {nom_exp}" + (f": {sujet}" if sujet else "."))
        else:
            annonces.annoncer(f"Tu as reçu un mail de {nom_exp}" + (f" : {sujet}" if sujet else "."))


def verifier():
    """Un passage : regarde les nouveaux e-mails de chaque boîte et applique les règles."""
    regles = [r for r in lister() if r.get("actif") and r["declencheur"]["type"] == "mail" and _pour_cet_appareil(r)]
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


_dernieres: dict = {}   # id -> dernière exécution (heure fixe : date du jour ; intervalle : horodatage)


def verifier_temps():
    """Règles à heure fixe et à intervalle (appelée toutes les 20 s)."""
    maintenant = datetime.now()
    for r in lister():
        d = r["declencheur"]
        if not r.get("actif") or not _pour_cet_appareil(r):
            continue
        if d.get("type") == "horaire" and d.get("heure"):
            jours = d.get("jours") or []
            cle = maintenant.strftime("%Y-%m-%d")
            if maintenant.strftime("%H:%M") == d["heure"].zfill(5) and (not jours or maintenant.weekday() in jours) \
                    and _dernieres.get(r["id"]) != cle:
                _dernieres[r["id"]] = cle
                _executer_regle(r)
        elif d.get("type") == "intervalle" and d.get("minutes"):
            derniere = _dernieres.get(r["id"])
            if derniere is None:
                _dernieres[r["id"]] = time.time()   # 1re exécution après un intervalle complet
            elif time.time() - derniere >= d["minutes"] * 60:
                _dernieres[r["id"]] = time.time()
                _executer_regle(r)


def demarrer():
    global _lance
    if _lance:
        return
    _lance = True

    def boucle():
        time.sleep(20)   # laisse les connecteurs démarrer
        for r in lister():   # règles « au démarrage »
            if r.get("actif") and r["declencheur"].get("type") == "demarrage" and _pour_cet_appareil(r):
                _executer_regle(r)
        dernier_mail = 0.0
        while True:
            try:
                verifier_temps()
                try:
                    from . import afaire
                    afaire.verifier_rappels()
                except Exception:
                    traceback.print_exc()
                if time.time() - dernier_mail >= INTERVALLE:
                    dernier_mail = time.time()
                    verifier()
            except Exception:
                traceback.print_exc()
            time.sleep(20)
    threading.Thread(target=boucle, daemon=True, name="automatisations").start()
