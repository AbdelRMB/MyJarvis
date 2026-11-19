"""Configuration et emplacements des fichiers.

Trois emplacements :
- RESSOURCES : fichiers livrés avec l'appli (interface compilée, voix Piper). En lecture seule une fois installée.
- RACINE     : données propres à CE PC (config.json, clé API .env, journaux, captures, scan du PC).
               Dossier du projet en développement, %LOCALAPPDATA%\\Jarvis dans l'appli installée.
- PARTAGE    : cache local du compte connecté (souvenirs, historique, connecteurs, profil), synchronisé
               avec le serveur de comptes (jarvis/compte.py). OneDrive ne sert plus qu'à importer l'ancienne mémoire.
"""
import json
import os
import platform
import shutil
import sys
from pathlib import Path

GELE = getattr(sys, "frozen", False)          # True dans l'appli .exe (PyInstaller)
RESSOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
if not GELE:
    RACINE = Path(__file__).resolve().parents[1]
elif sys.platform == "darwin":
    RACINE = Path.home() / "Library" / "Application Support" / "Jarvis"
else:
    RACINE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Jarvis"
RACINE.mkdir(parents=True, exist_ok=True)
FICHIER_CONFIG = RACINE / "config.json"
MACHINE = (platform.node() or "PC").removesuffix(".local")


def _onedrive():
    """Dossier OneDrive : variable d'environnement (Windows) ou emplacements de l'appli OneDrive pour Mac."""
    # Compte PERSONNEL en priorité partout, sinon un PC avec un OneDrive école/pro et un Mac avec le perso
    # n'utiliseraient pas le même dossier (%OneDrive% = compte pro sur Windows quand il y en a un).
    for var in ("OneDriveConsumer", "OneDrive"):
        od = os.environ.get(var)
        if od and Path(od).exists():
            return Path(od)
    if sys.platform == "darwin":
        nuage = Path.home() / "Library" / "CloudStorage"
        tous = sorted(nuage.glob("OneDrive*")) if nuage.exists() else []
        perso = [c for c in tous if c.name in ("OneDrive-Personal", "OneDrive-Personnel")]
        for c in perso + tous + [Path.home() / "OneDrive"]:
            if c.exists():
                return c
    return None


DEFAUT = {
    "modele": "qwen3.5:9b",
    "modele_vision": "qwen3.5:9b",
    "num_ctx": 16384,
    "temperature": 0.6,
    "reflexion": False,
    "max_etapes_outils": 25,
    "historique_max_messages": 40,
    "voix_tts": True,
    "whisper_modele": "small",
    "nom_utilisateur": "",
    "garder_modele": -1,          # -1 = garder le modèle en VRAM tant que Jarvis tourne (sinon Ollama le décharge après 5 min)
    "cerveau": "claude",          # "claude" (API Anthropic) ou "ollama" (local)
    "claude_modele": "claude-sonnet-5-5",
    "claude_effort": "low",       # low = le plus réactif à l'oral ; medium pour les tâches longues avec outils
    "serveur_comptes": "",        # vide = serveur de comptes officiel ; sinon l'adresse HTTPS de ton propre serveur
    "cle_appli": "",              # clé d'appli de ton propre serveur (JARVIS_CLE_APPLI dans serveur/.env)
    "ecoute_fond": True,          # appli de bureau : écoute « Hey Jarvis » même fenêtre cachée
    "seuil_eveil": 0.5,           # sensibilité du mot d'activation (0-1, plus bas = plus sensible)
    "silence_fin": 2.5,           # s de silence avant d'envoyer ta demande (il écoute en continu jusque-là)
    "raccourci": "<ctrl>+<alt>+j",
}

CONFIG = {**DEFAUT, **(json.loads(FICHIER_CONFIG.read_text(encoding="utf-8")) if FICHIER_CONFIG.exists() else {})}
if not CONFIG["nom_utilisateur"]:
    CONFIG["nom_utilisateur"] = os.environ.get("USERNAME", "").capitalize() or "toi"


def sauver_config(cles=None):
    actuel = json.loads(FICHIER_CONFIG.read_text(encoding="utf-8")) if FICHIER_CONFIG.exists() else {}
    actuel.update({k: CONFIG[k] for k in (cles or CONFIG.keys())})
    FICHIER_CONFIG.write_text(json.dumps(actuel, ensure_ascii=False, indent=2), encoding="utf-8")


def _dossier_compte() -> Path:
    """Cache local du compte connecté (RACINE/comptes/<id>) ; la source de vérité est le serveur (jarvis/compte.py)."""
    try:
        uid = json.loads((RACINE / "compte.json").read_text(encoding="utf-8")).get("id")
    except (OSError, ValueError):
        uid = None
    p = RACINE / "comptes" / (str(uid) if uid else "_sans_compte")
    (p / "memoire" / "historique").mkdir(parents=True, exist_ok=True)
    return p


PARTAGE = _dossier_compte()   # remplacé par compte.activer_dossiers() à la connexion

# Réglages communs à tous tes appareils (prénom, cerveau) : rangés dans ton compte
CLES_PARTAGEES = ["nom_utilisateur", "cerveau", "claude_modele", "claude_effort", "silence_fin"]
PROFIL = PARTAGE / "profil.json"
try:
    CONFIG.update({k: v for k, v in json.loads(PROFIL.read_text(encoding="utf-8")).items() if k in CLES_PARTAGEES and v})
except (OSError, ValueError):
    pass


def sauver_profil():
    profil = {k: CONFIG[k] for k in CLES_PARTAGEES}
    PROFIL.write_text(json.dumps(profil, ensure_ascii=False, indent=1), encoding="utf-8")
    from . import compte
    compte.document_modifie("profil", profil)
