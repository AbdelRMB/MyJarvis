"""Statistiques (administrateurs), tickets et rapports d'erreur."""
import asyncio
import time

from fastapi import APIRouter, HTTPException, Request

from ..web import _verifier

router = APIRouter()


# ---------- statistiques de l'appli (administrateurs) ----------
_telechargements = {"t": 0.0, "donnees": None}


def _telechargements_github() -> dict:
    """Téléchargements de chaque installateur publié (API publique GitHub, gardée 10 min en cache)."""
    if _telechargements["donnees"] is not None and time.time() - _telechargements["t"] < 600:
        return _telechargements["donnees"]
    import requests
    from ..version import DEPOT
    try:
        r = requests.get(f"https://api.github.com/repos/{DEPOT}/releases?per_page=100", timeout=15,
                         headers={"Accept": "application/vnd.github+json", "User-Agent": "Wesley"})
        r.raise_for_status()
        versions = []
        for rel in r.json():
            if rel.get("draft"):
                continue
            fichiers = {"windows": 0, "mac": 0}
            for a in rel.get("assets", []):
                n = a.get("name", "")
                cle = "mac" if n.endswith(".dmg") else "windows" if n.endswith(".exe") else None
                if cle:
                    fichiers[cle] += a.get("download_count", 0)
            versions.append({"version": rel["tag_name"].lstrip("v"), "date": (rel.get("published_at") or "")[:10],
                             **fichiers, "total": fichiers["windows"] + fichiers["mac"]})
        donnees = {"versions": versions, "total": sum(v["total"] for v in versions), "erreur": ""}
    except Exception as e:
        donnees = {"versions": [], "total": 0, "erreur": f"GitHub injoignable ({type(e).__name__})."}
    _telechargements.update(t=time.time(), donnees=donnees)
    return donnees


@router.get("/api/admin/stats")
async def statistiques_appli(req: Request, jours: int = 30):
    _verifier(req)
    from .. import compte
    if not compte.est_admin():
        raise HTTPException(403, "Réservé aux administrateurs.")
    try:
        stats = await asyncio.to_thread(compte.statistiques, jours)
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))
    stats["telechargements"] = await asyncio.to_thread(_telechargements_github)
    return stats


# ---------- tickets (bugs, améliorations, idées) ----------
@router.get("/api/tickets")
async def lister_tickets(req: Request):
    _verifier(req)
    from .. import compte
    if not compte.connecte():
        return {"connecte": False, "admin": False, "miens": [], "tous": []}
    try:
        miens = await asyncio.to_thread(compte.mes_tickets)
        admin = compte.est_admin()
        tous = await asyncio.to_thread(compte.tous_les_tickets) if admin else []
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))
    return {"connecte": True, "admin": admin, "miens": miens, "tous": tous}


@router.get("/api/rapport")
def lire_rapport(req: Request):
    _verifier(req)
    from .. import rapport
    r = rapport.en_attente()
    return {"rapport": {"titre": r["titre"], "ts": r["ts"], "plantage": r.get("plantage", False), "apercu": rapport.contenu(r)}
            if r else None}


@router.post("/api/rapport")
async def envoyer_rapport(req: Request):
    _verifier(req)
    from .. import compte, rapport
    d = await req.json()
    try:
        await asyncio.to_thread(rapport.envoyer, d.get("commentaire", ""))
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))
    return await lister_tickets(req)


@router.delete("/api/rapport")
def ignorer_rapport(req: Request):
    _verifier(req)
    from .. import rapport
    rapport.ignorer()
    return {"ok": True}


@router.post("/api/tickets")
async def creer_ticket(req: Request):
    _verifier(req)
    from .. import compte
    d = await req.json()
    if len(str(d.get("titre", "")).strip()) < 3:
        raise HTTPException(400, "Donne un titre au ticket.")
    try:
        await asyncio.to_thread(compte.creer_ticket, d.get("genre", "bug"), d["titre"].strip(), d.get("description", ""))
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))
    return await lister_tickets(req)


@router.patch("/api/tickets/{tid}")
async def traiter_ticket(tid: int, req: Request):
    _verifier(req)
    from .. import compte
    d = await req.json()
    try:
        await asyncio.to_thread(compte.traiter_ticket, tid, d.get("statut", ""), d.get("reponse"))
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))
    return await lister_tickets(req)


@router.post("/api/tickets/{tid}/corriger")
async def corriger_ticket(tid: int, req: Request):
    _verifier(req)
    from .. import compte
    d = await req.json()
    try:
        t = await asyncio.to_thread(compte.corriger_ticket, tid, d.get("projet", ""))
    except (compte.ErreurCompte, ValueError) as e:
        raise HTTPException(400, str(e))
    return {"tache": t["id"], **(await lister_tickets(req))}


@router.delete("/api/tickets/{tid}")
async def supprimer_ticket(tid: int, req: Request):
    _verifier(req)
    from .. import compte
    try:
        await asyncio.to_thread(compte.supprimer_ticket, tid)
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))
    return await lister_tickets(req)
