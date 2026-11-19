# Jarvis — règles du dépôt

Assistant personnel de bureau (Python + interface React), distribué en appli Windows (Inno Setup) et macOS (.dmg).
L'utilisateur parle français : messages de commit, CHANGELOG et textes de l'interface en français.

## Mises à jour : règle obligatoire pour chaque commit qui change l'appli

L'écran **Mises à jour** de l'appli liste les versions publiées dans les GitHub Releases de ce dépôt, avec leur
description, et permet d'installer la dernière ou une version précise. Pour qu'un changement y apparaisse :

1. **Incrémente la version** dans `jarvis/version.py` (seule source de vérité : spec PyInstaller, Inno Setup, CI la lisent).
   - correctif → `1.0.4` → `1.0.5` ; nouvelle fonction → `1.0.4` → `1.1.0` ; refonte incompatible → `2.0.0`.
2. **Ajoute en haut de `CHANGELOG.md`** une section `## x.y.z` (exactement la nouvelle version) avec la description
   de la mise à jour : une puce par changement, en français, écrite pour l'utilisateur (ce qui change pour lui),
   pas le détail du code. **Aucune version sans description** : la CI échoue si la section manque.
3. Commit + push sur `main`, puis **publier** (gratuit et sans limite, rien ne passe par GitHub Actions) :
   - sur le Mac : `./publier-mac.sh` → construit le .dmg et crée la release `vx.y.z` avec cette description ;
   - sur le PC Windows : `publier.bat` → construit JarvisSetup.exe et l'ajoute à la même release.
   La version apparaît alors dans « Mises à jour » sur tous les appareils (sur un appareil dont l'installateur
   n'est pas encore envoyé, elle s'affiche « pas encore prête »). `publier.py` refuse de publier si des commits
   ne sont pas poussés ou si la section du CHANGELOG manque.
   Secours : `.github/workflows/versions.yml` fait les deux builds sur GitHub, mais uniquement lancé à la main
   (Actions > Run workflow), car il consomme le quota mensuel de minutes.

Plusieurs commits peuvent partager une même version tant qu'elle n'est pas poussée : regroupe-les dans la même
section du CHANGELOG. Une version déjà publiée (tag existant) ne se modifie plus : il faut en créer une nouvelle.
Les commits qui ne touchent pas l'appli (README, CLAUDE.md, CI seule) n'ont pas besoin de nouvelle version.

## Installateurs

- Jamais committés dans le dépôt (`installateur/` est ignoré) : ils font 250+ Mo, au-delà de la limite de 100 Mo
  par fichier de GitHub. Ils sont publiés dans les **Releases** (`publier-mac.sh` / `publier.bat`).
- Build seul, sans publier : `bash construire-mac.sh` (Mac) ou `construire.bat` (Windows).
- Mise à jour sans désinstaller : Windows = même `AppId` Inno Setup, installation silencieuse par-dessus ;
  Mac = remplacement de `/Applications/Jarvis.app` depuis le .dmg (`jarvis/mises_a_jour.py`).
- Raccourci « Mettre à jour Jarvis » (menu Démarrer / Spotlight) = `Jarvis --maj`, ouvre l'écran Mises à jour.

## Données personnelles

Ne jamais committer `.env`, `config.json`, `memoire/`, `logs/`, jetons ou clés. La mémoire partagée vit dans
OneDrive (`OneDrive/Jarvis`), pas dans le dépôt.

## Interface

Source dans `interface/` ; `npm run build` recompile `jarvis/static/` (committé, servi par `jarvis/web.py`).
Vérifier avec `npx tsc -p .` avant de committer.
