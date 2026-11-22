"""Configuration et emplacements des fichiers.

Trois emplacements :
- RESSOURCES : fichiers livrés avec l'appli (interface compilée, voix Piper). En lecture seule une fois installée.
- RACINE     : données propres à CE PC (config.json, clé API .env, journaux, captures, scan du PC).
               Dossier du projet en développement, %LOCALAPPDATA%\\Wesley dans l'appli installée.
- PARTAGE    : cache local du compte connecté (souvenirs, historique, connecteurs, profil), synchronisé
               avec le serveur de comptes (wesley/compte.py). OneDrive ne sert plus qu'à importer l'ancienne mémoire.
"""
import json
import os
import platform
import shutil
import sys
from pathlib import Path

GELE = getattr(sys, "frozen", False)          # True dans l'appli .exe (PyInstaller)
RESSOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _donnees_appli() -> Path:
    """Dossier des données de l'appli sur cet appareil (~/Library/Application Support/Wesley ou
    %LOCALAPPDATA%\\Wesley). L'appli s'appelait Jarvis avant la 2.0.0 : l'ancien dossier est renommé une fois
    (renommage instantané, rien n'est copié). S'il est encore utilisé (ancienne version pas tout à fait fermée),
    on s'en sert tel quel et on réessaie au prochain lancement."""
    base = Path.home() / "Library" / "Application Support" if sys.platform == "darwin" \
        else Path(os.environ.get("LOCALAPPDATA", Path.home()))
    neuf, ancien = base / "Wesley", base / "Jarvis"
    if ancien.is_dir() and not neuf.exists():
        try:
            ancien.rename(neuf)
        except OSError:
            return ancien
    return neuf


DONNEES_APPLI = _donnees_appli()
RACINE = DONNEES_APPLI if GELE else Path(__file__).resolve().parents[1]
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
    "garder_modele": -1,          # -1 = garder le modèle en VRAM tant que Wesley tourne (sinon Ollama le décharge après 5 min)
    "cerveau": "claude",          # "claude", "ollama" (local) ou une IA compatible OpenAI de fournisseurs.py
    "claude_modele": "claude-sonnet-5-5",
    "claude_effort": "auto",      # auto = bas pour une conversation, élevé pour une vraie tâche, très élevé sur demande
    "openai_modele": "",
    "perso_url": "",              # cerveau « Autre (compatible OpenAI) » : adresse de l'API (ex. http://localhost:8000/v1)
    "langue": "fr",               # « fr » ou « en » : réponses de Wesley, reconnaissance vocale, voix, interface        # vide = le meilleur modèle disponible avec ta clé OpenAI       # low = le plus réactif à l'oral ; medium pour les tâches longues avec outils
    "serveur_comptes": "",        # vide = serveur de comptes officiel ; sinon l'adresse HTTPS de ton propre serveur
    "cle_appli": "",              # clé d'appli de ton propre serveur (WESLEY_CLE_APPLI dans serveur/.env)
    "ecoute_fond": True,          # appli de bureau : écoute « Hey Wesley » même fenêtre cachée
    "seuil_eveil": 0.5,           # sensibilité du mot d'activation (0-1, plus bas = plus sensible)
    "silence_fin": 2.5,           # s de silence avant d'envoyer ta demande (il écoute en continu jusque-là)
    "raccourci": "<ctrl>+<alt>+w",   # W comme Wesley (Ctrl+Alt+J du temps de Jarvis)
    "briefing_matin": True,       # au premier échange de la journée (5 h-12 h), Wesley commence par le briefing
    "conversation_suivie": True,  # après une réponse à l'oral, il écoute la suite quelques secondes sans « Wesley »
    "maj_auto": True,             # télécharge les mises à jour en fond et les installe au prochain démarrage
    "conseiller": True,           # cerveau Sonnet : consulte Opus sur les décisions difficiles (outil advisor)
    "recherche_web_native": True, # cerveau Claude : recherche et lecture web par Anthropic (sources citées)
}

CONFIG = {**DEFAUT, **(json.loads(FICHIER_CONFIG.read_text(encoding="utf-8")) if FICHIER_CONFIG.exists() else {})}
if not CONFIG["nom_utilisateur"]:
    CONFIG["nom_utilisateur"] = os.environ.get("USERNAME", "").capitalize() or "toi"


def _migrer_depuis_jarvis():
    """Réglages enregistrés du temps où l'appli s'appelait Jarvis (avant la 2.0.0)."""
    if not FICHIER_CONFIG.exists():
        return
    brut = json.loads(FICHIER_CONFIG.read_text(encoding="utf-8"))
    changes = []
    if brut.get("raccourci") == "<ctrl>+<alt>+j":   # l'ancien raccourci par défaut devient Ctrl+Alt+W
        CONFIG["raccourci"] = "<ctrl>+<alt>+w"
        changes.append("raccourci")
    if brut.get("depot_jarvis") and not brut.get("depot_wesley"):
        CONFIG["depot_wesley"] = brut["depot_jarvis"]
        changes.append("depot_wesley")
    if sys.platform == "darwin" and GELE and brut.get("autorisations_demandees") and not brut.get("autorisations_wesley"):
        # nouvel identifiant d'appli (com.abdel.wesley) : macOS a oublié les accès donnés à Jarvis, on les redemande
        CONFIG.update(autorisations_demandees=[], autorisation_automatisation="", autorisations_wesley=True)
        changes += ["autorisations_demandees", "autorisation_automatisation", "autorisations_wesley"]
    if changes:
        actuel = {**brut, **{k: CONFIG[k] for k in changes}}
        FICHIER_CONFIG.write_text(json.dumps(actuel, ensure_ascii=False, indent=2), encoding="utf-8")


try:
    _migrer_depuis_jarvis()
except (OSError, ValueError):
    pass


# ---------- trousseau de l'appareil (mots de passe, jetons) ----------
SERVICE_TROUSSEAU = "Wesley"
ANCIEN_SERVICE_TROUSSEAU = "Jarvis"   # nom du trousseau avant la 2.0.0


def lire_trousseau(nom: str) -> str:
    """Lit un secret du trousseau ; s'il n'existe que sous l'ancien nom (Jarvis), il est recopié sous le nouveau."""
    import keyring
    valeur = keyring.get_password(SERVICE_TROUSSEAU, nom)
    if valeur is None:
        valeur = keyring.get_password(ANCIEN_SERVICE_TROUSSEAU, nom)
        if valeur:
            try:
                keyring.set_password(SERVICE_TROUSSEAU, nom, valeur)
            except Exception:
                pass
    return valeur or ""


def ecrire_trousseau(nom: str, valeur: str):
    """Enregistre (ou efface si vide) un secret ; l'éventuelle copie sous l'ancien nom est effacée aussi."""
    import keyring
    if valeur:
        keyring.set_password(SERVICE_TROUSSEAU, nom, valeur)
    for service in ((ANCIEN_SERVICE_TROUSSEAU,) if valeur else (SERVICE_TROUSSEAU, ANCIEN_SERVICE_TROUSSEAU)):
        try:
            keyring.delete_password(service, nom)
        except Exception:
            pass


def sauver_config(cles=None):
    actuel = json.loads(FICHIER_CONFIG.read_text(encoding="utf-8")) if FICHIER_CONFIG.exists() else {}
    actuel.update({k: CONFIG[k] for k in (cles or CONFIG.keys())})
    FICHIER_CONFIG.write_text(json.dumps(actuel, ensure_ascii=False, indent=2), encoding="utf-8")


def _dossier_compte() -> Path:
    """Cache local du compte connecté (RACINE/comptes/<id>) ; la source de vérité est le serveur (wesley/compte.py)."""
    try:
        e = json.loads((RACINE / "compte.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e = {}
    uid = e.get("id")
    p = RACINE / "comptes" / ("local" if e.get("mode") == "local" else str(uid) if uid else "_sans_compte")
    (p / "memoire" / "historique").mkdir(parents=True, exist_ok=True)
    return p


PARTAGE = _dossier_compte()   # remplacé par compte.activer_dossiers() à la connexion

# Réglages communs à tous tes appareils (prénom, cerveau) : rangés dans ton compte
from .fournisseurs import CLES_MODELES   # « openai_modele », « gemini_modele »… : modèle choisi pour chaque IA
for _k in CLES_MODELES:
    CONFIG.setdefault(_k, "")
CLES_PARTAGEES = ["nom_utilisateur", "cerveau", "claude_modele", "claude_effort", *CLES_MODELES, "perso_url", "langue", "silence_fin"]
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
