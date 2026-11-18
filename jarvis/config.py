"""Configuration et emplacements des fichiers.

Trois emplacements :
- RESSOURCES : fichiers livrés avec l'appli (interface compilée, voix Piper). En lecture seule une fois installée.
- RACINE     : données propres à CE PC (config.json, clé API .env, journaux, captures, scan du PC).
               Dossier du projet en développement, %LOCALAPPDATA%\\Jarvis dans l'appli installée.
- PARTAGE    : mémoire commune à tous tes PC (souvenirs, historique, connecteurs).
               Par défaut OneDrive\\Jarvis : OneDrive la synchronise entre les machines.
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
    od = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if od and Path(od).exists():
        return Path(od)
    if sys.platform == "darwin":
        nuage = Path.home() / "Library" / "CloudStorage"
        candidats = sorted(nuage.glob("OneDrive*")) if nuage.exists() else []
        candidats += [Path.home() / "OneDrive"]
        for c in candidats:   # « OneDrive-Personnel » en priorité, puis un compte pro
            if c.exists():
                return c
    return None


def _partage_par_defaut() -> str:
    od = _onedrive()
    return str(od / "Jarvis") if od else str(RACINE / "partage")


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
    "dossier_partage": "",        # vide = OneDrive\Jarvis (ou un dossier local s'il n'y a pas OneDrive)
    "ecoute_fond": True,          # appli de bureau : écoute « Hey Jarvis » même fenêtre cachée
    "seuil_eveil": 0.5,           # sensibilité du mot d'activation (0-1, plus bas = plus sensible)
    "silence_fin": 5.0,           # s de silence avant d'envoyer ta demande (il t'écoute jusqu'au bout)
    "raccourci": "<ctrl>+<alt>+j",
}

CONFIG = {**DEFAUT, **(json.loads(FICHIER_CONFIG.read_text(encoding="utf-8")) if FICHIER_CONFIG.exists() else {})}
if not CONFIG["nom_utilisateur"]:
    CONFIG["nom_utilisateur"] = os.environ.get("USERNAME", "").capitalize() or "toi"


def sauver_config(cles=None):
    actuel = json.loads(FICHIER_CONFIG.read_text(encoding="utf-8")) if FICHIER_CONFIG.exists() else {}
    actuel.update({k: CONFIG[k] for k in (cles or CONFIG.keys())})
    FICHIER_CONFIG.write_text(json.dumps(actuel, ensure_ascii=False, indent=2), encoding="utf-8")


def dossier_partage() -> Path:
    p = Path(CONFIG.get("dossier_partage") or _partage_par_defaut())
    p.mkdir(parents=True, exist_ok=True)
    return p


PARTAGE = dossier_partage()

# Réglages communs à tous les PC (prénom, cerveau) : rangés dans le dossier partagé
CLES_PARTAGEES = ["nom_utilisateur", "cerveau", "claude_modele", "claude_effort", "silence_fin"]
PROFIL = PARTAGE / "profil.json"
try:
    CONFIG.update({k: v for k, v in json.loads(PROFIL.read_text(encoding="utf-8")).items() if k in CLES_PARTAGEES and v})
except (OSError, ValueError):
    if FICHIER_CONFIG.exists():   # 1er PC : on publie ses réglages pour les suivants
        PROFIL.write_text(json.dumps({k: CONFIG[k] for k in CLES_PARTAGEES}, ensure_ascii=False, indent=1), encoding="utf-8")


def sauver_profil():
    PROFIL.write_text(json.dumps({k: CONFIG[k] for k in CLES_PARTAGEES}, ensure_ascii=False, indent=1), encoding="utf-8")

# Première fois : la mémoire existante de ce PC rejoint le dossier partagé (sans rien écraser)
_ancienne = RACINE / "memoire"
if _ancienne.exists() and _ancienne.resolve() != (PARTAGE / "memoire").resolve():
    (PARTAGE / "memoire" / "historique").mkdir(parents=True, exist_ok=True)
    if (_ancienne / "faits.json").exists() and not (PARTAGE / "memoire" / "faits.json").exists():
        shutil.copy2(_ancienne / "faits.json", PARTAGE / "memoire" / "faits.json")
    for f in (_ancienne / "historique").glob("*.md") if (_ancienne / "historique").exists() else []:
        cible = PARTAGE / "memoire" / "historique" / (f.stem + f"__{MACHINE}.md" if "__" not in f.stem else f.name)
        if not cible.exists():
            shutil.copy2(f, cible)
        else:   # lignes écrites ici depuis la première copie : on les rajoute
            deja = cible.read_text(encoding="utf-8")
            nouvelles = f.read_text(encoding="utf-8")
            if nouvelles.startswith(deja) and len(nouvelles) > len(deja):
                with open(cible, "a", encoding="utf-8") as h:
                    h.write(nouvelles[len(deja):])
