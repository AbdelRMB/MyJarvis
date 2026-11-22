"""Mises à jour de Wesley depuis les GitHub Releases du dépôt (public : aucun jeton nécessaire ;
un jeton GitHub reste possible pour un dépôt privé ou pour dépasser la limite de 60 requêtes/heure).

- lister()     : versions plus récentes que celle installée, avec leur description (CHANGELOG.md).
- installer(v) : télécharge l'installateur de la version v pour cet appareil, quitte Wesley,
                 remplace l'appli sans la désinstaller, puis la relance. Mémoire et réglages ne bougent pas.
Chaque version contient toutes les précédentes : installer la 1.0.6 inclut la 1.0.5.
"""
import platform
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests

from .config import GELE, RACINE, ecrire_trousseau, lire_trousseau
from .version import DEPOT, VERSION

API = f"https://api.github.com/repos/{DEPOT}"
CLE = "github:jeton"
ETAT = {"en_cours": False}


# ---------- jeton GitHub (trousseau / gestionnaire d'identifiants de l'appareil) ----------
_jeton_lu: list = []   # lu une seule fois par lancement (chaque lecture du trousseau peut afficher une demande)


def jeton() -> str:
    if not _jeton_lu:
        try:
            _jeton_lu.append(lire_trousseau(CLE))
        except Exception:
            _jeton_lu.append("")
    return _jeton_lu[0]


def definir_jeton(valeur: str):
    _jeton_lu[:] = [valeur.strip()]
    ecrire_trousseau(CLE, valeur.strip())
    from . import compte
    compte.secret_modifie(CLE, valeur.strip())


def _entetes(binaire=False):
    h = {"X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Wesley",
         "Accept": "application/octet-stream" if binaire else "application/vnd.github+json"}
    if jeton():
        h["Authorization"] = f"Bearer {jeton()}"
    return h


def _num(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


def _fichier_attendu(version: str) -> str:
    if sys.platform == "darwin":
        return f"Wesley-{version}-mac-{platform.machine()}.dmg"
    return f"WesleySetup-{version}.exe"


# ---------- liste ----------
def lister() -> dict:
    base = {"version": VERSION, "jeton": bool(jeton()), "installee": GELE, "majs": [], "journal": [], "erreur": "",
            "prete": version_prete()}
    try:
        r = requests.get(f"{API}/releases?per_page=50", headers=_entetes(), timeout=15)
    except requests.RequestException as e:
        return {**base, "erreur": f"GitHub injoignable : {e}"}
    if r.status_code == 401:
        return {**base, "erreur": "Jeton GitHub refusé (expiré) : retire-le ou remplace-le."}
    if r.status_code == 403:
        return {**base, "erreur": "GitHub limite les vérifications : réessaie dans une heure."}
    if r.status_code == 404:
        return {**base, "erreur": f"Dépôt {DEPOT} introuvable."}
    if not r.ok:
        return {**base, "erreur": f"GitHub a répondu {r.status_code}."}
    majs, journal = [], []
    for rel in r.json():
        v = rel["tag_name"].lstrip("v")
        if rel.get("draft"):
            continue
        # journal : toutes les versions publiées, avec leur description (la tienne est marquée)
        journal.append({"version": v, "description": rel.get("body") or "", "date": (rel.get("published_at") or "")[:10],
                        "installee": v == VERSION, "plus_recente": _num(v) > _num(VERSION)})
        if _num(v) <= _num(VERSION):
            continue
        nom = _fichier_attendu(v)
        fichier = next((a for a in rel.get("assets", []) if a["name"] == nom), None)
        majs.append({"version": v, "titre": rel.get("name") or f"Wesley {v}", "description": rel.get("body") or "",
                     "date": (rel.get("published_at") or "")[:10], "disponible": bool(fichier),
                     "taille": fichier["size"] if fichier else 0, "id_fichier": fichier["id"] if fichier else None})
    majs.sort(key=lambda m: _num(m["version"]), reverse=True)
    journal.sort(key=lambda m: _num(m["version"]), reverse=True)
    return {**base, "majs": majs, "journal": journal}


# ---------- installation ----------
def installer(version: str, progression, quitter):
    """progression(etape, pct, texte) est appelé pendant l'opération ; quitter() ferme Wesley à la fin."""
    if ETAT["en_cours"]:
        raise RuntimeError("Une mise à jour est déjà en cours.")
    if not GELE:
        raise RuntimeError("Wesley tourne depuis le code source : mets-le à jour avec « git pull ».")
    maj = next((m for m in lister()["majs"] if m["version"] == version), None)
    if not maj or not maj["id_fichier"]:
        raise RuntimeError(f"Version {version} introuvable pour cet appareil.")
    ETAT["en_cours"] = True
    threading.Thread(target=_installer, args=(maj, progression, quitter), daemon=True).start()


def _telecharger(maj, cible: Path, progression=None):
    """Télécharge l'installateur (fichier .part renommé à la fin) et vérifie sa taille."""
    progression = progression or (lambda *a: None)
    partiel = cible.with_name(cible.name + ".part")
    # l'API renvoie vers un lien de stockage temporaire ; requests n'y renvoie pas le jeton
    with requests.get(f"{API}/releases/assets/{maj['id_fichier']}", headers=_entetes(True), stream=True,
                      timeout=60) as r:
        r.raise_for_status()
        total, recu, dernier = int(r.headers.get("content-length") or maj["taille"] or 0), 0, 0
        with open(partiel, "wb") as f:
            for bloc in r.iter_content(1 << 20):
                f.write(bloc)
                recu += len(bloc)
                pct = int(recu * 100 / total) if total else 0
                if pct != dernier:
                    dernier = pct
                    progression("telechargement", pct, f"Téléchargement… {recu >> 20} / {total >> 20} Mo")
    if maj.get("taille") and partiel.stat().st_size != maj["taille"]:
        partiel.unlink(missing_ok=True)
        raise RuntimeError("téléchargement incomplet")
    partiel.replace(cible)


def _lancer_installateur(cible: Path, version: str, cache=False):
    if sys.platform == "darwin":
        _remplacer_mac(cible, version, cache)
    else:
        # même AppId : l'installateur remplace l'ancienne version en place, puis relance Wesley
        subprocess.Popen([str(cible), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                         creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _installer(maj, progression, quitter):
    try:
        dossier = Path(tempfile.mkdtemp(prefix="wesley-maj-"))
        cible = dossier / _fichier_attendu(maj["version"])
        progression("telechargement", 0, f"Téléchargement de Wesley {maj['version']}…")
        _telecharger(maj, cible, progression)
        progression("installation", 100, "Installation : Wesley va se fermer puis se relancer tout seul.")
        _lancer_installateur(cible, maj["version"])
        ETAT["quitter_pour_maj"] = True   # app.py : fermeture immédiate, sans l'extraction des souvenirs
        time.sleep(1.5)
        quitter()
        time.sleep(15)   # la fenêtre ne s'est pas fermée : on part quand même, l'installateur attend notre fin
        import os
        os._exit(0)
    except Exception as e:
        ETAT["en_cours"] = False
        progression("erreur", 0, f"Mise à jour impossible : {e}")


def _bundle_mac() -> Path:
    """…/Wesley.app (l'exécutable est dans Wesley.app/Contents/MacOS/)."""
    return Path(sys.executable).resolve().parents[2]


def _remplacer_mac(dmg: Path, version: str, cache: bool = False):
    """Script détaché : attend que Wesley soit fermé (en le forçant au bout de 20 s), copie la nouvelle appli à côté,
    vérifie qu'elle est complète et dans la bonne version, puis échange les deux d'un coup (rien à moitié copié dans
    /Applications), relance Wesley et le vérifie. Un verrou empêche deux installations en même temps.
    L'appli s'installe toujours sous le nom Wesley.app (installée sous un autre nom, elle est remplacée puis retirée)."""
    import os
    import shlex
    actuelle = _bundle_mac()
    appli = actuelle.parent / "Wesley.app"
    q = shlex.quote
    neuve = appli.parent / ".Wesley-maj.app"
    ancienne = appli.parent / ".Wesley-ancien.app"
    script = dmg.parent / "installer.sh"
    script.write_text(f"""#!/bin/bash
# Mise à jour de Wesley {version} (journal : logs/mise_a_jour.log)
APPLI={q(str(appli))}; ACTUELLE={q(str(actuelle))}; NEUVE={q(str(neuve))}; ANCIENNE={q(str(ancienne))}; DMG={q(str(dmg))}
VERSION={q(version)}; PID={os.getpid()}; VERROU=/tmp/wesley-maj.verrou
log() {{ echo "$(date '+%F %T') $*"; }}
if ! mkdir "$VERROU" 2>/dev/null; then
  if [ -n "$(find "$VERROU" -maxdepth 0 -mmin -15 2>/dev/null)" ]; then log "une autre installation est en cours : abandon"; exit 0; fi
  rm -rf "$VERROU"; mkdir "$VERROU"
fi
MNT=$(mktemp -d)
fin() {{ hdiutil detach "$MNT" -quiet -force 2>/dev/null; rm -rf "$NEUVE" "$VERROU" "$(dirname "$DMG")"; }}
trap fin EXIT
relancer() {{
  [ -d "$APPLI" ] || APPLI="$ACTUELLE"   # échec avant la mise en place : on relance l'appli d'origine
  for i in 1 2 3; do open "$APPLI"{' --args --cache' if cache else ''} && return 0; sleep 2; done
  "$APPLI/Contents/MacOS/Wesley"{' --cache' if cache else ''} >/dev/null 2>&1 &
}}
log "début de la mise à jour vers $VERSION"
# 1. Wesley doit être fermé (20 s max, sinon on le force), ainsi que toute autre copie lancée entre-temps
for i in $(seq 1 40); do kill -0 $PID 2>/dev/null || break; sleep 0.5; done
kill -9 $PID 2>/dev/null
pkill -9 -f "$APPLI/Contents/MacOS/" 2>/dev/null
pkill -9 -f "$ACTUELLE/Contents/MacOS/" 2>/dev/null
sleep 1
# 2. Copie de la nouvelle version À CÔTÉ de l'ancienne, vérifiée, avec 3 essais
ok=""
for essai in 1 2 3; do
  hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$MNT" "$DMG" >/dev/null || {{ log "montage impossible (essai $essai)"; sleep 2; continue; }}
  rm -rf "$NEUVE"
  if ditto "$MNT/Wesley.app" "$NEUVE" \
     && [ "$(defaults read "$NEUVE/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null)" = "$VERSION" ] \
     && [ -x "$NEUVE/Contents/MacOS/Wesley" ] \
     && codesign --verify "$NEUVE" 2>/dev/null; then ok=1; break; fi
  log "copie incomplète (essai $essai), nouvel essai"
  hdiutil detach "$MNT" -quiet -force 2>/dev/null; sleep 2
done
if [ -z "$ok" ]; then log "ÉCHEC : la nouvelle version n'a pas pu être copiée, l'ancienne est gardée"; relancer; exit 1; fi
# 3. Échange en une fois (renommages : instantanés), avec retour à l'ancienne si besoin
pkill -9 -f "$APPLI/Contents/MacOS/" 2>/dev/null
rm -rf "$ANCIENNE"
[ -d "$APPLI" ] && ! mv "$APPLI" "$ANCIENNE" && {{ log "ÉCHEC : impossible de déplacer l'ancienne appli"; relancer; exit 1; }}
if ! mv "$NEUVE" "$APPLI"; then
  log "ÉCHEC : impossible de mettre la nouvelle appli en place, retour à l'ancienne"
  [ -d "$ANCIENNE" ] && mv "$ANCIENNE" "$APPLI"; relancer; exit 1
fi
rm -rf "$ANCIENNE"
if [ "$ACTUELLE" != "$APPLI" ] && [ -d "$ACTUELLE" ]; then rm -rf "$ACTUELLE"; log "ancienne appli $ACTUELLE retirée"; fi
xattr -dr com.apple.quarantine "$APPLI" 2>/dev/null
log "Wesley $VERSION installé"
# 4. Relance (plusieurs essais) et vérification
relancer
for i in $(seq 1 60); do curl -s -o /dev/null --max-time 2 http://127.0.0.1:7777/api/session && {{ log "Wesley relancé"; exit 0; }}; sleep 1; done
log "Wesley ne répond pas après la relance : nouvel essai"; relancer
""", encoding="utf-8")
    (RACINE / "logs").mkdir(exist_ok=True)
    log = open(RACINE / "logs" / "mise_a_jour.log", "a")
    subprocess.Popen(["/bin/bash", str(script)], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)


# ---------- mises à jour automatiques : téléchargées en fond, installées au prochain démarrage ----------
DOSSIER_AUTO = RACINE / "maj"


def _pret() -> dict | None:
    import json
    try:
        p = json.loads((DOSSIER_AUTO / "pret.json").read_text(encoding="utf-8"))
        f = DOSSIER_AUTO / p["fichier"]
        return p if f.exists() and (not p.get("taille") or f.stat().st_size == p["taille"]) else None
    except (OSError, ValueError, KeyError):
        return None


def version_prete() -> str:
    p = _pret()
    return p["version"] if p and _num(p["version"]) > _num(VERSION) else ""


def installer_au_demarrage(cache: bool) -> bool:
    """Au lancement de l'appli : une version téléchargée en fond attend ? On l'installe tout de suite (Wesley se
    relance tout seul). Deux essais au plus par version, pour ne jamais tourner en boucle si ça échoue."""
    import json
    import shutil
    from .config import CONFIG
    if not GELE or not CONFIG.get("maj_auto", True):
        return False
    p = _pret()
    if not p or _num(p["version"]) <= _num(VERSION):
        shutil.rmtree(DOSSIER_AUTO, ignore_errors=True)   # déjà installée (ou rien) : on fait le ménage
        return False
    if p.get("essais", 0) >= 2:
        return False
    p["essais"] = p.get("essais", 0) + 1
    (DOSSIER_AUTO / "pret.json").write_text(json.dumps(p), encoding="utf-8")
    # le script d'installation supprime son dossier à la fin : on lui donne une copie
    copie = Path(tempfile.mkdtemp(prefix="wesley-maj-")) / p["fichier"]
    shutil.copy2(DOSSIER_AUTO / p["fichier"], copie)
    print(f"  Mise à jour automatique vers {p['version']}…")
    _lancer_installateur(copie, p["version"], cache)
    return True


def _verifier_auto():
    import json
    from .config import CONFIG
    if not GELE or not CONFIG.get("maj_auto", True) or ETAT["en_cours"]:
        return
    l = lister()
    maj = next((m for m in l["majs"] if m["disponible"]), None)   # la plus récente disponible pour cet appareil
    if not maj:
        return
    p = _pret()
    if p and p["version"] == maj["version"]:
        return
    DOSSIER_AUTO.mkdir(parents=True, exist_ok=True)
    for f in DOSSIER_AUTO.iterdir():   # une ancienne version téléchargée est remplacée
        f.unlink(missing_ok=True)
    nom = _fichier_attendu(maj["version"])
    _telecharger(maj, DOSSIER_AUTO / nom)
    (DOSSIER_AUTO / "pret.json").write_text(json.dumps({"version": maj["version"], "fichier": nom, "taille": maj["taille"]}),
                                            encoding="utf-8")
    from . import notifications
    notifications.ajouter(f"Wesley {maj['version']} est prêt",
                          "Il s'installera tout seul au prochain démarrage de Wesley (ou maintenant depuis l'écran Mises à jour).",
                          genre="info", vue="majs")


def demarrer_auto():
    """Vérifie 3 minutes après le lancement, puis toutes les 6 heures."""
    def boucle():
        time.sleep(180)
        while True:
            try:
                _verifier_auto()
            except Exception as e:
                print(f"  ! Mise à jour automatique : {e}")
            time.sleep(6 * 3600)
    threading.Thread(target=boucle, daemon=True, name="maj-auto").start()


# ---------- raccourci « Mettre à jour Wesley » (Spotlight / Launchpad) sur Mac ----------
def creer_raccourci_mac():
    if not (GELE and sys.platform == "darwin"):
        return
    appli = _bundle_mac()
    if not str(appli).startswith("/Applications/"):
        return   # lancé depuis le .dmg : on attend qu'il soit installé
    import shutil
    raccourci = Path.home() / "Applications" / "Mettre à jour Wesley.app"
    marque = raccourci / "Contents" / "Resources" / "wesley-cible.txt"
    if marque.exists() and marque.read_text() == str(appli):
        return
    raccourci.parent.mkdir(exist_ok=True)
    exe = appli / "Contents" / "MacOS" / "Wesley"
    source = f'do shell script quoted form of "{exe}" & " --maj > /dev/null 2>&1 &"'
    subprocess.run(["/usr/bin/osacompile", "-o", str(raccourci), "-e", source], capture_output=True, timeout=30)
    icones = list((appli / "Contents" / "Resources").glob("*.icns"))
    if icones and (raccourci / "Contents" / "Resources").exists():
        shutil.copy2(icones[0], raccourci / "Contents" / "Resources" / "applet.icns")
        subprocess.run(["/usr/bin/touch", str(raccourci)])
    if marque.parent.exists():
        marque.write_text(str(appli))
