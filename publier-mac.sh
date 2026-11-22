#!/bin/bash
# Construit le .dmg sur ce Mac et le publie dans les GitHub Releases (gratuit, sans limite).
# Avant : version incrémentée dans wesley/version.py, description dans CHANGELOG.md, commit poussé.
set -euo pipefail
cd "$(dirname "$0")"
bash construire-mac.sh
VERSION=$(grep -E '^VERSION = ' wesley/version.py | cut -d'"' -f2)
.venv-mac/bin/python publier.py "installateur/Wesley-${VERSION}-mac-$(uname -m).dmg"
