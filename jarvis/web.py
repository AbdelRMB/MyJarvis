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
from .agent import Jarvis
from .config import CONFIG, MACHINE, PARTAGE, RACINE, sauver_config, sauver_profil

HOTE, PORT = "127.0.0.1", int(os.environ.get("JARVIS_PORT", 7777))
STATIC = Path(__file__).parent / "static"
JETON = secrets.token_urlsafe(24)
HOTES_OK = {"127.0.0.1", "localhost"}
CLES_CONFIG = ["modele", "modele_vision", "temperature", "reflexion", "num_ctx",
               "max_etapes_outils", "whisper_modele", "nom_utilisateur",
               "cerveau", "claude_modele", "claude_effort"]

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
    return {"jeton": JETON, "nom": CONFIG["nom_utilisateur"], "nb_outils": len(outils.OUTILS)}


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
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip().split("\n")[0]
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
    disque = psutil.disk_usage("C:\\")
    return {"cpu": psutil.cpu_percent(interval=None), "ram": ram.percent, "ram_used": ram.used / 2**30,
            "ram_total": ram.total / 2**30, "disque": disque.percent, "disque_libre": disque.free / 2**30,
            "gpu": _gpu(), "ollama": ollama_ok, "charges": charges, "cerveau": CONFIG.get("cerveau", "ollama"),
            "modele": CONFIG["claude_modele"] if CONFIG.get("cerveau") == "claude" else CONFIG["modele"],
            "cle_claude_manquante": CONFIG.get("cerveau") == "claude" and not __import__("os").environ.get("ANTHROPIC_API_KEY")
            and not (RACINE / ".env").exists(),
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
        diffuser(type="info", texte="Cerveau : " + ("Claude " + CONFIG["claude_modele"] if CONFIG["cerveau"] == "claude"
                                                     else "Ollama local " + CONFIG["modele"]))
        if CONFIG["cerveau"] == "claude":
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
    _verifier(req)
    fait = (await req.json()).get("fait", "")
    faits = memoire._charger()
    reste = [x for x in faits if x["fait"] != fait]
    memoire._sauver(reste)
    return {"supprimes": len(faits) - len(reste)}


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
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(CONFIG["whisper_modele"], device="cpu", compute_type="int8")
        _whisper_nom = CONFIG["whisper_modele"]
    return _whisper


def _transcrire(audio: np.ndarray, langue: str) -> str:
    with _whisper_verrou:
        segs, _ = _modele_whisper().transcribe(audio, language=langue or None, vad_filter=True, beam_size=1,
                                               initial_prompt="Jarvis, ouvre VS Code.")
        return " ".join(s.text for s in segs).strip()


_rapide, _rapide_verrou = None, threading.Lock()


def transcrire_rapide(audio: np.ndarray) -> str:
    """Petit Whisper (« base ») pour reconnaître le nom « Jarvis » dans l'écoute de fond : ~0,3 s par phrase."""
    global _rapide
    with _rapide_verrou:
        if _rapide is None:
            from faster_whisper import WhisperModel
            _rapide = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)
        segs, _ = _rapide.transcribe(audio, language="fr", beam_size=1, vad_filter=False,
                                     initial_prompt="Jarvis, ouvre Discord.", condition_on_previous_text=False)
        return " ".join(s.text for s in segs).strip()


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
APPLI = {"active": False, "afficher": None, "ecoute": None}   # renseigné par jarvis/app.py


@app.post("/api/fenetre/afficher")
def afficher_fenetre(req: Request):
    _verifier(req)
    if APPLI["afficher"]:
        APPLI["afficher"]()
    return {"ok": bool(APPLI["afficher"])}


@app.get("/api/appli")
def etat_appli(req: Request):
    _verifier(req)
    from . import demarrage
    return {"appli": APPLI["active"], "demarrage_auto": demarrage.est_actif(), "machine": MACHINE,
            "dossier_partage": str(PARTAGE), "ecoute_fond": CONFIG.get("ecoute_fond", True),
            "ecoute_active": bool(APPLI["ecoute"] and APPLI["ecoute"].actif),
            "seuil_eveil": CONFIG.get("seuil_eveil", 0.5), "raccourci": CONFIG.get("raccourci")}


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
        texte = _transcrire(audio, "fr")
    except Exception as e:
        diffuser(type="vocal", etat="fin")
        diffuser(type="erreur", texte=f"Transcription impossible : {e}")
        return
    diffuser(type="vocal", etat="fin", texte=texte)
    from .ecoute import RX_NOM
    texte = RX_NOM.sub("", texte).strip()
    if len(texte) >= 2:
        if re.match(r"^(stop|arr[êe]te|annule|tais[- ]toi)\b", texte, re.I):
            jarvis.arreter = True
            diffuser(type="stop_voix")
            return
        threading.Thread(target=executer, args=(texte,), daemon=True).start()


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
    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    for _ in range(30):
        time.sleep(0.5)
        try:
            ollama.list(); return
        except Exception:
            pass


def preparer():
    global jarvis
    if CONFIG.get("cerveau") != "claude":
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
