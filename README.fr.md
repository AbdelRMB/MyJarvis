<p align="center">
  <img src="jarvis.png" alt="Jarvis" width="120">
</p>

<h1 align="center">J.A.R.V.I.S.</h1>

<p align="center">
  <strong>L'assistant vocal en français qui pilote vraiment ton ordinateur.</strong><br>
  Dis <em>« Jarvis, … »</em> : il ouvre tes applis, clique, tape, lit ton écran, code dans VS Code,
  utilise tes sites (même avec double authentification) et gère tes serveurs.<br>
  Cerveau Claude, OpenAI ou <strong>Ollama (100 % local, gratuit)</strong>. macOS et Windows.
</p>

<p align="center">
  <a href="https://github.com/AbdelRMB/MyJarvis/releases/latest"><img alt="Dernière version" src="https://img.shields.io/github/v/release/AbdelRMB/MyJarvis?label=version&color=2f81f7"></a>
  <a href="https://github.com/AbdelRMB/MyJarvis/releases"><img alt="Téléchargements" src="https://img.shields.io/github/downloads/AbdelRMB/MyJarvis/total?label=t%C3%A9l%C3%A9chargements&color=2f81f7"></a>
  <img alt="Plateformes" src="https://img.shields.io/badge/plateformes-macOS%20(puce%20Apple)%20%7C%20Windows%2010%2F11-555">
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776ab?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="Licence GPL v3" src="https://img.shields.io/badge/licence-GPLv3-blue"></a>
  <a href="https://github.com/AbdelRMB/MyJarvis/stargazers"><img alt="Étoiles GitHub" src="https://img.shields.io/github/stars/AbdelRMB/MyJarvis?style=social"></a>
</p>

<p align="center">
  <a href="https://github.com/AbdelRMB/MyJarvis/releases/latest"><strong>⬇ Télécharger</strong></a> ·
  <a href="#-ce-que-tu-peux-lui-dire">Exemples</a> ·
  <a href="#-fonctionnalités">Fonctionnalités</a> ·
  <a href="#-vie-privée-et-sécurité">Vie privée</a> ·
  <a href="CONTRIBUTING.md">Contribuer</a> ·
  <a href="README.md">🇬🇧 English</a>
</p>

<!--
  DÉMO : enregistre une capture d'écran de 20 à 40 s (« Jarvis, ouvre Discord », « Jarvis, regarde mon écran… »),
  enregistre-la en docs/demo.gif (ou glisse un .mp4 dans une issue GitHub et colle le lien ici),
  puis remplace ce commentaire par :
  <p align="center"><img src="docs/demo.gif" alt="Démo de Jarvis" width="800"></p>
-->

---

## ✨ Pourquoi Jarvis ?

La plupart des « assistants IA » sont une fenêtre de discussion. Jarvis est un **agent qui a des mains** : il se sert
de ta souris, de ton clavier, de tes applis, de tes fichiers, de ton navigateur et de tes serveurs, et te dit à voix
haute ce qu'il a fait.

- 🎙️ **Mains libres.** Le mot « Jarvis » est reconnu **sur ton ordinateur** (openWakeWord + Whisper). Rien n'est
  envoyé tant qu'il n'a pas entendu son nom. Tu peux lui couper la parole en parlant.
- 🧠 **Cerveau au choix.** Claude (le plus intelligent), OpenAI, ou **Ollama : gratuit, hors ligne, rien ne sort de
  ton ordinateur.**
- 🖥️ **Vrai contrôle de l'ordinateur.** Applis, fichiers, fenêtres, souris et clavier, vision de l'écran, terminal,
  VS Code, git.
- 🌐 **Apprend tes sites.** Explore ton intranet ou tes logiciels métier sans rien modifier, retient tes
  démonstrations, puis fait la tâche à ta place. Se connecte tout seul, **codes 2FA compris** (calculés en local).
- 🔌 **Connecteurs + n'importe quel serveur MCP.** Gmail/IMAP, agenda, GitHub, Notion, serveurs SSH (avec assistant
  de configuration), WhatsApp, Spotify, Slack, Home Assistant…
- 📱 **Te suit partout.** Un compte : mémoire, historique et liste À faire synchronisés entre ton Mac, ton PC et ton
  téléphone. « Sur mon PC, lance Discord » marche depuis ton téléphone.
- 🔐 **Prudent.** Demande ton accord avant toute action destructrice, coffre chiffré pour les clés et mots de passe,
  journal de toutes les actions, arrêt d'urgence.
- 📦 **Une vraie appli, pas un script.** Appli Mac signée et notarisée par Apple, installateur Windows, mises à jour
  en un clic.

## 💬 Ce que tu peux lui dire

> « Jarvis, ouvre Discord et mets ma playlist concentration. »
>
> « Regarde mon écran : pourquoi ce build plante ? »
>
> « Crée une facture pour Dupont sur Sage. » *(un site qu'il a appris)*
>
> « Fais une capture du tableau des interventions et envoie-la à Karim sur WhatsApp. »
>
> « Pourquoi mon serveur est lent ? » *(en SSH, il demande avant chaque commande sudo)*
>
> « Rappelle-moi de sortir les poubelles à 20 h. » · « Fais-moi le briefing. »
>
> « À partir de maintenant, réponds-moi en une phrase. » *(il retient tes consignes)*

## 🚀 Démarrer en 2 minutes

1. **Télécharge** la [dernière version](https://github.com/AbdelRMB/MyJarvis/releases/latest) :

   | Ton ordinateur | Fichier |
   |---|---|
   | Mac avec puce Apple (M1 à M4) | `Jarvis-<version>-mac-arm64.dmg` |
   | PC Windows 10/11 | `JarvisSetup-<version>.exe` |

2. **Installe** : glisse Jarvis dans Applications (Mac) ou lance l'installateur (Windows, sans droits administrateur).
3. **Crée ton compte** (ou utilise-le en local, sans compte), puis choisis un cerveau dans **Réglages › Cerveau** :
   colle une [clé API Claude](https://platform.claude.com), ou installe [Ollama](https://ollama.com) et tape
   `ollama pull qwen3.5:9b` pour un cerveau local gratuit.

Puis dis **« Jarvis, … »** ou appuie sur `Ctrl+Alt+J` (Windows) / `⌃⌥J` (Mac).

> 🤖 **Encore plus simple :** clone ce dépôt, ouvre-le dans [Claude Code](https://claude.com/claude-code) et dis
> **« Installe Jarvis »**. Le dépôt contient un guide d'installation (`CLAUDE.md`) et Claude fait tout, en te
> demandant ton accord avant d'installer quoi que ce soit.

<details>
<summary><strong>Installation en détail (autorisations, SmartScreen, mises à jour)</strong></summary>

**Mac**
1. Ouvre le `.dmg` et glisse **Jarvis** dans **Applications**. L'appli est signée et vérifiée par Apple.
2. Dans **Réglages Système › Confidentialité et sécurité**, autorise Jarvis pour le **Micro**, l'**Accessibilité**
   (raccourcis, souris, clavier) et l'**Enregistrement de l'écran** (pour qu'il voie ton écran).

Jarvis vit dans la **barre des menus** et se lance à l'ouverture de ta session.

**Windows**
1. Lance `JarvisSetup-<version>.exe`. Si Windows affiche « Windows a protégé votre ordinateur », clique sur
   **Informations complémentaires › Exécuter quand même**.
2. Coche **« Lancer Jarvis au démarrage de Windows »** si tu veux qu'il soit toujours prêt.

Jarvis vit près de l'**horloge** (zone de notification).

**Premier lancement**
- Si cet ordinateur avait déjà une mémoire Jarvis (ancienne version), elle est ajoutée à ton compte, sans doublon.
- Claude est payant à l'usage : l'abonnement Claude Pro n'inclut pas de crédit API.
- Ollama demande une carte graphique avec environ 8 Go de mémoire.

**Mettre à jour** : l'écran **Mises à jour** affiche chaque version avec sa description et l'installe en un clic.
Jarvis peut aussi se mettre à jour tout seul au prochain démarrage.

</details>

> L'interface existe en français et en anglais (Réglages › Interface). Jarvis parle français par défaut.

---

## 🧰 Fonctionnalités

| | |
|---|---|
| **Système** | Terminal (PowerShell / zsh), scripts Python, ouvrir n'importe quelle appli, fichier ou URL, processus, verrouiller / éteindre |
| **Fichiers** | Lire, écrire, modifier, chercher (nom + contenu), déplacer, copier, supprimer (→ corbeille) |
| **Souris et clavier** | Déplacer, cliquer, glisser, défiler, taper, raccourcis, média / volume, presse-papier |
| **Fenêtres** | Lister, activer, maximiser, fermer, cliquer un bouton par son texte |
| **Vision** | Regarder l'écran, trouver un élément et cliquer dessus, analyser une image |
| **Navigateur** | Son propre navigateur ou **le tien** (Safari, Chrome, Edge, Brave, Arc sur Mac), en entourant chaque élément avant d'agir |
| **Sites appris** | Exploration en lecture seule, démonstrations, astuces, connexion automatique avec 2FA |
| **Code** | Ouvrir dans VS Code (fichier:ligne), git, créer un projet (Vite / Next / Node / Python) |
| **Web** | Recherche avec sources, actualités, lire une page, météo, télécharger |
| **Mémoire** | Retient ce qu'il apprend sur toi, tes consignes, et les leçons de ses propres erreurs |
| **Organisation** | Liste À faire, rappels dits à voix haute à l'heure, briefing du matin, routines, automatisations |
| **Connecteurs** | Gmail, IMAP, iCal, GitHub, Notion, serveurs SSH (sudo avec ton accord), WhatsApp, **n'importe quel serveur MCP** |
| **Voix** | Voix neuronales Microsoft, Piper (local) ou **Kyutai** (très naturelle, locale) ; dictionnaire de prononciation |
| **Appareils** | Pilote tes autres ordinateurs ; liste À faire et tickets sur ton téléphone |

<details>
<summary><strong>Utiliser Jarvis : raccourcis</strong></summary>

| Action | Comment |
|---|---|
| L'appeler | Dis **« Jarvis, ouvre Discord »** d'une traite, ou « Jarvis » puis ta demande. Ou `Ctrl+Alt+J` / `⌃⌥J`, ou clic sur l'icône. |
| Le faire taire | **« Jarvis, stop »** (même pendant qu'il parle), ou `Ctrl+Alt+S` / `⌃⌥S`, même fenêtre cachée. |
| Fermer la fenêtre | Elle se cache seulement. Pour quitter : icône Jarvis › Quitter. |
| Dans la fenêtre | `Échap` = stop · `Ctrl+K` = écrire · `Alt+1…9` = écrans |

</details>

## 🔐 Vie privée et sécurité

- **Cerveau Ollama = rien ne sort de ton ordinateur.** Avec Claude ou OpenAI, tes messages, souvenirs et résultats
  d'outils sont envoyés à ce fournisseur.
- **Écoute 100 % locale.** Le son n'est traité qu'après « Jarvis ».
- **Ton mot de passe ne quitte jamais l'appareil.** Il dérive une clé de connexion et une clé de coffre, qui chiffre
  ta clé API et tes mots de passe avant l'envoi. Ta mémoire et ton historique sont stockés sur le serveur, protégés
  mais pas chiffrés de bout en bout. Tu peux aussi utiliser Jarvis **sans compte**.
- **Il demande d'abord** avant les clics destructeurs (supprimer, envoyer, payer…) et chaque commande `sudo`.
- L'interface locale n'écoute que sur `127.0.0.1` (Host vérifié, jeton par session, Origin vérifiée).
- **Arrêt d'urgence** : souris dans le coin haut-gauche de l'écran. Toutes les actions sont journalisées
  (`logs/actions.log`).
- **Tes données t'appartiennent** : Réglages › Mon compte › **Télécharger mes données** / **Supprimer mon compte**.
  [Politique de confidentialité](https://jarvis.abdelrahimriche.com/mobile/confidentialite.html).

## 🏗️ Comment ça marche

```
 « Jarvis, … » ──► openWakeWord + Whisper (local) ──► Agent (Claude / OpenAI / Ollama)
                                                         │  appels d'outils
                                                         ▼
       applis · fichiers · souris/clavier · écran · navigateur · SSH · serveurs MCP · connecteurs
                                                         │
 Interface React (pywebview) ◄── FastAPI sur 127.0.0.1 ◄─┘──► voix (Microsoft / Piper / Kyutai)
                                                         │
                                serveur de comptes (FastAPI + SQLite) : mémoire, historique, synchro
```

- **Cœur** : Python 3.12 (`jarvis/`), outils dans `jarvis/outils/`, serveur local `jarvis/web.py`.
- **Interface** : React + TypeScript + Tailwind (`interface/`), affichée dans une fenêtre native (pywebview).
- **Serveur de comptes** : FastAPI + SQLite (`serveur/`), auto-hébergeable.

---

## 🤝 Contribuer

Toutes les contributions sont bienvenues, de la faute de frappe au nouvel outil. Commence par
[`CONTRIBUTING.md`](CONTRIBUTING.md) et les
[good first issues](https://github.com/AbdelRMB/MyJarvis/labels/good%20first%20issue).
Un bug, une idée ? [Ouvre une issue](https://github.com/AbdelRMB/MyJarvis/issues/new/choose) (en français ou en anglais).

Si Jarvis t'est utile, **une ⭐ aide beaucoup** : c'est comme ça que d'autres découvrent le projet.

<details>
<summary><strong>Installer l'environnement de développement</strong></summary>

Le détail des commandes est dans [`CLAUDE.md`](CLAUDE.md), qui sert aussi de guide pour Claude.

**Prérequis** : Python **3.12** (pas 3.13), Node.js **22+**, git. Optionnel : Ollama.

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

**Structure**

| Dossier / fichier | Rôle |
|---|---|
| `jarvis/` | Cœur en Python : agent, outils (`outils/`), voix, écoute, serveur local (`web.py`), compte (`compte.py`), mises à jour |
| `interface/` | Interface React + TypeScript + Tailwind, compilée dans `jarvis/static/` |
| `serveur/` | Serveur des comptes (FastAPI + SQLite), appli mobile et pages légales (`mobile/`) |
| `jarvis.spec` / `jarvis-mac.spec` | Recettes PyInstaller (Windows / Mac) |
| `installateur.iss` | Installateur Windows (Inno Setup) |
| `construire.bat` / `construire-mac.sh` | Construire les installateurs |
| `jarvis/version.py` + `CHANGELOG.md` | Version, et description de chaque mise à jour |

**Interface en direct** : `cd interface && npm run dev` (http://localhost:5173, branchée sur le serveur Python lancé à côté).

**Ajouter un outil** dans `jarvis/outils/*.py` :
```python
@outil
def mon_outil(param: str):
    """Description pour le modèle.
    param: description du paramètre"""
    return "résultat"
```

**Construire les installateurs** : `bash construire-mac.sh` (Mac) ou `construire.bat` (Windows, Inno Setup 6), ou sur
GitHub : **Actions › Versions de Jarvis › Run workflow**.

**Héberger ton serveur de comptes** : lance `serveur/app.py` avec uvicorn derrière un proxy HTTPS (variables
`JARVIS_DB` et `JARVIS_CLE_APPLI`), puis dans le `config.json` de l'appli : `"serveur_comptes"` et `"cle_appli"`.

**Où sont mes données ?**

| | Mac | Windows |
|---|---|---|
| Réglages de l'appareil, journaux, cache du compte | `~/Library/Application Support/Jarvis` | `%LOCALAPPDATA%\Jarvis` |
| Mémoire, historique, connecteurs, réglages communs | dans ton **compte** (et en cache local) | idem |
| Clé API, mots de passe des connecteurs | Trousseau macOS + coffre chiffré du compte | Gestionnaire d'identifiants + coffre chiffré du compte |

Diagnostic : `logs/jarvis.log` (démarrage, erreurs), `logs/perf.log` (vitesse du modèle), `logs/couts.json`
(dépenses estimées de l'API Claude).

</details>

## ⭐ Historique des étoiles

<a href="https://star-history.com/#AbdelRMB/MyJarvis&Date">
  <img src="https://api.star-history.com/svg?repos=AbdelRMB/MyJarvis&type=Date" alt="Historique des étoiles" width="600">
</a>

## 📄 Licence

Copyright (C) 2026 Abdelrahim Riche. Jarvis est un logiciel libre sous **GNU General Public License v3** (ou toute
version ultérieure) : tu peux l'utiliser, l'étudier, le modifier et le partager ; toute version modifiée que tu
distribues doit rester sous cette même licence, avec son code source. Il est fourni **sans aucune garantie**.
Texte complet : [LICENSE](LICENSE).
