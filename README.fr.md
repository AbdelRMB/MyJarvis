<p align="center">
  <a href="README.md">English</a> · <strong>Français</strong>
</p>

# J.A.R.V.I.S. — ton assistant personnel de bureau

Jarvis est un assistant qui **pilote ton ordinateur** à ta place : il ouvre tes applis, gère tes fichiers, clique et
tape pour toi, regarde ton écran, code dans VS Code, cherche sur le web… Tu lui parles à la voix (« Jarvis, ouvre
Discord ») ou par écrit, et il te répond à voix haute.

- **macOS** (puce Apple) et **Windows 10/11**.
- **Cerveau au choix** : Claude (API Anthropic, le plus intelligent), OpenAI, ou Ollama (gratuit, 100 % local).
- **Un compte par personne** : ta mémoire, ton historique, tes connecteurs et tes réglages te suivent sur tous tes
  appareils. Ta clé API et tes mots de passe sont chiffrés avec ton mot de passe : le serveur ne peut pas les lire.
- **Mises à jour intégrées** : l'appli affiche les nouvelles versions et ce qu'elles contiennent, et s'installe en un clic.

---

## Installer Jarvis avec Claude (le plus simple)

Ce dépôt contient un guide d'installation pour [Claude Code](https://claude.com/claude-code) (`CLAUDE.md`) :
**Claude peut installer Jarvis tout seul**, de bout en bout.

1. Installe Claude Code, puis récupère le projet :
   ```bash
   git clone https://github.com/AbdelRMB/MyJarvis.git
   cd MyJarvis
   claude
   ```
2. Dis-lui simplement : **« Installe Jarvis »**.

Claude détecte ton système et te demande si tu veux juste utiliser Jarvis ou le développer. Il télécharge et
installe tout, puis te guide pour les autorisations et la création de ton compte. Il te demande ton accord avant
d'installer un logiciel sur ton ordinateur, et c'est toi qui tapes les mots de passe éventuels.

---

## Installer Jarvis à la main

### 1. Télécharger

Va dans l'onglet **[Releases](https://github.com/AbdelRMB/MyJarvis/releases)** et prends la dernière version :

| Ton ordinateur | Fichier |
|---|---|
| Mac avec puce Apple (M1, M2, M3…) | `Jarvis-<version>-mac-arm64.dmg` |
| PC Windows 10/11 | `JarvisSetup-<version>.exe` |

### 2. Installer

**Sur Mac**
1. Ouvre le `.dmg` et glisse **Jarvis** dans **Applications**. L'appli est signée et vérifiée par Apple : elle
   s'ouvre normalement.
2. Dans **Réglages Système › Confidentialité et sécurité**, autorise Jarvis pour le **Micro**, l'**Accessibilité**
   (raccourcis, souris, clavier) et l'**Enregistrement de l'écran** (pour qu'il voie ton écran).

Jarvis vit dans la **barre des menus**, en haut à droite. Il se lance tout seul à l'ouverture de ta session.

**Sur Windows**
1. Lance `JarvisSetup-<version>.exe` (pas besoin de droits administrateur). Si Windows affiche « Windows a protégé
   votre ordinateur », clique sur **Informations complémentaires › Exécuter quand même**.
2. Coche **« Lancer Jarvis au démarrage de Windows »** si tu veux qu'il soit toujours prêt.

Jarvis vit près de l'**horloge** (zone de notification).

### 3. Premier lancement

1. **Crée ton compte** (prénom, e-mail, mot de passe) ou connecte-toi. Tu peux aussi utiliser Jarvis **en local**,
   sans compte : rien n'est alors envoyé au serveur.
   - Si cet ordinateur avait déjà une mémoire Jarvis (ancienne version, OneDrive), elle est ajoutée à ton compte
     automatiquement, sans doublon.
2. **Choisis le cerveau** dans **Réglages › Cerveau** :
   - **Claude** : colle ta clé API, à créer sur [platform.claude.com](https://platform.claude.com) › API keys.
     C'est payant à l'usage, et l'abonnement Claude Pro n'inclut pas de crédit API.
   - **Ollama** : gratuit et local. Installe [Ollama](https://ollama.com), puis tape `ollama pull qwen3.5:9b`.
     Il faut une carte graphique avec environ 8 Go de mémoire.
3. C'est prêt. Dis **« Jarvis, … »**.

### Mettre à jour

- Dans l'appli : écran **Mises à jour**. Tu vois chaque nouvelle version avec sa description, et tu installes la
  dernière ou une version précise. Pas besoin de désinstaller.
- Ou cherche **« Mettre à jour Jarvis »** dans le menu Démarrer (Windows) ou Spotlight (Mac).

---

## Utiliser Jarvis

| Action | Comment |
|---|---|
| L'appeler | Dis **« Jarvis, ouvre Discord »** d'une traite, ou « Jarvis » puis ta demande. Ou `Ctrl+Alt+J` (Windows) / `⌃ Ctrl + ⌥ Option + J` (Mac), ou clic sur l'icône. |
| Le faire taire | **« Jarvis, stop »** (même pendant qu'il parle), ou `Ctrl+Alt+S` / `⌃⌥S`, même fenêtre cachée. |
| Fermer la fenêtre | Elle se cache seulement. Pour quitter : icône Jarvis › Quitter. |
| Raccourcis dans la fenêtre | `Échap` = stop · `Ctrl+K` = écrire · `Alt+1…9` = écrans |

- **Démarrage discret** : à l'allumage, Jarvis tourne en fond sans ouvrir son interface ; elle apparaît quand tu l'appelles.
- **Écoute 100 % locale** : le mot « Jarvis » est reconnu sur ton ordinateur (openWakeWord + petit Whisper).
  Rien n'est envoyé tant qu'il n'a pas entendu son nom.
- **Voix** : Microsoft neuronal (Henri, très naturel, en ligne) ou Piper (100 % local). Réglages › Voix.

### Ce qu'il sait faire
- **Système** : terminal (PowerShell / zsh), scripts Python, ouvrir n'importe quelle appli, fichier ou URL, processus, verrouiller/éteindre
- **Fichiers** : lire, écrire, modifier, chercher (nom + contenu), déplacer, copier, supprimer (→ corbeille)
- **Souris et clavier** : déplacer, cliquer, glisser, défiler, taper, raccourcis, média/volume, presse-papier
- **Fenêtres** : lister, activer, maximiser, fermer, cliquer un bouton par son texte
- **Vision** : regarder l'écran, trouver un élément et cliquer dessus, analyser une image
- **Code** : ouvrir dans VS Code (fichier:ligne), git, créer un projet (Vite / Next / Node / Python)
- **Web** : recherche, actualités, lire une page, météo, télécharger
- **Mémoire** : retient ce qu'il apprend sur toi, avec un historique de vos conversations sur tous tes appareils
- **Connecteurs** : Gmail, autre messagerie IMAP, agenda (iCal), GitHub, Notion, serveurs SSH (VPS), et
  **n'importe quel serveur MCP** (Spotify, Slack, Home Assistant…)
- **Tes autres appareils** : « sur mon PC, lance Discord », y compris depuis ton téléphone

### Écrans
Rangés par sections dans la barre de gauche : **Assistant**, **À faire** · *Ma mémoire* : Historique, Mémoire ·
*Automatiser* : Tâches, Automatisations, Connecteurs · *Mes machines* : Mes appareils, Système, Activité, Arsenal ·
*Jarvis* : Réglages, Mises à jour, Tickets.

### Sécurité et vie privée
- L'interface locale n'écoute que sur `127.0.0.1` (Host vérifié, jeton par session, Origin vérifiée).
- **Compte** : ton mot de passe ne quitte jamais l'appareil. Il sert à dériver une clé de connexion et une clé de
  coffre, qui chiffre ta clé API et tes mots de passe avant l'envoi. Ta mémoire et ton historique sont stockés sur
  le serveur, protégés mais pas chiffrés de bout en bout.
- **Tes données t'appartiennent** : Réglages › Mon compte › **Télécharger mes données** ou **Supprimer mon compte**
  (tout est effacé du serveur). Détails dans la
  [politique de confidentialité](https://jarvis.abdelrahimriche.com/mobile/confidentialite.html).
- Avec le cerveau Claude ou OpenAI, tes messages, souvenirs et résultats d'outils sont envoyés à ce fournisseur.
  Avec Ollama, rien ne sort de ton ordinateur.
- **Arrêt d'urgence** : souris dans le coin haut-gauche de l'écran (pyautogui coupe l'action). Toutes les actions
  sont journalisées (`logs/actions.log`).

---

## Développer

Le détail des commandes est dans [`CLAUDE.md`](CLAUDE.md), qui sert aussi de guide pour Claude. En bref :

**Prérequis** : Python **3.12**, Node.js **22+**, git. Optionnel : Ollama.

```bash
# Mac
python3.12 -m venv .venv-mac && .venv-mac/bin/pip install -r requirements-mac.txt
(cd interface && npm ci && npm run build)
.venv-mac/bin/python lanceur.pyw
```
```powershell
# Windows
py -3.12 -m venv .venv; .venv\Scripts\pip install -r requirements.txt -r requirements-voix.txt
cd interface; npm ci; npm run build; cd ..
.venv\Scripts\pythonw lanceur.pyw          # ou jarvis-web.bat (navigateur) / jarvis.bat (terminal)
```

### Structure
| Dossier / fichier | Rôle |
|---|---|
| `jarvis/` | Le cœur en Python : agent, outils (`outils/`), voix, écoute, serveur local (`web.py`), compte (`compte.py`), mises à jour |
| `interface/` | Interface React + TypeScript + Tailwind, compilée dans `jarvis/static/` |
| `serveur/` | Serveur des comptes (FastAPI + SQLite), appli mobile et pages légales (`mobile/`) |
| `jarvis.spec` / `jarvis-mac.spec` | Recettes PyInstaller (Windows / Mac) |
| `installateur.iss` | Installateur Windows (Inno Setup) |
| `construire.bat` / `construire-mac.sh` | Construire les installateurs |
| `jarvis/version.py` + `CHANGELOG.md` | Version, et description de chaque mise à jour |

### Interface en direct
```bash
cd interface
npm run dev        # http://localhost:5173, branchée sur le serveur Python lancé à côté
npm run build      # recompile jarvis/static
```

### Ajouter un outil
Dans `jarvis/outils/*.py` :
```python
@outil
def mon_outil(param: str):
    """Description pour le modèle.
    param: description du paramètre"""
    return "résultat"
```

### Construire les installateurs
- Mac : `bash construire-mac.sh` → `installateur/Jarvis-<version>-mac-arm64.dmg` (signé et notarisé si un
  certificat Developer ID est présent)
- Windows : `construire.bat` (Inno Setup 6 requis) → `installateur\JarvisSetup-<version>.exe`
- Ou sur GitHub : **Actions › Versions de Jarvis › Run workflow** (case Windows et/ou Mac).

### Publier une version
1. Incrémente `jarvis/version.py`.
2. Décris la version en haut de `CHANGELOG.md` (section `## x.y.z`, écrite pour l'utilisateur).
3. Pousse sur `main`, puis lance `./publier-mac.sh` (Mac) ou `publier.bat` (Windows). Le script construit
   l'installateur de ta machine, crée la version dans les Releases, et demande à GitHub de construire celui de
   l'autre système.

### Serveur de comptes
Le code du serveur est dans `serveur/app.py`. La configuration de déploiement du serveur officiel n'est pas publiée.
Pour utiliser ton propre serveur : lance `app.py` avec uvicorn derrière un proxy HTTPS (variables `JARVIS_DB` et
`JARVIS_CLE_APPLI`), puis dans le `config.json` de l'appli : `"serveur_comptes"` et `"cle_appli"`.

---

## Où sont mes données ?

| | Mac | Windows |
|---|---|---|
| Réglages de l'appareil, journaux, cache du compte | `~/Library/Application Support/Jarvis` | `%LOCALAPPDATA%\Jarvis` |
| Mémoire, historique, connecteurs, réglages communs | dans ton **compte** (et en cache local) | idem |
| Clé API, mots de passe des connecteurs | Trousseau macOS + coffre chiffré du compte | Gestionnaire d'identifiants + coffre chiffré du compte |

Diagnostic : `logs/jarvis.log` (démarrage, erreurs), `logs/perf.log` (vitesse du modèle), `logs/couts.json`
(dépenses estimées de l'API Claude).

## Licence

Copyright (C) 2026 Abdelrahim Riche

Jarvis est un logiciel libre : tu peux le redistribuer et le modifier selon les termes de la
**GNU General Public License version 3** (ou toute version ultérieure), publiée par la Free Software Foundation.
Toute version modifiée que tu distribues doit rester sous cette même licence, avec son code source.
Jarvis est fourni **sans aucune garantie**. Texte complet : [LICENSE](LICENSE).
