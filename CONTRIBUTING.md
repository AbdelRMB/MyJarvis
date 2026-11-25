# Contributing to Wesley

🇫🇷 *Version française plus bas.*

Thanks for wanting to help! Every contribution counts: a bug report, a typo, a translation, a new tool.

## Ways to help

- **Try Wesley and report bugs**: [open an issue](https://github.com/AbdelRMB/Wesley/issues/new/choose).
  You can also send a bug report straight from the app (**Tickets** screen).
- **Pick a [good first issue](https://github.com/AbdelRMB/Wesley/labels/good%20first%20issue)**: small, well
  scoped tasks to get to know the code.
- **Add a tool**: a Python function in `wesley/outils/` decorated with `@outil` (see the README).
- **Improve the interface** (`interface/`, React + TypeScript + Tailwind) or its English translation.
- **Share Wesley**: a ⭐, a post, a demo video. It really helps.

## Setting up

Requirements: Python **3.12** (not 3.13), Node.js **22+**, git. The full commands are in the README
(*Development setup*) and in [`CLAUDE.md`](CLAUDE.md). Tip: open the repo in Claude Code and say
"install Wesley for development".

## Pull requests

1. Fork, create a branch from `main`, keep the change focused.
2. Before committing: `cd interface && npx tsc -p .` if you touched the interface, and run Wesley once to check.
3. If your change affects users, add a line at the top of `CHANGELOG.md` (written for users, not about the code).
   The maintainer bumps the version when publishing.
4. Never commit personal data or secrets: `.env`, `config.json`, `memoire/`, `logs/`, `comptes/`, API keys, tokens.
5. Open the PR and describe what changes and how you tested it.

The code and comments are in **French**, commit messages in **English** (variable names like `outil`, `memoire`, `reglages`).
Writing your issue or PR in English is completely fine.

By contributing, you agree that your code is published under the project's license (GPLv3 or later).

---

# Contribuer à Wesley

Merci de vouloir aider ! Chaque contribution compte : un rapport de bug, une faute, une traduction, un nouvel outil.

## Comment aider

- **Essaie Wesley et signale les bugs** : [ouvre une issue](https://github.com/AbdelRMB/Wesley/issues/new/choose),
  ou envoie un rapport directement depuis l'appli (écran **Tickets**).
- **Prends une [good first issue](https://github.com/AbdelRMB/Wesley/labels/good%20first%20issue)** : des tâches
  courtes et bien délimitées pour découvrir le code.
- **Ajoute un outil** : une fonction Python dans `wesley/outils/` décorée par `@outil` (voir le README).
- **Améliore l'interface** (`interface/`, React + TypeScript + Tailwind) ou sa traduction anglaise.
- **Fais connaître Wesley** : une ⭐, un post, une vidéo de démo. Ça aide vraiment.

## Installer l'environnement

Prérequis : Python **3.12** (pas 3.13), Node.js **22+**, git. Les commandes complètes sont dans le README
(*Installer l'environnement de développement*) et dans [`CLAUDE.md`](CLAUDE.md). Astuce : ouvre le dépôt dans
Claude Code et dis « installe Wesley pour le développement ».

## Pull requests

1. Fork, crée une branche depuis `main`, garde un changement ciblé.
2. Avant de committer : `cd interface && npx tsc -p .` si tu as touché l'interface, et lance Wesley une fois pour vérifier.
3. Si ton changement concerne l'utilisateur, ajoute une ligne en haut de `CHANGELOG.md` (écrite pour l'utilisateur).
   Le mainteneur incrémente la version à la publication.
4. Ne committe jamais de données personnelles ni de secrets : `.env`, `config.json`, `memoire/`, `logs/`, `comptes/`,
   clés API, jetons.
5. Ouvre la PR en expliquant ce qui change et comment tu l'as testé.

En contribuant, tu acceptes que ton code soit publié sous la licence du projet (GPLv3 ou ultérieure).
