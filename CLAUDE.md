# Jarvis — règles du dépôt

Assistant personnel de bureau (Python + interface React), distribué en appli Windows (Inno Setup) et macOS (.dmg).
L'utilisateur parle français : messages de commit, CHANGELOG et textes de l'interface en français.

## Fin de tâche : toujours proposer de publier

Quand tu as fini de coder un changement de l'appli et que tous les commits sont faits, **demande à l'utilisateur
s'il veut publier la mise à jour** (en lui rappelant la version et la description prévues dans le CHANGELOG).
S'il répond oui, fais tout toi-même, selon la machine sur laquelle tu tournes :

- **Sur le Mac** : version + CHANGELOG, commit, push sur `main`, puis `./publier-mac.sh`.
  Il fabrique le .dmg ici, crée la release, puis demande à GitHub de fabriquer le .exe Windows.
- **Sur le PC Windows** : version + CHANGELOG, commit, push sur `main`, puis `publier.bat --auto` (sans pause).
  Il fabrique le .exe ici, crée la release, puis demande à GitHub de fabriquer le .dmg Mac.

Vérifie à la fin (onglet Actions puis la release) que la version contient bien **les deux** installateurs, et
corrige si le build GitHub échoue. S'il répond non, laisse les changements en local sans publier.

## Mises à jour : règle obligatoire pour chaque commit qui change l'appli

L'écran **Mises à jour** de l'appli liste les versions publiées dans les GitHub Releases de ce dépôt, avec leur
description, et permet d'installer la dernière ou une version précise. Pour qu'un changement y apparaisse :

1. **Incrémente la version** dans `jarvis/version.py` (seule source de vérité : spec PyInstaller, Inno Setup, CI la lisent).
   - correctif → `1.0.4` → `1.0.5` ; nouvelle fonction → `1.0.4` → `1.1.0` ; refonte incompatible → `2.0.0`.
2. **Ajoute en haut de `CHANGELOG.md`** une section `## x.y.z` (exactement la nouvelle version) avec la description
   de la mise à jour : une puce par changement, en français, écrite pour l'utilisateur (ce qui change pour lui),
   pas le détail du code. **Aucune version sans description** : la CI échoue si la section manque.
3. Commit + push sur `main`, puis publier comme décrit dans « Fin de tâche » : l'installateur de la machine
   où tu es est fabriqué en local, celui de l'autre système par GitHub (`.github/workflows/versions.yml`, lancé
   automatiquement par `publier.py`). Gratuit : quota GitHub de 2000 min/mois (≈12 min pour Windows,
   ≈70 min pour Mac). `publier.py` refuse de publier si des commits ne sont pas poussés ou si la section du
   CHANGELOG manque.

Plusieurs commits peuvent partager une même version tant qu'elle n'est pas poussée : regroupe-les dans la même
section du CHANGELOG. Une version déjà publiée (tag existant) ne se modifie plus : il faut en créer une nouvelle.
Les commits qui ne touchent pas l'appli (README, CLAUDE.md, CI seule) n'ont pas besoin de nouvelle version.

## Installateurs

- Jamais committés dans le dépôt (`installateur/` est ignoré) : ils font 250+ Mo, au-delà de la limite de 100 Mo
  par fichier de GitHub. Ils sont publiés dans les **Releases** (`publier-mac.sh` / `publier.bat` + GitHub pour l'autre système).
- Build seul, sans publier : `bash construire-mac.sh` (Mac) ou `construire.bat` (Windows).
- Mise à jour sans désinstaller : Windows = même `AppId` Inno Setup, installation silencieuse par-dessus ;
  Mac = remplacement de `/Applications/Jarvis.app` depuis le .dmg (`jarvis/mises_a_jour.py`).
- Raccourci « Mettre à jour Jarvis » (menu Démarrer / Spotlight) = `Jarvis --maj`, ouvre l'écran Mises à jour.

## Serveur des comptes (VPS)

- Code : `serveur/` (FastAPI + SQLite dans Docker, conteneur `jarvis-comptes`, port 127.0.0.1:8020), exposé par Apache
  sur https://jarvis.abdelrahimriche.com (`serveur/apache-jarvis.conf`, installé par `sudo bash installer-apache.sh`).
- Accès SSH : `ssh -i ~/.ssh/cle utilisateur@serveur` (sudo demande le mot de passe de l'utilisateur :
  lui faire lancer les commandes sudo). 
- Redéployer après un changement de `serveur/` : `rsync -az --exclude __pycache__ serveur/ utilisateur@serveur:~/jarvis-serveur/`
  puis `docker compose up -d --build` dans `~/jarvis-serveur`. Ne jamais supprimer le volume `donnees` (comptes des utilisateurs).
- La clé d'appli (`CLE_APPLI` dans `jarvis/compte.py`) doit être identique dans `serveur/.env` (non versionné) et
  dans `serveur/apache-jarvis.conf`. Toute modification de l'API doit rester compatible avec les versions déjà installées.

## Données personnelles

Ne jamais committer `.env`, `config.json`, `memoire/`, `logs/`, jetons ou clés. La mémoire partagée vit dans
OneDrive (`OneDrive/Jarvis`), pas dans le dépôt.

## Interface

Source dans `interface/` ; `npm run build` recompile `jarvis/static/` (committé, servi par `jarvis/web.py`).
Vérifier avec `npx tsc -p .` avant de committer.
