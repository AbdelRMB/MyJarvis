"""Sauvegarde complète et restauration (Réglages › Application) : un seul fichier chiffré avec un mot de passe.

Contenu : souvenirs, historique des conversations, liste À faire, automatisations, sites appris, profil, et
transcriptions de cet appareil (texte, locuteurs, résumés ; pas l'audio). Marche en local comme en ligne : de quoi
changer d'ordinateur, garder une copie hors du serveur ou quitter le service sans rien perdre.

Format : b"WESLEY-SAUVEGARDE-1\\n" + sel (16 o) + nonce (12 o) + AES-256-GCM(zip). Clé = scrypt(mot de passe, sel).
Le mot de passe n'est jamais gardé : sans lui, le fichier est illisible.

Restaurer FUSIONNE, n'écrase jamais : seuls les éléments absents sont ajoutés (souvenirs, lignes d'historique,
tâches, automatisations, sites, transcriptions), par les mêmes fonctions que l'appli (donc synchronisés avec le
compte en ligne s'il y en a un). Connecteurs et clés ne sont pas dans le fichier (ils restent dans le trousseau).
"""
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from . import config
from .config import MACHINE

ENTETE = b"WESLEY-SAUVEGARDE-1\n"
EXTENSION = ".wesley"
FICHIERS_COMPTE = ("afaire.json", "automatisations.json", "profil.json")
LONGUEUR_MIN = 8


class ErreurSauvegarde(Exception):
    pass


def _cle(mdp: str, sel: bytes) -> bytes:
    import hashlib
    return hashlib.scrypt(mdp.encode(), salt=sel, n=2**15, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024)


def chiffrer(donnees: bytes, mdp: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    sel, nonce = os.urandom(16), os.urandom(12)
    return ENTETE + sel + nonce + AESGCM(_cle(mdp, sel)).encrypt(nonce, donnees, ENTETE)


def dechiffrer(blob: bytes, mdp: str) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(ENTETE):
        raise ErreurSauvegarde("Ce fichier n'est pas une sauvegarde de Wesley.")
    reste = blob[len(ENTETE):]
    sel, nonce, chiffre = reste[:16], reste[16:28], reste[28:]
    try:
        return AESGCM(_cle(mdp, sel)).decrypt(nonce, chiffre, ENTETE)
    except InvalidTag:
        raise ErreurSauvegarde("Mot de passe incorrect, ou fichier abîmé.") from None


def _dossier_transcriptions() -> Path:
    from . import transcription
    return transcription.DOSSIER_DONNEES


# ---------- créer ----------
def contenu_zip() -> tuple[bytes, dict]:
    """Archive zip des données (en mémoire) et son manifeste."""
    from .version import VERSION
    compte = Path(config.PARTAGE)
    tampon = io.BytesIO()
    nb = {"souvenirs": 0, "jours": 0, "transcriptions": 0}
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        faits = compte / "memoire" / "faits.json"
        if faits.exists():
            z.write(faits, "memoire/faits.json")
            try:
                nb["souvenirs"] = len(json.loads(faits.read_text(encoding="utf-8")))
            except ValueError:
                pass
        for f in sorted((compte / "memoire" / "historique").glob("*.md")):
            z.write(f, f"memoire/historique/{f.name}")
            nb["jours"] += 1
        for nom in FICHIERS_COMPTE:
            if (compte / nom).exists():
                z.write(compte / nom, nom)
        for f in sorted((compte / "sites").rglob("*")) if (compte / "sites").exists() else []:
            if f.is_file():
                z.write(f, f"sites/{f.relative_to(compte / 'sites').as_posix()}")
        dt = _dossier_transcriptions()
        for f in sorted(list(dt.glob("*.json")) + list(dt.glob("*.npz"))) if dt.exists() else []:
            z.write(f, f"transcriptions/{f.name}")   # .npz : empreintes des voix (pour refaire la répartition)
            nb["transcriptions"] += f.suffix == ".json"
        manifeste = {"version": VERSION, "date": datetime.now().isoformat(timespec="seconds"), "appareil": MACHINE,
                     "contenu": nb}
        z.writestr("manifeste.json", json.dumps(manifeste, ensure_ascii=False, indent=1))
    return tampon.getvalue(), manifeste


def creer(mdp: str, dossier: Path | None = None) -> dict:
    """Écrit la sauvegarde chiffrée (Téléchargements par défaut) ; renvoie {fichier, contenu}."""
    if len(mdp or "") < LONGUEUR_MIN:
        raise ErreurSauvegarde(f"Choisis un mot de passe d'au moins {LONGUEUR_MIN} caractères.")
    donnees, manifeste = contenu_zip()
    if dossier is None:
        dossier = Path.home() / "Downloads"
        if not dossier.is_dir():
            dossier = Path.home()
    f = Path(dossier) / f"wesley-sauvegarde-{datetime.now():%Y-%m-%d-%H%M}{EXTENSION}"
    f.write_bytes(chiffrer(donnees, mdp))
    return {"fichier": str(f), "contenu": manifeste["contenu"]}


# ---------- restaurer (fusion) ----------
def _json(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def _fusionner_souvenirs(src: Path) -> int:
    from . import memoire
    connus = {x["fait"].strip().lower() for x in memoire._charger()}
    n = 0
    for x in _json(src / "memoire" / "faits.json", []):
        fait = (x.get("fait") or "").strip()
        if fait and fait.lower() not in connus:
            memoire.ajouter(fait, x.get("categorie") or "general")
            connus.add(fait.lower())
            n += 1
    return n


def _fusionner_historique(src: Path) -> int:
    from . import compte, memoire
    n = 0
    memoire.HIST.mkdir(parents=True, exist_ok=True)
    for f in sorted((src / "memoire" / "historique").glob("*.md")):
        jour, _, machine = f.stem.partition("__")
        cible = memoire.HIST / f.name
        deja = set(cible.read_text(encoding="utf-8").splitlines()) if cible.exists() else set()
        nouvelles = [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and l not in deja]
        if not nouvelles:
            continue
        with open(cible, "a", encoding="utf-8") as sortie:
            sortie.write("\n".join(nouvelles) + "\n")
        if compte.connecte():   # le compte en ligne les reçoit aussi (envoi idempotent)
            for l in nouvelles:
                compte._mettre_en_attente({"type": "ligne", "ligne": {"jour": jour, "machine": machine or MACHINE,
                                                                      "ligne": l}})
        n += len(nouvelles)
    return n


def _fusionner_liste(src: Path, nom: str, module) -> int:
    restaurees = _json(src / nom, [])
    if not isinstance(restaurees, list):
        return 0
    actuelles = module.lister()
    ids = {x.get("id") for x in actuelles}
    ajout = [x for x in restaurees if isinstance(x, dict) and x.get("id") and x["id"] not in ids]
    if ajout:
        module._ecrire(actuelles + ajout)
    return len(ajout)


def _fusionner_profil(src: Path) -> bool:
    """Profil (prénom, cerveau…) : repris seulement si cet appareil n'en a pas encore."""
    p = Path(config.PROFIL)
    if p.exists() or not (src / "profil.json").exists():
        return False
    shutil.copy2(src / "profil.json", p)
    return True


def _fusionner_sites(src: Path) -> int:
    n = 0
    racine = src / "sites"
    cible = Path(config.PARTAGE) / "sites"
    for f in racine.rglob("*") if racine.exists() else []:
        if f.is_file():
            dest = cible / f.relative_to(racine)
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                n += 1
    return n


def _fusionner_transcriptions(src: Path) -> int:
    dt = _dossier_transcriptions()
    dt.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted((src / "transcriptions").glob("*")):
        dest = dt / f.name
        if f.suffix in (".json", ".npz") and not dest.exists():
            shutil.copy2(f, dest)
            n += f.suffix == ".json"
    return n


def restaurer(blob: bytes, mdp: str) -> dict:
    """Ajoute ce qui manque ; renvoie le nombre d'éléments repris par catégorie et le manifeste."""
    from . import afaire, automatisations
    donnees = dechiffrer(blob, mdp)
    with tempfile.TemporaryDirectory(prefix="wesley-restauration-") as tmp:
        src = Path(tmp)
        with zipfile.ZipFile(io.BytesIO(donnees)) as z:
            for nom in z.namelist():   # jamais en dehors du dossier temporaire (chemins « ../ »)
                cible = (src / nom).resolve()
                if src.resolve() not in cible.parents:
                    raise ErreurSauvegarde("Sauvegarde invalide.")
            z.extractall(src)
        manifeste = _json(src / "manifeste.json", {})
        if not manifeste:
            raise ErreurSauvegarde("Sauvegarde invalide (manifeste absent).")
        res = {"souvenirs": _fusionner_souvenirs(src), "historique": _fusionner_historique(src),
               "afaire": _fusionner_liste(src, "afaire.json", afaire),
               "automatisations": _fusionner_liste(src, "automatisations.json", automatisations),
               "sites": _fusionner_sites(src), "profil": _fusionner_profil(src),
               "transcriptions": _fusionner_transcriptions(src)}
    return {"repris": res, "manifeste": manifeste}
