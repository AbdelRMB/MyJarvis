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
- `python -m pytest tests -q` : tests du cœur Python (seul pytest est nécessaire)
- `cd serveur && WESLEY_DB=/tmp/wesley-test.db python -m pytest tests -q` : tests du serveur de comptes

## Conventions
- Messages, commits, CHANGELOG et textes de l'interface en français ; traductions anglaises dans `interface/src/lib/en.ts` (mobile : `en-mobile.ts`).
- Un changement de l'appli = nouvelle version dans `wesley/version.py` + section `## x.y.z` en haut de `CHANGELOG.md`, écrite pour l'utilisateur.
- Jamais de données personnelles ni de secrets dans git (`.env`, `config.json`, `memoire/`, `logs/`, `comptes/`, fichiers de déploiement du serveur).
- Serveur de comptes : n'utiliser que **GET, POST et PUT** (`compte._appel` côté bureau, `api()` dans `interface/mobile/src`). Le proxy Apache devant l'API renvoie un 404 HTML à toute autre méthode (PATCH, DELETE…), vu dans Wesley comme « Erreur du serveur (404) sur … ». Pour modifier ou supprimer : `POST /v1/…/{id}` ou `POST /v1/…/{id}/supprimer`. Vérifié par `tests/test_methodes_serveur.py`.
- Un outil de Wesley = une fonction décorée `@outil` dans `wesley/outils/` (docstring : 1re ligne = description, puis `param: description`), module ajouté à `charger_tous()`.

## Décisions
- WESLEY.md : priorité sur la mémoire, les autres fichiers et les règles par défaut, mais la demande en cours et les consignes personnelles de l'utilisateur passent avant.
- Tâches de code : si l'agent n'a pas mis à jour le WESLEY.md, Wesley le relance une fois, puis l'y consigne lui-même avant le commit final.

## Journal des changements
- 2026-11-22 : version 2.2.0, prise en charge des WESLEY.md (lecture en priorité, transmission à Claude Code / Codex, mise à jour obligatoire à chaque modification, création à la demande, PC, Mac et mobile). Ajout de ce fichier et des tests `tests/test_wesley_md.py`.
- 2026-11-22 : tests Python du cœur (`tests/`) lancés dans le job « version » du workflow `.github/workflows/versions.yml` : ils bloquent la construction des installateurs s'ils échouent.
- 2026-11-23 : version 2.2.1, tickets (ticket n°1) : `traiter_ticket` / `resoudre_ticket` renvoyaient « Erreur du serveur (404) » car le proxy Apache bloque PATCH et DELETE. Le serveur accepte maintenant `POST /v1/admin/tickets/{id}` et `POST /v1/admin/tickets/{id}/supprimer` (PATCH/DELETE gardés), le bureau et le mobile les utilisent, le message d'erreur sans détail indique la requête. Tests : `serveur/tests/test_tickets.py`, `tests/test_methodes_serveur.py`.
