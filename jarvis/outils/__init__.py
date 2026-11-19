"""Registre d'outils : chaque fonction décorée avec @outil devient appelable par le modèle."""
import inspect
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path

OUTILS: dict = {}
from ..config import RACINE
LOG_DIR = RACINE / "logs"
LOG_DIR.mkdir(exist_ok=True)
log = logging.getLogger("jarvis.actions")
_h = logging.FileHandler(LOG_DIR / "actions.log", encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
log.addHandler(_h)
log.setLevel(logging.INFO)

_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


VERSION = 0   # change à chaque ajout/retrait d'outil (les cerveaux recalculent leur liste)


def outil(fn):
    """Décorateur : la fonction devient un outil de Jarvis."""
    return ajouter_fonction(fn, fn.__name__)


def ajouter_fonction(fn, nom, source="jarvis", prefixe_desc=""):
    """Docstring : 1re ligne = description, puis lignes 'param: description'.
    prefixe_desc : précise le compte concerné quand il y en a plusieurs (ex : « [Gmail travail] »)."""
    global VERSION
    doc = inspect.getdoc(fn) or nom
    lignes = doc.splitlines()
    desc = prefixe_desc + lignes[0]
    pdesc = {}
    for l in lignes[1:]:
        if ":" in l:
            k, v = l.split(":", 1)
            pdesc[k.strip()] = v.strip()
    props, requis = {}, []
    for param, p in inspect.signature(fn).parameters.items():
        t = _TYPES.get(p.annotation, "string")
        props[param] = {"type": t, "description": pdesc.get(param, param)}
        if t == "array":
            props[param]["items"] = {"type": "string"}
        if p.default is inspect.Parameter.empty:
            requis.append(param)
    OUTILS[nom] = {
        "fn": fn, "source": source,
        "schema": {"type": "function", "function": {
            "name": nom, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": requis}}},
    }
    VERSION += 1
    return fn


def ajouter_brut(nom, description, parametres, appel, source):
    """Outil défini par un schéma JSON (serveurs MCP) ; appel(dict) -> str."""
    global VERSION
    parametres = dict(parametres or {"type": "object", "properties": {}})
    parametres.setdefault("type", "object")
    parametres.setdefault("properties", {})
    OUTILS[nom] = {"brut": appel, "source": source,
                   "schema": {"type": "function", "function": {
                       "name": nom, "description": (description or nom)[:1000], "parameters": parametres}}}
    VERSION += 1


def retirer_source(source):
    """Retire tous les outils d'un connecteur."""
    global VERSION
    for nom in [n for n, o in OUTILS.items() if o.get("source") == source]:
        del OUTILS[nom]
    VERSION += 1


def schemas():
    return [o["schema"] for o in OUTILS.values()]


ARRET = __import__("threading").Event()   # bouton STOP / « Jarvis, stop » : coupe l'action en cours


def arreter_tout():
    """Arrêt demandé : l'outil en cours est abandonné et les programmes qu'il a lancés sont tués."""
    ARRET.set()


def _tuer_enfants_depuis(t0: float):
    """Tue les programmes lancés par l'outil interrompu (commande, script, AppleScript…), pas les autres."""
    try:
        import psutil
        for p in psutil.Process().children(recursive=True):
            try:
                if p.create_time() >= t0 - 0.5:
                    p.kill()
            except psutil.Error:
                pass
    except Exception:
        pass


def appeler(nom: str, args: dict) -> str:
    """Exécute l'outil dans un fil à part : un STOP l'interrompt aussitôt, sans attendre qu'il ait fini."""
    import threading
    import time
    if ARRET.is_set():
        return "Annulé par l'utilisateur."
    resultat, t0 = {}, time.time()
    fil = threading.Thread(target=lambda: resultat.update(r=_appeler(nom, args)), daemon=True, name=f"outil-{nom}")
    fil.start()
    while fil.is_alive():
        fil.join(0.1)
        if ARRET.is_set():
            _tuer_enfants_depuis(t0)
            log.info("  -> interrompu par l'utilisateur")
            return "Action interrompue par l'utilisateur (STOP). Ne la relance pas."
    return resultat.get("r", "Erreur : l'outil n'a rien renvoyé.")


def _appeler(nom: str, args: dict) -> str:
    if nom not in OUTILS:
        return f"Erreur : outil inconnu '{nom}'."
    args = args or {}
    log.info("%s %s", nom, json.dumps(args, ensure_ascii=False)[:500])
    try:
        if "brut" in OUTILS[nom]:
            res = OUTILS[nom]["brut"](args)
            res = "OK" if res is None else str(res)
            log.info("  -> %s", res[:300].replace("\n", " "))
            return res[:12000] + ("\n[...tronqué]" if len(res) > 12000 else "")
        sig = inspect.signature(OUTILS[nom]["fn"])
        propres = {}
        for k, v in args.items():
            if k not in sig.parameters:
                continue
            ann = sig.parameters[k].annotation
            try:
                if ann is int: v = int(v)
                elif ann is float: v = float(v)
                elif ann is bool and isinstance(v, str): v = v.lower() in ("true", "1", "oui", "yes")
                elif ann is list and isinstance(v, str): v = json.loads(v) if v.startswith("[") else [v]
            except Exception:
                pass
            propres[k] = v
        res = OUTILS[nom]["fn"](**propres)
        res = "OK" if res is None else str(res)
    except Exception as e:
        res = f"Erreur : {e}\n{traceback.format_exc(limit=2)}"
    log.info("  -> %s", res[:300].replace("\n", " "))
    return res[:12000] + ("\n[...tronqué]" if len(res) > 12000 else "")


def charger_tous():
    from . import systeme, fichiers, controle, ecran, web, code, memoire_outils, divers, automatisations_outils, taches_outils, appareils_outils  # noqa: F401
