# Wesley — instructions pour Wesley

> À lire en premier avant de travailler sur ce projet, et à suivre avant tout le reste.
> Wesley (et les agents de code qu'il pilote) le tiennent à jour à chaque modification du projet.

## Présentation
Wesley lui-même : assistant personnel de bureau (Python + interface React) pour macOS (puce Apple) et Windows,
avec une appli mobile web (`interface/mobile`) et un serveur de comptes (`serveur/`).
Le guide complet (installation, construction, règles du dépôt) est dans `CLAUDE.md` : il s'applique aussi ici.

## Commandes utiles
- `cd interface && npx tsc -p .` : vérifier les types de l'interface (bureau + mobile) avant chaque commit
- `cd interface && npm run build` : compiler l'interface de bureau dans `wesley/static` (committée)
- `cd interface && npm run build:mobile` : compiler l'appli mobile dans `serveur/mobile` (committée)
- `python -m pytest tests -q` : tests du cœur Python (pytest et numpy)
- `cd serveur && WESLEY_DB=/tmp/wesley-test.db python -m pytest tests -q` : tests du serveur de comptes

## Conventions
- Messages, commits, CHANGELOG et textes de l'interface en français ; traductions anglaises dans `interface/src/lib/en.ts` (mobile : `en-mobile.ts`).
- Un changement de l'appli = nouvelle version dans `wesley/version.py` + section `## x.y.z` en haut de `CHANGELOG.md`, écrite pour l'utilisateur.
- Jamais de données personnelles ni de secrets dans git (`.env`, `config.json`, `memoire/`, `logs/`, `comptes/`, fichiers de déploiement du serveur).
- Un outil de Wesley = une fonction décorée `@outil` dans `wesley/outils/` (docstring : 1re ligne = description, puis `param: description`), module ajouté à `charger_tous()`.

## Décisions
- Transcription de réunions (`wesley/transcription.py`) : 100 % local. Whisper (faster-whisper) + empreintes vocales sherpa-onnx (WeSpeaker CAM++, ONNX ~28 Mo téléchargé dans `RACINE/modeles` au 1er usage ; à défaut, empreinte spectrale numpy, moins précise). Regroupement en direct (cosinus, seuil 0,5) puis final hiérarchique (lien moyen) à l'arrêt ; nombre de personnes imposable. Pas de pyannote (torch, jeton Hugging Face).
- Son de l'ordinateur : ScreenCaptureKit via pyobjc sur Mac (autorisation Enregistrement de l'écran, pas de pilote), WASAPI loopback via PyAudioWPatch sur Windows, périphérique loopback (BlackHole, VB-Cable…) en secours. Les sources passent par un `Mixeur` calé sur l'horloge (WASAPI n'envoie rien quand le PC est muet). Les rappels Objective-C doivent renvoyer `None` (sinon plantage).
- Données : `RACINE/transcriptions/<id>.json` + `<id>.npz` (empreintes, jamais le son) ; fichier lisible `.md` réécrit au fil de l'eau dans `~/Documents/Wesley/Transcriptions` (`CONFIG["dossier_transcriptions"]`). Pendant une transcription au micro, l'écoute « Wesley » est coupée.
- WESLEY.md : priorité sur la mémoire, les autres fichiers et les règles par défaut, mais la demande en cours et les consignes personnelles de l'utilisateur passent avant.
- Tâches de code : si l'agent n'a pas mis à jour le WESLEY.md, Wesley le relance une fois, puis l'y consigne lui-même avant le commit final.

## Journal des changements
- 2026-11-22 : version 2.2.0, prise en charge des WESLEY.md (lecture en priorité, transmission à Claude Code / Codex, mise à jour obligatoire à chaque modification, création à la demande, PC, Mac et mobile). Ajout de ce fichier et des tests `tests/test_wesley_md.py`.
- 2026-11-22 : tests Python du cœur (`tests/`) lancés dans le job « version » du workflow `.github/workflows/versions.yml` : ils bloquent la construction des installateurs s'ils échouent.
- 2026-11-23 : version 2.3.0, onglet Transcription (réunions en ligne ou au micro, fichier importé, diarisation locale, renommage/fusion/réattribution des locuteurs, export .md/.txt), outils `demarrer_transcription`, `arreter_transcription`, `lister_transcriptions`, `lire_transcription`, tests `tests/test_transcription.py` ; la CI installe numpy pour les tests.
