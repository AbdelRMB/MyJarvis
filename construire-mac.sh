#!/bin/bash
# Construit Wesley pour macOS : installateur/Wesley-<version>-mac-<puce>.dmg
# À lancer SUR UN MAC (Apple Silicon ou Intel), dans le dossier du projet :  ./construire-mac.sh
# Prérequis : Python 3.12 (python.org ou « brew install python@3.12 ») et Node.js (« brew install node »).
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(grep -E '^VERSION = ' wesley/version.py | cut -d'"' -f2)
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
# modèles communs d'openWakeWord (spectrogramme, empreintes) : servent au détecteur eveil/hey_wesley.onnx s'il existe
python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_wesley'])"

echo "[4/5] Application (PyInstaller, quelques minutes)..."
# Construction HORS du Bureau : s'il est synchronisé par iCloud, iCloud ajoute des attributs aux fichiers pendant
# la construction (signature refusée) et crée des copies « Wesley 2.app ». Dossier non synchronisé :
SORTIE="${WESLEY_BUILD:-$HOME/Library/Caches/wesley-build}"
mkdir -p "$SORTIE"
rm -rf "$SORTIE/build" "$SORTIE/dist" dist/Wesley dist/Wesley.app
pyinstaller wesley-mac.spec --noconfirm --log-level WARN --distpath "$SORTIE/dist" --workpath "$SORTIE/build"
mkdir -p dist && ln -sfn "$SORTIE/dist/Wesley.app" dist/Wesley.app   # dist/Wesley.app reste utilisable
xattr -cr "$SORTIE/dist/Wesley.app"   # retire les attributs Finder (sinon codesign refuse)
# Signature STABLE : macOS rattache les autorisations (micro, écran, accessibilité…) à la signature.
# Avec une signature « ad hoc », elle change à chaque version et macOS oublie tout ; avec un certificat
# Apple (Developer ID ou Apple Development), les autorisations restent acquises après chaque mise à jour.
# Choix : $WESLEY_SIGNATURE, sinon Developer ID Application, sinon Apple Development, sinon ad hoc.
IDENTITE=${WESLEY_SIGNATURE:-$(security find-identity -v -p codesigning 2>/dev/null | grep -o '"Developer ID Application[^"]*"' | head -1 | tr -d '"' || true)}
[ -n "$IDENTITE" ] || IDENTITE=$(security find-identity -v -p codesigning 2>/dev/null | grep -o '"Apple Development[^"]*"' | head -1 | tr -d '"' || true)
if [[ "$IDENTITE" == "Developer ID Application"* ]]; then
  # Distribution : runtime renforcé + horodatage (exigés par la notarisation Apple). On signe d'abord chaque
  # binaire intérieur (.so, .dylib, exécutables), puis les frameworks, puis l'appli elle-même.
  echo "    signature : $IDENTITE (runtime renforcé)"
  APP="$SORTIE/dist/Wesley.app"
  SIGNER=(codesign --force --timestamp --options runtime --entitlements entitlements.plist --sign "$IDENTITE")
  find "$APP/Contents" -type f \( -perm -u+x -o -name "*.so" -o -name "*.dylib" \) -print0 |
    while IFS= read -r -d '' f; do
      if file -b "$f" | grep -q "Mach-O"; then "${SIGNER[@]}" "$f"; fi
    done
  find "$APP/Contents" -type d -name "*.framework" -print0 | while IFS= read -r -d '' f; do "${SIGNER[@]}" "$f"; done
  "${SIGNER[@]}" "$APP"
elif [ -n "$IDENTITE" ]; then
  echo "    signature : $IDENTITE"
  codesign --force --deep --sign "$IDENTITE" --entitlements entitlements.plist "$SORTIE/dist/Wesley.app"
else
  echo "    ! aucun certificat Apple : signature ad hoc (les autorisations seront redemandées à chaque version)"
  codesign --force --deep --sign - --entitlements entitlements.plist "$SORTIE/dist/Wesley.app"
fi

echo "[5/5] Image disque..."
mkdir -p installateur
DMG="installateur/Wesley-${VERSION}-mac-${PUCE}.dmg"
TMP=$(mktemp -d)
# copie SANS les attributs Finder (le Bureau synchronisé en ajoute, ce qui invaliderait la signature)
ditto --norsrc --noextattr --noacl "$SORTIE/dist/Wesley.app" "$TMP/Wesley.app"
xattr -cr "$TMP/Wesley.app"
codesign --verify --deep --strict "$TMP/Wesley.app"
ln -s /Applications "$TMP/Applications"
rm -f "$DMG"
hdiutil create -volname "Wesley" -srcfolder "$TMP" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$TMP"

# Notarisation Apple (seulement avec un certificat Developer ID et les identifiants Apple) : le .dmg s'ouvre
# alors sans avertissement « développeur non identifié » sur n'importe quel Mac.
if [[ "$IDENTITE" == "Developer ID Application"* && -n "${APPLE_ID:-}" && -n "${APPLE_MDP_APPLI:-}" && -n "${APPLE_EQUIPE:-}" ]]; then
  echo "    notarisation par Apple (quelques minutes)..."
  codesign --force --timestamp --sign "$IDENTITE" "$DMG"
  xcrun notarytool submit "$DMG" --apple-id "$APPLE_ID" --password "$APPLE_MDP_APPLI" --team-id "$APPLE_EQUIPE" --wait     | tee "$SORTIE/notarisation.txt"
  if ! grep -q "status: Accepted" "$SORTIE/notarisation.txt"; then
    ID=$(grep -m1 -o 'id: [0-9a-f-]*' "$SORTIE/notarisation.txt" | cut -d' ' -f2)
    [ -n "$ID" ] && xcrun notarytool log "$ID" --apple-id "$APPLE_ID" --password "$APPLE_MDP_APPLI" --team-id "$APPLE_EQUIPE" || true
    echo "Notarisation refusée (détails ci-dessus)."; exit 1
  fi
  xcrun stapler staple "$DMG"
  echo "    notarisé ✓"
elif [[ "$IDENTITE" == "Developer ID Application"* ]]; then
  echo "    (pas de notarisation : APPLE_ID, APPLE_MDP_APPLI ou APPLE_EQUIPE manquant)"
fi
echo
echo "Terminé : $DMG"
echo "Installe-le : ouvre le .dmg, glisse Wesley dans Applications, puis clic droit > Ouvrir la première fois."
