# J.A.R.V.I.S. — assistant local (Ollama + qwen3.5:9b)

Lancer :
- **Application** : `lanceur.pyw` (développement) ou Jarvis installé (voir plus bas)
- **Interface web** : double-clic sur `jarvis-web.bat` → ouvre http://127.0.0.1:7777 (démarre Ollama si besoin)
- Terminal : `jarvis.bat` (ou `jarvis.bat --voix`)

## Interface web (React + TypeScript + Tailwind)
Code source dans `interface/`, compilé dans `jarvis/static/` et servi par `jarvis/web.py` (FastAPI).

Écrans : **Assistant** (chat en streaming, cartes d'outils dépliables, réacteur animé, panneau audio et actions en direct), **Historique**, **Mémoire** (ajouter / oublier des souvenirs), **Activité** (journal `logs/actions.log`), **Arsenal** (les 52 outils), **Système** (jauges, courbes, VRAM d'Ollama), **Réglages** (micro, voix, cerveau, interface).

- Micro : périphérique, gain, seuil (VU-mètre), silence, anti-bruit/écho, test avec réécoute + transcription
- Modes : **Appui** (Espace maintenu), **Auto** (mains libres), **« Jarvis »** (mot d'activation, « Jarvis, stop »)
- Raccourcis : Échap = stop · Ctrl+K = saisie · Alt+1…7 = écrans
- Sécurité : 127.0.0.1 uniquement, Host vérifié (anti DNS-rebinding), jeton par session, Origin vérifiée sur la WebSocket

Développer l'interface :
```
cd interface
npm run dev        # http://localhost:5173, branché sur le serveur Python (lancer jarvis-web.bat à côté)
npm run build      # recompile jarvis/static
```

## Application de bureau (installée)
- **Installer** : `installateur\JarvisSetup-1.0.0.exe` (sans droits admin). Coche « Lancer au démarrage de Windows ».
- **Au démarrage du PC** : Jarvis se lance caché (icône près de l'horloge), sans fenêtre.
- **Le faire taire** : « Jarvis, stop » (même pendant qu'il parle) ou `Ctrl+Alt+S`, même fenêtre cachée.
- **L'appeler** : dis « Jarvis, ouvre Discord » (d'une traite) ou « Jarvis » puis ta demande — ou `Ctrl+Alt+J`, ou double-clic sur l'icône. La fenêtre apparaît.
- **Fermer la fenêtre** la cache seulement. Quitter : clic droit sur l'icône > Quitter.
- Écoute de fond 100 % locale : openWakeWord (« Hey Jarvis » à l'anglaise) + petit Whisper qui reconnaît « Jarvis » en français. Rien n'est envoyé avant que le nom soit reconnu.
- Données de ce PC : `%LOCALAPPDATA%\Jarvis` (config, clé API `.env`, journaux `logs\jarvis.log`).

## macOS
Le même code tourne sur Mac (outils adaptés : terminal zsh, applis de /Applications, fenêtres via AppleScript, Cmd au lieu de Ctrl, LaunchAgent au démarrage, Trousseau pour les mots de passe).
- **Construire sur un Mac** : copie le dossier du projet (sans `.venv`, `dist`, `node_modules`), puis `bash construire-mac.sh` -> `installateur/Jarvis-<version>-mac-<arm64|x86_64>.dmg`.
- **Ou sans Mac** : pousse le projet sur un dépôt GitHub privé, onglet Actions > « Jarvis macOS » > Run workflow -> le .dmg (puce Apple et Intel) est dans les Artifacts.
- **Installer** : ouvre le .dmg, glisse Jarvis dans Applications, puis **clic droit > Ouvrir** la première fois (appli non signée par Apple). Autorise ensuite le micro, l'Accessibilité (raccourcis, souris, clavier) et l'Enregistrement de l'écran (vision) dans Réglages Système > Confidentialité et sécurité.
- Icône dans la barre des menus ; appel : « Jarvis, … » ou ⌃ Ctrl + ⌥ Option + J ; arrêt : « Jarvis, stop » ou ⌃ Ctrl + ⌥ Option + S.

## Comptes : une mémoire par personne, sur tous ses appareils
- Au lancement : créer un compte ou se connecter. Mémoire, historique, connecteurs et réglages sont dans le compte (serveur `serveur/`, hébergé sur le VPS : https://jarvis.abdelrahimriche.com, réservé à l'appli).
- Clé API et mots de passe des connecteurs : chiffrés sur l'appareil avec le mot de passe du compte (le serveur ne peut pas les lire).
- 1re connexion sur un appareil : sa mémoire existante (ancienne version, OneDrive) est versée dans le compte, sans doublon.
- Serveur : `serveur/app.py` (FastAPI + SQLite, Docker). Redéployer : `rsync` de `serveur/` vers `~/jarvis-serveur/` sur le VPS puis `docker compose up -d --build`.

## Connecteurs
Écran **Connecteurs** : Gmail (mot de passe d'application), autre messagerie IMAP, agenda (lien iCal secret), GitHub, Notion, et **n'importe quel serveur MCP** (Spotify, Slack, Home Assistant…). Leurs outils s'ajoutent à Jarvis.

## Reconstruire l'installateur
`construire.bat` (interface Vite -> PyInstaller `jarvis.spec` -> Inno Setup `installateur.iss`). Pour une nouvelle version, change `#define Version` dans `installateur.iss`.

## Cerveau : Claude (API) ou Ollama (local)
Réglages > Cerveau, bascule en un clic (nouvelle conversation à chaque changement).
- **Claude** (par défaut : Sonnet 5.5, effort bas) : plus intelligent, ne charge pas la carte graphique (la vision passe aussi par Claude). Payant à l'usage ; messages, souvenirs et résultats d'outils sont envoyés à Anthropic.
  - Clé API : platform.claude.com > API keys, à coller dans Réglages > Cerveau (enregistrée dans `.env`, jamais ailleurs). L'abonnement Claude Pro n'inclut pas de crédit API.
  - Cache de prompt activé (instructions + outils relus ~10x moins cher), secours automatique si le modèle refuse une demande.
  - Dépenses estimées : Réglages > Cerveau et `logs/couts.json`.
- **Ollama** : gratuit, 100 % privé, sur la carte graphique.

## Vitesse & voix
- **Voix** : Microsoft neuronal (Henri par défaut, en ligne, très naturel) ou **Piper** 100 % local (`voix/fr_FR-tom-medium`). Réglages > Voix. Jarvis parle phrase par phrase pendant qu'il écrit ; sans Internet il bascule sur Piper.
- **Rapidité** : le modèle reste chargé en VRAM tant que Jarvis tourne (`garder_modele: -1`) et le prompt est pré-lu au démarrage → premier mot en ~0,2-0,6 s. À la fermeture, la VRAM est rendue.
- **Un seul Jarvis à la fois** : deux instances s'écrasent le cache d'Ollama (chaque question relit tout le prompt). `jarvis-web.bat` ouvre l'instance existante au lieu d'en lancer une 2e.
- **Carte graphique pleine** (jeux, LDPlayer, Wallpaper Engine…) : le modèle déborde sur le CPU. Système > « Libérer la VRAM » avant de jouer ; Réglages > Interface > animations « Désactivées » si besoin.
- Diagnostic : `logs/perf.log` (une ligne par appel au modèle : tokens relus, durées, vitesse).

## Ce qu'il sait faire (52 outils, sans demander de permission)
- **Système** : PowerShell, scripts Python, ouvrir n'importe quelle appli/fichier/URL, processus, infos PC, verrouiller/éteindre
- **Fichiers** : lire, écrire, modifier, chercher (nom + contenu), déplacer, copier, supprimer (→ corbeille)
- **Souris/clavier** : déplacer, cliquer, glisser, défiler, taper du texte, raccourcis, média/volume, presse-papier
- **Fenêtres** : lister, activer, maximiser, fermer, cliquer un bouton par son texte (UI Automation)
- **Vision** : regarder l'écran, trouver un élément et cliquer dessus, analyser une image
- **Code** : ouvrir dans VS Code (fichier:ligne), palette de commandes, git, créer un projet (Vite/Next/Node/Python)
- **Web** : recherche DuckDuckGo, actus, lire une page, météo, télécharger
- **Mémoire** : faits sur toi (`memoire/faits.json`), scan du PC (`memoire/systeme.md`), historique des conversations (`memoire/historique/`). À la sortie (`/quit`), il extrait tout seul ce qu'il a appris.
- **Divers** : date/heure, rappels, notifications, calculs

## Commandes
`/voix` `/think` `/memoire` `/scan` `/reset` `/quit` `/aide`

## Sécurité
- **Arrêt d'urgence** : souris dans le coin haut-gauche de l'écran → pyautogui coupe l'action. `Ctrl+C` interrompt la tâche en cours.
- Toutes les actions sont journalisées dans `logs/actions.log`.

## Voix (optionnel)
```
.venv\Scripts\python.exe -m pip install -r requirements-voix.txt
```
Reconnaissance : faster-whisper (local, CPU). Synthèse : voix Windows (installe une voix française dans Paramètres > Heure et langue > Voix si besoin).

## Ajouter un outil
Dans `jarvis/outils/*.py` :
```python
@outil
def mon_outil(param: str):
    """Description pour le modèle.
    param: description du paramètre"""
    return "résultat"
```

## Config (`config.json`)
`modele`, `num_ctx`, `reflexion` (thinking qwen), `max_etapes_outils`, `voix_tts`, `whisper_modele`.
