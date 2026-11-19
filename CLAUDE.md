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
3. Commit + push sur `main` : le workflow `.github/workflows/versions.yml` construit le .dmg et le .exe,
   puis crée la release `vx.y.z` avec cette description. Elle apparaît alors dans « Mises à jour » sur tous les appareils.

Plusieurs commits peuvent partager une même version tant qu'elle n'est pas poussée : regroupe-les dans la même
section du CHANGELOG. Une version déjà publiée (tag existant) ne se modifie plus : il faut en créer une nouvelle.
Les commits qui ne touchent pas l'appli (README, CLAUDE.md, CI seule) n'ont pas besoin de nouvelle version.

Chaque build macOS est poussé sur des runners macOS (minutes GitHub ×10 sur un dépôt privé) : ne publie pas une
version pour chaque micro-commit, regroupe.

## Installateurs

- Jamais committés dans le dépôt (`installateur/` est ignoré) : ils font 250+ Mo, au-delà de la limite de 100 Mo
  par fichier de GitHub. Ils sont publiés dans les **Releases** par la CI.
- Build local : `bash construire-mac.sh` (Mac) ou `construire.bat` (Windows).
- Mise à jour sans désinstaller : Windows = même `AppId` Inno Setup, installation silencieuse par-dessus ;
  Mac = remplacement de `/Applications/Jarvis.app` depuis le .dmg (`jarvis/mises_a_jour.py`).
- Raccourci « Mettre à jour Jarvis » (menu Démarrer / Spotlight) = `Jarvis --maj`, ouvre l'écran Mises à jour.

## Données personnelles

Ne jamais committer `.env`, `config.json`, `memoire/`, `logs/`, jetons ou clés. La mémoire partagée vit dans
OneDrive (`OneDrive/Jarvis`), pas dans le dépôt.

## Interface

Source dans `interface/` ; `npm run build` recompile `jarvis/static/` (committé, servi par `jarvis/web.py`).
Vérifier avec `npx tsc -p .` avant de committer.
