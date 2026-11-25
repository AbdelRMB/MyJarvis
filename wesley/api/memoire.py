"""Mémoire, documents, contexte, historique, journal des actions et liste des outils."""
import asyncio
import inspect
import json
import re
import time

from fastapi import APIRouter, HTTPException, Request

from .. import memoire, outils, web
from ..config import RACINE
from ..web import _verifier

router = APIRouter()


# ---------- recherche unique (souvenirs, conversations, transcriptions, documents, À faire) ----------
@router.get("/api/recherche")
async def recherche_partout(req: Request, q: str = "", n: int = 6):
    _verifier(req)
    from .. import recherche
    return await asyncio.to_thread(recherche.chercher_partout, q, max(1, min(20, n)))


# ---------- mémoire ----------
@router.get("/api/memoire")
def lire_memoire(req: Request):
    _verifier(req)
    return memoire._charger()


@router.post("/api/memoire")
async def ajouter_fait(req: Request):
    _verifier(req)
    d = await req.json()
    if not str(d.get("fait", "")).strip():
        raise HTTPException(400, "Fait vide")
    return {"message": memoire.ajouter(d["fait"].strip(), d.get("categorie") or "general")}


@router.delete("/api/memoire")
async def supprimer_fait(req: Request):
    """Bouton « Oublier » : supprimé partout (sauf si un autre appareil l'utilise après)."""
    _verifier(req)
    d = await req.json()
    return {"supprimes": memoire.supprimer_un(d.get("fid", ""), d.get("fait", ""))}


@router.put("/api/memoire")
async def modifier_fait(req: Request):
    _verifier(req)
    d = await req.json()
    if not str(d.get("fait", "")).strip():
        raise HTTPException(400, "Fait vide")
    if not memoire.modifier(d.get("fid", ""), d["fait"], d.get("categorie")):
        raise HTTPException(404, "Souvenir introuvable (actualise la mémoire).")
    return {"ok": True}


@router.get("/api/memoire/intelligence")
def etat_intelligence(req: Request):
    """Écran Mémoire : recherche par le sens, propositions à confirmer, dernier rangement, coûts du mois."""
    _verifier(req)
    from .. import consolidation, semantique
    couts = {}
    try:
        from .. import claude
        couts = claude.resume_couts()
    except Exception:
        pass
    return {"semantique": semantique.etat(), "propositions": consolidation.propositions(),
            "rangement": consolidation._etat().get("resultat"), "couts": couts,
            "nb_lecons": len([x for x in memoire._charger() if x.get("categorie") == "lecon"])}


@router.get("/api/sante")
def sante_wesley(req: Request, jours: int = 7):
    """Tableau de santé : outils qui échouent, cerveaux, temps de réponse (compté sur cet appareil)."""
    _verifier(req)
    from .. import sante
    return sante.resume(max(1, min(30, jours)))


@router.get("/api/documents")
def etat_documents(req: Request):
    _verifier(req)
    from .. import documents
    return documents.etat()


@router.post("/api/documents/{action}")
async def agir_documents(action: str, req: Request):
    _verifier(req)
    from .. import documents
    d = await req.json() if (await req.body()) else {}
    try:
        if action == "ajouter":
            documents.ajouter_dossier(str(d.get("chemin") or ""))
        elif action == "retirer":
            documents.retirer_dossier(str(d.get("chemin") or ""))
        elif action == "reindexer":
            documents.indexer_en_fond()
        elif action == "chercher":
            return {"resultats": await asyncio.to_thread(documents.chercher, str(d.get("question") or ""), 8)}
        else:
            raise HTTPException(404, "Action inconnue.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return documents.etat()


@router.get("/api/contexte")
def dernier_contexte(req: Request):
    """Dernière capture du raccourci « ce que je regarde » (si l'interface vient de s'ouvrir et l'a ratée)."""
    _verifier(req)
    from .. import contexte
    c = dict(contexte.DERNIER)
    return c if c and time.time() - c.get("ts", 0) < 30 else {}


@router.post("/api/contexte/consigne")
async def consigne_contexte(req: Request):
    _verifier(req)
    from .. import contexte
    d = await req.json()
    return {"texte": contexte.consigne(str(d.get("action") or ""), str(d.get("selection") or ""), str(d.get("fenetre") or ""),
                                       str(d.get("precision") or ""))}


@router.post("/api/memoire/propositions/{pid}")
async def repondre_proposition(pid: str, req: Request):
    _verifier(req)
    from .. import consolidation
    d = await req.json()
    return {"message": await asyncio.to_thread(consolidation.repondre, pid, bool(d.get("accepter")))}


@router.post("/api/memoire/ranger")
async def ranger_memoire(req: Request):
    _verifier(req)
    from .. import consolidation
    try:
        return await asyncio.to_thread(consolidation.consolider, None, True)
    except Exception as e:
        raise HTTPException(400, f"Rangement impossible : {e}")


@router.get("/api/memoire/journal")
async def journal_memoire(req: Request):
    """Historique de ta mémoire gardé par le serveur : qui a ajouté, modifié, utilisé ou supprimé quoi, et quand."""
    _verifier(req)
    from .. import compte
    try:
        return await asyncio.to_thread(compte.journal_memoire)
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))


@router.post("/api/memoire/restaurer")
async def restaurer_fait(req: Request):
    _verifier(req)
    d = await req.json()
    memoire.restaurer(d["fid"], d["fait"], d.get("categorie") or "general")
    return {"ok": True}


@router.post("/api/memoriser_session")
def memoriser_session(req: Request):
    _verifier(req)
    if not web.verrou_tache.acquire(blocking=False):
        raise HTTPException(409, "Wesley est occupé")
    try:
        return {"faits": web.wesley.extraire_souvenirs()}
    finally:
        web.verrou_tache.release()


# ---------- historique ----------
RX_LIGNE = re.compile(r"^\[(\d\d:\d\d)\] ([^:]+): ?(.*)$")


@router.get("/api/historique")
def jours(req: Request):
    _verifier(req)
    out = []
    jours = memoire.fichiers_par_jour()
    for j in sorted(jours, reverse=True):
        lignes = [l for _, _, l in memoire.lignes_du_jour(jours[j])]
        premier = next((RX_LIGNE.match(l).group(3) for l in lignes if RX_LIGNE.match(l)), "")
        out.append({"jour": j, "nb": sum(1 for l in lignes if RX_LIGNE.match(l)), "apercu": premier[:120],
                    "pcs": sorted({f.stem.split("__")[1] for f in jours[j] if "__" in f.stem})})
    return out


@router.get("/api/historique/{jour}")
def jour(jour: str, req: Request):
    _verifier(req)
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", jour):
        raise HTTPException(400)
    fichiers = memoire.fichiers_par_jour().get(jour)
    if not fichiers:
        raise HTTPException(404)
    entrees = []
    for f in fichiers:   # chaque PC séparément : les lignes de suite restent attachées à leur message
        pc = f.stem.split("__")[1] if "__" in f.stem else ""
        for l in f.read_text(encoding="utf-8").splitlines():
            m = RX_LIGNE.match(l)
            if m:
                entrees.append({"heure": m.group(1), "role": "wesley" if m.group(2).lower() == "wesley" else "user",
                                "texte": m.group(3), "pc": pc})
            elif entrees:
                entrees[-1]["texte"] += "\n" + l
    return sorted(entrees, key=lambda e: e["heure"])


# ---------- journal des actions & outils ----------
RX_ACTION = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (\w+) (.*)$")
RX_RES = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+\s+-> (.*)$")


@router.get("/api/actions")
def actions(req: Request, n: int = 200):
    _verifier(req)
    f = RACINE / "logs" / "actions.log"
    if not f.exists():
        return []
    with open(f, "rb") as fh:
        fh.seek(0, 2)
        fh.seek(max(0, fh.tell() - 400_000))
        lignes = fh.read().decode("utf-8", "replace").splitlines()
    out = []
    for l in lignes:
        if m := RX_RES.match(l):
            if out:
                out[-1]["resultat"] = m.group(1)
        elif m := RX_ACTION.match(l):
            try:
                args = json.loads(m.group(3))
            except Exception:
                args = {"brut": m.group(3)}
            out.append({"date": m.group(1), "outil": m.group(2), "args": args, "resultat": None})
    return out[-n:][::-1]


@router.get("/api/outils")
def liste_outils(req: Request):
    _verifier(req)
    out = []
    for nom, o in OUTILS_TRIES():
        f = o["schema"]["function"]
        out.append({"nom": nom, "description": f["description"], "module": o["fn"].__module__.rsplit(".", 1)[-1],
                    "params": [{"nom": k, "type": v["type"], "description": v["description"],
                                "requis": k in f["parameters"]["required"]} for k, v in f["parameters"]["properties"].items()],
                    "doc": inspect.getdoc(o["fn"]) or ""})
    return out


def OUTILS_TRIES():
    return sorted(outils.OUTILS.items(), key=lambda kv: (kv[1]["fn"].__module__, kv[0]))
