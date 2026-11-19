#!/bin/bash
# Construit Jarvis pour macOS : installateur/Jarvis-<version>-mac-<puce>.dmg
# À lancer SUR UN MAC (Apple Silicon ou Intel), dans le dossier du projet :  ./construire-mac.sh
# Prérequis : Python 3.12 (python.org ou « brew install python@3.12 ») et Node.js (« brew install node »).
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(grep -E '^VERSION = ' jarvis/version.py | cut -d'"' -f2)
PUCE=$(uname -m)   # arm64 (Apple Silicon) ou x86_64 (Intel)
PY=${PYTHON:-python3.12}
command -v "$PY" >/dev/null || PY=python3

echo "[1/5] Environnement Python ($($PY --version))..."
[ -d .venv-mac ] || "$PY" -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements-mac.txt

echo "[2/5] Interface..."
(cd interface && (npm ci || npm install) && npm run build)

echo "[3/5] Voix et détecteur (téléchargés une fois)..."
mkdir -p voix
[ -f voix/fr_FR-tom-medium.onnx ] || python -m piper.download_voices fr_FR-tom-medium --data-dir voix
python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis'])"

echo "[4/5] Application (PyInstaller, quelques minutes)..."
rm -rf build dist/Jarvis dist/Jarvis.app
pyinstaller jarvis-mac.spec --noconfirm --log-level WARN
xattr -cr dist/Jarvis.app   # retire les attributs Finder (sinon codesign refuse)
codesign --force --deep --sign - --entitlements entitlements.plist dist/Jarvis.app   # signature ad hoc

echo "[5/5] Image disque..."
mkdir -p installateur
DMG="installateur/Jarvis-${VERSION}-mac-${PUCE}.dmg"
TMP=$(mktemp -d)
cp -R dist/Jarvis.app "$TMP/"
ln -s /Applications "$TMP/Applications"
rm -f "$DMG"
hdiutil create -volname "Jarvis" -srcfolder "$TMP" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$TMP" build
echo
echo "Terminé : $DMG"
echo "Installe-le : ouvre le .dmg, glisse Jarvis dans Applications, puis clic droit > Ouvrir la première fois."
