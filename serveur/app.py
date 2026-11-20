"""Serveur des comptes Jarvis : chaque utilisateur a sa mémoire, son historique, ses réglages et son coffre.

- Connexion : l'appli ne transmet JAMAIS le mot de passe. Elle en dérive deux clés (scrypt) :
    * cle_auth -> envoyée ici, stockée hachée (scrypt + sel) : prouve l'identité ;
    * cle_coffre -> reste sur l'appareil : chiffre le coffre (clé API, mots de passe des connecteurs).
  Le serveur ne stocke donc que du chiffré qu'il ne peut pas lire.
- Toutes les données sont filtrées par l'utilisateur du jeton de session : personne ne voit celles des autres.
- Base SQLite (fichier /donnees/jarvis.db, volume Docker).
"""
import asyncio
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = os.environ.get("JARVIS_DB", "/donnees/jarvis.db")
app = FastAPI(title="Jarvis — comptes", docs_url=None, redoc_url=None, openapi_url=None)
_verrou = threading.Lock()
CLE_APPLI = os.environ.get("JARVIS_CLE_APPLI", "")   # même valeur que jarvis/compte.py (CLE_APPLI)


@app.middleware("http")
async def seulement_l_appli(req: Request, suite):
    """Tout ce qui n'est pas l'appli Jarvis (navigateur, robots) reçoit un 404 vide (Apache filtre déjà)."""
    if req.url.path.startswith("/mobile/") and req.method == "GET":   # l'appli mobile (pages) est publique
        return await suite(req)
    if CLE_APPLI and (not req.url.path.startswith("/v1/") or
                      not hmac.compare_digest(req.headers.get("x-jarvis-appli", ""), CLE_APPLI)):
        return JSONResponse({"detail": "Introuvable"}, status_code=404)
    return await suite(req)


def _ip(req: Request) -> str:
    """IP réelle de l'appareil (le site passe par Cloudflare puis Apache)."""
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")

SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, prenom TEXT NOT NULL DEFAULT '',
    auth_sel BLOB NOT NULL, auth_hash BLOB NOT NULL, coffre TEXT NOT NULL DEFAULT '', cree REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    jeton_hash TEXT PRIMARY KEY, utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    appareil TEXT NOT NULL DEFAULT '', cree REAL NOT NULL, vu REAL NOT NULL);
CREATE TABLE IF NOT EXISTS faits (
    id INTEGER PRIMARY KEY, utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    fait TEXT NOT NULL, cle TEXT NOT NULL, categorie TEXT NOT NULL DEFAULT 'general', date TEXT NOT NULL DEFAULT '',
    UNIQUE (utilisateur, cle));
CREATE TABLE IF NOT EXISTS historique (
    id INTEGER PRIMARY KEY, utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    jour TEXT NOT NULL, machine TEXT NOT NULL, ligne TEXT NOT NULL, empreinte TEXT NOT NULL,
    UNIQUE (utilisateur, jour, machine, empreinte));
CREATE TABLE IF NOT EXISTS journal_memoire (
    id INTEGER PRIMARY KEY, utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    fid TEXT NOT NULL, action TEXT NOT NULL, fait TEXT NOT NULL, categorie TEXT NOT NULL DEFAULT '',
    appareil TEXT NOT NULL DEFAULT '', ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS journal_par_utilisateur ON journal_memoire (utilisateur, ts);
CREATE TABLE IF NOT EXISTS appareils (
    jeton_hash TEXT PRIMARY KEY, utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    nom TEXT NOT NULL DEFAULT '', plateforme TEXT NOT NULL DEFAULT '', version TEXT NOT NULL DEFAULT '',
    vu REAL NOT NULL DEFAULT 0, occupe INTEGER NOT NULL DEFAULT 0, accepte INTEGER NOT NULL DEFAULT 1,
    mode TEXT NOT NULL DEFAULT 'libre', cree REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS ordres (
    id TEXT PRIMARY KEY, utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    de TEXT NOT NULL, vers TEXT NOT NULL, blob TEXT NOT NULL, reponse TEXT, livre INTEGER NOT NULL DEFAULT 0,
    cree REAL NOT NULL, repondu REAL);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY, utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    genre TEXT NOT NULL DEFAULT 'bug', titre TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    statut TEXT NOT NULL DEFAULT 'ouvert', reponse TEXT NOT NULL DEFAULT '', version TEXT NOT NULL DEFAULT '',
    plateforme TEXT NOT NULL DEFAULT '', appareil TEXT NOT NULL DEFAULT '', cree REAL NOT NULL, modifie REAL NOT NULL);
CREATE INDEX IF NOT EXISTS tickets_par_utilisateur ON tickets (utilisateur, modifie);
CREATE TABLE IF NOT EXISTS documents (
    utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE, nom TEXT NOT NULL,
    contenu TEXT NOT NULL, modifie REAL NOT NULL, PRIMARY KEY (utilisateur, nom));
"""


def _connexion():
    os.makedirs(os.path.dirname(BASE) or ".", exist_ok=True)
    c = sqlite3.connect(BASE, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    return c


with _connexion() as _c:
    _c.executescript(SCHEMA)
    # compteur de changements par compte : les appareils le surveillent pour se mettre à jour en temps réel
    if "revision" not in [r[1] for r in _c.execute("PRAGMA table_info(utilisateurs)")]:
        _c.execute("ALTER TABLE utilisateurs ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")
    # administrateurs : voient et traitent les tickets de tous les utilisateurs (mis à 1 à la main dans la base)
    if "admin" not in [r[1] for r in _c.execute("PRAGMA table_info(utilisateurs)")]:
        _c.execute("ALTER TABLE utilisateurs ADD COLUMN admin INTEGER NOT NULL DEFAULT 0")
    # souvenirs : identifiant stable, date de dernière action, suppression conservée (« pierre tombale »)
    colonnes = [r[1] for r in _c.execute("PRAGMA table_info(faits)")]
    for col, decl in (("fid", "TEXT"), ("modifie", "REAL NOT NULL DEFAULT 0"), ("supprime", "INTEGER NOT NULL DEFAULT 0"),
                      ("appareil", "TEXT NOT NULL DEFAULT ''")):
        if col not in colonnes:
            _c.execute(f"ALTER TABLE faits ADD COLUMN {col} {decl}")
    _c.execute("UPDATE faits SET fid = lower(hex(randomblob(8))) WHERE fid IS NULL OR fid = ''")
    _c.execute("CREATE UNIQUE INDEX IF NOT EXISTS faits_fid ON faits (utilisateur, fid)")
    # journal de départ : l'état actuel de chaque souvenir
    if not _c.execute("SELECT 1 FROM journal_memoire LIMIT 1").fetchone():
        _c.execute("INSERT INTO journal_memoire (utilisateur, fid, action, fait, categorie, appareil, ts) "
                   "SELECT utilisateur, fid, 'ajout', fait, categorie, '', strftime('%s','now') FROM faits WHERE supprime = 0")


def _toucher(c, uid):
    """Quelque chose a changé dans ce compte (mémoire, historique, réglages, coffre) : les autres appareils le verront."""
    c.execute("UPDATE utilisateurs SET revision = revision + 1 WHERE id = ?", (uid,))


@contextmanager
def db():
    c = _connexion()
    try:
        with _verrou:
            yield c
            c.commit()
    finally:
        c.close()


def _hacher(cle_auth: str, sel: bytes) -> bytes:
    return hashlib.scrypt(cle_auth.encode(), salt=sel, n=2 ** 14, r=8, p=1, dklen=32)


def _empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode()).hexdigest()[:32]


# ---------- anti force brute (par IP et par e-mail) ----------
_essais: dict = {}


def _limiter(cle: str, maxi=10, fenetre=600):
    t = time.time()
    liste = [x for x in _essais.get(cle, []) if t - x < fenetre]
    if len(liste) >= maxi:
        raise HTTPException(429, "Trop de tentatives, réessaie dans quelques minutes.")
    liste.append(t)
    _essais[cle] = liste


# ---------- session ----------
def session_courante(authorization: str = Header("")) -> tuple[int, str]:
    """(utilisateur, empreinte du jeton) : l'empreinte identifie l'appareil (une session = un appareil)."""
    jeton = authorization.removeprefix("Bearer ").strip()
    if not jeton:
        raise HTTPException(401, "Non connecté.")
    h = _empreinte(jeton)
    with db() as c:
        r = c.execute("SELECT utilisateur FROM sessions WHERE jeton_hash = ?", (h,)).fetchone()
        if not r:
            raise HTTPException(401, "Session expirée, reconnecte-toi.")
        return r["utilisateur"], h


def utilisateur(authorization: str = Header("")) -> int:
    jeton = authorization.removeprefix("Bearer ").strip()
    if not jeton:
        raise HTTPException(401, "Non connecté.")
    with db() as c:
        r = c.execute("SELECT utilisateur FROM sessions WHERE jeton_hash = ?", (_empreinte(jeton),)).fetchone()
        if not r:
            raise HTTPException(401, "Session expirée, reconnecte-toi.")
        c.execute("UPDATE sessions SET vu = ? WHERE jeton_hash = ?", (time.time(), _empreinte(jeton)))
        return r["utilisateur"]


def _ouvrir_session(c, uid: int, appareil: str) -> str:
    jeton = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)", (_empreinte(jeton), uid, appareil[:80], time.time(), time.time()))
    return jeton


# ---------- comptes ----------
class Inscription(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    cle_auth: str = Field(min_length=32, max_length=200)
    prenom: str = Field("", max_length=60)
    appareil: str = Field("", max_length=80)


class Connexion(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    cle_auth: str = Field(min_length=32, max_length=200)
    appareil: str = Field("", max_length=80)


def _profil(c, uid):
    u = c.execute("SELECT id, email, prenom, coffre, revision, admin FROM utilisateurs WHERE id = ?", (uid,)).fetchone()
    return {"id": u["id"], "email": u["email"], "prenom": u["prenom"], "coffre": u["coffre"], "revision": u["revision"],
            "admin": bool(u["admin"])}


@app.post("/v1/inscription")
def inscription(d: Inscription, req: Request):
    _limiter(f"ins:{_ip(req)}", maxi=5, fenetre=3600)
    email = d.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "Adresse e-mail invalide.")
    sel = secrets.token_bytes(16)
    with db() as c:
        if c.execute("SELECT 1 FROM utilisateurs WHERE email = ?", (email,)).fetchone():
            raise HTTPException(409, "Un compte existe déjà avec cette adresse.")
        uid = c.execute("INSERT INTO utilisateurs (email, prenom, auth_sel, auth_hash, cree) VALUES (?, ?, ?, ?, ?)",
                        (email, d.prenom.strip(), sel, _hacher(d.cle_auth, sel), time.time())).lastrowid
        return {"jeton": _ouvrir_session(c, uid, d.appareil), **_profil(c, uid)}


@app.post("/v1/connexion")
def connexion(d: Connexion, req: Request):
    email = d.email.strip().lower()
    _limiter(f"cnx:{_ip(req)}")
    _limiter(f"cnx:{email}")
    with db() as c:
        u = c.execute("SELECT id, auth_sel, auth_hash FROM utilisateurs WHERE email = ?", (email,)).fetchone()
        attendu = u["auth_hash"] if u else b"\0" * 32
        calcule = _hacher(d.cle_auth, u["auth_sel"] if u else b"\0" * 16)
        if not u or not hmac.compare_digest(attendu, calcule):
            raise HTTPException(401, "E-mail ou mot de passe incorrect.")
        return {"jeton": _ouvrir_session(c, u["id"], d.appareil), **_profil(c, u["id"])}


@app.post("/v1/deconnexion")
def deconnexion(authorization: str = Header("")):
    with db() as c:
        c.execute("DELETE FROM sessions WHERE jeton_hash = ?", (_empreinte(authorization.removeprefix("Bearer ").strip()),))
    return {"ok": True}


@app.get("/v1/moi")
def moi(uid: int = Depends(utilisateur)):
    with db() as c:
        return _profil(c, uid)


class Prenom(BaseModel):
    prenom: str = Field(max_length=60)


@app.put("/v1/moi/prenom")
def changer_prenom(d: Prenom, uid: int = Depends(utilisateur)):
    with db() as c:
        c.execute("UPDATE utilisateurs SET prenom = ? WHERE id = ?", (d.prenom.strip(), uid))
        _toucher(c, uid)
    return {"ok": True}


class Coffre(BaseModel):
    coffre: str = Field(max_length=200_000)   # chiffré par l'appareil (AES-GCM), illisible ici


@app.put("/v1/coffre")
def sauver_coffre(d: Coffre, uid: int = Depends(utilisateur)):
    with db() as c:
        c.execute("UPDATE utilisateurs SET coffre = ? WHERE id = ?", (d.coffre, uid))
        _toucher(c, uid)
    return {"ok": True}


# ---------- mémoire : chaque souvenir a un identifiant, une date de dernière action et un journal ----------
# Règle : la DERNIÈRE action gagne, quel que soit l'appareil. Une suppression efface le souvenir partout ;
# mais si un autre appareil l'a ajouté, modifié ou réutilisé APRÈS cette suppression, il reste.
# Une suppression n'efface pas la ligne (« pierre tombale ») : elle garde la date qui permet de trancher.
class Fait(BaseModel):
    fait: str = Field(min_length=1, max_length=2000)
    categorie: str = Field("general", max_length=40)
    date: str = Field("", max_length=20)
    fid: str = Field("", max_length=40)          # identifiant du souvenir (vide = retrouvé par son texte)
    ts: float = 0                                 # moment de l'action sur l'appareil (0 = maintenant)
    appareil: str = Field("", max_length=80)
    action: str = Field("", max_length=20)        # ajout | modification | utilisation | restauration


def _journal(c, uid, fid, action, fait, categorie, appareil, ts):
    c.execute("INSERT INTO journal_memoire (utilisateur, fid, action, fait, categorie, appareil, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (uid, fid, action, fait, categorie, appareil, ts))


def _appliquer_fait(c, uid, f: Fait, import_ancien=False) -> str:
    """Ajoute / modifie / restaure / réutilise un souvenir si cette action est la plus récente. Renvoie l'action
    retenue, ou "" si une action plus récente (ex. une suppression faite après) l'emporte."""
    texte, cle = f.fait.strip(), f.fait.strip().lower()
    ts = 0.0 if import_ancien else (f.ts or time.time())   # l'import d'une vieille mémoire ne ressuscite rien
    ligne = None
    if f.fid:
        ligne = c.execute("SELECT * FROM faits WHERE utilisateur = ? AND fid = ?", (uid, f.fid)).fetchone()
    if ligne is None:
        ligne = c.execute("SELECT * FROM faits WHERE utilisateur = ? AND cle = ?", (uid, cle)).fetchone()
    if ligne is None:
        fid = f.fid or secrets.token_hex(8)
        c.execute("INSERT INTO faits (utilisateur, fait, cle, categorie, date, fid, modifie, supprime, appareil) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)", (uid, texte, cle, f.categorie, f.date, fid, ts, f.appareil))
        _journal(c, uid, fid, "ajout", texte, f.categorie, f.appareil, ts or time.time())
        return "ajout"
    if ts <= (ligne["modifie"] or 0):
        return ""   # une action plus récente existe déjà
    if cle != ligne["cle"] and c.execute("SELECT 1 FROM faits WHERE utilisateur = ? AND cle = ? AND fid != ?",
                                         (uid, cle, ligne["fid"])).fetchone():
        return ""   # ce texte existe déjà comme autre souvenir
    if ligne["supprime"]:
        action = "restauration"
    elif cle != ligne["cle"] or f.categorie != ligne["categorie"]:
        action = "modification"
    else:
        action = f.action or "utilisation"
    c.execute("UPDATE faits SET fait = ?, cle = ?, categorie = ?, modifie = ?, supprime = 0, appareil = ? WHERE id = ?",
              (texte, cle, f.categorie, ts, f.appareil, ligne["id"]))
    _journal(c, uid, ligne["fid"], action, texte, f.categorie, f.appareil, ts)
    return action


def _supprimer_fait(c, uid, ligne, ts, appareil) -> bool:
    if ligne["supprime"] or ts < (ligne["modifie"] or 0):
        return False   # déjà supprimé, ou réutilisé / modifié après cette suppression : il reste
    c.execute("UPDATE faits SET supprime = 1, modifie = ?, appareil = ? WHERE id = ?", (ts, appareil, ligne["id"]))
    _journal(c, uid, ligne["fid"], "suppression", ligne["fait"], ligne["categorie"], appareil, ts)
    return True


def _ajouter_faits(c, uid, faits) -> int:
    """Import de l'ancienne mémoire d'un appareil : ajoute ce qui manque, ne ressuscite rien de supprimé."""
    return sum(1 for f in faits if _appliquer_fait(c, uid, f, import_ancien=True) == "ajout")


@app.get("/v1/faits")
def lister_faits(uid: int = Depends(utilisateur)):
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT fait, categorie, date, fid, modifie FROM faits WHERE utilisateur = ? AND supprime = 0 ORDER BY id", (uid,))]


@app.post("/v1/faits")
def ajouter_fait(f: Fait, uid: int = Depends(utilisateur)):
    with db() as c:
        action = _appliquer_fait(c, uid, f)
        if action:
            _toucher(c, uid)
        return {"ajoute": action == "ajout", "action": action}


class Suppression(BaseModel):
    fid: str = Field("", max_length=40)
    texte: str = Field("", max_length=2000)        # anciens appareils : supprime ce qui contient ce texte
    ts: float = 0
    appareil: str = Field("", max_length=80)


@app.post("/v1/faits/supprimer")
def supprimer(d: Suppression, uid: int = Depends(utilisateur)):
    ts = d.ts or time.time()
    with db() as c:
        if d.fid:
            lignes = c.execute("SELECT * FROM faits WHERE utilisateur = ? AND fid = ?", (uid, d.fid)).fetchall()
        else:
            lignes = c.execute("SELECT * FROM faits WHERE utilisateur = ? AND supprime = 0 AND instr(cle, ?) > 0",
                               (uid, d.texte.strip().lower())).fetchall() if d.texte.strip() else []
        n = sum(_supprimer_fait(c, uid, l, ts, d.appareil) for l in lignes)
        if n:
            _toucher(c, uid)
        return {"supprimes": n}


class Oubli(BaseModel):
    texte: str = Field(min_length=1, max_length=2000)


@app.post("/v1/faits/oublier")   # compatibilité avec les versions 1.1.0
def oublier(d: Oubli, uid: int = Depends(utilisateur)):
    return supprimer(Suppression(texte=d.texte), uid)


@app.get("/v1/memoire/journal")
def journal(limite: int = 300, uid: int = Depends(utilisateur)):
    """Tout ce qui est arrivé à ta mémoire : ajouts, modifications, réutilisations, suppressions, restaurations."""
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT j.fid, j.action, j.fait, j.categorie, j.appareil, j.ts, f.supprime AS supprime_actuellement "
            "FROM journal_memoire j LEFT JOIN faits f ON f.utilisateur = j.utilisateur AND f.fid = j.fid "
            "WHERE j.utilisateur = ? ORDER BY j.ts DESC, j.id DESC LIMIT ?", (uid, max(1, min(limite, 2000))))]


# ---------- historique des conversations ----------
class Ligne(BaseModel):
    jour: str = Field(min_length=10, max_length=10)
    machine: str = Field(max_length=80)
    ligne: str = Field(max_length=20_000)


class Lignes(BaseModel):
    lignes: list[Ligne] = Field(max_length=20_000)


def _ajouter_lignes(c, uid, lignes, import_appareil=False) -> int:
    """import_appareil : une même ligne, le même jour, déjà présente sous un autre nom d'appareil (copie
    d'une ancienne mémoire trouvée à deux endroits) n'est pas ajoutée une 2e fois."""
    n = 0
    for l in lignes:
        if import_appareil and c.execute("SELECT 1 FROM historique WHERE utilisateur = ? AND jour = ? AND empreinte = ?",
                                         (uid, l.jour, _empreinte(l.ligne))).fetchone():
            continue
        cur = c.execute("INSERT OR IGNORE INTO historique (utilisateur, jour, machine, ligne, empreinte) VALUES (?, ?, ?, ?, ?)",
                        (uid, l.jour, l.machine, l.ligne, _empreinte(l.ligne)))
        n += cur.rowcount
    return n


@app.get("/v1/historique")
def lire_historique(depuis: int = 0, uid: int = Depends(utilisateur)):
    """Lignes dont l'id > depuis (synchro incrémentale)."""
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, jour, machine, ligne FROM historique WHERE utilisateur = ? AND id > ? ORDER BY id LIMIT 20000",
            (uid, depuis))]


@app.post("/v1/historique")
def ecrire_historique(d: Lignes, uid: int = Depends(utilisateur)):
    with db() as c:
        n = _ajouter_lignes(c, uid, d.lignes)
        if n:
            _toucher(c, uid)
        return {"ajoutees": n}


# ---------- documents (réglages partagés, connecteurs) ----------
NOMS_DOCS = {"profil", "connecteurs", "automatisations", "afaire"}


@app.get("/v1/documents/{nom}")
def lire_doc(nom: str, uid: int = Depends(utilisateur)):
    if nom not in NOMS_DOCS:
        raise HTTPException(404, "Document inconnu.")
    with db() as c:
        r = c.execute("SELECT contenu, modifie FROM documents WHERE utilisateur = ? AND nom = ?", (uid, nom)).fetchone()
    return {"contenu": json.loads(r["contenu"]) if r else None, "modifie": r["modifie"] if r else 0}


@app.put("/v1/documents/{nom}")
async def ecrire_doc(nom: str, req: Request, uid: int = Depends(utilisateur)):
    if nom not in NOMS_DOCS:
        raise HTTPException(404, "Document inconnu.")
    corps = await req.body()
    if len(corps) > 500_000:
        raise HTTPException(413, "Document trop gros.")
    contenu = json.loads(corps)["contenu"]
    with db() as c:
        c.execute("INSERT INTO documents VALUES (?, ?, ?, ?) ON CONFLICT (utilisateur, nom) DO UPDATE SET contenu = excluded.contenu, modifie = excluded.modifie",
                  (uid, nom, json.dumps(contenu, ensure_ascii=False), time.time()))
        _toucher(c, uid)
    return {"ok": True}


# ---------- import de la mémoire d'un appareil (fusion, rien n'est écrasé) ----------
class Import(BaseModel):
    faits: list[Fait] = Field(default_factory=list, max_length=20_000)
    lignes: list[Ligne] = Field(default_factory=list, max_length=200_000)


@app.post("/v1/import")
def importer(d: Import, uid: int = Depends(utilisateur)):
    with db() as c:
        r = {"faits": _ajouter_faits(c, uid, d.faits), "lignes": _ajouter_lignes(c, uid, d.lignes, import_appareil=True)}
        if r["faits"] or r["lignes"]:
            _toucher(c, uid)
        return r


# ---------- temps réel : l'appareil attend qu'un autre appareil change quelque chose ----------
def _revision(uid: int) -> int:
    c = _connexion()
    try:
        return c.execute("SELECT revision FROM utilisateurs WHERE id = ?", (uid,)).fetchone()["revision"]
    finally:
        c.close()


def _ordres_en_attente(uid: int, appareil: str) -> list:
    c = _connexion()
    try:
        lignes = c.execute("SELECT id, de, blob, cree FROM ordres WHERE utilisateur = ? AND vers = ? AND livre = 0 "
                           "AND cree > ?", (uid, appareil, time.time() - 600)).fetchall()
        if lignes:
            c.execute(f"UPDATE ordres SET livre = 1 WHERE id IN ({','.join('?' * len(lignes))})", [l["id"] for l in lignes])
            c.commit()
        return [dict(l) for l in lignes]
    finally:
        c.close()


@app.get("/v1/attendre")
async def attendre(depuis: int = 0, s: tuple = Depends(session_courante)):
    """Répond dès que le compte change (révision > depuis), qu'un ordre arrive pour cet appareil, ou au bout de
    25 s. Les appareils rappellent aussitôt : changements et ordres arrivent partout en ~1 s."""
    uid, appareil = s
    for _ in range(50):
        ordres = await asyncio.to_thread(_ordres_en_attente, uid, appareil[:16])
        r = await asyncio.to_thread(_revision, uid)
        if r > depuis or ordres:
            return {"revision": r, "change": r > depuis, "ordres": ordres}
        await asyncio.sleep(0.5)
    return {"revision": await asyncio.to_thread(_revision, uid), "change": False, "ordres": []}


# ---------- mes appareils : présence, déconnexion à distance ----------
EN_LIGNE = 75   # secondes sans nouvelles avant d'être considéré hors ligne


class Presence(BaseModel):
    nom: str = Field("", max_length=80)
    plateforme: str = Field("", max_length=40)
    version: str = Field("", max_length=20)
    occupe: bool = False
    accepte: bool = True
    mode: str = Field("libre", max_length=20)


@app.post("/v1/appareils/presence")
def presence(d: Presence, s: tuple = Depends(session_courante)):
    uid, h = s
    with db() as c:
        c.execute("INSERT INTO appareils (jeton_hash, utilisateur, nom, plateforme, version, vu, occupe, accepte, mode, cree) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (jeton_hash) DO UPDATE SET nom = excluded.nom, "
                  "plateforme = excluded.plateforme, version = excluded.version, vu = excluded.vu, occupe = excluded.occupe, "
                  "accepte = excluded.accepte, mode = excluded.mode",
                  (h, uid, d.nom, d.plateforme, d.version, time.time(), int(d.occupe), int(d.accepte), d.mode, time.time()))
    return {"id": h[:16]}


@app.get("/v1/appareils")
def appareils(s: tuple = Depends(session_courante)):
    uid, h = s
    with db() as c:
        # les sessions sans présence (anciennes versions) apparaissent aussi, comme « connecté »
        lignes = c.execute(
            "SELECT s.jeton_hash, COALESCE(a.nom, s.appareil) AS nom, COALESCE(a.plateforme, '') AS plateforme, "
            "COALESCE(a.version, '') AS version, COALESCE(a.vu, s.vu) AS vu, COALESCE(a.occupe, 0) AS occupe, "
            "COALESCE(a.accepte, 0) AS accepte, COALESCE(a.mode, '') AS mode, s.cree AS connecte_depuis "
            "FROM sessions s LEFT JOIN appareils a ON a.jeton_hash = s.jeton_hash WHERE s.utilisateur = ? "
            "ORDER BY vu DESC", (uid,)).fetchall()
    t = time.time()
    return [{"id": l["jeton_hash"][:16], "nom": l["nom"], "plateforme": l["plateforme"], "version": l["version"],
             "vu": l["vu"], "en_ligne": t - (l["vu"] or 0) < EN_LIGNE and bool(l["plateforme"]), "occupe": bool(l["occupe"]),
             "accepte": bool(l["accepte"]), "mode": l["mode"], "connecte_depuis": l["connecte_depuis"],
             "moi": l["jeton_hash"] == h} for l in lignes]


@app.post("/v1/appareils/{aid}/deconnecter")
def deconnecter_appareil(aid: str, s: tuple = Depends(session_courante)):
    """Déconnecte un de tes appareils (depuis n'importe lequel) : sa session est supprimée, il revient à la connexion."""
    uid, _ = s
    with db() as c:
        cibles = [r["jeton_hash"] for r in c.execute("SELECT jeton_hash FROM sessions WHERE utilisateur = ? AND substr(jeton_hash, 1, 16) = ?",
                                                     (uid, aid))]
        for h in cibles:
            c.execute("DELETE FROM sessions WHERE jeton_hash = ?", (h,))
            c.execute("DELETE FROM appareils WHERE jeton_hash = ?", (h,))
    return {"deconnectes": len(cibles)}


# ---------- ordres entre appareils (chiffrés par les appareils : le serveur ne peut ni les lire ni les fabriquer) ----------
class Ordre(BaseModel):
    vers: str = Field(min_length=4, max_length=16)
    blob: str = Field(max_length=20_000_000)


@app.post("/v1/ordres")
def envoyer_ordre(d: Ordre, s: tuple = Depends(session_courante)):
    uid, h = s
    with db() as c:
        if not c.execute("SELECT 1 FROM sessions WHERE utilisateur = ? AND substr(jeton_hash, 1, 16) = ?", (uid, d.vers)).fetchone():
            raise HTTPException(404, "Appareil inconnu ou déconnecté.")
        oid = secrets.token_hex(8)
        c.execute("DELETE FROM ordres WHERE cree < ?", (time.time() - 86400,))
        c.execute("INSERT INTO ordres (id, utilisateur, de, vers, blob, cree) VALUES (?, ?, ?, ?, ?, ?)",
                  (oid, uid, h[:16], d.vers, d.blob, time.time()))
    return {"id": oid}


class Reponse(BaseModel):
    blob: str = Field(max_length=20_000_000)


@app.post("/v1/ordres/{oid}/reponse")
def repondre_ordre(oid: str, d: Reponse, s: tuple = Depends(session_courante)):
    uid, h = s
    with db() as c:
        n = c.execute("UPDATE ordres SET reponse = ?, repondu = ? WHERE id = ? AND utilisateur = ? AND vers = ?",
                      (d.blob, time.time(), oid, uid, h[:16])).rowcount
    if not n:
        raise HTTPException(404, "Ordre introuvable.")
    return {"ok": True}


def _reponse(uid, oid):
    c = _connexion()
    try:
        r = c.execute("SELECT reponse, livre FROM ordres WHERE id = ? AND utilisateur = ?", (oid, uid)).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


@app.get("/v1/ordres/{oid}/attendre")
async def attendre_reponse(oid: str, s: tuple = Depends(session_courante)):
    """Attend (jusqu'à 25 s) la réponse de l'appareil ; l'appelant rappelle tant que ce n'est pas fini."""
    uid, _ = s
    for _ in range(50):
        r = await asyncio.to_thread(_reponse, uid, oid)
        if r is None:
            raise HTTPException(404, "Ordre introuvable.")
        if r["reponse"] is not None:
            return {"pret": True, "blob": r["reponse"], "recu": bool(r["livre"])}
        await asyncio.sleep(0.5)
    return {"pret": False, "recu": bool((await asyncio.to_thread(_reponse, uid, oid) or {}).get("livre"))}


# ---------- tickets : bugs, améliorations, idées envoyés par les utilisateurs aux administrateurs ----------
GENRES_TICKET = {"bug", "amelioration", "idee", "question", "autre"}
STATUTS_TICKET = {"ouvert", "en_cours", "resolu", "ferme"}
_COLONNES_TICKET = "t.id, t.genre, t.titre, t.description, t.statut, t.reponse, t.version, t.plateforme, t.appareil, t.cree, t.modifie"


class NouveauTicket(BaseModel):
    genre: str = Field("bug", max_length=20)
    titre: str = Field(min_length=3, max_length=200)
    description: str = Field("", max_length=10_000)
    version: str = Field("", max_length=20)
    plateforme: str = Field("", max_length=40)
    appareil: str = Field("", max_length=80)


class ReponseTicket(BaseModel):
    statut: str = Field("", max_length=20)
    reponse: str | None = Field(None, max_length=10_000)


def _admin(uid: int = Depends(utilisateur)) -> int:
    with db() as c:
        if not c.execute("SELECT admin FROM utilisateurs WHERE id = ?", (uid,)).fetchone()["admin"]:
            raise HTTPException(403, "Réservé aux administrateurs.")
    return uid


@app.post("/v1/tickets")
def creer_ticket(d: NouveauTicket, uid: int = Depends(utilisateur)):
    _limiter(f"ticket:{uid}", maxi=20, fenetre=3600)
    genre = d.genre if d.genre in GENRES_TICKET else "autre"
    t = time.time()
    with db() as c:
        tid = c.execute("INSERT INTO tickets (utilisateur, genre, titre, description, version, plateforme, appareil, cree, modifie) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (uid, genre, d.titre.strip(), d.description.strip(), d.version,
                                                               d.plateforme, d.appareil, t, t)).lastrowid
        for a in c.execute("SELECT id FROM utilisateurs WHERE admin = 1"):   # les admins sont prévenus en temps réel
            _toucher(c, a["id"])
    return {"id": tid}


@app.get("/v1/tickets")
def mes_tickets(uid: int = Depends(utilisateur)):
    with db() as c:
        return [dict(r) for r in c.execute(f"SELECT {_COLONNES_TICKET} FROM tickets t WHERE t.utilisateur = ? "
                                           "ORDER BY t.modifie DESC LIMIT 500", (uid,))]


@app.get("/v1/admin/tickets")
def tous_les_tickets(uid: int = Depends(_admin)):
    with db() as c:
        return [dict(r) for r in c.execute(
            f"SELECT {_COLONNES_TICKET}, u.email, u.prenom FROM tickets t JOIN utilisateurs u ON u.id = t.utilisateur "
            "ORDER BY t.modifie DESC LIMIT 2000")]


@app.patch("/v1/admin/tickets/{tid}")
def traiter_ticket(tid: int, d: ReponseTicket, uid: int = Depends(_admin)):
    if d.statut and d.statut not in STATUTS_TICKET:
        raise HTTPException(400, "Statut inconnu.")
    with db() as c:
        r = c.execute("SELECT utilisateur FROM tickets WHERE id = ?", (tid,)).fetchone()
        if not r:
            raise HTTPException(404, "Ticket introuvable.")
        if d.statut:
            c.execute("UPDATE tickets SET statut = ? WHERE id = ?", (d.statut, tid))
        if d.reponse is not None:
            c.execute("UPDATE tickets SET reponse = ? WHERE id = ?", (d.reponse.strip(), tid))
        c.execute("UPDATE tickets SET modifie = ? WHERE id = ?", (time.time(), tid))
        _toucher(c, r["utilisateur"])   # l'auteur voit la réponse tout de suite
    return {"ok": True}


@app.delete("/v1/admin/tickets/{tid}")
def supprimer_ticket(tid: int, uid: int = Depends(_admin)):
    with db() as c:
        c.execute("DELETE FROM tickets WHERE id = ?", (tid,))
    return {"ok": True}


@app.get("/v1/sante")
def sante():
    return {"ok": True}


# ---------- appli mobile (télécommande depuis le téléphone) ----------
@app.get("/mobile/config.js")
def config_mobile():
    return PlainTextResponse(f"window.JARVIS_CLE_APPLI = {json.dumps(CLE_APPLI)};", media_type="application/javascript",
                             headers={"Cache-Control": "no-store"})


_MOBILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mobile")
if os.path.isdir(_MOBILE):
    app.mount("/mobile", StaticFiles(directory=_MOBILE, html=True), name="mobile")
