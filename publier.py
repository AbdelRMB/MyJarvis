"""Publie un installateur dans les GitHub Releases du dépôt.

Utilisé par publier-mac.sh (Mac), publier.bat (Windows) et la CI (.github/workflows/versions.yml) :
    python publier.py installateur/Jarvis-1.0.5-mac-arm64.dmg
Crée la release vX.Y.Z si elle n'existe pas (description = section « ## X.Y.Z » de CHANGELOG.md),
puis y ajoute le fichier (remplace un fichier du même nom). Le 2e appareil ajoute son installateur à la même release.
Identifiant GitHub : celui que git utilise déjà sur cette machine (aucun jeton à créer).
"""
import re
import subprocess
import sys
from pathlib import Path

import requests

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from jarvis.version import DEPOT, VERSION  # noqa: E402

API = f"https://api.github.com/repos/{DEPOT}"


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ICI, capture_output=True, text=True).stdout.strip()


def jeton() -> str:
    import os
    if os.environ.get("GH_TOKEN"):   # GitHub Actions
        return os.environ["GH_TOKEN"]
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, cwd=ICI)
    m = re.search(r"^password=(.+)$", r.stdout, re.M)
    if not m:
        sys.exit("Pas d'identifiant GitHub dans git sur cette machine : fais un « git push » une fois pour te connecter.")
    return m.group(1)


def notes() -> str:
    texte = (ICI / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(VERSION)}\s*$(.*?)(?=^## |\Z)", texte, re.M | re.S)
    if not m or not m.group(1).strip():
        sys.exit(f"CHANGELOG.md n'a pas de description pour la version {VERSION} (section « ## {VERSION} »).")
    return m.group(1).strip()


def main():
    fichier = Path(sys.argv[1])
    if not fichier.exists():
        sys.exit(f"Introuvable : {fichier}")
    if VERSION not in fichier.name:
        sys.exit(f"{fichier.name} ne correspond pas à la version {VERSION} de jarvis/version.py.")
    git("fetch", "-q", "origin")
    if git("rev-list", "--count", "origin/main..HEAD") not in ("", "0"):
        sys.exit("Des commits ne sont pas encore poussés : fais « git push » avant de publier.")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {jeton()}", "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28"})
    tag = f"v{VERSION}"
    r = s.get(f"{API}/releases/tags/{tag}")
    if r.status_code == 404:
        r = s.post(f"{API}/releases", json={"tag_name": tag, "target_commitish": git("rev-parse", "HEAD"),
                                            "name": f"Jarvis {VERSION}", "body": notes()})
        if r.status_code == 422:   # créée au même moment par l'autre appareil / la CI
            r = s.get(f"{API}/releases/tags/{tag}")
        else:
            print(f"Release {tag} créée.")
    r.raise_for_status()
    rel = r.json()
    for a in rel.get("assets", []):
        if a["name"] == fichier.name:
            s.delete(f"{API}/releases/assets/{a['id']}").raise_for_status()
            print(f"Ancien {fichier.name} remplacé.")
    taille = fichier.stat().st_size
    print(f"Envoi de {fichier.name} ({taille >> 20} Mo)…")
    with open(fichier, "rb") as f:
        r = s.post(rel["upload_url"].split("{")[0], params={"name": fichier.name}, data=f,
                   headers={"Content-Type": "application/octet-stream", "Content-Length": str(taille)}, timeout=3600)
    r.raise_for_status()
    print(f"Publié : {rel['html_url']}")


if __name__ == "__main__":
    main()
