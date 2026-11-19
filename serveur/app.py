"""Serveur des comptes Jarvis : chaque utilisateur a sa mémoire, son historique, ses réglages et son coffre.

- Connexion : l'appli ne transmet JAMAIS le mot de passe. Elle en dérive deux clés (scrypt) :
    * cle_auth -> envoyée ici, stockée hachée (scrypt + sel) : prouve l'identité ;
    * cle_coffre -> reste sur l'appareil : chiffre le coffre (clé API, mots de passe des connecteurs).
  Le serveur ne stocke donc que du chiffré qu'il ne peut pas lire.
- Toutes les données sont filtrées par l'utilisateur du jeton de session : personne ne voit celles des autres.
- Base SQLite (fichier /donnees/jarvis.db, volume Docker).
"""
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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

BASE = os.environ.get("JARVIS_DB", "/donnees/jarvis.db")
app = FastAPI(title="Jarvis — comptes", docs_url=None, redoc_url=None, openapi_url=None)
_verrou = threading.Lock()
CLE_APPLI = os.environ.get("JARVIS_CLE_APPLI", "")   # même valeur que jarvis/compte.py (CLE_APPLI)


@app.middleware("http")
async def seulement_l_appli(req: Request, suite):
    """Tout ce qui n'est pas l'appli Jarvis (navigateur, robots) reçoit un 404 vide (Apache filtre déjà)."""
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
    u = c.execute("SELECT id, email, prenom, coffre FROM utilisateurs WHERE id = ?", (uid,)).fetchone()
    return {"id": u["id"], "email": u["email"], "prenom": u["prenom"], "coffre": u["coffre"]}


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
    return {"ok": True}


class Coffre(BaseModel):
    coffre: str = Field(max_length=200_000)   # chiffré par l'appareil (AES-GCM), illisible ici


@app.put("/v1/coffre")
def sauver_coffre(d: Coffre, uid: int = Depends(utilisateur)):
    with db() as c:
        c.execute("UPDATE utilisateurs SET coffre = ? WHERE id = ?", (d.coffre, uid))
    return {"ok": True}


# ---------- mémoire ----------
class Fait(BaseModel):
    fait: str = Field(min_length=1, max_length=2000)
    categorie: str = Field("general", max_length=40)
    date: str = Field("", max_length=20)


def _ajouter_faits(c, uid, faits) -> int:
    n = 0
    for f in faits:
        cur = c.execute("INSERT OR IGNORE INTO faits (utilisateur, fait, cle, categorie, date) VALUES (?, ?, ?, ?, ?)",
                        (uid, f.fait.strip(), f.fait.strip().lower(), f.categorie, f.date))
        n += cur.rowcount
    return n


@app.get("/v1/faits")
def lister_faits(uid: int = Depends(utilisateur)):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT fait, categorie, date FROM faits WHERE utilisateur = ? ORDER BY id", (uid,))]


@app.post("/v1/faits")
def ajouter_fait(f: Fait, uid: int = Depends(utilisateur)):
    with db() as c:
        return {"ajoute": _ajouter_faits(c, uid, [f]) == 1}


class Oubli(BaseModel):
    texte: str = Field(min_length=1, max_length=2000)


@app.post("/v1/faits/oublier")
def oublier(d: Oubli, uid: int = Depends(utilisateur)):
    with db() as c:
        cur = c.execute("DELETE FROM faits WHERE utilisateur = ? AND instr(cle, ?) > 0", (uid, d.texte.strip().lower()))
        return {"supprimes": cur.rowcount}


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
        return {"ajoutees": _ajouter_lignes(c, uid, d.lignes)}


# ---------- documents (réglages partagés, connecteurs) ----------
NOMS_DOCS = {"profil", "connecteurs"}


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
    return {"ok": True}


# ---------- import de la mémoire d'un appareil (fusion, rien n'est écrasé) ----------
class Import(BaseModel):
    faits: list[Fait] = Field(default_factory=list, max_length=20_000)
    lignes: list[Ligne] = Field(default_factory=list, max_length=200_000)


@app.post("/v1/import")
def importer(d: Import, uid: int = Depends(utilisateur)):
    with db() as c:
        return {"faits": _ajouter_faits(c, uid, d.faits), "lignes": _ajouter_lignes(c, uid, d.lignes, import_appareil=True)}


@app.get("/v1/sante")
def sante():
    return {"ok": True}
