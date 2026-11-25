"""Cerveaux : IA compatibles OpenAI et Claude (clés, tests)."""
import asyncio
import time

from fastapi import APIRouter, HTTPException, Request

from ..config import CONFIG
from ..fournisseurs import PAR_ID as IA
from ..web import _fid, _ia, _verifier

router = APIRouter()


@router.get("/api/ia")
def liste_ia(req: Request):
    _verifier(req)
    from ..fournisseurs import pour_interface
    return {"fournisseurs": pour_interface()}


@router.get("/api/ia/{fid}")
async def etat_ia(fid: str, req: Request):
    _verifier(req)
    o = _ia()
    fid = _fid(fid)
    modeles, erreur = [], ""
    if o.cle_configuree(fid):
        try:
            modeles = await asyncio.to_thread(o.modeles, fid)
        except Exception as e:
            erreur = f"Liste des modèles indisponible ({type(e).__name__}) : tu peux écrire le nom du modèle à la main."
    return {"cle": o.cle_configuree(fid), "cle_masquee": o.cle_masquee(fid), "modeles": modeles,
            "modele": CONFIG.get(f"{fid}_modele") or "", "conseille": IA[fid].get("defaut", ""),
            "url": o.url(fid) or "", "erreur": erreur}


@router.post("/api/ia/{fid}/cle")
async def cle_ia(fid: str, req: Request):
    _verifier(req)
    o = _ia()
    fid = _fid(fid)
    cle = str((await req.json()).get("cle", "")).strip()
    prefixe = IA[fid].get("prefixe")
    if cle and prefixe and not cle.startswith(prefixe):
        raise HTTPException(400, f"Ce n'est pas une clé {IA[fid]['nom']} (elle commence par {prefixe}).")
    o.definir_cle(cle, fid=fid)
    return await etat_ia(fid, req)


@router.post("/api/ia/{fid}/tester")
async def tester_ia(fid: str, req: Request):
    _verifier(req)
    o = _ia()
    fid = _fid(fid)
    try:
        texte, s = await asyncio.to_thread(o.tester, fid)
    except Exception as e:
        raise HTTPException(502, f"Échec : {e}")
    return {"texte": texte, "secondes": round(s, 1), "modele": o.modele(fid)}


# ---------- cerveau Claude ----------
@router.get("/api/claude")
def etat_claude(req: Request):
    _verifier(req)
    from .. import claude
    return {"cle": claude.cle_configuree(), "cle_masquee": claude.cle_masquee(), "couts": claude.resume_couts(),
            "modeles": [{"id": k, "nom": v} for k, v in claude.MODELES.items()]}


@router.post("/api/claude/cle")
async def cle_claude(req: Request):
    _verifier(req)
    from .. import claude
    cle = str((await req.json()).get("cle", "")).strip()
    if cle and not cle.startswith("sk-ant-"):
        raise HTTPException(400, "Ce n'est pas une clé API Anthropic (elle commence par sk-ant-).")
    claude.definir_cle(cle)
    return {"cle": claude.cle_configuree(), "cle_masquee": claude.cle_masquee()}


@router.post("/api/claude/tester")
async def tester_claude(req: Request):
    _verifier(req)
    from .. import claude

    def essai():
        t0 = time.time()
        r = claude.client().messages.create(model=CONFIG["claude_modele"], max_tokens=50,
                                            output_config={"effort": "low"},
                                            messages=[{"role": "user", "content": "Réponds juste : opérationnel."}])
        claude.enregistrer_cout(r.usage, CONFIG["claude_modele"])
        return "".join(b.text for b in r.content if b.type == "text"), time.time() - t0
    try:
        texte, s = await asyncio.to_thread(essai)
    except Exception as e:
        raise HTTPException(502, f"Échec : {e}")
    return {"reponse": texte, "secondes": round(s, 2)}
