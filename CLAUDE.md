# Jarvis — guide d'installation pour Claude

Tu es Claude Code, ouvert dans le dossier de ce projet. Quand l'utilisateur te demande d'**installer Jarvis**
(« installe Jarvis », « installe le projet », « mets-moi Jarvis sur ce PC »…), suis ce guide de bout en bout,
toi-même, sans lui faire taper les commandes. Parle-lui en français, simplement.

Jarvis est un assistant personnel de bureau (Python + interface React) pour **macOS** (puce Apple) et **Windows**.
Il pilote l'ordinateur (applis, fichiers, souris/clavier, écran), parle et écoute, et garde une mémoire par
utilisateur dans un **compte en ligne**.

## 0. Avant de commencer

1. Détecte le système (`uname -s` / `uname -m` sur Mac, `ver` ou `$env:OS` sur Windows).
2. Demande à l'utilisateur ce qu'il veut, s'il ne l'a pas dit :
   - **« Utiliser Jarvis »** (cas normal) → partie 1 : installer l'appli publiée.
   - **« Développer / modifier Jarvis »** → partie 2 : installation depuis le code source.
   - **« Héberger mon propre serveur de comptes »** (optionnel, avancé) → partie 4.
3. Demande confirmation avant d'installer un logiciel système (Homebrew, Python, Node, Inno Setup…) et
   préviens si une étape demande son mot de passe (sudo, fenêtre d'autorisation) : c'est lui qui le tape.

## 1. Installer l'appli (recommandé)

Les installateurs sont publiés dans les **Releases** du dépôt GitHub (`jarvis/version.py` → `DEPOT`) :
`Jarvis-<version>-mac-arm64.dmg` (Mac puce Apple) et `JarvisSetup-<version>.exe` (Windows 10/11 x64).
Dernière version : `https://api.github.com/repos/<DEPOT>/releases/latest` (champ `assets[].browser_download_url`).

**macOS**
```bash
cd "$(mktemp -d)"
curl -fL -o Jarvis.dmg "<url du .dmg>"
hdiutil attach -nobrowse -readonly -mountpoint ./vol Jarvis.dmg
ditto ./vol/Jarvis.app /Applications/Jarvis.app      # remplace une ancienne version sans la désinstaller
hdiutil detach ./vol
xattr -dr com.apple.quarantine /Applications/Jarvis.app   # appli non signée par Apple
open /Applications/Jarvis.app
```
Puis dis à l'utilisateur d'autoriser, dans Réglages Système › Confidentialité et sécurité :
**Micro**, **Accessibilité** (raccourcis, souris, clavier) et **Enregistrement de l'écran** (vision),
pour l'appli Jarvis. Jarvis vit dans la **barre des menus** (pas d'icône dans le Dock).

**Windows** (PowerShell, sans droits administrateur)
```powershell
$f = "$env:TEMP\JarvisSetup.exe"
Invoke-WebRequest "<url du .exe>" -OutFile $f
Start-Process $f -ArgumentList "/SILENT" -Wait    # ou sans argument pour l'assistant graphique
```
L'installateur propose « Lancer au démarrage de Windows » et ajoute « Mettre à jour Jarvis » au menu Démarrer.
Jarvis vit près de l'horloge (zone de notification).

**Premier lancement (les deux systèmes)**
- L'écran de connexion s'affiche : l'utilisateur **crée son compte** (prénom, e-mail, mot de passe) ou se connecte.
  Sa mémoire, son historique, ses connecteurs et ses réglages sont liés à ce compte et le suivent partout.
- Réglages › Cerveau : coller sa **clé API Claude** (platform.claude.com › API keys ; l'abonnement Claude Pro n'en
  inclut pas), ou choisir **Ollama** (gratuit, local : installer Ollama puis `ollama pull qwen3.5:9b`).
- L'appeler : dire « Jarvis, … » ou `Ctrl+Alt+J` (Windows) / `⌃⌥J` (Mac). Le faire taire : « Jarvis, stop » ou `Ctrl+Alt+S`.

Vérifie que ça tourne : `curl -s http://127.0.0.1:7777/api/session` doit répondre (serveur local de l'appli).
Journal en cas de souci : `~/Library/Application Support/Jarvis/logs/jarvis.log` (Mac) ou
`%LOCALAPPDATA%\Jarvis\logs\jarvis.log` (Windows).

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
(cd interface && npm ci && npm run build)          # compile l'interface dans jarvis/static
.venv-mac/bin/python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis'])"
[ -f voix/fr_FR-tom-medium.onnx ] || .venv-mac/bin/python -m piper.download_voices fr_FR-tom-medium --data-dir voix
.venv-mac/bin/python lanceur.pyw                    # appli de bureau (fenêtre + barre des menus)
```

**Windows** (PowerShell)
```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-voix.txt
cd interface; npm ci; npm run build; cd ..
.venv\Scripts\python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis'])"
if (-not (Test-Path voix\fr_FR-tom-medium.onnx)) { .venv\Scripts\python -m piper.download_voices fr_FR-tom-medium --data-dir voix }
.venv\Scripts\pythonw lanceur.pyw                   # appli de bureau
```
Autres façons de lancer (Windows) : `jarvis-web.bat` (interface dans le navigateur, http://127.0.0.1:7777),
`jarvis.bat` (terminal, `--voix` pour parler).

En mode développement, les données (config, `.env`, journaux, cache du compte) sont dans le dossier du projet :
`config.json`, `memoire/`, `logs/`, `comptes/` sont ignorés par git. **Ne les committe jamais.**

Interface en direct : `cd interface && npm run dev` (http://localhost:5173, branchée sur le serveur Python lancé à côté).
Vérification avant commit : `cd interface && npx tsc -p .`

## 3. Construire les installateurs

- **Mac** (sur un Mac) : `bash construire-mac.sh` → `installateur/Jarvis-<version>-mac-<arm64|x86_64>.dmg`.
  Le script signe avec un certificat Apple s'il en trouve un (`Developer ID Application`, sinon `Apple Development`,
  ou `JARVIS_SIGNATURE="nom du certificat"`). Une signature stable est indispensable : macOS y rattache les
  autorisations (micro, écran, accessibilité, fichiers). Sans certificat (signature ad hoc), elles sont perdues à
  chaque nouvelle version.
  Si `codesign` refuse (« resource fork… »), le script retire déjà les attributs Finder (`xattr -cr`).
- **Windows** (sur un PC) : installer **Inno Setup 6** (`winget install JRSoftware.InnoSetup`), puis `construire.bat`
  → `installateur\JarvisSetup-<version>.exe`.
- Un Mac ne peut pas construire le .exe et un PC ne peut pas construire le .dmg. Le workflow GitHub Actions
  `.github/workflows/versions.yml` (Actions › Run workflow) construit l'un ou l'autre sur les machines de GitHub.
- La version vient de `jarvis/version.py` ; la description de chaque version, de `CHANGELOG.md`.
- Les installateurs (~250 Mo) ne vont jamais dans git (limite GitHub de 100 Mo) : ils sont publiés dans les Releases.

## 4. Héberger son propre serveur de comptes (optionnel)

Par défaut, l'appli utilise le serveur de comptes officiel. Pour héberger le sien (Linux avec Docker + un
sous-domaine en HTTPS) :
```bash
scp -r serveur/ utilisateur@serveur:~/jarvis-serveur/
ssh utilisateur@serveur
cd ~/jarvis-serveur
echo "JARVIS_CLE_APPLI=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" > .env && chmod 600 .env
docker compose up -d --build                      # API sur 127.0.0.1:8020, base SQLite dans le volume « donnees »
```
Puis un proxy HTTPS devant : exemple Apache dans `serveur/apache-jarvis.conf` + `serveur/installer-apache.sh`
(remplacer le domaine et la clé d'appli ; `sudo` requis). Dans l'appli, `config.json` :
`"serveur_comptes": "https://ton-sous-domaine"` et `"cle_appli": "<valeur de JARVIS_CLE_APPLI>"`.
Sauvegarder le volume Docker `donnees` : il contient tous les comptes.

## 5. Dépannage

| Problème | Solution |
|---|---|
| « Jarvis est endommagé » / ne s'ouvre pas (Mac) | `xattr -dr com.apple.quarantine /Applications/Jarvis.app`, puis clic droit › Ouvrir |
| Pas de micro / raccourcis / vision (Mac) | Réglages Système › Confidentialité : Micro, Accessibilité, Enregistrement de l'écran |
| Port 7777 déjà pris | Un Jarvis tourne déjà : le relancer affiche la fenêtre existante |
| `pip install` échoue sur une dépendance audio/IA | Vérifier Python **3.12** (`python --version`) |
| « Serveur Jarvis injoignable » | Pas d'Internet, ou serveur de comptes arrêté ; Jarvis garde un cache et resynchronise ensuite |
| Clé API ou mot de passe oublié | Mémoire conservée ; la clé API et les mots de passe des connecteurs sont à ressaisir |

## Règles pour Claude dans ce dépôt

- Messages, commits, CHANGELOG et textes de l'interface **en français**.
- Ne committe jamais de données personnelles ou secrets : `.env`, `config.json`, `memoire/`, `logs/`, `comptes/`,
  `serveur/.env`, jetons, clés.
- Un changement de l'appli = nouvelle version dans `jarvis/version.py` + section `## x.y.z` décrite pour
  l'utilisateur en haut de `CHANGELOG.md` (l'écran « Mises à jour » affiche ces descriptions).
- Le fichier `CLAUDE.local.md` (non versionné), s'il existe, contient les notes privées du mainteneur
  (accès au serveur, procédure de publication) : il complète ce guide.
