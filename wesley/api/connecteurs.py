"""Connecteurs, clés SSH, sites appris et navigateur de Wesley."""
import asyncio

from fastapi import APIRouter, HTTPException, Request

from .. import connecteurs
from ..web import _verifier, demander_texte

router = APIRouter()


# ---------- connecteurs (Gmail, agenda, GitHub, Notion, MCP…) ----------
@router.get("/api/connecteurs")
def liste_connecteurs(req: Request):
    _verifier(req)
    return {"catalogue": connecteurs.catalogue(), "installes": connecteurs.etat()}


@router.post("/api/ssh/generer-cle")
def generer_cle_ssh(req: Request):
    _verifier(req)
    return connecteurs.generer_cle_ssh()


@router.get("/api/ssh/cle-publique")
def cle_publique_ssh(cid: str, req: Request):
    _verifier(req)
    try:
        return {"publique": connecteurs.cle_publique_ssh(cid)}
    except Exception as e:
        raise HTTPException(400, f"Clé enregistrée illisible : {e}"[:300])


@router.post("/api/connecteurs/{cid:path}/tester")
async def tester_connecteur(cid: str, req: Request):
    _verifier(req)
    try:
        return {"message": await asyncio.to_thread(connecteurs.tester, cid)}
    except Exception as e:
        raise HTTPException(400, f"{e}"[:300])


@router.post("/api/connecteurs/{cid:path}")
async def enregistrer_connecteur(cid: str, req: Request):
    _verifier(req)
    d = await req.json()
    try:
        await asyncio.to_thread(connecteurs.enregistrer, cid, d.get("type"), d.get("conf"), d.get("secrets"),
                                d.get("actif", True))
    except Exception as e:
        raise HTTPException(400, f"{e}"[:300])
    return connecteurs.etat().get(cid, {})


@router.delete("/api/connecteurs/{cid:path}")
async def supprimer_connecteur(cid: str, req: Request):
    _verifier(req)
    await asyncio.to_thread(connecteurs.supprimer, cid)
    return {"ok": True}



# ---------- sites appris et navigateur de Wesley ----------
@router.get("/api/sites")
def lister_sites(req: Request):
    _verifier(req)
    from .. import navigateur, sites
    return {"sites": [sites.resume(s) for s in sites.lister()], "navigateur": navigateur.etat(),
            "exploration": {k: v for k, v in sites.EXPLO.items() if k != "arreter"}}


@router.get("/api/sites/{sid}")
def lire_site(sid: str, req: Request):
    _verifier(req)
    from .. import sites
    s = sites.lire(sid)
    if not s:
        raise HTTPException(404, "Site introuvable.")
    return {**s, "procedures": [{**p, "texte": [sites.decrire_etape(e) for e in p["etapes"]]} for p in s.get("procedures", [])]}


@router.post("/api/sites")
async def ajouter_site(req: Request):
    _verifier(req)
    from .. import sites
    d = await req.json()
    if not str(d.get("url", "")).strip():
        raise HTTPException(400, "Indique l'adresse du site.")
    return sites.resume(sites.ajouter(d.get("nom", ""), d["url"].strip()))


@router.delete("/api/sites/{sid}")
def supprimer_site(sid: str, req: Request):
    _verifier(req)
    from .. import sites
    sites.supprimer(sid)
    return {"ok": True}


@router.post("/api/navigateur_perso/tester")
async def tester_navigateur_perso(req: Request):
    """Bouton « Tester » : Wesley lit l'onglet ouvert dans ton navigateur et l'entoure brièvement."""
    _verifier(req)
    from .. import navigateur_perso as p
    try:
        v = await asyncio.to_thread(p.instantane)
        await asyncio.to_thread(p.js, "(() => { const e = document.querySelector('[data-wesley-ref]') || document.body; "
                                      f"({p._SURLIGNER})(e); return true; }})()")
        return {"ok": True, "message": f"{v.get('navigateur')} : je vois « {v.get('titre') or v.get('url')} » ({len(v.get('elements', []))} éléments)."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.post("/api/navigateur/installer")
def installer_navigateur(req: Request):
    _verifier(req)
    from .. import navigateur
    navigateur.installer_chrome()
    return navigateur.etat()


@router.post("/api/sites/{sid}/{action}")
async def agir_site(sid: str, action: str, req: Request):
    _verifier(req)
    from .. import navigateur, sites
    d = await req.json() if (req.headers.get("content-length") or "0") != "0" else {}
    s = sites.lire(sid)
    if not s and action != "arreter":
        raise HTTPException(404, "Site introuvable.")
    try:
        if action == "ouvrir":   # pour s'y connecter (identifiants, double authentification…)
            await asyncio.to_thread(navigateur.ouvrir, s["url"])
            await asyncio.to_thread(navigateur.afficher)
        elif action == "explorer":
            sites.explorer(sid, max(5, min(int(d.get("max_pages") or 80), 300)))
        elif action == "arreter":
            sites.EXPLO["arreter"] = True
        elif action == "demo":   # démonstration : l'utilisateur fait la tâche, Wesley enregistre
            await asyncio.to_thread(navigateur.demarrer_enregistrement, sid)
            if not ((await asyncio.to_thread(navigateur.instantane)) or {}).get("url", "").startswith("http"):
                await asyncio.to_thread(navigateur.ouvrir, s["url"])
        elif action == "demo_fin":
            etapes = navigateur.arreter_enregistrement()
            if d.get("garder", True) and etapes:
                sites.ajouter_procedure(sid, d.get("nom", "") or "Procédure", etapes, d.get("description", ""))
            return {"etapes": len(etapes), **(await asyncio.to_thread(sites.lire, sid))}
        elif action == "astuce":
            sites.noter(sid, d.get("texte", ""))
        elif action == "identifiants":   # rien n'est renvoyé : les secrets ne repartent jamais vers l'interface
            try:
                connexion = sites.definir_identifiants(sid, d.get("identifiant"), d.get("mot_de_passe"), d.get("totp"))
            except Exception:
                raise HTTPException(400, "Clé de double authentification invalide : copie la clé secrète (ou l'adresse otpauth://).")
            return {"connexion": connexion}
        elif action == "code":
            c = sites.code_2fa(sid)
            return {"code": c[0] if c else "", "reste": c[1] if c else 0}
        elif action == "connecter":
            r = await asyncio.to_thread(sites.se_connecter, sid, lambda q: demander_texte(q, "Saisis le code affiché par ton appli ou reçu par SMS."))
            await asyncio.to_thread(navigateur.afficher)
            return {"resultat": r.split("\n")[0]}
        elif action == "retirer":
            sites.retirer(sid, d.get("quoi", "astuces"), d.get("id", ""))
        else:
            raise HTTPException(404, "Action inconnue.")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
