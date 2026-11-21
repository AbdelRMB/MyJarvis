"""Liste « À faire » : ce que l'utilisateur a prévu de faire (« souviens-toi que je dois appeler le garage »).

Chaque tâche passe par trois étapes : à faire → en cours → fait. La liste est rangée dans le compte (document
« afaire », même mécanisme que les automatisations) : elle est la même sur tous les appareils.
"""
import json
import threading
import uuid
from datetime import datetime

from . import config

STATUTS = ("a_faire", "en_cours", "fait")
LIBELLES = {"a_faire": "à faire", "en_cours": "en cours", "fait": "fait"}
PRIORITES = ("basse", "normale", "haute")
_verrou = threading.RLock()


def _fichier():
    return config.PARTAGE / "afaire.json"


def lister() -> list:
    try:
        return json.loads(_fichier().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _ecrire(liste: list, synchro=True):
    _fichier().write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    if synchro:
        from . import compte
        compte.document_modifie("afaire", liste)
    try:
        from . import web
        web.diffuser(type="afaire_maj")
    except Exception:
        pass


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _date(texte: str) -> str:
    """« 2026-11-21 18:00 » ou « 2026-11-21T18:00 » -> « 2026-11-21T18:00 » ; une date seule reste une date."""
    texte = (texte or "").strip().replace(" ", "T", 1)
    return texte[:16]


def ajouter(titre: str, note: str = "", echeance: str = "", priorite: str = "normale", statut: str = "a_faire",
            rappel: str = "") -> dict:
    t = {"id": uuid.uuid4().hex[:8], "titre": titre.strip(), "note": note.strip(), "echeance": _date(echeance),
         "rappel": _date(rappel),
         "priorite": priorite if priorite in PRIORITES else "normale",
         "statut": statut if statut in STATUTS else "a_faire", "cree": _maintenant(), "modifie": _maintenant(),
         "fait_le": _maintenant() if statut == "fait" else ""}
    with _verrou:
        _ecrire(lister() + [t])
    return t


def trouver(cle: str) -> list:
    """Par identifiant (début) ou par un morceau du titre."""
    cle = cle.strip("[] ").lower()
    liste = lister()
    return [t for t in liste if t["id"].startswith(cle)] or [t for t in liste if cle in t["titre"].lower()]


def modifier(tid: str, **champs) -> dict | None:
    with _verrou:
        liste = lister()
        t = next((t for t in liste if t["id"] == tid), None)
        if not t:
            return None
        for k in ("titre", "note"):
            if champs.get(k) is not None:
                t[k] = str(champs[k]).strip()
        for k in ("echeance", "rappel"):
            if champs.get(k) is not None:
                t[k] = _date(str(champs[k]))
        if champs.get("priorite") in PRIORITES:
            t["priorite"] = champs["priorite"]
        if champs.get("statut") in STATUTS and champs["statut"] != t["statut"]:
            t["statut"] = champs["statut"]
            t["fait_le"] = _maintenant() if t["statut"] == "fait" else ""
        t["modifie"] = _maintenant()
        _ecrire(liste)
        return t


def supprimer(tid: str) -> bool:
    with _verrou:
        liste = lister()
        reste = [t for t in liste if t["id"] != tid]
        if len(reste) == len(liste):
            return False
        _ecrire(reste)
        return True


def vider_faits() -> int:
    with _verrou:
        liste = lister()
        reste = [t for t in liste if t["statut"] != "fait"]
        if len(reste) != len(liste):
            _ecrire(reste)
        return len(liste) - len(reste)


def decrire(t: dict) -> str:
    extra = []
    if t.get("echeance"):
        extra.append(f"pour le {t['echeance'].replace('T', ' à ')}")
    if t.get("rappel"):
        extra.append(f"rappel le {t['rappel'].replace('T', ' à ')}")
    if t.get("priorite") == "haute":
        extra.append("prioritaire")
    if t.get("note"):
        extra.append(t["note"])
    return f"[{t['id']}] ({LIBELLES.get(t['statut'], t['statut'])}) {t['titre']}" + (f" — {', '.join(extra)}" if extra else "")



# ---------- rappels (appelé toutes les 20 s par la boucle des automatisations) ----------
def _vus_fichier():
    return config.PARTAGE / "afaire_rappels.json"


def _moment(texte: str):
    try:
        return datetime.fromisoformat(texte) if texte and "T" in texte else None
    except ValueError:
        return None


def verifier_rappels():
    """Annonce à voix haute : le rappel demandé, « dans une heure » et « c'est l'heure » pour une échéance avec heure,
    et une fois par jour (après 9 h) les tâches en retard. Chaque appareil annonce une seule fois chaque rappel."""
    from datetime import timedelta
    from . import annonces
    try:
        vus = json.loads(_vus_fichier().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        vus = {}
    maintenant = datetime.now()
    a_dire = []
    restant = [t for t in lister() if t["statut"] != "fait"]
    for t in restant:
        moments = []
        r = _moment(t.get("rappel", ""))
        if r:
            moments.append(("rappel", r, f"Rappel : {t['titre']}."))
        e = _moment(t.get("echeance", ""))
        if e and not r:
            reste = int((e - maintenant).total_seconds() // 60)
            quand_avant = "Dans une heure" if reste >= 55 else f"Dans {max(1, reste)} minute{'s' if reste > 1 else ''}"
            if reste > 2:
                moments.append(("avant", e - timedelta(hours=1), f"{quand_avant} : {t['titre']}."))
            moments.append(("heure", e, f"C'est l'heure : {t['titre']}."))
        for genre, quand, phrase in moments:
            cle = f"{t['id']}|{genre}|{quand:%Y-%m-%dT%H:%M}"
            if cle in vus or quand > maintenant:
                continue
            vus[cle] = maintenant.isoformat(timespec="seconds")
            if maintenant - quand < timedelta(hours=12):   # Jarvis était éteint depuis longtemps : on ne radote pas
                a_dire.append(phrase)
    jour = maintenant.strftime("%Y-%m-%d")
    if maintenant.hour >= 9 and vus.get("retard") != jour:
        en_retard = [t for t in restant if t.get("echeance") and t["echeance"][:10] < jour]
        vus["retard"] = jour
        if en_retard:
            noms = ", ".join(t["titre"] for t in en_retard[:3]) + (" …" if len(en_retard) > 3 else "")
            a_dire.append(f"Petit rappel : {len(en_retard)} tâche{'s' if len(en_retard) > 1 else ''} en retard ({noms}).")
    if len(vus) > 2000:
        vus = dict(list(vus.items())[-1000:])
    _vus_fichier().write_text(json.dumps(vus), encoding="utf-8")
    for phrase in a_dire:
        annonces.annoncer(phrase, titre="À faire", vue="afaire")


# ---------- briefing du matin ----------
def resume_du_jour() -> str:
    jour = datetime.now().strftime("%Y-%m-%d")
    restant = [t for t in lister() if t["statut"] != "fait"]
    en_cours = [t for t in restant if t["statut"] == "en_cours"]
    retard = [t for t in restant if t.get("echeance") and t["echeance"][:10] < jour]
    aujourdhui = [t for t in restant if (t.get("echeance") or "")[:10] == jour or (t.get("rappel") or "")[:10] == jour]
    lignes = []
    for titre, liste in (("En retard", retard), ("Pour aujourd'hui", aujourdhui), ("En cours", en_cours)):
        if liste:
            lignes.append(f"{titre} :\n" + "\n".join("  " + decrire(t) for t in liste))
    autres = len(restant) - len({t["id"] for t in retard + aujourdhui + en_cours})
    if autres > 0:
        lignes.append(f"Et {autres} autre(s) tâche(s) à faire sans urgence.")
    return "\n".join(lignes) or "Rien de prévu dans la liste « À faire »."
