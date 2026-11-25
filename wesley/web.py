"""Serveur de l'interface web de Wesley (FastAPI, 127.0.0.1 uniquement).

Lancer : wesley-web.bat  (ou .venv\\Scripts\\python.exe -m wesley.web)
Le front (React) est dans /interface ; `npm run build` le compile dans wesley/static.
"""
import asyncio
import os
import secrets
import shutil
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import ollama
import psutil
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import connecteurs, memoire, outils, tts
from .plateforme import MAC, WIN
from .agent import Wesley
from .config import CONFIG, sauver_config, sauver_profil
from .fournisseurs import CLES_MODELES, PAR_ID as IA, est_compatible

HOTE, PORT = "127.0.0.1", int(os.environ.get("WESLEY_PORT", 7777))
STATIC = Path(__file__).parent / "static"
JETON = secrets.token_urlsafe(24)
HOTES_OK = {"127.0.0.1", "localhost"}
CLES_CONFIG = ["modele", "modele_vision", "temperature", "reflexion", "num_ctx",
               "max_etapes_outils", "whisper_modele", "nom_utilisateur",
               "cerveau", "claude_modele", "claude_effort", "langue",
               "briefing_matin", "conversation_suivie", "maj_auto", "conseiller", "recherche_web_native",
               "transcription_resume_auto", "transcription_actions_afaire", "transcription_gpu",
               "memoire_semantique", "apprentissage_auto", "budget_mensuel", "modele_rapide_fond",
               "bilan_soir", "bilan_soir_heure",
               *CLES_MODELES, "perso_url"]

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
wesley: Wesley | None = None
verrou_tache = threading.Lock()
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
        wesley.arreter = True
        wesley.reset()
        diffuser(type="reset")
        diffuser(type="info", texte="Cerveau : " + _nom_cerveau())
        if CONFIG["cerveau"] != "ollama":
            threading.Thread(target=Wesley.liberer, daemon=True).start()   # rend la VRAM
        else:
            threading.Thread(target=wesley.prechauffer, daemon=True).start()
    sauver_config(CLES_CONFIG)
    sauver_profil()   # prénom et cerveau : communs à tous les PC
    return {"ok": True}



# ---------- cerveaux compatibles OpenAI (OpenAI, Gemini, Mistral, DeepSeek, Grok, OpenRouter, LM Studio…) ----------
def _ia():
    from . import openai_cerveau
    return openai_cerveau


def _nom_modele() -> str:
    c = CONFIG.get("cerveau")
    if c == "claude":
        return CONFIG["claude_modele"]
    if est_compatible(c):
        return CONFIG.get(f"{c}_modele") or IA[c]["nom"]
    return CONFIG["modele"]


def _nom_cerveau() -> str:
    c = CONFIG.get("cerveau")
    if c == "claude":
        return "Claude " + CONFIG["claude_modele"]
    if est_compatible(c):
        return IA[c]["nom"] + (" " + CONFIG.get(f"{c}_modele") if CONFIG.get(f"{c}_modele") else "")
    return "Ollama local " + CONFIG["modele"]


def _fid(fid: str) -> str:
    if fid not in IA:
        raise HTTPException(404, "IA inconnue.")
    return fid


# ---------- application de bureau (fenêtre, démarrage, écoute de fond) ----------
APPLI = {"active": False, "afficher": None, "ecoute": None, "quitter": None, "relancer_raccourcis": None, "icone": None}   # renseigné par wesley/app.py
PAROLE = {"actif": False, "depuis": 0.0}   # la fenêtre signale quand Wesley parle (pour l'écoute de fond)


def wesley_occupe() -> bool:
    """Wesley parle ou travaille : l'écoute de fond guette « stop » même mêlé à sa voix."""
    parle = PAROLE["actif"] and time.time() - PAROLE["depuis"] < 300   # sécurité si la fenêtre disparaît
    return parle or verrou_tache.locked()


def stop_vocal():
    """« Wesley, stop » ou Ctrl+Alt+S : coupe la voix et la tâche en cours."""
    if wesley is not None:
        wesley.arreter = True
    outils.arreter_tout()
    PAROLE["actif"] = False
    diffuser(type="stop_voix")
    print("  Stop demandé")


# ---------- confirmations (ex : commande qui modifie un serveur SSH en mode « confirmation ») ----------
_confirmations: dict = {}


def demander_confirmation(titre: str, detail: str = "", delai: float = 180) -> bool:
    """Affiche « Autoriser / Refuser » dans la fenêtre de Wesley et attend la réponse (refus si STOP ou sans réponse)."""
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


def demander_texte(titre: str, detail: str = "", delai: float = 300) -> str:
    """Wesley a besoin d'une info (ex : le code reçu par SMS) : champ de saisie dans sa fenêtre, réponse attendue."""
    import uuid
    cid = uuid.uuid4().hex[:10]
    attente = {"ev": threading.Event(), "ok": False, "texte": ""}
    _confirmations[cid] = attente
    if APPLI.get("afficher"):
        try:
            APPLI["afficher"]()
        except Exception:
            pass
    debut = time.time()
    try:
        while time.time() - debut < delai and not attente["ev"].is_set():
            if outils.ARRET.is_set():
                break
            diffuser(type="confirmation", id=cid, titre=titre, detail=detail[:2000], saisie=True)
            attente["ev"].wait(2)
    finally:
        _confirmations.pop(cid, None)
        diffuser(type="confirmation_fin", id=cid)
    return attente["texte"] if attente["ok"] else ""


@app.post("/api/confirmation")
async def repondre_confirmation(req: Request):
    _verifier(req)
    d = await req.json()
    c = _confirmations.get(d.get("id"))
    if c:
        c["ok"] = bool(d.get("ok"))
        c["texte"] = str(d.get("texte", ""))[:500]
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


# ---------- conversation ----------
def _conversation():
    """Conversation en cours au format de l'interface (pour restaurer après un rechargement)."""
    if wesley.avec_claude:
        from . import claude
        return claude.conversation_ui(wesley.histo_claude)
    if wesley.avec_openai:
        from . import openai_cerveau
        return openai_cerveau.conversation_ui(wesley.histo_openai)
    out = []
    for m in wesley.messages[1:]:
        if m["role"] == "user":
            out.append({"role": "user", "texte": m["content"]})
        elif m["role"] == "assistant":
            if not out or out[-1]["role"] != "wesley":
                out.append({"role": "wesley", "blocs": []})
            if m.get("content"):
                out[-1]["blocs"].append({"type": "texte", "texte": m["content"]})
            for tc in m.get("tool_calls") or []:
                out[-1]["blocs"].append({"type": "outil", "nom": tc["function"]["name"],
                                         "args": {k: str(v)[:200] for k, v in tc["function"]["arguments"].items()},
                                         "resultat": None})
        elif m["role"] == "tool" and out and out[-1]["role"] == "wesley":
            for b in out[-1]["blocs"]:
                if b["type"] == "outil" and b["resultat"] is None:
                    b["resultat"] = m["content"][:600]
                    break
    return out


def _avec_briefing(texte: str) -> str:
    """Premier échange de la journée (le matin) : Wesley commence par le briefing, puis répond."""
    if not CONFIG.get("briefing_matin", True):
        return texte
    from datetime import datetime
    from . import config
    n = datetime.now()
    f = config.PARTAGE / "briefing.txt"
    jour = n.strftime("%Y-%m-%d")
    try:
        deja = f.read_text(encoding="utf-8").strip() == jour
    except OSError:
        deja = False
    if deja or not 5 <= n.hour < 12 or len(texte) < 2:
        return texte
    f.write_text(jour, encoding="utf-8")
    return ("[Premier échange de la journée : commence par le briefing du matin (outil briefing_du_jour), court, "
            f"puis réponds à ce qui suit s'il y a une vraie demande]\n{texte}")


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
        demande = _avec_briefing(texte)
        rep = wesley.demander(demande, sur_texte=lambda t: diffuser(type="texte", t=t),
                              sur_pensee=lambda t: diffuser(type="pensee", t=t), sur_outil=sur_outil)
        diffuser(type="fin", texte=rep)
    except Exception as e:
        diffuser(type="erreur", texte=f"Erreur : {e}")
        import traceback as _tb
        from . import rapport
        rapport.noter(_tb.format_exc(), contexte=texte[:200])
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
                wesley.arreter = True
                outils.arreter_tout()
            elif t == "parle":
                avant = PAROLE["actif"]
                PAROLE.update(actif=bool(m.get("actif")), depuis=time.time())
                if avant and not PAROLE["actif"]:
                    from .api.voix import _ecouter_suite_bientot
                    _ecouter_suite_bientot()
            elif t == "reset":
                wesley.arreter = True
                wesley.reset()
                diffuser(type="reset")
                threading.Thread(target=wesley.prechauffer, daemon=True).start()
            elif t == "scan":
                await asyncio.to_thread(memoire.scanner_systeme)
                wesley.reset()
                diffuser(type="reset")
                diffuser(type="info", texte="PC re-scanné, nouvelle conversation.")
                threading.Thread(target=wesley.prechauffer, daemon=True).start()
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(q)
        tache.cancel()


# ---------- routes de l'API, une par domaine (wesley/api/*) : avant le front, qui attrape tout le reste ----------
from .api import (cerveaux as _r_cerveaux, compte as _r_compte, connecteurs as _r_connecteurs,  # noqa: E402
                  memoire as _r_memoire, systeme as _r_systeme, taches as _r_taches, tickets as _r_tickets,
                  transcriptions as _r_transcriptions, voix as _r_voix)
for _r in (_r_systeme, _r_memoire, _r_voix, _r_cerveaux, _r_connecteurs, _r_compte, _r_taches, _r_transcriptions,
           _r_tickets):
    app.include_router(_r.router)
# noms utilisés par le reste de Wesley (web.xxx)
from .api.transcriptions import _lancer_transcription, lancer_resume, reprendre_transcription  # noqa: E402,F401
from .api.voix import commande_vocale, transcrire_rapide  # noqa: E402,F401


# ---------- fichiers du front (compilé par Vite) ----------
if (STATIC / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")


@app.get("/{chemin:path}", response_class=HTMLResponse)
def front(chemin: str):
    f = (STATIC / chemin).resolve()
    # Sans « no-cache », la fenêtre (WebKit sur Mac, WebView2 sur Windows) gardait l'ancienne page en cache :
    # après une mise à jour, l'appli tournait en nouvelle version mais affichait l'ancienne interface.
    # Les fichiers de assets/ changent de nom à chaque version : eux peuvent rester en cache.
    if chemin and f.is_file() and STATIC.resolve() in f.parents:
        return FileResponse(f, headers={"Cache-Control": "no-cache"})
    index = STATIC / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Interface non compilée</h1><p>Lance <code>npm run build</code> dans le dossier interface.</p>", 503)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


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
    global wesley
    from . import compte

    def apres_synchro(changements):
        """Un autre appareil a modifié le compte : Wesley tient compte des nouveaux souvenirs dès maintenant."""
        if wesley is not None and (changements["faits_texte"] or changements["reglages"]):
            from .agent import prompt_systeme
            wesley.messages[0]["content"] = prompt_systeme()
        if changements["connecteurs"]:
            threading.Thread(target=connecteurs.demarrer_tous, daemon=True).start()
        diffuser(type="memoire_maj", **changements)
    compte.ecouteurs.append(apres_synchro)
    compte.au_demarrage()   # mémoire, connecteurs et profil du compte connecté (cache local + synchro)
    from . import automatisations, taches
    automatisations.demarrer()   # surveille tes boîtes mail pour les règles « quand je reçois… »
    taches.au_demarrage()        # tâches de fond coupées par la fermeture : « interrompues » (bouton Reprendre)
    from . import transcription
    transcription.ecouteurs.append(lambda tid: diffuser(type="transcription_maj", id=tid))
    transcription.au_demarrage()  # transcription coupée par la fermeture : marquée « interrompue »
    from . import serveur_mcp
    serveur_mcp.au_demarrage()   # Wesley comme serveur MCP, si activé (Réglages › Application)
    from . import partage
    partage.demarrer()           # tâches et transcriptions visibles (chiffrées) sur tes autres appareils
    from . import consolidation, semantique
    memoire.indexer_en_fond()    # mémoire par le sens : modèle téléchargé une fois, vecteurs calculés à l'avance
    consolidation.demarrer()     # chaque jour : doublons fusionnés, contradictions à confirmer, résumé de la semaine
    from . import annulation, documents
    threading.Thread(target=annulation.menage, daemon=True).start()   # copies de plus de 14 jours
    documents.demarrer()         # tes documents (PDF, Word…) indexés par le sens, mis à jour toutes les 30 min
    partage.ecouteurs.append(lambda: (diffuser(type="tache_maj", id=""), diffuser(type="transcription_maj", id="")))
    from . import agents_code
    agents_code.surveiller()     # prévient si Claude Code / Codex ne sont plus connectés
    if CONFIG.get("cerveau") == "ollama":
        _demarrer_ollama()
    if not memoire.SYSTEME.exists():
        print("  Premier lancement : scan du PC...")
        memoire.scanner_systeme()
    wesley = Wesley()
    psutil.cpu_percent(interval=None)

    def prechauffer_tout():
        t0 = time.time()
        try:
            connecteurs.demarrer_tous()
            print(f"  Connecteurs : {len(connecteurs.INSTANCES)}")
        except Exception as e:
            print(f"  ! Connecteurs : {e}")
        wesley.prechauffer()
        print(f"  Modèle prêt ({time.time() - t0:.0f} s)")
        try:
            from .api.voix import _modele_whisper, _whisper_verrou
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
    # Un seul Wesley à la fois : deux instances s'écrasent mutuellement le cache d'Ollama
    # et chaque question doit alors relire tout le prompt (~6-30 s au lieu de 0,2 s).
    if _deja_lance(url):
        print(f"\n  Wesley tourne déjà -> {url} (j'ouvre l'interface existante)\n")
        if ouvrir:
            webbrowser.open(url)
        return
    preparer()
    print(f"\n  Wesley en ligne -> {url}\n  (Ctrl+C pour arrêter)\n")
    if ouvrir:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host=HOTE, port=PORT, log_level="warning")
    finally:
        print("Je mémorise ce que j'ai appris...")
        try:
            for f in wesley.extraire_souvenirs():
                print(" ", f)
        except Exception:
            pass
        Wesley.liberer()   # rend la VRAM (jeux, etc.)


if __name__ == "__main__":
    import sys
    main(ouvrir="--sans-navigateur" not in sys.argv)
