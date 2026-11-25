"""Voix : reconnaissance vocale (Whisper), commande vocale, synthèse, Kyutai, modèle en mémoire vidéo."""
import asyncio
import re
import threading
import time

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from .. import tts, web
from ..config import CONFIG
from ..modeles import charger_whisper
from ..web import APPLI, PAROLE, _verifier, diffuser, executer, stop_vocal

router = APIRouter()
_whisper, _whisper_nom, _whisper_verrou = None, None, threading.Lock()


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
                                               initial_prompt="Wesley, open VS Code." if langue == "en" else "Wesley, ouvre VS Code.")
        return " ".join(s.text for s in segs).strip()


_rapide, _rapide_verrou = None, threading.Lock()


def transcrire_rapide(audio: np.ndarray) -> str:
    """Petit Whisper (« base ») pour reconnaître le nom « Wesley » dans l'écoute de fond : ~0,3 s par phrase."""
    global _rapide
    with _rapide_verrou:
        if _rapide is None:
            _rapide = charger_whisper("base", cpu_threads=4)
        en = CONFIG.get("langue") == "en"
        segs, _ = _rapide.transcribe(audio, language="en" if en else "fr", beam_size=1, vad_filter=False,
                                     initial_prompt="Wesley, open Discord." if en else "Wesley, ouvre Discord.",
                                     condition_on_previous_text=False)
        return " ".join(s.text for s in segs).strip()


@router.post("/api/transcrire_rapide")
async def transcrire_vite(req: Request):
    """Petit Whisper pour les interruptions (« stop ») pendant que Wesley parle : ~0,3 s."""
    _verifier(req)
    audio = np.frombuffer(await req.body(), dtype=np.float32)
    if audio.size < 16000 * 0.2:
        return {"texte": ""}
    return {"texte": await asyncio.to_thread(transcrire_rapide, audio)}


@router.post("/api/transcrire")
async def transcrire(req: Request, langue: str = "fr"):
    """Corps : PCM float32 mono 16 kHz brut."""
    _verifier(req)
    audio = np.frombuffer(await req.body(), dtype=np.float32)
    if audio.size < 16000 * 0.3:
        return {"texte": ""}
    t0 = time.time()
    texte = await asyncio.to_thread(_transcrire, audio, langue)
    return {"texte": texte, "secondes": round(time.time() - t0, 2)}


@router.post("/api/precharger_whisper")
async def precharger(req: Request):
    _verifier(req)
    t0 = time.time()

    def charger():
        with _whisper_verrou:
            _modele_whisper()
    await asyncio.to_thread(charger)
    return {"ok": True, "secondes": round(time.time() - t0, 1)}



VOCAL = {"ts": 0.0}   # dernière demande faite à la voix (conversation suivie)


def _ecouter_suite_bientot():
    """La voix de Wesley s'est tue : si la réponse est finie et que la demande était orale, on écoute la suite
    8 s sans redire « Wesley »."""
    def verifier():
        time.sleep(0.8)   # entre deux phrases, la voix s'arrête un instant : on attend d'être sûr
        ecoute = APPLI.get("ecoute")
        if (CONFIG.get("conversation_suivie", True) and ecoute is not None and ecoute.actif and not PAROLE["actif"]
                and not web.verrou_tache.locked() and time.time() - VOCAL["ts"] < 180):
            ecoute.ecouter_suite(8.0)
            diffuser(type="vocal", etat="suite")
    threading.Thread(target=verifier, daemon=True).start()


def commande_vocale(audio: np.ndarray):
    """Phrase dite après « Hey Wesley » (fenêtre éventuellement cachée) : transcription puis exécution."""
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
    from ..ecoute import RX_NOM
    texte = RX_NOM.sub("", texte).strip()
    if len(texte) >= 2:
        from ..ecoute import RX_STOP_SEUL
        if RX_STOP_SEUL.match(texte) or re.match(r"^(stop|arr[êe]te|annule|tais[- ]toi|chut|silence)\b", texte, re.I):
            stop_vocal()
            return
        VOCAL["ts"] = time.time()

        def lancer():
            for _ in range(80):   # jusqu'à 8 s : fenêtre réveillée à l'instant, pas encore branchée
                if web._clients:
                    break
                time.sleep(0.1)
            executer(texte)
        threading.Thread(target=lancer, daemon=True).start()


# ---------- synthèse vocale ----------
@router.get("/api/tts/voix")
def tts_voix(req: Request):
    _verifier(req)
    from .. import kyutai
    return {"kyutai": [{"id": i, "nom": n} for i, n in kyutai.VOIX],
            "edge": [{"id": i, "nom": n} for i, n in tts.VOIX_EDGE],
            "piper": [{"id": v, "nom": v.replace("_", " ")} for v in tts.voix_piper()]}


@router.post("/api/tts")
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



# ---------- voix Kyutai (locale, téléchargeable) ----------
@router.get("/api/kyutai")
def etat_kyutai(req: Request):
    _verifier(req)
    from .. import kyutai
    return kyutai.etat()


@router.post("/api/kyutai/{action}")
async def agir_kyutai(action: str, req: Request):
    _verifier(req)
    from .. import kyutai
    try:
        if action == "installer":
            kyutai.installer()
        elif action == "supprimer":
            await asyncio.to_thread(kyutai.supprimer)
        elif action == "demarrer":   # charge le modèle à l'avance (choix de la voix Kyutai dans les réglages)
            threading.Thread(target=kyutai.demarrer_serveur, daemon=True).start()
        else:
            raise HTTPException(404, "Action inconnue.")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return kyutai.etat()


# ---------- modèle en mémoire vidéo ----------
@router.post("/api/modele/liberer")
def liberer(req: Request):
    _verifier(req)
    if web.verrou_tache.locked():
        raise HTTPException(409, "Wesley est occupé")
    from ..agent import Wesley
    Wesley.liberer()
    return {"ok": True}


@router.post("/api/modele/charger")
def charger(req: Request):
    _verifier(req)
    threading.Thread(target=web.wesley.prechauffer, daemon=True).start()
    return {"ok": True}
