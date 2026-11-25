"""État du système, autorisations, mises à jour et réglages de l'appli de bureau."""
import asyncio
import shutil
import subprocess
import time

import ollama
import psutil
from fastapi import APIRouter, HTTPException, Request

from .. import web
from ..config import CONFIG, MACHINE, sauver_config, sauver_profil
from ..fournisseurs import est_compatible
from ..plateforme import CACHE_FENETRE, MAC, WIN
from ..web import APPLI, _ia, _nom_modele, _verifier, diffuser

router = APIRouter()


# ---------- état système ----------
def _gpu():
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3,
                             **CACHE_FENETRE).stdout.strip().split("\n")[0]
        nom, util, used, tot, temp = [x.strip() for x in out.split(",")]
        return {"nom": nom, "util": float(util), "vram_used": float(used) / 1024, "vram_total": float(tot) / 1024,
                "temp": float(temp)}
    except Exception:
        return None


@router.get("/api/systeme")
def systeme(req: Request):
    _verifier(req)
    try:
        charges = [{"nom": m.model, "vram": (m.size_vram or 0) / 2**30, "taille": (m.size or 0) / 2**30}
                   for m in ollama.ps().models]
        ollama_ok = True
    except Exception:
        charges, ollama_ok = [], False
    ram = psutil.virtual_memory()
    disque = psutil.disk_usage("C:\\" if WIN else "/")
    return {"cpu": psutil.cpu_percent(interval=None), "ram": ram.percent, "ram_used": ram.used / 2**30,
            "ram_total": ram.total / 2**30, "disque": disque.percent, "disque_libre": disque.free / 2**30,
            "gpu": _gpu(), "ollama": ollama_ok, "charges": charges, "cerveau": CONFIG.get("cerveau", "ollama"),
            "modele": _nom_modele(),
            "cle_claude_manquante": (CONFIG.get("cerveau") == "claude" and not __import__("os").environ.get("ANTHROPIC_API_KEY"))
            or (est_compatible(CONFIG.get("cerveau")) and not _ia().cle_configuree()),
            "occupe": web.verrou_tache.locked(), "uptime": int(time.time() - psutil.boot_time())}




# ---------- autorisations du système (micro, écran, accessibilité, fichiers, applis) ----------
@router.get("/api/autorisations")
def lire_autorisations(req: Request):
    _verifier(req)
    from .. import autorisations
    return autorisations.etat()


@router.post("/api/autorisations/{action}")
async def agir_autorisation(action: str, req: Request):
    _verifier(req)
    from .. import autorisations
    d = await req.json()
    if action == "demander":
        r = await asyncio.to_thread(autorisations.demander, d["id"])
    elif action == "retirer":
        r = await asyncio.to_thread(autorisations.retirer, d["id"])
    elif action == "reglages":
        autorisations.ouvrir_reglages(d["id"])
        r = "reglages"
    elif action == "ignorer":
        autorisations.ignorer(d.get("ids", []))
        r = "ignore"
    else:
        raise HTTPException(404, "Action inconnue.")
    return {"resultat": r, **autorisations.etat()}


# ---------- mises à jour ----------
@router.get("/api/majs")
def lister_majs(req: Request):
    _verifier(req)
    from .. import mises_a_jour
    return mises_a_jour.lister()


@router.post("/api/majs/jeton")
async def jeton_majs(req: Request):
    _verifier(req)
    from .. import mises_a_jour
    mises_a_jour.definir_jeton((await req.json()).get("jeton", ""))
    return mises_a_jour.lister()


@router.post("/api/majs/installer")
async def installer_maj(req: Request):
    _verifier(req)
    from .. import mises_a_jour
    version = (await req.json()).get("version", "")
    if not APPLI["quitter"]:
        raise HTTPException(400, "Les mises à jour s'installent depuis l'application Wesley installée.")
    try:
        mises_a_jour.installer(version, lambda etape, pct, texte: diffuser(type="maj", etape=etape, pct=pct, texte=texte),
                               APPLI["quitter"])
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.get("/api/appli")
def etat_appli(req: Request):
    _verifier(req)
    from .. import demarrage
    return {"appli": APPLI["active"], "plateforme": "mac" if MAC else "windows" if WIN else "linux",
            "demarrage_auto": demarrage.est_actif(), "machine": MACHINE,
            "ecoute_fond": CONFIG.get("ecoute_fond", True),
            "ecoute_active": bool(APPLI["ecoute"] and APPLI["ecoute"].actif),
            "seuil_eveil": CONFIG.get("seuil_eveil", 0.5), "raccourci": CONFIG.get("raccourci"),
            "silence_fin": CONFIG.get("silence_fin", 2.5)}


@router.post("/api/appli")
async def regler_appli(req: Request):
    _verifier(req)
    from .. import demarrage
    d = await req.json()
    if "demarrage_auto" in d:
        demarrage.activer(bool(d["demarrage_auto"]))
    for k in ("ecoute_fond", "seuil_eveil"):
        if k in d:
            CONFIG[k] = d[k]
            sauver_config([k])
    if "silence_fin" in d:   # partagé entre tous tes ordinateurs
        CONFIG["silence_fin"] = max(0.5, min(15.0, float(d["silence_fin"])))
        sauver_config(["silence_fin"])
        sauver_profil()
    if APPLI["ecoute"] and "ecoute_fond" in d:
        APPLI["ecoute"].demarrer() if d["ecoute_fond"] else APPLI["ecoute"].arreter()
    return etat_appli(req)
