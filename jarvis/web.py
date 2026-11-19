"""Serveur de l'interface web de Jarvis (FastAPI, 127.0.0.1 uniquement).

Lancer : jarvis-web.bat  (ou .venv\\Scripts\\python.exe -m jarvis.web)
Le front (React) est dans /interface ; `npm run build` le compile dans jarvis/static.
"""
import asyncio
import os
import inspect
import json
import re
import secrets
import shutil
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import numpy as np
import ollama
import psutil
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import connecteurs, memoire, outils, tts
from .modeles import charger_whisper
from .plateforme import CACHE_FENETRE, MAC, WIN
from .agent import Jarvis
from .config import CONFIG, MACHINE, PARTAGE, RACINE, sauver_config, sauver_profil

HOTE, PORT = "127.0.0.1", int(os.environ.get("JARVIS_PORT", 7777))
STATIC = Path(__file__).parent / "static"
JETON = secrets.token_urlsafe(24)
HOTES_OK = {"127.0.0.1", "localhost"}
CLES_CONFIG = ["modele", "modele_vision", "temperature", "reflexion", "num_ctx",
               "max_etapes_outils", "whisper_modele", "nom_utilisateur",
               "cerveau", "claude_modele", "claude_effort", "openai_modele", "langue"]

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
jarvis: Jarvis | None = None
verrou_tache = threading.Lock()
_whisper, _whisper_nom, _whisper_verrou = None, None, threading.Lock()
_clients: set = set()          # files d'attente des onglets connectés
_boucle: asyncio.AbstractEventLoop | None = None
_seq = 0


# ---------- sécurité ----------
def _hote(valeur: str | None) -> str:
    v = (valeur or "").split("://")[-1].split("/")[0]
    return v.rsplit(":", 1)[0] if ":" in v else v


@app.middleware("http")
async def garde_hote(req: Request, suite):
    # bloque le DNS rebinding : seul un Host local est accepté
    if _hote(req.headers.get("host")) not in HOTES_OK:
        return JSONResponse({"detail": "Hôte refusé"}, 403)
    return await suite(req)


def _verifier(req: Request):
    if req.headers.get("x-jeton") != JETON:
        raise HTTPException(403, "Jeton invalide")


@app.get("/api/session")
def session():
    """Sans en-tête CORS : seule une page servie en local peut lire ce jeton."""
    return {"jeton": JETON, "nom": CONFIG["nom_utilisateur"], "nb_outils": len(outils.OUTILS),
            "plateforme": "mac" if MAC else "windows" if WIN else "linux"}


# ---------- diffusion vers tous les onglets ----------
def diffuser(**m):
    if _boucle:
        for q in list(_clients):
            _boucle.call_soon_threadsafe(q.put_nowait, m)


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


@app.get("/api/systeme")
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
            "modele": {"claude": CONFIG["claude_modele"], "openai": CONFIG.get("openai_modele") or "OpenAI"}.get(
                CONFIG.get("cerveau"), CONFIG["modele"]),
            "cle_claude_manquante": (CONFIG.get("cerveau") == "claude" and not __import__("os").environ.get("ANTHROPIC_API_KEY"))
            or (CONFIG.get("cerveau") == "openai" and not __import__("os").environ.get("OPENAI_API_KEY")),
            "occupe": verrou_tache.locked(), "uptime": int(time.time() - psutil.boot_time())}


# ---------- config ----------
@app.get("/api/config")
def lire_config(req: Request):
    _verifier(req)
    try:
        modeles = sorted(m.model for m in ollama.list().models)
    except Exception:
        modeles = [CONFIG["modele"]]
    return {"config": {k: CONFIG[k] for k in CLES_CONFIG}, "modeles": modeles}


@app.post("/api/config")
async def ecrire_config(req: Request):
    _verifier(req)
    data = await req.json()
    ancien_cerveau = CONFIG.get("cerveau")
    for k in CLES_CONFIG:
        if k in data:
            CONFIG[k] = data[k]
    if CONFIG.get("cerveau") != ancien_cerveau:
        # les deux cerveaux n'ont pas le même format d'historique : nouvelle conversation
        jarvis.arreter = True
        jarvis.reset()
        diffuser(type="reset")
        diffuser(type="info", texte="Cerveau : " + ("OpenAI " + (CONFIG.get("openai_modele") or "") if CONFIG["cerveau"] == "openai" else "Claude " + CONFIG["claude_modele"] if CONFIG["cerveau"] == "claude"
                                                     else "Ollama local " + CONFIG["modele"]))
        if CONFIG["cerveau"] in ("claude", "openai"):
            threading.Thread(target=Jarvis.liberer, daemon=True).start()   # rend la VRAM
        else:
            threading.Thread(target=jarvis.prechauffer, daemon=True).start()
    sauver_config(CLES_CONFIG)
    sauver_profil()   # prénom et cerveau : communs à tous les PC
    return {"ok": True}


# ---------- mémoire ----------
@app.get("/api/memoire")
def lire_memoire(req: Request):
    _verifier(req)
    return memoire._charger()


@app.post("/api/memoire")
async def ajouter_fait(req: Request):
    _verifier(req)
    d = await req.json()
    if not str(d.get("fait", "")).strip():
        raise HTTPException(400, "Fait vide")
    return {"message": memoire.ajouter(d["fait"].strip(), d.get("categorie") or "general")}


@app.delete("/api/memoire")
async def supprimer_fait(req: Request):
    """Bouton « Oublier » : supprimé partout (sauf si un autre appareil l'utilise après)."""
    _verifier(req)
    d = await req.json()
    return {"supprimes": memoire.supprimer_un(d.get("fid", ""), d.get("fait", ""))}


@app.put("/api/memoire")
async def modifier_fait(req: Request):
    _verifier(req)
    d = await req.json()
    if not str(d.get("fait", "")).strip():
        raise HTTPException(400, "Fait vide")
    if not memoire.modifier(d.get("fid", ""), d["fait"], d.get("categorie")):
        raise HTTPException(404, "Souvenir introuvable (actualise la mémoire).")
    return {"ok": True}


@app.get("/api/memoire/journal")
async def journal_memoire(req: Request):
    """Historique de ta mémoire gardé par le serveur : qui a ajouté, modifié, utilisé ou supprimé quoi, et quand."""
    _verifier(req)
    from . import compte
    try:
        return await asyncio.to_thread(compte.journal_memoire)
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))


@app.post("/api/memoire/restaurer")
async def restaurer_fait(req: Request):
    _verifier(req)
    d = await req.json()
    memoire.restaurer(d["fid"], d["fait"], d.get("categorie") or "general")
    return {"ok": True}


@app.post("/api/memoriser_session")
def memoriser_session(req: Request):
    _verifier(req)
    if not verrou_tache.acquire(blocking=False):
        raise HTTPException(409, "Jarvis est occupé")
    try:
        return {"faits": jarvis.extraire_souvenirs()}
    finally:
        verrou_tache.release()


# ---------- historique ----------
RX_LIGNE = re.compile(r"^\[(\d\d:\d\d)\] ([^:]+): ?(.*)$")


@app.get("/api/historique")
def jours(req: Request):
    _verifier(req)
    out = []
    jours = memoire.fichiers_par_jour()
    for j in sorted(jours, reverse=True):
        lignes = [l for _, _, l in memoire.lignes_du_jour(jours[j])]
        premier = next((RX_LIGNE.match(l).group(3) for l in lignes if RX_LIGNE.match(l)), "")
        out.append({"jour": j, "nb": sum(1 for l in lignes if RX_LIGNE.match(l)), "apercu": premier[:120],
                    "pcs": sorted({f.stem.split("__")[1] for f in jours[j] if "__" in f.stem})})
    return out


@app.get("/api/historique/{jour}")
def jour(jour: str, req: Request):
    _verifier(req)
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", jour):
        raise HTTPException(400)
    fichiers = memoire.fichiers_par_jour().get(jour)
    if not fichiers:
        raise HTTPException(404)
    entrees = []
    for f in fichiers:   # chaque PC séparément : les lignes de suite restent attachées à leur message
        pc = f.stem.split("__")[1] if "__" in f.stem else ""
        for l in f.read_text(encoding="utf-8").splitlines():
            m = RX_LIGNE.match(l)
            if m:
                entrees.append({"heure": m.group(1), "role": "jarvis" if m.group(2).lower() == "jarvis" else "user",
                                "texte": m.group(3), "pc": pc})
            elif entrees:
                entrees[-1]["texte"] += "\n" + l
    return sorted(entrees, key=lambda e: e["heure"])


# ---------- journal des actions & outils ----------
RX_ACTION = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (\w+) (.*)$")
RX_RES = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+\s+-> (.*)$")


@app.get("/api/actions")
def actions(req: Request, n: int = 200):
    _verifier(req)
    f = RACINE / "logs" / "actions.log"
    if not f.exists():
        return []
    with open(f, "rb") as fh:
        fh.seek(0, 2)
        fh.seek(max(0, fh.tell() - 400_000))
        lignes = fh.read().decode("utf-8", "replace").splitlines()
    out = []
    for l in lignes:
        if m := RX_RES.match(l):
            if out:
                out[-1]["resultat"] = m.group(1)
        elif m := RX_ACTION.match(l):
            try:
                args = json.loads(m.group(3))
            except Exception:
                args = {"brut": m.group(3)}
            out.append({"date": m.group(1), "outil": m.group(2), "args": args, "resultat": None})
    return out[-n:][::-1]


@app.get("/api/outils")
def liste_outils(req: Request):
    _verifier(req)
    out = []
    for nom, o in OUTILS_TRIES():
        f = o["schema"]["function"]
        out.append({"nom": nom, "description": f["description"], "module": o["fn"].__module__.rsplit(".", 1)[-1],
                    "params": [{"nom": k, "type": v["type"], "description": v["description"],
                                "requis": k in f["parameters"]["required"]} for k, v in f["parameters"]["properties"].items()],
                    "doc": inspect.getdoc(o["fn"]) or ""})
    return out


def OUTILS_TRIES():
    return sorted(outils.OUTILS.items(), key=lambda kv: (kv[1]["fn"].__module__, kv[0]))


# ---------- reconnaissance vocale ----------
def _modele_whisper():
    global _whisper, _whisper_nom
    if _whisper is None or _whisper_nom != CONFIG["whisper_modele"]:
        _whisper = charger_whisper(CONFIG["whisper_modele"])
        _whisper_nom = CONFIG["whisper_modele"]
    return _whisper


def _transcrire(audio: np.ndarray, langue: str) -> str:
    with _whisper_verrou:
        segs, _ = _modele_whisper().transcribe(audio, language=langue or None, vad_filter=True, beam_size=1,
                                               initial_prompt="Jarvis, open VS Code." if langue == "en" else "Jarvis, ouvre VS Code.")
        return " ".join(s.text for s in segs).strip()


_rapide, _rapide_verrou = None, threading.Lock()


def transcrire_rapide(audio: np.ndarray) -> str:
    """Petit Whisper (« base ») pour reconnaître le nom « Jarvis » dans l'écoute de fond : ~0,3 s par phrase."""
    global _rapide
    with _rapide_verrou:
        if _rapide is None:
            _rapide = charger_whisper("base", cpu_threads=4)
        en = CONFIG.get("langue") == "en"
        segs, _ = _rapide.transcribe(audio, language="en" if en else "fr", beam_size=1, vad_filter=False,
                                     initial_prompt="Jarvis, open Discord." if en else "Jarvis, ouvre Discord.",
                                     condition_on_previous_text=False)
        return " ".join(s.text for s in segs).strip()


@app.post("/api/transcrire_rapide")
async def transcrire_vite(req: Request):
    """Petit Whisper pour les interruptions (« stop ») pendant que Jarvis parle : ~0,3 s."""
    _verifier(req)
    audio = np.frombuffer(await req.body(), dtype=np.float32)
    if audio.size < 16000 * 0.2:
        return {"texte": ""}
    return {"texte": await asyncio.to_thread(transcrire_rapide, audio)}


@app.post("/api/transcrire")
async def transcrire(req: Request, langue: str = "fr"):
    """Corps : PCM float32 mono 16 kHz brut."""
    _verifier(req)
    audio = np.frombuffer(await req.body(), dtype=np.float32)
    if audio.size < 16000 * 0.3:
        return {"texte": ""}
    t0 = time.time()
    texte = await asyncio.to_thread(_transcrire, audio, langue)
    return {"texte": texte, "secondes": round(time.time() - t0, 2)}


@app.post("/api/precharger_whisper")
async def precharger(req: Request):
    _verifier(req)
    t0 = time.time()

    def charger():
        with _whisper_verrou:
            _modele_whisper()
    await asyncio.to_thread(charger)
    return {"ok": True, "secondes": round(time.time() - t0, 1)}


# ---------- cerveau OpenAI ----------
@app.get("/api/openai")
async def etat_openai(req: Request):
    _verifier(req)
    from . import openai_cerveau as o
    modeles, erreur = [], ""
    if o.cle_configuree():
        try:
            modeles = await asyncio.to_thread(o.modeles)
        except Exception as e:
            erreur = f"Liste des modèles indisponible : {e}"
    return {"cle": o.cle_configuree(), "cle_masquee": o.cle_masquee(), "modeles": modeles,
            "modele": CONFIG.get("openai_modele") or "", "erreur": erreur}


@app.post("/api/openai/cle")
async def cle_openai(req: Request):
    _verifier(req)
    from . import openai_cerveau as o
    cle = str((await req.json()).get("cle", "")).strip()
    if cle and not cle.startswith("sk-"):
        raise HTTPException(400, "Ce n'est pas une clé API OpenAI (elle commence par sk-).")
    o.definir_cle(cle)
    return await etat_openai(req)


@app.post("/api/openai/tester")
async def tester_openai(req: Request):
    _verifier(req)
    from . import openai_cerveau as o
    try:
        texte, s = await asyncio.to_thread(o.tester)
    except Exception as e:
        raise HTTPException(502, f"Échec : {e}")
    return {"texte": texte, "secondes": round(s, 1), "modele": o.modele()}


# ---------- cerveau Claude ----------
@app.get("/api/claude")
def etat_claude(req: Request):
    _verifier(req)
    from . import claude
    return {"cle": claude.cle_configuree(), "cle_masquee": claude.cle_masquee(), "couts": claude.resume_couts(),
            "modeles": [{"id": k, "nom": v} for k, v in claude.MODELES.items()]}


@app.post("/api/claude/cle")
async def cle_claude(req: Request):
    _verifier(req)
    from . import claude
    cle = str((await req.json()).get("cle", "")).strip()
    if cle and not cle.startswith("sk-ant-"):
        raise HTTPException(400, "Ce n'est pas une clé API Anthropic (elle commence par sk-ant-).")
    claude.definir_cle(cle)
    return {"cle": claude.cle_configuree(), "cle_masquee": claude.cle_masquee()}


@app.post("/api/claude/tester")
async def tester_claude(req: Request):
    _verifier(req)
    from . import claude

    def essai():
        t0 = time.time()
        r = claude.client().messages.create(model=CONFIG["claude_modele"], max_tokens=50,
                                            output_config={"effort": "low"},
                                            messages=[{"role": "user", "content": "Réponds juste : opérationnel."}])
        claude.enregistrer_cout(r.usage, CONFIG["claude_modele"])
        return "".join(b.text for b in r.content if b.type == "text"), time.time() - t0
    try:
        texte, s = await asyncio.to_thread(essai)
    except Exception as e:
        raise HTTPException(502, f"Échec : {e}")
    return {"reponse": texte, "secondes": round(s, 2)}


# ---------- connecteurs (Gmail, agenda, GitHub, Notion, MCP…) ----------
@app.get("/api/connecteurs")
def liste_connecteurs(req: Request):
    _verifier(req)
    return {"catalogue": connecteurs.catalogue(), "installes": connecteurs.etat()}


@app.post("/api/connecteurs/{cid:path}/tester")
async def tester_connecteur(cid: str, req: Request):
    _verifier(req)
    try:
        return {"message": await asyncio.to_thread(connecteurs.tester, cid)}
    except Exception as e:
        raise HTTPException(400, f"{e}"[:300])


@app.post("/api/connecteurs/{cid:path}")
async def enregistrer_connecteur(cid: str, req: Request):
    _verifier(req)
    d = await req.json()
    try:
        await asyncio.to_thread(connecteurs.enregistrer, cid, d.get("type"), d.get("conf"), d.get("secrets"),
                                d.get("actif", True))
    except Exception as e:
        raise HTTPException(400, f"{e}"[:300])
    return connecteurs.etat().get(cid, {})


@app.delete("/api/connecteurs/{cid:path}")
async def supprimer_connecteur(cid: str, req: Request):
    _verifier(req)
    await asyncio.to_thread(connecteurs.supprimer, cid)
    return {"ok": True}


# ---------- application de bureau (fenêtre, démarrage, écoute de fond) ----------
APPLI = {"active": False, "afficher": None, "ecoute": None, "quitter": None, "relancer_raccourcis": None, "icone": None}   # renseigné par jarvis/app.py
PAROLE = {"actif": False, "depuis": 0.0}   # la fenêtre signale quand Jarvis parle (pour l'écoute de fond)


def jarvis_occupe() -> bool:
    """Jarvis parle ou travaille : l'écoute de fond guette « stop » même mêlé à sa voix."""
    parle = PAROLE["actif"] and time.time() - PAROLE["depuis"] < 300   # sécurité si la fenêtre disparaît
    return parle or verrou_tache.locked()


def stop_vocal():
    """« Jarvis, stop » ou Ctrl+Alt+S : coupe la voix et la tâche en cours."""
    if jarvis is not None:
        jarvis.arreter = True
    outils.arreter_tout()
    PAROLE["actif"] = False
    diffuser(type="stop_voix")
    print("  Stop demandé")


# ---------- compte en ligne ----------
def _etat_compte():
    from . import compte
    e = compte.etat()
    return {"connecte": compte.connecte(), "mode": compte.mode(), "email": e.get("email", ""),
            "prenom": e.get("prenom", ""), "serveur": compte.serveur(), "machine": MACHINE}


def _apres_connexion():
    """Le compte a changé : nouvelle conversation avec la mémoire et les connecteurs de ce compte."""
    from .agent import prompt_systeme
    if jarvis is not None:
        jarvis.reset()
        jarvis.messages[0]["content"] = prompt_systeme()
    diffuser(type="reset")
    threading.Thread(target=connecteurs.demarrer_tous, daemon=True).start()


@app.get("/api/compte")
def lire_compte(req: Request):
    _verifier(req)
    return _etat_compte()


@app.post("/api/compte/{action}")
async def agir_compte(action: str, req: Request):
    _verifier(req)
    from . import compte
    d = await req.json() if action in ("inscription", "connexion") else {}
    try:
        if action == "inscription":
            r = await asyncio.to_thread(compte.inscrire, d.get("email", ""), d.get("mot_de_passe", ""), d.get("prenom", ""))
        elif action == "connexion":
            r = await asyncio.to_thread(compte.connecter, d.get("email", ""), d.get("mot_de_passe", ""))
        elif action == "deconnexion":
            await asyncio.to_thread(compte.deconnecter)
            r = {}
        elif action == "importer":   # bouton « Envoyer la mémoire de cet appareil vers mon compte »
            r = {"import": await asyncio.to_thread(compte.importer_appareil)}
            await asyncio.to_thread(compte.synchroniser)
        elif action == "synchroniser":
            await asyncio.to_thread(compte.synchroniser)
            r = {}
        elif action == "local":   # « Utiliser Jarvis en local » : pas de compte, rien n'est envoyé
            await asyncio.to_thread(compte.choisir_local)
            r = {}
        elif action == "changer_mode":   # « Passer en ligne » depuis le local (ou l'inverse)
            await asyncio.to_thread(compte.changer_de_mode)
            r = {}
        else:
            raise HTTPException(404, "Action inconnue.")
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))
    if action in ("inscription", "connexion", "deconnexion", "importer", "local"):
        _apres_connexion()
    return {**_etat_compte(), **r}


# ---------- confirmations (ex : commande qui modifie un serveur SSH en mode « confirmation ») ----------
_confirmations: dict = {}


def demander_confirmation(titre: str, detail: str = "", delai: float = 180) -> bool:
    """Affiche « Autoriser / Refuser » dans la fenêtre de Jarvis et attend la réponse (refus si STOP ou sans réponse)."""
    import uuid
    cid = uuid.uuid4().hex[:10]
    attente = {"ev": threading.Event(), "ok": False}
    _confirmations[cid] = attente
    if APPLI.get("afficher"):
        try:
            APPLI["afficher"]()   # la question doit être vue, même fenêtre cachée
        except Exception:
            pass
    debut = time.time()
    try:
        while time.time() - debut < delai and not attente["ev"].is_set():
            if outils.ARRET.is_set():
                break
            # renvoyée régulièrement : l'interface peut s'être (re)connectée entre-temps
            diffuser(type="confirmation", id=cid, titre=titre, detail=detail[:4000])
            attente["ev"].wait(2)
    finally:
        _confirmations.pop(cid, None)
        diffuser(type="confirmation_fin", id=cid)
    return attente["ok"]


@app.post("/api/confirmation")
async def repondre_confirmation(req: Request):
    _verifier(req)
    d = await req.json()
    c = _confirmations.get(d.get("id"))
    if c:
        c["ok"] = bool(d.get("ok"))
        c["ev"].set()
    return {"ok": bool(c)}


@app.post("/api/fenetre/afficher")
async def afficher_fenetre(req: Request):
    _verifier(req)
    try:
        vue = (await req.json()).get("vue")
    except Exception:
        vue = None
    if APPLI["afficher"]:
        APPLI["afficher"](vue)
    return {"ok": bool(APPLI["afficher"])}


# ---------- mes appareils ----------
@app.get("/api/appareils")
async def lister_appareils(req: Request):
    _verifier(req)
    from . import appareils, compte
    liste, erreur = [], ""
    if compte.connecte():
        try:
            liste = await asyncio.to_thread(appareils.lister)
        except compte.ErreurCompte as e:
            erreur = str(e)
    return {"appareils": liste, "reglages": appareils.reglages(), "journal": list(reversed(appareils.journal()))[:100],
            "connecte": compte.connecte(), "mode": compte.mode(), "erreur": erreur}


@app.post("/api/appareils/reglages")
async def regler_appareil(req: Request):
    _verifier(req)
    from . import appareils
    d = await req.json()
    appareils.regler(d.get("accepte"), d.get("mode"))
    return await lister_appareils(req)


@app.post("/api/appareils/{aid}/deconnecter")
async def deconnecter_un_appareil(aid: str, req: Request):
    _verifier(req)
    from . import appareils, compte
    moi = next((a for a in await asyncio.to_thread(appareils.lister) if a["moi"]), None)
    if moi and moi["id"] == aid:   # cet appareil-ci : déconnexion complète
        await asyncio.to_thread(compte.deconnecter)
        return {"moi": True}
    try:
        return await asyncio.to_thread(appareils.deconnecter, aid)
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))


@app.post("/api/appareils/{aid}/demander")
async def demander_appareil(aid: str, req: Request):
    """Depuis l'onglet Appareils : envoyer une demande à un autre appareil et attendre sa réponse."""
    _verifier(req)
    from . import appareils
    texte = (await req.json()).get("texte", "").strip()
    try:
        r = await asyncio.to_thread(appareils.envoyer, aid, {"type": "demande", "texte": texte}, 600)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"resultat": r.get("resultat", ""), "ok": r.get("ok", False)}


# ---------- notifications (cloche) ----------
@app.get("/api/notifications")
def lire_notifications(req: Request):
    _verifier(req)
    from . import notifications
    return list(reversed(notifications.lister()))


@app.post("/api/notifications/{action}")
async def agir_notifications(action: str, req: Request):
    _verifier(req)
    from . import notifications
    if action == "lues":
        d = await req.json()
        notifications.marquer_lues(d.get("ids"))
    elif action == "effacer":
        notifications.effacer()
    return {"ok": True}


# ---------- agents de code (Claude Code, Codex) ----------
@app.get("/api/agents_code")
async def etat_agents_code(req: Request):
    _verifier(req)
    from . import agents_code
    etats = await asyncio.gather(*(asyncio.to_thread(agents_code.etat, a) for a in agents_code.NOMS))
    return [{**e, "probleme": agents_code.probleme(e)} for e in etats]


@app.post("/api/agents_code/{agent}/{action}")
async def agir_agent_code(agent: str, action: str, req: Request):
    _verifier(req)
    from . import agents_code
    if agent not in agents_code.NOMS:
        raise HTTPException(404, "Agent inconnu.")
    fn = {"connecter": agents_code.connecter, "deconnecter": agents_code.deconnecter, "installer": agents_code.installer}.get(action)
    if not fn:
        raise HTTPException(404, "Action inconnue.")
    return {"message": await asyncio.to_thread(fn, agent)}


# ---------- tâches de fond (code avec Claude Code / Jarvis) ----------
@app.get("/api/taches")
def lister_taches(req: Request):
    _verifier(req)
    from . import taches
    return [taches.resume(t) for t in taches.lister()]


@app.get("/api/taches/{tid}")
def lire_tache(tid: str, req: Request):
    _verifier(req)
    from . import taches
    t = taches.lire(tid)
    if not t:
        raise HTTPException(404, "Tâche introuvable.")
    return t


@app.post("/api/taches")
async def creer_tache(req: Request):
    _verifier(req)
    from . import taches
    d = await req.json()
    try:
        t = await asyncio.to_thread(taches.creer, d.get("consigne", ""), d.get("projet", ""), d.get("outil", "claude_code"), d.get("titre", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return taches.resume(t)


@app.post("/api/taches/{tid}/{action}")
async def agir_tache(tid: str, action: str, req: Request):
    _verifier(req)
    from . import taches
    if action == "consigne":
        return {"message": taches.mettre_a_jour(tid, (await req.json()).get("texte", ""))}
    if action == "arreter":
        return {"message": taches.arreter(tid)}
    if action == "reprendre":
        t = taches.lire(tid)
        if t and t["statut"] != "en_cours":
            t["statut"] = "en_cours"
            taches._sauver(t)
            taches.demarrer(tid)
        return {"message": "Tâche reprise."}
    if action == "ouvrir":
        t = taches.lire(tid)
        if t and t.get("dossier"):
            from .plateforme import ouvrir_chemin
            ouvrir_chemin(t["dossier"])
        return {"ok": True}
    raise HTTPException(404, "Action inconnue.")


@app.delete("/api/taches/{tid}")
def supprimer_tache(tid: str, req: Request):
    _verifier(req)
    from . import taches
    return {"ok": taches.supprimer(tid)}


# ---------- automatisations ----------
@app.get("/api/automatisations")
def lister_automatisations(req: Request):
    _verifier(req)
    from . import automatisations
    boites = [{"cid": cid, "nom": f"{c.nom} — {c.etiquette()}"} for cid, c in automatisations._boites().items()]
    return {"regles": [{**r, "description": automatisations.decrire(r)} for r in automatisations.lister()], "boites": boites,
            "machine": MACHINE}


@app.post("/api/automatisations")
async def creer_automatisation(req: Request):
    _verifier(req)
    from . import automatisations
    d = await req.json()
    typ = d.get("type", "mail")
    if typ == "mail" and not (d.get("expediteur") or d.get("sujet") or d.get("contient")):
        raise HTTPException(400, "Indique au moins un expéditeur, un mot du sujet ou un mot du texte.")
    if typ == "horaire" and not d.get("heure"):
        raise HTTPException(400, "Indique l'heure.")
    if typ == "intervalle" and not d.get("minutes"):
        raise HTTPException(400, "Indique l'intervalle en minutes.")
    if d.get("action") == "jarvis" and not d.get("consigne", "").strip():
        raise HTTPException(400, "Indique ce que Jarvis doit faire.")
    automatisations.creer(d.get("nom", ""), d.get("expediteur", ""), d.get("sujet", ""), d.get("contient", ""),
                          d.get("connecteur", ""), d.get("action", "prevenir"), d.get("consigne", ""), typ,
                          d.get("heure", ""), d.get("jours") or [], int(d.get("minutes") or 0),
                          None if d.get("appareil") is None else d.get("appareil"), d.get("message", ""))
    return lister_automatisations(req)


@app.patch("/api/automatisations/{rid}")
async def modifier_automatisation(rid: str, req: Request):
    _verifier(req)
    from . import automatisations
    automatisations.modifier(rid, **(await req.json()))
    return lister_automatisations(req)


@app.delete("/api/automatisations/{rid}")
def supprimer_automatisation(rid: str, req: Request):
    _verifier(req)
    from . import automatisations
    automatisations.supprimer(rid)
    return lister_automatisations(req)


@app.post("/api/automatisations/tester")
async def tester_annonce(req: Request):
    """Bouton « Tester la voix » : Jarvis parle comme il le fera pour une automatisation."""
    _verifier(req)
    from . import annonces
    annonces.annoncer("This is a test: this is how I'll let you know." if CONFIG.get("langue") == "en"
                      else "Ceci est un test : c'est comme ça que je te préviendrai.")
    return {"ok": True}


# ---------- autorisations du système (micro, écran, accessibilité, fichiers, applis) ----------
@app.get("/api/autorisations")
def lire_autorisations(req: Request):
    _verifier(req)
    from . import autorisations
    return autorisations.etat()


@app.post("/api/autorisations/{action}")
async def agir_autorisation(action: str, req: Request):
    _verifier(req)
    from . import autorisations
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
@app.get("/api/majs")
def lister_majs(req: Request):
    _verifier(req)
    from . import mises_a_jour
    return mises_a_jour.lister()


@app.post("/api/majs/jeton")
async def jeton_majs(req: Request):
    _verifier(req)
    from . import mises_a_jour
    mises_a_jour.definir_jeton((await req.json()).get("jeton", ""))
    return mises_a_jour.lister()


@app.post("/api/majs/installer")
async def installer_maj(req: Request):
    _verifier(req)
    from . import mises_a_jour
    version = (await req.json()).get("version", "")
    if not APPLI["quitter"]:
        raise HTTPException(400, "Les mises à jour s'installent depuis l'application Jarvis installée.")
    try:
        mises_a_jour.installer(version, lambda etape, pct, texte: diffuser(type="maj", etape=etape, pct=pct, texte=texte),
                               APPLI["quitter"])
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/appli")
def etat_appli(req: Request):
    _verifier(req)
    from . import demarrage
    return {"appli": APPLI["active"], "plateforme": "mac" if MAC else "windows" if WIN else "linux",
            "demarrage_auto": demarrage.est_actif(), "machine": MACHINE,
            "ecoute_fond": CONFIG.get("ecoute_fond", True),
            "ecoute_active": bool(APPLI["ecoute"] and APPLI["ecoute"].actif),
            "seuil_eveil": CONFIG.get("seuil_eveil", 0.5), "raccourci": CONFIG.get("raccourci"),
            "silence_fin": CONFIG.get("silence_fin", 2.5)}


@app.post("/api/appli")
async def regler_appli(req: Request):
    _verifier(req)
    from . import demarrage
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


def commande_vocale(audio: np.ndarray):
    """Phrase dite après « Hey Jarvis » (fenêtre éventuellement cachée) : transcription puis exécution."""
    if audio is None:   # rien dit après le mot d'activation
        diffuser(type="vocal", etat="fin")
        return
    diffuser(type="vocal", etat="transcription")
    try:
        texte = _transcrire(audio, CONFIG.get("langue") or "fr")
    except Exception as e:
        diffuser(type="vocal", etat="fin")
        diffuser(type="erreur", texte=f"Transcription impossible : {e}")
        return
    diffuser(type="vocal", etat="fin", texte=texte)
    from .ecoute import RX_NOM
    texte = RX_NOM.sub("", texte).strip()
    if len(texte) >= 2:
        from .ecoute import RX_STOP_SEUL
        if RX_STOP_SEUL.match(texte) or re.match(r"^(stop|arr[êe]te|annule|tais[- ]toi|chut|silence)\b", texte, re.I):
            stop_vocal()
            return
        def lancer():
            for _ in range(80):   # jusqu'à 8 s : fenêtre réveillée à l'instant, pas encore branchée
                if _clients:
                    break
                time.sleep(0.1)
            executer(texte)
        threading.Thread(target=lancer, daemon=True).start()


# ---------- synthèse vocale ----------
@app.get("/api/tts/voix")
def tts_voix(req: Request):
    _verifier(req)
    return {"edge": [{"id": i, "nom": n} for i, n in tts.VOIX_EDGE],
            "piper": [{"id": v, "nom": v.replace("_", " ")} for v in tts.voix_piper()]}


@app.post("/api/tts")
async def tts_synthese(req: Request):
    _verifier(req)
    d = await req.json()
    if not str(d.get("texte", "")).strip():
        raise HTTPException(400, "Texte vide")
    try:
        audio, mime, moteur = await tts.synthese(d["texte"], d.get("moteur", "edge"), d.get("voix", ""),
                                                 float(d.get("debit", 1.0)))
    except Exception as e:
        raise HTTPException(502, f"Synthèse impossible : {e}")
    return Response(audio, media_type=mime, headers={"x-moteur": moteur, "cache-control": "no-store"})


# ---------- modèle en mémoire vidéo ----------
@app.post("/api/modele/liberer")
def liberer(req: Request):
    _verifier(req)
    if verrou_tache.locked():
        raise HTTPException(409, "Jarvis est occupé")
    Jarvis.liberer()
    return {"ok": True}


@app.post("/api/modele/charger")
def charger(req: Request):
    _verifier(req)
    threading.Thread(target=jarvis.prechauffer, daemon=True).start()
    return {"ok": True}


# ---------- conversation ----------
def _conversation():
    """Conversation en cours au format de l'interface (pour restaurer après un rechargement)."""
    if jarvis.avec_claude:
        from . import claude
        return claude.conversation_ui(jarvis.histo_claude)
    if jarvis.avec_openai:
        from . import openai_cerveau
        return openai_cerveau.conversation_ui(jarvis.histo_openai)
    out = []
    for m in jarvis.messages[1:]:
        if m["role"] == "user":
            out.append({"role": "user", "texte": m["content"]})
        elif m["role"] == "assistant":
            if not out or out[-1]["role"] != "jarvis":
                out.append({"role": "jarvis", "blocs": []})
            if m.get("content"):
                out[-1]["blocs"].append({"type": "texte", "texte": m["content"]})
            for tc in m.get("tool_calls") or []:
                out[-1]["blocs"].append({"type": "outil", "nom": tc["function"]["name"],
                                         "args": {k: str(v)[:200] for k, v in tc["function"]["arguments"].items()},
                                         "resultat": None})
        elif m["role"] == "tool" and out and out[-1]["role"] == "jarvis":
            for b in out[-1]["blocs"]:
                if b["type"] == "outil" and b["resultat"] is None:
                    b["resultat"] = m["content"][:600]
                    break
    return out


def executer(texte: str):
    global _seq
    if not verrou_tache.acquire(blocking=False):
        diffuser(type="erreur", texte="Je suis déjà sur une tâche. STOP pour l'interrompre.")
        return
    outils.ARRET.clear()   # nouvelle tâche : l'arrêt précédent ne compte plus
    id_outil = None

    def sur_outil(nom, a, res):
        nonlocal id_outil
        global _seq
        if res is None:
            _seq += 1
            id_outil = _seq
            diffuser(type="outil", id=id_outil, nom=nom, args={k: str(v)[:200] for k, v in a.items()})
        else:
            diffuser(type="resultat", id=id_outil, nom=nom, res=res[:600], erreur=res.startswith("Erreur"))

    try:
        diffuser(type="utilisateur", texte=texte)
        diffuser(type="etat", occupe=True)
        rep = jarvis.demander(texte, sur_texte=lambda t: diffuser(type="texte", t=t),
                              sur_pensee=lambda t: diffuser(type="pensee", t=t), sur_outil=sur_outil)
        diffuser(type="fin", texte=rep)
    except Exception as e:
        diffuser(type="erreur", texte=f"Erreur : {e}")
    finally:
        verrou_tache.release()
        diffuser(type="etat", occupe=False)


@app.websocket("/ws")
async def ws(sock: WebSocket):
    global _boucle
    if _hote(sock.headers.get("origin")) not in HOTES_OK or sock.query_params.get("jeton") != JETON:
        await sock.close(code=4403)
        return
    await sock.accept()
    _boucle = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    _clients.add(q)
    await sock.send_json({"type": "init", "conversation": _conversation(), "occupe": verrou_tache.locked()})

    async def emetteur():
        while True:
            await sock.send_json(await q.get())

    tache = asyncio.create_task(emetteur())
    try:
        while True:
            m = await sock.receive_json()
            t = m.get("type")
            if t == "message" and str(m.get("texte", "")).strip():
                threading.Thread(target=executer, args=(m["texte"].strip(),), daemon=True).start()
            elif t == "stop":
                jarvis.arreter = True
                outils.arreter_tout()
            elif t == "parle":
                PAROLE.update(actif=bool(m.get("actif")), depuis=time.time())
            elif t == "reset":
                jarvis.arreter = True
                jarvis.reset()
                diffuser(type="reset")
                threading.Thread(target=jarvis.prechauffer, daemon=True).start()
            elif t == "scan":
                await asyncio.to_thread(memoire.scanner_systeme)
                jarvis.reset()
                diffuser(type="reset")
                diffuser(type="info", texte="PC re-scanné, nouvelle conversation.")
                threading.Thread(target=jarvis.prechauffer, daemon=True).start()
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(q)
        tache.cancel()


# ---------- fichiers du front (compilé par Vite) ----------
if (STATIC / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")


@app.get("/{chemin:path}", response_class=HTMLResponse)
def front(chemin: str):
    f = (STATIC / chemin).resolve()
    if chemin and f.is_file() and STATIC.resolve() in f.parents:
        return FileResponse(f)
    index = STATIC / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Interface non compilée</h1><p>Lance <code>npm run build</code> dans le dossier interface.</p>", 503)
    return FileResponse(index)


# ---------- lancement ----------
def _demarrer_ollama():
    """Lance Ollama en arrière-plan s'il ne répond pas."""
    try:
        ollama.list(); return
    except Exception:
        pass
    exe = shutil.which("ollama")
    if not exe:
        print("  ! Ollama introuvable : installe-le depuis ollama.com"); return
    print("  Démarrage d'Ollama...")
    if WIN:
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    else:
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(30):
        time.sleep(0.5)
        try:
            ollama.list(); return
        except Exception:
            pass


def preparer():
    global jarvis
    from . import compte

    def apres_synchro(changements):
        """Un autre appareil a modifié le compte : Jarvis tient compte des nouveaux souvenirs dès maintenant."""
        if jarvis is not None and (changements["faits_texte"] or changements["reglages"]):
            from .agent import prompt_systeme
            jarvis.messages[0]["content"] = prompt_systeme()
        if changements["connecteurs"]:
            threading.Thread(target=connecteurs.demarrer_tous, daemon=True).start()
        diffuser(type="memoire_maj", **changements)
    compte.ecouteurs.append(apres_synchro)
    compte.au_demarrage()   # mémoire, connecteurs et profil du compte connecté (cache local + synchro)
    from . import automatisations, taches
    automatisations.demarrer()   # surveille tes boîtes mail pour les règles « quand je reçois… »
    taches.au_demarrage()        # tâches de fond coupées par la fermeture : « interrompues » (bouton Reprendre)
    from . import agents_code
    agents_code.surveiller()     # prévient si Claude Code / Codex ne sont plus connectés
    if CONFIG.get("cerveau") not in ("claude", "openai"):
        _demarrer_ollama()
    if not memoire.SYSTEME.exists():
        print("  Premier lancement : scan du PC...")
        memoire.scanner_systeme()
    jarvis = Jarvis()
    psutil.cpu_percent(interval=None)

    def prechauffer_tout():
        t0 = time.time()
        try:
            connecteurs.demarrer_tous()
            print(f"  Connecteurs : {len(connecteurs.INSTANCES)}")
        except Exception as e:
            print(f"  ! Connecteurs : {e}")
        jarvis.prechauffer()
        print(f"  Modèle prêt ({time.time() - t0:.0f} s)")
        try:
            with _whisper_verrou:
                _modele_whisper()
            print("  Reconnaissance vocale prête")
        except Exception as e:
            print(f"  ! Whisper : {e}")
        tts.precharger_piper()
    threading.Thread(target=prechauffer_tout, daemon=True).start()


def _deja_lance(url):
    try:
        import urllib.request
        with urllib.request.urlopen(f"{url}/api/session", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def main(ouvrir=True):
    import uvicorn
    url = f"http://{HOTE}:{PORT}"
    # Un seul Jarvis à la fois : deux instances s'écrasent mutuellement le cache d'Ollama
    # et chaque question doit alors relire tout le prompt (~6-30 s au lieu de 0,2 s).
    if _deja_lance(url):
        print(f"\n  Jarvis tourne déjà -> {url} (j'ouvre l'interface existante)\n")
        if ouvrir:
            webbrowser.open(url)
        return
    preparer()
    print(f"\n  J.A.R.V.I.S. en ligne -> {url}\n  (Ctrl+C pour arrêter)\n")
    if ouvrir:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host=HOTE, port=PORT, log_level="warning")
    finally:
        print("Je mémorise ce que j'ai appris...")
        try:
            for f in jarvis.extraire_souvenirs():
                print(" ", f)
        except Exception:
            pass
        Jarvis.liberer()   # rend la VRAM (jeux, etc.)


if __name__ == "__main__":
    import sys
    main(ouvrir="--sans-navigateur" not in sys.argv)
