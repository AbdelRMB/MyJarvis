"""Santé de Wesley : ce qui marche et ce qui échoue, pour savoir quoi améliorer en priorité.

Compté sur cet appareil (RACINE/logs/sante.json, 30 derniers jours, rien n'est envoyé) :
- chaque outil : appels, échecs, durée, dernière erreur ;
- chaque cerveau (Claude, OpenAI, Ollama…) : demandes, échecs, temps de réponse.
L'écran Système montre les outils qui échouent le plus ; un ticket peut joindre ce résumé (avec l'accord de
l'utilisateur, comme le reste du diagnostic).
"""
import json
import re
import threading
import time
from datetime import date, timedelta

from .config import RACINE

FICHIER = RACINE / "logs" / "sante.json"
JOURS = 30
_verrou = threading.Lock()
_cache: dict = {}
_dernier_ecrit = [0.0]
_RX_ECHEC = re.compile(r"^(erreur|error|impossible|échec|echec|traceback)|introuvable\b|\bfailed\b", re.I)


def _charger() -> dict:
    if not _cache:
        try:
            _cache.update(json.loads(FICHIER.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return _cache


def _ecrire(forcer=False):
    if not forcer and time.time() - _dernier_ecrit[0] < 30:
        return   # pas une écriture disque par outil : toutes les 30 s au plus
    _dernier_ecrit[0] = time.time()
    limite = (date.today() - timedelta(days=JOURS)).isoformat()
    for jour in [j for j in _cache if j < limite]:
        _cache.pop(jour)
    try:
        FICHIER.parent.mkdir(parents=True, exist_ok=True)
        FICHIER.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def echec(resultat: str) -> bool:
    return bool(_RX_ECHEC.search(str(resultat or "")[:300]))


def _compter(genre: str, nom: str, duree: float, rate: bool, erreur: str = ""):
    with _verrou:
        jour = _charger().setdefault(date.today().isoformat(), {})
        x = jour.setdefault(genre, {}).setdefault(nom, {"n": 0, "echecs": 0, "duree": 0.0, "erreur": ""})
        x["n"] += 1
        x["duree"] += duree
        if rate:
            x["echecs"] += 1
            x["erreur"] = erreur[:300]
        _ecrire()


def outil(nom: str, duree: float, resultat: str):
    try:
        _compter("outils", nom, duree, echec(resultat), str(resultat or "")[:300])
    except Exception:
        pass


def demande(cerveau: str, duree: float, erreur: str = ""):
    try:
        _compter("cerveaux", cerveau or "?", duree, bool(erreur), erreur)
    except Exception:
        pass


def resume(jours: int = 7) -> dict:
    """Totaux sur les `jours` derniers jours : outils triés par nombre d'échecs, cerveaux."""
    limite = (date.today() - timedelta(days=jours - 1)).isoformat()
    tot: dict = {"outils": {}, "cerveaux": {}}
    with _verrou:
        for jour, d in _charger().items():
            if jour < limite:
                continue
            for genre in tot:
                for nom, x in d.get(genre, {}).items():
                    t = tot[genre].setdefault(nom, {"n": 0, "echecs": 0, "duree": 0.0, "erreur": ""})
                    t["n"] += x["n"]
                    t["echecs"] += x["echecs"]
                    t["duree"] += x["duree"]
                    if x.get("erreur") and (jour >= t.get("jour_erreur", "")):
                        t["erreur"], t["jour_erreur"] = x["erreur"], jour

    def liste(genre):
        return sorted(({"nom": n, "n": x["n"], "echecs": x["echecs"], "taux": round(x["echecs"] / x["n"], 3) if x["n"] else 0,
                        "duree": round(x["duree"] / x["n"], 2) if x["n"] else 0, "erreur": x["erreur"]}
                       for n, x in tot[genre].items()), key=lambda x: (-x["echecs"], -x["n"]))
    o = liste("outils")
    return {"jours": jours, "outils": o, "cerveaux": liste("cerveaux"),
            "appels": sum(x["n"] for x in o), "echecs": sum(x["echecs"] for x in o)}


def texte(jours: int = 7) -> str:
    """Résumé lisible (pour un ticket ou pour l'utilisateur)."""
    r = resume(jours)
    lignes = [f"Santé de Wesley ({jours} jours) : {r['appels']} actions, {r['echecs']} en échec."]
    for c in r["cerveaux"]:
        lignes.append(f"- cerveau {c['nom']} : {c['n']} demandes, {c['echecs']} échecs, {c['duree']} s en moyenne")
    for x in [x for x in r["outils"] if x["echecs"]][:10]:
        lignes.append(f"- {x['nom']} : {x['echecs']}/{x['n']} échecs — {x['erreur'][:150]}")
    return "\n".join(lignes)


def enregistrer_maintenant():
    with _verrou:
        _ecrire(forcer=True)
