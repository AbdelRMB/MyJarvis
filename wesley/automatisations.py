"""Automatisations : « quand je reçois un mail de mon père, préviens-moi ».

Une règle = un déclencheur + une action, rangée dans ton compte (donc la même sur tous tes appareils) :
- déclencheur « mail » : un nouvel e-mail arrive sur une de tes boîtes (Gmail, IMAP), filtré par expéditeur,
  sujet et/ou mots du texte ;
- action « prévenir » : Wesley te le dit à voix haute + notification ;
  action « wesley » : Wesley exécute une consigne avec le mail en contexte (« résume-le-moi », « réponds que… »).

Le moteur vérifie les boîtes toutes les minutes. Les e-mails déjà présents à la création de la règle ne
déclenchent rien : seuls les nouveaux comptent.

Autres déclencheurs (2.8.0) :
- « rendez_vous » : X minutes avant un événement de l'agenda (connecteur Agenda), filtré par mots du titre ;
- « fichier »     : un nouveau fichier arrive dans un dossier (Téléchargements…), filtré par motif (*.pdf) ;
- « tache_finie » : une tâche de code se termine (ici ou sur un autre appareil du compte) ;
- « site »        : un site ou un serveur ne répond plus (vérifié toutes les X minutes) ; prévenu aussi au retour.
- « transcription_finie » (2.9.0) : une transcription de cet appareil se termine, avec son résumé en contexte
  (« envoie-moi le compte rendu sur Telegram », « envoie les actions à l'équipe sur Slack ») ;
Toute règle peut avoir une « condition » en français (« seulement si c'est une facture ») : Wesley la vérifie
avec le contexte (mail, fichier, rendez-vous…) avant d'agir.
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


TYPES = ("mail", "horaire", "intervalle", "demarrage", "commande",   # commande = routine lancée en la disant
         "rendez_vous", "fichier", "tache_finie", "site", "transcription_finie")
IGNORES = (".crdownload", ".part", ".tmp", ".download", ".partial", ".~lock")   # téléchargements en cours
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def creer(nom: str, expediteur="", sujet="", contient="", connecteur="", action="prevenir", consigne="",
          type_declencheur="mail", heure="", jours=None, minutes=0, appareil=None, message="", phrase="",
          avant=0, dossier="", motif="", url="", condition="") -> dict:
    """type_declencheur : mail | horaire (heure HH:MM, jours 0=lundi…6=dimanche, vide = tous) | intervalle (minutes)
    | demarrage (à chaque lancement de Wesley) | rendez_vous (avant minutes avant, mots du titre dans contient)
    | fichier (dossier, motif) | tache_finie | site (url, toutes les minutes)
    | transcription_finie (mots du titre dans contient). appareil : celui qui l'exécute (« » = tous).
    condition : phrase vérifiée par Wesley avant d'agir (facultatif)."""
    from .config import MACHINE
    type_declencheur = type_declencheur if type_declencheur in TYPES else "mail"
    if type_declencheur == "fichier":
        import os
        dossier = os.path.expanduser(dossier.strip() or "~/Downloads")
    regle = {"id": uuid.uuid4().hex[:10], "nom": nom.strip() or "Automatisation", "actif": True,
             "declencheur": {"type": type_declencheur, "expediteur": expediteur.strip(), "sujet": sujet.strip(),
                             "contient": contient.strip(), "connecteur": connecteur.strip(), "heure": heure.strip(),
                             "jours": sorted({int(j) for j in (jours or []) if 0 <= int(j) <= 6}),
                             "minutes": max(1, int(minutes or 0)) if type_declencheur in ("intervalle", "site") else 0,
                             "phrase": (phrase or nom).strip() if type_declencheur == "commande" else "",
                             "avant": max(1, int(avant or 15)) if type_declencheur == "rendez_vous" else 0,
                             "dossier": dossier if type_declencheur == "fichier" else "",
                             "motif": (motif.strip() or "*") if type_declencheur == "fichier" else "",
                             "url": url.strip() if type_declencheur == "site" else "",
                             "condition": condition.strip()},
             "action": {"type": action if action in ("prevenir", "wesley") else "prevenir", "consigne": consigne.strip(),
                        "message": message.strip()},
             # les règles « à heure fixe » ne s'exécutent par défaut que sur l'appareil où elles ont été créées
             # (sinon chaque ordinateur allumé dirait la même chose) ; les règles mail aussi sur tous
             # dossier surveillé, rendez-vous, site : sur CET appareil seulement (sinon chaque ordinateur préviendrait)
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
        quand = "Au démarrage de Wesley"
    elif t == "commande":
        quand = f"Quand tu dis « {d.get('phrase') or r['nom']} »"
    elif t == "rendez_vous":
        quand = f"{d.get('avant') or 15} min avant un rendez-vous" + (f" contenant « {d['contient']} »" if d.get("contient") else "")
    elif t == "fichier":
        quand = f"Quand un fichier {d.get('motif') or '*'} arrive dans {d.get('dossier')}"
    elif t == "tache_finie":
        quand = "Quand une tâche de code se termine" + (f" (« {d['contient']} »)" if d.get("contient") else "")
    elif t == "transcription_finie":
        quand = "Quand une transcription se termine" + (f" (« {d['contient']} »)" if d.get("contient") else "")
    elif t == "site":
        quand = f"Quand {d.get('url')} ne répond plus (vérifié toutes les {d.get('minutes') or 5} min)"
    else:
        conditions = [f"de « {d['expediteur']} »" if d.get("expediteur") else "",
                      f"sujet contenant « {d['sujet']} »" if d.get("sujet") else "",
                      f"texte contenant « {d['contient']} »" if d.get("contient") else ""]
        quand = "Quand un e-mail arrive " + (", ".join(c for c in conditions if c) or "(n'importe lequel)")
    if a["type"] == "wesley":
        faire = f"Wesley : « {a['consigne']} »"
    else:
        faire = f"te dire « {a['message']} »" if a.get("message") else "te prévenir à voix haute"
    ou = "" if t == "commande" else f" (sur {r['appareil']})" if r.get("appareil") else " (sur tous tes appareils)"
    si = f", si {d['condition']}" if d.get("condition") else ""
    return f"{quand}{si} → {faire}{ou}"


def condition_remplie(r: dict, contexte: str, completer=None) -> bool:
    """La condition en français de la règle (« seulement si c'est une facture ») est-elle remplie ? Sans condition :
    oui. En cas de doute ou d'erreur du cerveau : non (mieux vaut ne rien faire que faire à tort)."""
    cond = (r.get("declencheur") or {}).get("condition", "").strip()
    if not cond:
        return True
    if completer is None:
        from .agent import completer
    try:
        rep = completer(f"Une automatisation se déclenche. Contexte :\n{contexte[:4000]}\n\nCondition à vérifier : {cond}\n\n"
                        "La condition est-elle remplie ? Réponds par OUI ou NON, seul.")
    except Exception as e:
        print(f"  ! Condition de « {r.get('nom')} » : {e}")
        return False
    return (rep or "").strip().upper().startswith(("OUI", "YES"))


def _pour_cet_appareil(r) -> bool:
    from .config import MACHINE
    return not r.get("appareil") or r["appareil"] == MACHINE


def _wesley_execute(r: dict, contexte: str = ""):
    """Action « demander à Wesley » : une instance séparée (ta conversation n'est pas dérangée) ; le résultat
    est dit à voix haute et rangé dans les notifications."""
    from . import annonces
    from .agent import Wesley

    def travail():
        try:
            j = Wesley()
            reponse = j.demander(f"[Automatisation « {r['nom']} » déclenchée automatiquement — réponds pour être "
                                 f"lu à voix haute à l'utilisateur]\n{contexte}\n\nConsigne : {r['action']['consigne']}")
            annonces.annoncer(reponse.strip() or "C'est fait.", titre=r["nom"], vue="automatisations", detail=reponse)
        except Exception as e:
            annonces.annoncer(f"L'automatisation « {r['nom']} » a échoué : {e}", titre=r["nom"], vue="automatisations",
                              genre="erreur")
    threading.Thread(target=travail, daemon=True, name=f"automatisation-{r['id']}").start()


def _executer_regle(r: dict, contexte: str = "", resume: str = ""):
    from . import annonces
    if r["declencheur"].get("condition"):   # vérifiée en fond : le moteur ne doit pas attendre le cerveau
        def verifier_puis():
            if condition_remplie(r, contexte or resume or r["nom"]):
                _agir(r, contexte, resume)
        threading.Thread(target=verifier_puis, daemon=True).start()
        return
    _agir(r, contexte, resume)


def _agir(r: dict, contexte: str = "", resume: str = ""):
    from . import annonces
    if r["action"]["type"] == "wesley" and r["action"].get("consigne"):
        _wesley_execute(r, contexte)
    else:
        annonces.annoncer(r["action"].get("message") or resume or r["nom"], titre=r["nom"], vue="automatisations",
                          detail=contexte[:500] if contexte else "")


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
    if r["declencheur"].get("condition"):
        contexte = f"Nouvel e-mail.\nDe : {expediteur}\nSujet : {sujet}\n\n{texte[:3000]}"
        threading.Thread(target=lambda: condition_remplie(r, contexte) and _declencher_mail(r, boite, expediteur, sujet, texte),
                         daemon=True).start()
        return
    _declencher_mail(r, boite, expediteur, sujet, texte)


def _declencher_mail(r: dict, boite, expediteur: str, sujet: str, texte: str):
    from . import annonces
    nom_exp = re.sub(r"\s*<[^>]+>", "", expediteur).strip().strip('"') or expediteur
    if r["action"]["type"] == "wesley" and r["action"].get("consigne"):
        contexte = f"Nouvel e-mail reçu sur {boite.etiquette()}.\nDe : {expediteur}\nSujet : {sujet}\n\n{texte[:3000]}"
        annonces.annoncer(f"New email from {nom_exp}: {sujet}" if _en() else f"Nouveau mail de {nom_exp} : {sujet}",
                          vue="automatisations")
        _wesley_execute(r, contexte)
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
    """Règles à heure fixe et à intervalle (appelée toutes les 20 s), et le bilan du soir (réglage)."""
    maintenant = datetime.now()
    c = config.CONFIG
    if c.get("bilan_soir") and maintenant.strftime("%H:%M") == (c.get("bilan_soir_heure") or "19:00").zfill(5) \
            and _dernieres.get("bilan_soir") != maintenant.strftime("%Y-%m-%d"):
        _dernieres["bilan_soir"] = maintenant.strftime("%Y-%m-%d")
        _wesley_execute({"id": "bilan_soir", "nom": "Bilan du soir", "declencheur": {"type": "horaire"},
                         "action": {"type": "wesley", "consigne": "Fais-moi mon bilan du soir (outil bilan_du_soir)."}})
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


# ---------- rendez-vous, fichiers, tâches finies, sites ----------
_agenda = {"lu": 0.0, "evenements": []}
_rdv_faits: set = set()


def _evenements_proches() -> list[tuple]:
    """(début, titre, lieu) des 24 prochaines heures, tous agendas confondus (relus toutes les 10 min)."""
    from datetime import timedelta
    from . import connecteurs
    if time.time() - _agenda["lu"] < 600:
        return _agenda["evenements"]
    evs = []
    for c in list(connecteurs.INSTANCES.values()):
        if getattr(c, "type", "") == "agenda" and not c.manquants():
            try:
                maintenant = datetime.now()
                for d, avec_heure, titre, lieu in c._evenements(maintenant, maintenant + timedelta(days=1)):
                    if avec_heure:
                        evs.append((d.astimezone().replace(tzinfo=None) if d.tzinfo else d, titre, lieu))
            except Exception as e:
                print(f"  ! Agenda pour les automatisations : {e}")
    _agenda.update(lu=time.time(), evenements=evs)
    return evs


def verifier_rendez_vous(maintenant: datetime | None = None, evenements=None):
    regles = [r for r in lister() if r.get("actif") and r["declencheur"].get("type") == "rendez_vous" and _pour_cet_appareil(r)]
    if not regles:
        return
    maintenant = maintenant or datetime.now()
    for debut, titre, lieu in (evenements if evenements is not None else _evenements_proches()):
        reste = (debut - maintenant).total_seconds() / 60
        for r in regles:
            d = r["declencheur"]
            mots = (d.get("contient") or "").lower()
            cle = (r["id"], debut.isoformat(), titre)
            if 0 <= reste <= (d.get("avant") or 15) and (not mots or mots in titre.lower()) and cle not in _rdv_faits:
                _rdv_faits.add(cle)
                contexte = (f"Rendez-vous « {titre} » à {debut:%H:%M}" + (f", lieu : {lieu}" if lieu else "")
                            + f" (dans {max(0, round(reste))} min).")
                _executer_regle(r, contexte, f"Dans {max(0, round(reste))} minutes : {titre}" + (f" ({lieu})" if lieu else ""))


_fichiers_vus: dict = {}   # id de règle -> {chemin: taille} (taille stable = téléchargement fini)


def verifier_fichiers():
    import fnmatch
    import os
    for r in lister():
        d = r["declencheur"]
        if not r.get("actif") or d.get("type") != "fichier" or not _pour_cet_appareil(r):
            continue
        dossier = os.path.expanduser(d.get("dossier") or "~/Downloads")
        try:
            presents = {e.path: e.stat().st_size for e in os.scandir(dossier)
                        if e.is_file() and not e.name.startswith(".") and not e.name.lower().endswith(IGNORES)
                        and fnmatch.fnmatch(e.name.lower(), (d.get("motif") or "*").lower())}
        except OSError:
            continue
        vus = _fichiers_vus.get(r["id"])
        if vus is None:   # 1er passage : ce qui est déjà là ne compte pas
            _fichiers_vus[r["id"]] = {p: -1 for p in presents}
            continue
        for chemin, taille in presents.items():
            avant = vus.get(chemin)
            if avant == -1:
                continue                      # déjà traité
            if avant is None or avant != taille:
                vus[chemin] = taille          # nouveau ou encore en train d'arriver : on attend une taille stable
                continue
            vus[chemin] = -1
            nom = os.path.basename(chemin)
            _executer_regle(r, f"Nouveau fichier arrivé : {chemin} ({taille // 1024} Ko).", f"Nouveau fichier : {nom}")
        for chemin in [p for p in vus if p not in presents]:
            vus.pop(chemin)


_taches_etat: dict = {}


def verifier_taches():
    regles = [r for r in lister() if r.get("actif") and r["declencheur"].get("type") == "tache_finie" and _pour_cet_appareil(r)]
    if not regles:
        return
    from . import partage, taches
    try:
        liste = [dict(t, appareil="") for t in taches.lister()] + partage.distants("tache")
    except Exception:
        return
    premiere = not _taches_etat
    for t in liste:
        avant = _taches_etat.get(t["id"])
        _taches_etat[t["id"]] = t.get("statut")
        if premiere or avant != "en_cours" or t.get("statut") == "en_cours":
            continue
        for r in regles:
            mots = (r["declencheur"].get("contient") or "").lower()
            if mots and mots not in (t.get("titre") or "").lower():
                continue
            etat = {"terminee": "terminée", "echec": "en échec", "arretee": "arrêtée", "interrompue": "interrompue"}.get(t.get("statut"), t.get("statut"))
            ou = f" sur {t['appareil']}" if t.get("appareil") else ""
            _executer_regle(r, f"La tâche de code « {t.get('titre')} »{ou} est {etat}. Bilan : {t.get('bilan') or '—'}",
                            f"Tâche {etat}{ou} : {t.get('titre')}")


def transcription_finie(tid: str):
    """Une transcription de CET appareil vient de se terminer (et d'être résumée si le résumé automatique est
    actif) : les règles « transcription_finie » reçoivent le titre, la durée et le résumé en contexte."""
    regles = [r for r in lister() if r.get("actif") and r["declencheur"].get("type") == "transcription_finie"
              and _pour_cet_appareil(r)]
    if not regles:
        return
    from . import resume_transcription, transcription
    s = transcription.lire(tid)
    if not s or s.get("etat") != "terminee":
        return
    titre = s.get("titre") or "Transcription"
    minutes = round((s.get("duree") or 0) / 60)
    resume = resume_transcription.en_markdown(s.get("resume") or {})
    contexte = (f"La transcription « {titre} » ({minutes} min, {len(transcription.locuteurs(s))} personne(s), "
                f"identifiant {tid}) est terminée.\n\n"
                + (resume or "Pas de résumé : lis-la avec lire_transcription si tu en as besoin."))
    for r in regles:
        mots = (r["declencheur"].get("contient") or "").lower()
        if mots and mots not in titre.lower():
            continue
        _executer_regle(r, contexte[:8000], f"Transcription terminée : {titre}")


_sites: dict = {}   # id -> {"dernier": ts, "ok": bool | None}


def site_repond(url: str) -> tuple[bool, str]:
    import requests
    try:
        r = requests.get(url, timeout=15, allow_redirects=True, headers={"User-Agent": "Wesley (surveillance)"})
        return r.status_code < 500, f"HTTP {r.status_code}"
    except Exception as e:
        return False, type(e).__name__


def verifier_sites(verif=site_repond):
    from . import annonces
    for r in lister():
        d = r["declencheur"]
        if not r.get("actif") or d.get("type") != "site" or not d.get("url") or not _pour_cet_appareil(r):
            continue
        e = _sites.setdefault(r["id"], {"dernier": 0.0, "ok": None})
        if time.time() - e["dernier"] < max(1, int(d.get("minutes") or 5)) * 60:
            continue
        e["dernier"] = time.time()
        ok, detail = verif(d["url"])
        if not ok and e["ok"] is not False:
            _executer_regle(r, f"Le site {d['url']} ne répond plus ({detail}).", f"{d['url']} ne répond plus ({detail})")
        elif ok and e["ok"] is False:
            annonces.annoncer(f"{d['url']} répond de nouveau.", titre=r["nom"], vue="automatisations")
        e["ok"] = ok


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
                for f in (verifier_fichiers, verifier_rendez_vous, verifier_taches, verifier_sites):
                    try:
                        f()
                    except Exception:
                        traceback.print_exc()
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
