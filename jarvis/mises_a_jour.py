"""Mises à jour de Jarvis depuis les GitHub Releases du dépôt (public : aucun jeton nécessaire ;
un jeton GitHub reste possible pour un dépôt privé ou pour dépasser la limite de 60 requêtes/heure).

- lister()     : versions plus récentes que celle installée, avec leur description (CHANGELOG.md).
- installer(v) : télécharge l'installateur de la version v pour cet appareil, quitte Jarvis,
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

from .config import GELE, RACINE
from .version import DEPOT, VERSION

API = f"https://api.github.com/repos/{DEPOT}"
SERVICE, CLE = "Jarvis", "github:jeton"
ETAT = {"en_cours": False}


# ---------- jeton GitHub (trousseau / gestionnaire d'identifiants de l'appareil) ----------
_jeton_lu: list = []   # lu une seule fois par lancement (chaque lecture du trousseau peut afficher une demande)


def jeton() -> str:
    if not _jeton_lu:
        try:
            import keyring
            _jeton_lu.append(keyring.get_password(SERVICE, CLE) or "")
        except Exception:
            _jeton_lu.append("")
    return _jeton_lu[0]


def definir_jeton(valeur: str):
    import keyring
    _jeton_lu[:] = [valeur.strip()]
    if valeur:
        keyring.set_password(SERVICE, CLE, valeur.strip())
    else:
        try:
            keyring.delete_password(SERVICE, CLE)
        except Exception:
            pass
    from . import compte
    compte.secret_modifie(CLE, valeur.strip())


def _entetes(binaire=False):
    h = {"X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Jarvis",
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
        return f"Jarvis-{version}-mac-{platform.machine()}.dmg"
    return f"JarvisSetup-{version}.exe"


# ---------- liste ----------
def lister() -> dict:
    base = {"version": VERSION, "jeton": bool(jeton()), "installee": GELE, "majs": [], "journal": [], "erreur": ""}
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
        majs.append({"version": v, "titre": rel.get("name") or f"Jarvis {v}", "description": rel.get("body") or "",
                     "date": (rel.get("published_at") or "")[:10], "disponible": bool(fichier),
                     "taille": fichier["size"] if fichier else 0, "id_fichier": fichier["id"] if fichier else None})
    majs.sort(key=lambda m: _num(m["version"]), reverse=True)
    journal.sort(key=lambda m: _num(m["version"]), reverse=True)
    return {**base, "majs": majs, "journal": journal}


# ---------- installation ----------
def installer(version: str, progression, quitter):
    """progression(etape, pct, texte) est appelé pendant l'opération ; quitter() ferme Jarvis à la fin."""
    if ETAT["en_cours"]:
        raise RuntimeError("Une mise à jour est déjà en cours.")
    if not GELE:
        raise RuntimeError("Jarvis tourne depuis le code source : mets-le à jour avec « git pull ».")
    maj = next((m for m in lister()["majs"] if m["version"] == version), None)
    if not maj or not maj["id_fichier"]:
        raise RuntimeError(f"Version {version} introuvable pour cet appareil.")
    ETAT["en_cours"] = True
    threading.Thread(target=_installer, args=(maj, progression, quitter), daemon=True).start()


def _installer(maj, progression, quitter):
    try:
        dossier = Path(tempfile.mkdtemp(prefix="jarvis-maj-"))
        cible = dossier / _fichier_attendu(maj["version"])
        progression("telechargement", 0, f"Téléchargement de Jarvis {maj['version']}…")
        # l'API renvoie vers un lien de stockage temporaire ; requests n'y renvoie pas le jeton
        with requests.get(f"{API}/releases/assets/{maj['id_fichier']}", headers=_entetes(True), stream=True,
                          timeout=60) as r:
            r.raise_for_status()
            total, recu, dernier = int(r.headers.get("content-length") or maj["taille"] or 0), 0, 0
            with open(cible, "wb") as f:
                for bloc in r.iter_content(1 << 20):
                    f.write(bloc)
                    recu += len(bloc)
                    pct = int(recu * 100 / total) if total else 0
                    if pct != dernier:
                        dernier = pct
                        progression("telechargement", pct, f"Téléchargement… {recu >> 20} / {total >> 20} Mo")
        progression("installation", 100, "Installation : Jarvis va se fermer puis se relancer tout seul.")
        if sys.platform == "darwin":
            _remplacer_mac(cible)
        else:
            # même AppId : l'installateur remplace l'ancienne version en place, puis relance Jarvis
            subprocess.Popen([str(cible), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                             creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        time.sleep(1.5)
        quitter()
    except Exception as e:
        ETAT["en_cours"] = False
        progression("erreur", 0, f"Mise à jour impossible : {e}")


def _bundle_mac() -> Path:
    """…/Jarvis.app (l'exécutable est dans Jarvis.app/Contents/MacOS/)."""
    return Path(sys.executable).resolve().parents[2]


def _remplacer_mac(dmg: Path):
    appli = _bundle_mac()
    script = dmg.parent / "installer.sh"
    script.write_text(f"""#!/bin/bash
# attend la fermeture de Jarvis, remplace l'appli par celle du .dmg, puis la relance
while kill -0 {__import__('os').getpid()} 2>/dev/null; do sleep 0.5; done
MNT=$(mktemp -d)
hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "{dmg}" >/dev/null || exit 1
rm -rf "{appli}.ancien"
mv "{appli}" "{appli}.ancien" && ditto "$MNT/Jarvis.app" "{appli}" && rm -rf "{appli}.ancien" || mv "{appli}.ancien" "{appli}"
hdiutil detach "$MNT" -quiet
xattr -dr com.apple.quarantine "{appli}" 2>/dev/null
open "{appli}"
rm -rf "{dmg.parent}"
""", encoding="utf-8")
    log = open(RACINE / "logs" / "mise_a_jour.log", "a")
    subprocess.Popen(["/bin/bash", str(script)], stdout=log, stderr=log, start_new_session=True)


# ---------- raccourci « Mettre à jour Jarvis » (Spotlight / Launchpad) sur Mac ----------
def creer_raccourci_mac():
    if not (GELE and sys.platform == "darwin"):
        return
    appli = _bundle_mac()
    if not str(appli).startswith("/Applications/"):
        return   # lancé depuis le .dmg : on attend qu'il soit installé
    raccourci = Path.home() / "Applications" / "Mettre à jour Jarvis.app"
    marque = raccourci / "Contents" / "Resources" / "jarvis-cible.txt"
    if marque.exists() and marque.read_text() == str(appli):
        return
    raccourci.parent.mkdir(exist_ok=True)
    exe = appli / "Contents" / "MacOS" / "Jarvis"
    source = f'do shell script quoted form of "{exe}" & " --maj > /dev/null 2>&1 &"'
    subprocess.run(["/usr/bin/osacompile", "-o", str(raccourci), "-e", source], capture_output=True, timeout=30)
    icones = list((appli / "Contents" / "Resources").glob("*.icns"))
    if icones and (raccourci / "Contents" / "Resources").exists():
        import shutil
        shutil.copy2(icones[0], raccourci / "Contents" / "Resources" / "applet.icns")
        subprocess.run(["/usr/bin/touch", str(raccourci)])
    if marque.parent.exists():
        marque.write_text(str(appli))
