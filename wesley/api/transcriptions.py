"""Transcription de réunions (wesley/transcription.py, 100 % local)."""
import asyncio
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..config import CONFIG, MACHINE, sauver_config
from ..plateforme import MAC, WIN
from ..web import APPLI, _verifier

router = APIRouter()
from .taches import _agir_a_distance  # noqa: E402


# ---------- transcription de réunions (wesley/transcription.py, 100 % local) ----------
def _apres_transcription(t, ecoute_coupee: bool, fichier_temp: Path | None):
    """Fin d'une transcription : l'écoute « Wesley » reprend, le fichier importé temporaire est effacé."""
    t.attendre()
    if fichier_temp is not None:
        fichier_temp.unlink(missing_ok=True)
    from .. import resume_transcription
    resume_transcription.au_terme(t.session["id"])   # résumé automatique (cours, réunion, discussion…)
    ecoute = APPLI.get("ecoute")
    if ecoute_coupee and ecoute is not None and CONFIG.get("ecoute_fond", True):
        ecoute.demarrer()


def _lancer_transcription(fichier_temp: Path | None = None, reprendre: str = "", **options) -> dict:
    """Lance une transcription, ou reprend celle d'identifiant `reprendre` (la suite s'y ajoute)."""
    from .. import transcription
    # pendant une réunion, « Wesley » dans la conversation ne doit pas réveiller l'assistant
    ecoute = APPLI.get("ecoute")
    couper = options.get("source") == "micro" or bool(options.get("avec_micro"))
    ecoute_coupee = bool(couper and ecoute is not None and ecoute.actif)
    try:
        etat = transcription.reprendre(reprendre, **options) if reprendre else transcription.demarrer(**options)
    except ValueError as e:
        if fichier_temp is not None:
            fichier_temp.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    if ecoute_coupee:
        ecoute.arreter()
    threading.Thread(target=_apres_transcription, args=(transcription.en_cours(), ecoute_coupee, fichier_temp),
                     daemon=True).start()
    return etat


@router.get("/api/transcriptions")
def lister_transcriptions(req: Request):
    _verifier(req)
    from .. import transcription
    from .. import partage
    t = transcription.en_cours()
    liste = [r | {"appareil": MACHINE} for r in transcription.lister()] + partage.distants("transcription")
    return {"liste": sorted(liste, key=lambda r: r.get("debut") or 0, reverse=True),
            "en_cours": t.instantane() if t else None, "appareil": MACHINE,
            "modeles": transcription.MODELES_WHISPER,
            "modele": transcription.modele_par_defaut(), "modele_auto": transcription.modele_auto(),
            "dossier": str(transcription.dossier_export()), "plateforme": "mac" if MAC else "windows" if WIN else "linux"}


@router.get("/api/transcriptions/chercher")
async def chercher_transcriptions(req: Request, q: str = ""):
    """Recherche dans toutes les transcriptions, de tous les appareils (avant la route /{tid})."""
    _verifier(req)
    from .. import recherche_transcriptions
    return {"resultats": await asyncio.to_thread(recherche_transcriptions.chercher, q, 40)}


@router.get("/api/transcriptions/{tid}")
def lire_transcription(tid: str, req: Request):
    _verifier(req)
    from .. import transcription
    try:
        s = transcription.lire(tid)
    except ValueError:
        s = None
    if s is None:
        from .. import partage
        d = partage.lire("transcription", tid)   # faite sur un autre appareil : dernière version publiée
        if d is None:
            raise HTTPException(404, "Transcription introuvable.")
        return d | {"locuteurs": d.get("locuteurs") or transcription.locuteurs(d), "regroupable": False}
    return s | {"locuteurs": transcription.locuteurs(s), "regroupable": transcription.regroupable(tid)}


def lancer_resume(tid: str):
    """Résumé demandé par l'utilisateur : fait en fond (30 s à quelques minutes), l'état est dans session["resume"]."""
    from .. import resume_transcription, transcription
    s = transcription.lire(tid)
    if s is None:
        raise ValueError("Transcription introuvable.")
    if s.get("etat") in ("preparation", "en_cours", "finalisation"):
        raise ValueError("Attends la fin de la transcription pour la résumer.")
    if not (s.get("segments") or []):
        raise ValueError("Rien n'a été transcrit : il n'y a rien à résumer.")
    if tid in resume_transcription._en_cours:
        return

    def fond():
        try:
            resume_transcription.resumer(tid)
        except Exception as e:
            print(f"  ! Résumé de {tid} : {e}")
    threading.Thread(target=fond, daemon=True, name=f"resume-{tid}").start()
    for _ in range(20):   # le temps que l'état « en cours » soit rangé (affiché tout de suite)
        if tid in resume_transcription._en_cours:
            break
        time.sleep(0.05)


def reprendre_transcription(tid: str, d: dict) -> dict:
    """Reprend une transcription de cet appareil : la suite s'ajoute à la même transcription ; source d'origine
    par défaut (micro pour un fichier importé). ValueError avec la raison si c'est impossible."""
    from .. import transcription
    s = transcription.lire(tid)
    if not s:
        raise ValueError("Transcription introuvable.")
    source = d.get("source") or (s.get("source") if s.get("source") in ("micro", "systeme") else "micro")
    source = source if source in ("micro", "systeme") else "micro"
    avec_micro = bool(d["avec_micro"]) if "avec_micro" in d else bool(s.get("avec_micro"))
    try:
        return _lancer_transcription(reprendre=tid, source=source, avec_micro=avec_micro and source == "systeme")
    except HTTPException as e:
        raise ValueError(e.detail)


@router.post("/api/transcriptions/demarrer")
async def demarrer_transcription(req: Request):
    _verifier(req)
    d = await req.json()
    if d.get("appareil"):   # sur un autre ordinateur : son micro ou son son, son modèle de reconnaissance
        from .. import partage
        params = {k: d[k] for k in ("source", "avec_micro", "titre", "langue", "nb_locuteurs", "vocabulaire") if k in d}
        try:
            return {"message": await asyncio.to_thread(partage.lancer, d["appareil"], "transcription", params), "distant": True}
        except ValueError as e:
            raise HTTPException(409, str(e))
    if d.get("modele"):
        CONFIG["transcription_modele"] = d["modele"]   # retenu pour la prochaine fois
        CONFIG["transcription_modele_choisi"] = True   # choix réel (les réglages d'avant 2.4.0 repassent en « auto »)
        sauver_config(["transcription_modele", "transcription_modele_choisi"])
    return await asyncio.to_thread(
        _lancer_transcription, source=d.get("source", "micro"), avec_micro=bool(d.get("avec_micro")),
        langue=d.get("langue", CONFIG.get("langue", "fr")), modele=d.get("modele", ""), titre=d.get("titre", ""),
        nb_locuteurs=int(d.get("nb_locuteurs") or 0), vocabulaire=str(d.get("vocabulaire") or ""))


async def _recevoir_fichier(req: Request, nom: str) -> Path:
    """Enregistre le corps de la requête (fichier audio ou vidéo, 2 Go au plus) dans le dossier des imports."""
    from .. import transcription
    ext = re.sub(r"[^a-z0-9]", "", Path(nom).suffix.lower())[:6] or "audio"
    dossier = transcription.DOSSIER_DONNEES / "imports"
    dossier.mkdir(parents=True, exist_ok=True)
    f = dossier / f"{secrets.token_hex(8)}.{ext}"
    taille = 0
    with open(f, "wb") as sortie:
        async for morceau in req.stream():
            taille += len(morceau)
            if taille > 2 * 1024 ** 3:
                sortie.close()
                f.unlink(missing_ok=True)
                raise HTTPException(413, "Fichier trop gros (2 Go au maximum).")
            sortie.write(morceau)
    if not taille:
        f.unlink(missing_ok=True)
        raise HTTPException(400, "Fichier vide.")
    return f


@router.post("/api/transcriptions/importer")
async def importer_transcription(req: Request, nom: str = "", langue: str = "fr", modele: str = "", nb_locuteurs: int = 0,
                                 vocabulaire: str = ""):
    """Corps : le fichier audio ou vidéo brut (mp3, m4a, wav, mp4…), transcrit puis effacé."""
    _verifier(req)
    f = await _recevoir_fichier(req, nom)
    return await asyncio.to_thread(_lancer_transcription, f, source="fichier", fichier_audio=str(f), langue=langue,
                                   modele=modele, titre=Path(nom).stem[:120], nb_locuteurs=nb_locuteurs,
                                   vocabulaire=vocabulaire)


@router.post("/api/transcriptions/arreter")
def arreter_transcription(req: Request):
    _verifier(req)
    from .. import transcription
    return {"etat": transcription.arreter()}


@router.post("/api/transcriptions/{tid}/reprendre_fichier")
async def reprendre_avec_fichier(tid: str, req: Request, nom: str = ""):
    """La suite d'une transcription est dans un fichier (2e partie d'un cours, autre enregistrement de la réunion) :
    il est transcrit à la fin de la même transcription, mêmes locuteurs, horodatage qui continue. Corps : le fichier."""
    _verifier(req)
    from .. import transcription
    try:
        if transcription.lire(tid) is None:
            raise HTTPException(404, "Transcription introuvable sur cet ordinateur (une transcription d'un autre appareil se reprend sur lui).")
    except ValueError:
        raise HTTPException(400, "Identifiant de transcription invalide.")
    f = await _recevoir_fichier(req, nom)
    return await asyncio.to_thread(_lancer_transcription, f, reprendre=tid, source="fichier", fichier_audio=str(f))


@router.post("/api/transcriptions/{tid}/{action}")
async def agir_transcription(tid: str, action: str, req: Request):
    _verifier(req)
    from .. import transcription
    from ..plateforme import ouvrir_chemin
    d = await req.json() if (await req.body()) else {}
    try:
        local = transcription.lire(tid) is not None
    except ValueError:
        raise HTTPException(400, "Identifiant de transcription invalide.")
    if not local:
        return await _agir_transcription_distante(tid, action, d)
    try:
        if action == "exporter":
            f = await asyncio.to_thread(transcription.enregistrer_sous, tid, d.get("format", "md"))
            if d.get("ouvrir"):
                ouvrir_chemin(str(f))
            return {"fichier": str(f), "texte": f.read_text(encoding="utf-8")}
        if action == "ouvrir":
            s = transcription.lire(tid)
            if not s:
                raise ValueError("Transcription introuvable.")
            f = Path(s.get("fichier") or "")
            ouvrir_chemin(str(f if f.is_file() else transcription.dossier_export()))
            return {"ok": True}
        if action == "reprendre":
            return await asyncio.to_thread(reprendre_transcription, tid, d)
        if action == "resumer":
            lancer_resume(tid)
            s = transcription.lire(tid)
        elif action == "arreter":
            t = transcription.en_cours()
            if t is None or t.session["id"] != tid:
                raise ValueError("Cette transcription n'est pas en cours.")
            transcription.arreter()
            s = transcription.lire(tid)
        else:
            s = await asyncio.to_thread(transcription.modifier, tid, action, d)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s | {"locuteurs": transcription.locuteurs(s), "regroupable": transcription.regroupable(tid)}


async def _agir_transcription_distante(tid: str, action: str, d: dict):
    """Transcription faite sur un autre appareil : la lecture et l'export se font ici, avec la dernière version
    publiée ; reprendre, arrêter et modifier sont demandés à l'appareil d'origine (sinon : la raison)."""
    from .. import partage, transcription
    s = await asyncio.to_thread(partage.lire, "transcription", tid)
    if s is None:
        raise HTTPException(404, "Transcription introuvable (supprimée sur son appareil ?).")
    if action == "exporter":
        format = "txt" if d.get("format") == "txt" else "md"
        debut = datetime.fromtimestamp(s["debut"]).strftime("%Y-%m-%d %Hh%M")
        f = transcription.dossier_export() / f"{debut} - {transcription.nom_de_fichier(s.get('titre', ''))}.{format}"
        texte = transcription.exporter(s, format)
        f.write_text(texte, encoding="utf-8")
        if d.get("ouvrir"):
            from ..plateforme import ouvrir_chemin
            ouvrir_chemin(str(f))
        return {"fichier": str(f), "texte": texte}
    if action == "ouvrir":
        raise HTTPException(400, f"Le fichier est sur {s.get('appareil')} : exporte la transcription pour l'avoir ici.")
    message = await asyncio.to_thread(_agir_a_distance, "transcription", tid, action, d)
    return {"message": message, "distant": True}


@router.delete("/api/transcriptions/{tid}")
def supprimer_transcription(tid: str, req: Request, fichier: bool = False):
    _verifier(req)
    from .. import transcription
    try:
        if transcription.lire(tid) is None:
            return {"ok": True, "message": _agir_a_distance("transcription", tid, "supprimer", {"fichier": fichier})}
        return {"ok": transcription.supprimer(tid, fichier)}
    except ValueError as e:
        raise HTTPException(400, str(e))
