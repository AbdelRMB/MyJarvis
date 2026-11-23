# Wesley — guide d'installation pour Claude

Tu es Claude Code, ouvert dans le dossier de ce projet. Quand l'utilisateur te demande d'**installer Wesley**
(« installe Wesley », « installe le projet », « mets-moi Wesley sur ce PC »…), suis ce guide de bout en bout,
toi-même, sans lui faire taper les commandes. Parle-lui en français, simplement.

Wesley est un assistant personnel de bureau (Python + interface React) pour **macOS** (puce Apple) et **Windows**.
Il pilote l'ordinateur (applis, fichiers, souris/clavier, écran), parle et écoute, et garde une mémoire par
utilisateur dans un **compte en ligne**.

## 0. Avant de commencer

1. Détecte le système (`uname -s` / `uname -m` sur Mac, `ver` ou `$env:OS` sur Windows).
2. Demande à l'utilisateur ce qu'il veut, s'il ne l'a pas dit :
   - **« Utiliser Wesley »** (cas normal) → partie 1 : installer l'appli publiée.
   - **« Développer / modifier Wesley »** → partie 2 : installation depuis le code source.
3. Demande confirmation avant d'installer un logiciel système (Homebrew, Python, Node, Inno Setup…) et
   préviens si une étape demande son mot de passe (sudo, fenêtre d'autorisation) : c'est lui qui le tape.

## 1. Installer l'appli (recommandé)

Les installateurs sont publiés dans les **Releases** du dépôt GitHub (`wesley/version.py` → `DEPOT`) :
`Wesley-<version>-mac-arm64.dmg` (Mac puce Apple) et `WesleySetup-<version>.exe` (Windows 10/11 x64).
Dernière version : `https://api.github.com/repos/<DEPOT>/releases/latest` (champ `assets[].browser_download_url`).

**macOS**
```bash
cd "$(mktemp -d)"
curl -fL -o Wesley.dmg "<url du .dmg>"
hdiutil attach -nobrowse -readonly -mountpoint ./vol Wesley.dmg
ditto ./vol/Wesley.app /Applications/Wesley.app      # remplace une ancienne version sans la désinstaller
hdiutil detach ./vol
xattr -dr com.apple.quarantine /Applications/Wesley.app   # appli non signée par Apple
open /Applications/Wesley.app
```
Puis dis à l'utilisateur d'autoriser, dans Réglages Système › Confidentialité et sécurité :
**Micro**, **Accessibilité** (raccourcis, souris, clavier) et **Enregistrement de l'écran** (vision),
pour l'appli Wesley. Wesley vit dans la **barre des menus** (pas d'icône dans le Dock).

**Windows** (PowerShell, sans droits administrateur)
```powershell
$f = "$env:TEMP\WesleySetup.exe"
Invoke-WebRequest "<url du .exe>" -OutFile $f
Start-Process $f -ArgumentList "/SILENT" -Wait    # ou sans argument pour l'assistant graphique
```
L'installateur propose « Lancer au démarrage de Windows » et ajoute « Mettre à jour Wesley » au menu Démarrer.
Wesley vit près de l'horloge (zone de notification).

**Premier lancement (les deux systèmes)**
- L'écran de connexion s'affiche : l'utilisateur **crée son compte** (prénom, e-mail, mot de passe) ou se connecte.
  Sa mémoire, son historique, ses connecteurs et ses réglages sont liés à ce compte et le suivent partout.
- Réglages › Cerveau : choisir l'IA et coller sa clé API. **Claude** (platform.claude.com › API keys ; l'abonnement
  Claude Pro n'en inclut pas), OpenAI, Gemini, Mistral, DeepSeek, Grok, OpenRouter, Groq… (l'écran indique où créer
  chaque clé ; Gemini, Mistral, Groq et Cerebras ont une offre gratuite), ou **Ollama** (gratuit, local : installer
  Ollama puis `ollama pull qwen3.5:9b`) / **LM Studio**. Ajouter une IA compatible OpenAI = une entrée dans
  `wesley/fournisseurs.py` (plus sa traduction dans `interface/src/lib/en.ts`).
- L'appeler : dire « Wesley, … » ou `Ctrl+Alt+W` (Windows) / `⌃⌥W` (Mac). Le faire taire : « Wesley, stop » ou `Ctrl+Alt+S`.

Vérifie que ça tourne : `curl -s http://127.0.0.1:7777/api/session` doit répondre (serveur local de l'appli).
Journal en cas de souci : `~/Library/Application Support/Wesley/logs/wesley.log` (Mac) ou
`%LOCALAPPDATA%\Wesley\logs\wesley.log` (Windows).

## 2. Installer depuis le code source (développement)

Prérequis : **git**, **Python 3.12** (pas 3.13 : certaines dépendances audio/IA n'ont pas encore de paquets),
**Node.js 22 ou plus**. Optionnel : **Ollama** pour le cerveau local.
- Mac : `brew install python@3.12 node` (Homebrew : https://brew.sh).
- Windows : `winget install Python.Python.3.12 OpenJS.NodeJS.LTS Git.Git`.

**macOS**
```bash
python3.12 -m venv .venv-mac
.venv-mac/bin/python -m pip install --upgrade pip
.venv-mac/bin/python -m pip install -r requirements-mac.txt
(cd interface && npm ci && npm run build)          # compile l'interface dans wesley/static
.venv-mac/bin/python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_wesley'])"
[ -f voix/fr_FR-tom-medium.onnx ] || .venv-mac/bin/python -m piper.download_voices fr_FR-tom-medium --data-dir voix
.venv-mac/bin/python lanceur.pyw                    # appli de bureau (fenêtre + barre des menus)
```

**Windows** (PowerShell)
```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-voix.txt
cd interface; npm ci; npm run build; cd ..
.venv\Scripts\python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_wesley'])"
if (-not (Test-Path voix\fr_FR-tom-medium.onnx)) { .venv\Scripts\python -m piper.download_voices fr_FR-tom-medium --data-dir voix }
.venv\Scripts\pythonw lanceur.pyw                   # appli de bureau
```
Autres façons de lancer (Windows) : `wesley-web.bat` (interface dans le navigateur, http://127.0.0.1:7777),
`wesley.bat` (terminal, `--voix` pour parler).

En mode développement, les données (config, `.env`, journaux, cache du compte) sont dans le dossier du projet :
`config.json`, `memoire/`, `logs/`, `comptes/` sont ignorés par git. **Ne les committe jamais.**

Interface en direct : `cd interface && npm run dev` (http://localhost:5173, branchée sur le serveur Python lancé à côté).
Vérification avant commit : `cd interface && npx tsc -p .`
Tests Python du cœur (sans dépendances lourdes) : `python -m pytest tests -q` (`pytest` et `numpy` suffisent).

### WESLEY.md (instructions par projet)

`wesley/wesley_md.py` gère les fichiers `WESLEY.md` des projets de l'utilisateur (l'équivalent de ce CLAUDE.md pour
Wesley) : lecture racine + sous-dossiers, modèle, journal. Outils : `wesley/outils/projets_outils.py`
(`lire_wesley_md`, `creer_wesley_md`, `noter_wesley_md`). Les tâches de code (`wesley/taches.py`) le placent en tête
de la consigne de Claude Code / Codex et exigent qu'il soit tenu à jour avant le commit final. Ce dépôt a aussi
son `WESLEY.md` : tiens-le à jour quand tu modifies Wesley.

### Wesley mobile (téléphone)

Appli web réservée aux téléphones (iPhone, Android), servie par le serveur de comptes sur `/mobile/`. Wesley y
tourne vraiment (cerveau, outils, mémoire, À faire, automatisations, tickets, voix du téléphone) ; ce qu'un
téléphone ne peut pas faire passe par un ordinateur du compte (ordres chiffrés, `wesley/appareils.py`).
- Code : `interface/mobile/src` (`moteur/` = compte, chiffrement, synchro, cerveau, outils ; `vues/` = écrans).
  Il réutilise `interface/src` (composants, thème, Markdown, `t()`) ; traductions propres dans `en-mobile.ts`.
- Compiler (à committer avec le code) : `cd interface && npm run build:mobile` → `serveur/mobile/index.html` + `app/`.
  En direct : `npm run dev:mobile` (http://localhost:5174/mobile/, ouvrir avec l'émulation téléphone du navigateur).
- Téléphones seulement : `serveur/app.py` (`est_telephone`) sert une page de refus aux ordinateurs et refuse l'API
  aux navigateurs d'ordinateur ; `interface/mobile/src/garde.ts` vérifie aussi côté page. L'appli de bureau
  (User-Agent « Wesley ») n'est pas concernée.
- Tests : `serveur/tests/test_telephone.py` (pytest) et `serveur/tests/e2e_mobile.py` (Playwright, iPhone émulé).

## 3. Construire les installateurs

- **Mac** (sur un Mac) : `bash construire-mac.sh` → `installateur/Wesley-<version>-mac-<arm64|x86_64>.dmg`.
  Le script signe avec un certificat Apple s'il en trouve un (`Developer ID Application`, sinon `Apple Development`,
  ou `WESLEY_SIGNATURE="nom du certificat"`). Une signature stable est indispensable : macOS y rattache les
  autorisations (micro, écran, accessibilité, fichiers). Sans certificat (signature ad hoc), elles sont perdues à
  chaque nouvelle version.
  Si `codesign` refuse (« resource fork… »), le script retire déjà les attributs Finder (`xattr -cr`).
  Avec un certificat `Developer ID Application`, le script signe en runtime renforcé et, si `APPLE_ID`,
  `APPLE_MDP_APPLI` (mot de passe pour app) et `APPLE_EQUIPE` (Team ID) sont définis, fait notariser le .dmg par Apple.
  Sur GitHub Actions : secrets du dépôt `APPLE_CERT_P12` (le .p12 en base64), `APPLE_CERT_MDP`, `APPLE_ID`,
  `APPLE_MDP_APPLI`, `APPLE_EQUIPE`. Sans eux, la construction continue en signature ad hoc.
- **Windows** (sur un PC) : installer **Inno Setup 6** (`winget install JRSoftware.InnoSetup`), puis `construire.bat`
  → `installateur\WesleySetup-<version>.exe`.
- Un Mac ne peut pas construire le .exe et un PC ne peut pas construire le .dmg. Le workflow GitHub Actions
  `.github/workflows/versions.yml` (Actions › Run workflow) construit l'un ou l'autre sur les machines de GitHub.
- La version vient de `wesley/version.py` ; la description de chaque version, de `CHANGELOG.md`.
- Les installateurs (~250 Mo) ne vont jamais dans git (limite GitHub de 100 Mo) : ils sont publiés dans les Releases.

## 4. Serveur de comptes

L'appli utilise le serveur de comptes officiel. Son code est dans `serveur/` (`app.py` : API FastAPI + SQLite,
`mobile/` : appli web du téléphone et pages légales). La configuration de déploiement (Docker, Apache, scripts du
VPS) n'est **pas publiée** : ces fichiers sont ignorés par git et restent sur la machine du mainteneur
(voir `CLAUDE.local.md`). Pour un autre serveur : lancer `app.py` avec uvicorn derrière un proxy HTTPS
(variables `WESLEY_DB` et `WESLEY_CLE_APPLI`), puis dans `config.json` de l'appli :
`"serveur_comptes": "https://ton-sous-domaine"` et `"cle_appli": "<valeur de WESLEY_CLE_APPLI>"`.

## 5. Dépannage

| Problème | Solution |
|---|---|
| « Wesley est endommagé » / ne s'ouvre pas (Mac) | `xattr -dr com.apple.quarantine /Applications/Wesley.app`, puis clic droit › Ouvrir |
| Pas de micro / raccourcis / vision (Mac) | Réglages Système › Confidentialité : Micro, Accessibilité, Enregistrement de l'écran |
| Port 7777 déjà pris | Un Wesley tourne déjà : le relancer affiche la fenêtre existante |
| `pip install` échoue sur une dépendance audio/IA | Vérifier Python **3.12** (`python --version`) |
| « Serveur Wesley injoignable » | Pas d'Internet, ou serveur de comptes arrêté ; Wesley garde un cache et resynchronise ensuite |
| Clé API ou mot de passe oublié | Mémoire conservée ; la clé API et les mots de passe des connecteurs sont à ressaisir |

## Règles pour Claude dans ce dépôt

- Messages, commits, CHANGELOG et textes de l'interface **en français**.
- Ne committe jamais de données personnelles ou secrets : `.env`, `config.json`, `memoire/`, `logs/`, `comptes/`,
  `serveur/.env`, jetons, clés, ni les fichiers de déploiement du serveur (Docker, Apache).
- Un changement de l'appli = nouvelle version dans `wesley/version.py` + section `## x.y.z` décrite pour
  l'utilisateur en haut de `CHANGELOG.md` (l'écran « Mises à jour » affiche ces descriptions).
- Le fichier `CLAUDE.local.md` (non versionné), s'il existe, contient les notes privées du mainteneur
  (accès au serveur, procédure de publication) : il complète ce guide.
