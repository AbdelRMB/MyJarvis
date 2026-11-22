#!/bin/bash
# Construit le .dmg sur ce Mac et le publie dans les GitHub Releases (gratuit, sans limite).
# Avant : version incrémentée dans wesley/version.py, description dans CHANGELOG.md, commit poussé.
set -euo pipefail
cd "$(dirname "$0")"
bash construire-mac.sh
VERSION=$(grep -E '^VERSION = ' wesley/version.py | cut -d'"' -f2)
# + copie sous l'ancien nom (Jarvis-…dmg) : la mise à jour automatique des Mac encore en version Jarvis la cherche
.venv-mac/bin/python publier.py "installateur/Wesley-${VERSION}-mac-$(uname -m).dmg" "installateur/Jarvis-${VERSION}-mac-$(uname -m).dmg"
