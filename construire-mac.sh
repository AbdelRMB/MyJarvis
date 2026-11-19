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
# Signature STABLE : macOS rattache les autorisations (micro, écran, accessibilité…) à la signature.
# Avec une signature « ad hoc », elle change à chaque version et macOS oublie tout ; avec un certificat
# Apple (Developer ID ou Apple Development), les autorisations restent acquises après chaque mise à jour.
# Choix : $JARVIS_SIGNATURE, sinon Developer ID Application, sinon Apple Development, sinon ad hoc.
IDENTITE=${JARVIS_SIGNATURE:-$(security find-identity -v -p codesigning 2>/dev/null | grep -o '"Developer ID Application[^"]*"' | head -1 | tr -d '"' || true)}
[ -n "$IDENTITE" ] || IDENTITE=$(security find-identity -v -p codesigning 2>/dev/null | grep -o '"Apple Development[^"]*"' | head -1 | tr -d '"' || true)
if [ -n "$IDENTITE" ]; then
  echo "    signature : $IDENTITE"
  codesign --force --deep --sign "$IDENTITE" --entitlements entitlements.plist dist/Jarvis.app
else
  echo "    ! aucun certificat Apple : signature ad hoc (les autorisations seront redemandées à chaque version)"
  codesign --force --deep --sign - --entitlements entitlements.plist dist/Jarvis.app
fi

echo "[5/5] Image disque..."
mkdir -p installateur
DMG="installateur/Jarvis-${VERSION}-mac-${PUCE}.dmg"
TMP=$(mktemp -d)
# copie SANS les attributs Finder (le Bureau synchronisé en ajoute, ce qui invaliderait la signature)
ditto --norsrc --noextattr --noacl dist/Jarvis.app "$TMP/Jarvis.app"
xattr -cr "$TMP/Jarvis.app"
codesign --verify --deep --strict "$TMP/Jarvis.app"
ln -s /Applications "$TMP/Applications"
rm -f "$DMG"
hdiutil create -volname "Jarvis" -srcfolder "$TMP" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$TMP" build
echo
echo "Terminé : $DMG"
echo "Installe-le : ouvre le .dmg, glisse Jarvis dans Applications, puis clic droit > Ouvrir la première fois."
