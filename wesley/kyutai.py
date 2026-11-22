"""Voix Kyutai TTS : voix neuronale française très naturelle, 100 % locale et gratuite (modèle kyutai/tts-1.6b-en_fr,
poids sous licence CC-BY 4.0, code MIT).

Wesley est une appli empaquetée : on ne peut pas y ajouter de paquets Python. Le bouton « Télécharger » prépare donc un
environnement à part, dans le dossier de Wesley (RACINE/kyutai) :
  1. télécharge `uv` (gestionnaire d'environnements Python d'Astral) ;
  2. crée un Python 3.12 dédié et y installe Kyutai : `moshi_mlx` sur Mac (puces Apple), `moshi` + PyTorch CUDA sur
     Windows (carte graphique NVIDIA nécessaire : le script officiel ne vise que CUDA) ;
  3. télécharge le modèle (~4 Go) et les voix, puis fait un essai.
Ensuite, un petit serveur local (127.0.0.1:7781) charge le modèle une fois ; Wesley lui envoie chaque phrase à dire.
Le serveur s'arrête tout seul quand Wesley se ferme.
"""
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import requests

from .config import DONNEES_APPLI, RACINE

# hors du dossier du projet (souvent synchronisé par iCloud / OneDrive) : 4 Go n'ont rien à y faire
DOSSIER = DONNEES_APPLI / "kyutai"
VENV = DOSSIER / "venv"
SERVEUR = DOSSIER / "serveur_kyutai.py"
PRET = DOSSIER / "pret.json"
PORT = 7781
MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"

# voix françaises du dépôt kyutai/tts-voices (CML-TTS, lectures en français)
VOIX = [
    ("cml-tts/fr/10087_11650_000028-0002.wav", "Voix française 1"),
    ("cml-tts/fr/10177_10625_000134-0003.wav", "Voix française 2"),
    ("cml-tts/fr/10179_11051_000005-0001.wav", "Voix française 3"),
    ("cml-tts/fr/12080_11650_000047-0001.wav", "Voix française 4"),
    ("cml-tts/fr/12205_11650_000004-0002.wav", "Voix française 5"),
    ("cml-tts/fr/12977_10625_000037-0001.wav", "Voix française 6"),
    ("cml-tts/fr/1406_1028_000009-0003.wav", "Voix française 7"),
    ("cml-tts/fr/1591_1028_000108-0004.wav", "Voix française 8"),
    ("expresso/ex03-ex01_happy_001_channel1_334s.wav", "Voix anglaise expressive (par défaut de Kyutai)"),
]
VOIX_DEFAUT = VOIX[0][0]

ETAT = {"en_cours": False, "etape": "", "pct": 0, "erreur": ""}
_serveur = {"proc": None}
_verrou = threading.Lock()


# ---------- compatibilité ----------
def _nvidia() -> bool:
    try:
        return subprocess.run(["nvidia-smi"], capture_output=True, timeout=10,
                              creationflags=0x08000000 if WIN else 0).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def compatibilite() -> tuple[bool, str]:
    if MAC:
        if platform.machine() != "arm64":
            return False, "Kyutai sur Mac demande une puce Apple (M1 ou plus récente)."
        return True, ""
    if WIN:
        if not _nvidia():
            return False, ("Kyutai sur Windows demande une carte graphique NVIDIA (le modèle officiel ne tourne qu'avec CUDA). "
                           "Garde les voix Microsoft « Multilingual », très naturelles aussi.")
        return True, ""
    return False, "Système non pris en charge."


def installe() -> bool:
    return PRET.exists() and _python_venv().exists()


def etat() -> dict:
    ok, raison = compatibilite()
    return {"compatible": ok, "raison": raison, "installe": installe(), **ETAT,
            "voix": [{"id": v, "nom": n} for v, n in VOIX], "taille": "environ 4 Go" if MAC else "environ 7 Go",
            "actif": _serveur_repond()}


# ---------- installation ----------
def _python_venv() -> Path:
    return VENV / ("Scripts/python.exe" if WIN else "bin/python")


def _uv() -> Path:
    return DOSSIER / ("uv.exe" if WIN else "uv")


def _etape(texte: str, pct: int):
    ETAT.update(etape=texte, pct=pct)
    try:
        from . import web
        web.diffuser(type="kyutai", **ETAT)
    except Exception:
        pass


def _lancer(cmd: list, pct_fin: int, texte: str, timeout=3600):
    """Lance une commande en faisant avancer doucement la barre (les outils ne donnent pas de pourcentage)."""
    debut_pct = ETAT["pct"]
    proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            env={**os.environ, "UV_PYTHON_INSTALL_DIR": str(DOSSIER / "python"),
                                 "UV_CACHE_DIR": str(DOSSIER / "cache"), "HF_HOME": str(DOSSIER / "hf"),
                                 "PYTHONIOENCODING": "utf-8"},
                            creationflags=0x08000000 if WIN else 0)
    sortie, t0 = [], time.time()

    def lire():
        for ligne in proc.stdout:
            sortie.append(ligne.rstrip())
    threading.Thread(target=lire, daemon=True).start()
    while proc.poll() is None:
        ecoule = time.time() - t0
        if ecoule > timeout:
            proc.kill()
            raise RuntimeError(f"{texte} : trop long")
        # progression estimée qui ralentit en approchant de la fin de l'étape
        _etape(texte, int(debut_pct + (pct_fin - debut_pct) * (1 - 1 / (1 + ecoule / 60))))
        time.sleep(1)
    if proc.returncode != 0:
        raise RuntimeError(f"{texte} : échec\n" + "\n".join(sortie[-15:]))
    _etape(texte, pct_fin)


def _telecharger_uv():
    if _uv().exists():
        return
    nom = "uv-aarch64-apple-darwin.tar.gz" if MAC else "uv-x86_64-pc-windows-msvc.zip"
    r = requests.get(f"https://github.com/astral-sh/uv/releases/latest/download/{nom}", timeout=120)
    r.raise_for_status()
    DOSSIER.mkdir(parents=True, exist_ok=True)
    if nom.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            membre = next(m for m in z.namelist() if m.endswith("uv.exe"))
            _uv().write_bytes(z.read(membre))
    else:
        with tarfile.open(fileobj=io.BytesIO(r.content)) as t:
            membre = next(m for m in t.getmembers() if m.name.endswith("/uv") or m.name == "uv")
            _uv().write_bytes(t.extractfile(membre).read())
        _uv().chmod(0o755)


def installer():
    if ETAT["en_cours"]:
        raise RuntimeError("Installation déjà en cours.")
    ok, raison = compatibilite()
    if not ok:
        raise RuntimeError(raison)
    ETAT.update(en_cours=True, erreur="", pct=0, etape="Préparation…")
    threading.Thread(target=_installer, daemon=True, name="installation-kyutai").start()


def _installer():
    try:
        arreter_serveur()
        DOSSIER.mkdir(parents=True, exist_ok=True)
        _etape("Téléchargement de l'installateur Python…", 2)
        _telecharger_uv()
        _etape("Installation de Python 3.12…", 5)
        if not _python_venv().exists():
            _lancer([_uv(), "venv", "--python", "3.12", VENV], 15, "Installation de Python 3.12…")
        py = _python_venv()
        if MAC:
            _lancer([_uv(), "pip", "install", "--python", py, "moshi_mlx==0.2.12", "huggingface_hub", "numpy",
                     "sentencepiece", "sphn"], 40, "Installation de Kyutai (MLX)…")
        else:
            _lancer([_uv(), "pip", "install", "--python", py, "torch", "--index-url",
                     "https://download.pytorch.org/whl/cu124"], 35, "Installation de PyTorch (CUDA)…")
            _lancer([_uv(), "pip", "install", "--python", py, "moshi==0.2.11", "sphn", "numpy"], 45,
                    "Installation de Kyutai…")
        SERVEUR.write_text(SCRIPT_SERVEUR, encoding="utf-8")
        # 1er lancement : télécharge le modèle et les voix (Hugging Face), puis un essai de synthèse
        _lancer([py, SERVEUR, "--prechauffer", "--voix", VOIX_DEFAUT], 98,
                "Téléchargement du modèle (environ 4 Go) et essai de la voix…", timeout=3 * 3600)
        PRET.write_text(json.dumps({"date": time.strftime("%Y-%m-%d %H:%M"), "voix": VOIX_DEFAUT}), encoding="utf-8")
        _etape("Kyutai est prêt.", 100)
    except Exception as e:
        ETAT["erreur"] = str(e)[-1500:]
        _etape("Échec de l'installation.", ETAT["pct"])
    finally:
        ETAT["en_cours"] = False
        _etape(ETAT["etape"], ETAT["pct"])


def supprimer():
    arreter_serveur()
    shutil.rmtree(DOSSIER, ignore_errors=True)
    ETAT.update(en_cours=False, etape="", pct=0, erreur="")


# ---------- serveur local ----------
def _serveur_repond() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/sante", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def demarrer_serveur(attendre=120) -> bool:
    with _verrou:
        if _serveur_repond():
            return True
        if not installe():
            return False
        p = _serveur["proc"]
        if p is None or p.poll() is not None:
            (RACINE / "logs").mkdir(exist_ok=True)
            log = open(RACINE / "logs" / "kyutai.log", "a", encoding="utf-8")
            # stdin relié à Wesley : quand Wesley se ferme (même brutalement), le tube se ferme et le serveur s'arrête
            _serveur["proc"] = subprocess.Popen(
                [str(_python_venv()), str(SERVEUR), "--port", str(PORT), "--avec-parent"],
                stdin=subprocess.PIPE, stdout=log, stderr=log, env={**os.environ, "HF_HOME": str(DOSSIER / "hf"), "PYTHONIOENCODING": "utf-8"},
                creationflags=0x08000000 if WIN else 0)
        for _ in range(attendre * 2):   # chargement du modèle : quelques secondes à une minute
            if _serveur_repond():
                return True
            if _serveur["proc"].poll() is not None:
                return False
            time.sleep(0.5)
        return False


def arreter_serveur():
    p = _serveur.get("proc")
    if p is not None and p.poll() is None:
        p.terminate()
    _serveur["proc"] = None


def synthese(texte: str, voix: str = "") -> bytes:
    if not demarrer_serveur():
        raise RuntimeError("Voix Kyutai indisponible (non installée ou serveur arrêté).")
    r = requests.post(f"http://127.0.0.1:{PORT}/tts", json={"texte": texte, "voix": voix or VOIX_DEFAUT}, timeout=120)
    r.raise_for_status()
    return r.content


# ---------- script du serveur (exécuté par le Python de l'environnement Kyutai, pas par Wesley) ----------
SCRIPT_SERVEUR = r'''
"""Serveur local de synthèse Kyutai pour Wesley : POST /tts {"texte", "voix"} -> audio WAV 24 kHz."""
import argparse, io, json, os, sys, threading, time, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np

MAC = sys.platform == "darwin"
verrou = threading.Lock()


def charger():
    """Suit les scripts officiels tts_mlx.py / tts_pytorch.py (kyutai-labs/delayed-streams-modeling)."""
    if MAC:
        import mlx.core as mx, mlx.nn as nn, sentencepiece
        from moshi_mlx import models
        from moshi_mlx.models.tts import DEFAULT_DSM_TTS_REPO, DEFAULT_DSM_TTS_VOICE_REPO, TTSModel
        from moshi_mlx.utils.loaders import hf_get
        mx.random.seed(299792458)
        raw_config = hf_get("config.json", DEFAULT_DSM_TTS_REPO)
        with open(hf_get(raw_config), "r") as f:
            raw_config = json.load(f)
        mimi_weights = hf_get(raw_config["mimi_name"], DEFAULT_DSM_TTS_REPO)
        moshi_weights = hf_get(raw_config.get("moshi_name", "model.safetensors"), DEFAULT_DSM_TTS_REPO)
        tokenizer = hf_get(raw_config["tokenizer_name"], DEFAULT_DSM_TTS_REPO)
        lm_config = models.LmConfig.from_config_dict(raw_config)
        lm_config.transformer.max_seq_len = lm_config.transformer.context   # contournement officiel (moshi_mlx <= 0.3.0)
        model = models.Lm(lm_config)
        model.set_dtype(mx.bfloat16)
        model.load_pytorch_weights(str(moshi_weights), lm_config, strict=True)
        bits = int(os.environ.get("KYUTAI_QUANTIZE", "8"))   # 8 bits : assez rapide pour parler en direct
        if bits:
            nn.quantize(model.depformer, bits=bits)
            for layer in model.transformer.layers:
                nn.quantize(layer.self_attn, bits=bits)
                nn.quantize(layer.gating, bits=bits)
        text_tokenizer = sentencepiece.SentencePieceProcessor(str(tokenizer))
        audio_tokenizer = models.mimi.Mimi(models.mimi_202407(lm_config.generated_codebooks))
        audio_tokenizer.load_pytorch_weights(str(mimi_weights), strict=True)
        tts = TTSModel(model, audio_tokenizer, text_tokenizer, voice_repo=DEFAULT_DSM_TTS_VOICE_REPO, temp=0.6, cfg_coef=1,
                       max_padding=8, initial_padding=2, final_padding=2, padding_bonus=0, raw_config=raw_config)
        cfg_cond = None
        if tts.valid_cfg_conditionings:
            cfg_cond, tts.cfg_coef = tts.cfg_coef, 1.0
            no_text = no_prefix = False
        else:
            no_text = no_prefix = True

        def dire(texte, voix):
            entrees = [tts.prepare_script([texte])]
            voices = [tts.get_voice_path(voix)] if tts.multi_speaker else []
            attributs = [tts.make_condition_attributes(voices, cfg_cond)]
            morceaux = []

            def sur_trame(frame):
                if (frame == -1).any():
                    return
                pcm = tts.mimi.decode_step(frame[:, :, None])
                morceaux.append(np.array(mx.clip(pcm[0, 0], -1, 1)))
            tts.generate(entrees, attributs, cfg_is_no_prefix=no_prefix, cfg_is_no_text=no_text, on_frame=sur_trame)
            tts.mimi.reset_all() if hasattr(tts.mimi, "reset_all") else None
            return np.concatenate(morceaux, -1) if morceaux else np.zeros(1, dtype=np.float32), tts.mimi.sample_rate
        return dire
    import torch
    from moshi.models.loaders import CheckpointInfo
    from moshi.models.tts import DEFAULT_DSM_TTS_REPO, TTSModel
    tts = TTSModel.from_checkpoint_info(CheckpointInfo.from_hf_repo(DEFAULT_DSM_TTS_REPO), n_q=32, temp=0.6, device="cuda")

    def dire(texte, voix):
        entrees = tts.prepare_script([texte], padding_between=1)
        attributs = tts.make_condition_attributes([tts.get_voice_path(voix)], cfg_coef=2.0)
        resultat = tts.generate([entrees], [attributs])
        with tts.mimi.streaming(1), torch.no_grad():
            pcms = [np.clip(tts.mimi.decode(f[:, 1:, :]).cpu().numpy()[0, 0], -1, 1) for f in resultat.frames[tts.delay_steps:]]
        return np.concatenate(pcms, axis=-1), tts.mimi.sample_rate
    return dire


def en_wav(pcm, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(sr))
        w.writeframes((np.asarray(pcm, dtype=np.float32) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7781)
    ap.add_argument("--avec-parent", action="store_true")
    ap.add_argument("--voix", default="")
    ap.add_argument("--prechauffer", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    dire = charger()
    print(f"modèle chargé en {time.time() - t0:.0f} s", flush=True)
    if a.prechauffer:   # installation : télécharge tout et vérifie que la voix fonctionne
        pcm, sr = dire("Bonjour, je suis Wesley. Ma nouvelle voix est prête.", a.voix)
        print(f"essai OK : {len(pcm) / sr:.1f} s d'audio", flush=True)
        return

    class Gestion(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def do_GET(self):
            self.send_response(200 if self.path == "/sante" else 404); self.end_headers(); self.wfile.write(b"ok")

        def do_POST(self):
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
                with verrou:
                    pcm, sr = dire(d["texte"], d.get("voix") or a.voix)
                corps = en_wav(pcm, sr)
                self.send_response(200); self.send_header("content-type", "audio/wav")
                self.send_header("content-length", str(len(corps))); self.end_headers(); self.wfile.write(corps)
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Gestion)
    if a.avec_parent:   # Wesley fermé : son tube (stdin) se ferme, on s'arrête aussi
        def surveiller():
            try:
                sys.stdin.read()
            finally:
                os._exit(0)
        threading.Thread(target=surveiller, daemon=True).start()
    print(f"prêt sur le port {a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
'''
