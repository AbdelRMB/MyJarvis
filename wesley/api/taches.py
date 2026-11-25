"""Agents de code, tâches de fond, automatisations et liste « À faire »."""
import asyncio
import threading

from fastapi import APIRouter, HTTPException, Request

from ..config import CONFIG, MACHINE
from ..web import _verifier, executer

router = APIRouter()


# ---------- agents de code (Claude Code, Codex) ----------
@router.get("/api/agents_code")
async def etat_agents_code(req: Request):
    _verifier(req)
    from .. import agents_code
    etats = await asyncio.gather(*(asyncio.to_thread(agents_code.etat, a) for a in agents_code.NOMS))
    return [{**e, "probleme": agents_code.probleme(e)} for e in etats]


@router.post("/api/agents_code/{agent}/{action}")
async def agir_agent_code(agent: str, action: str, req: Request):
    _verifier(req)
    from .. import agents_code
    if agent not in agents_code.NOMS:
        raise HTTPException(404, "Agent inconnu.")
    fn = {"connecter": agents_code.connecter, "deconnecter": agents_code.deconnecter, "installer": agents_code.installer}.get(action)
    if not fn:
        raise HTTPException(404, "Action inconnue.")
    return {"message": await asyncio.to_thread(fn, agent)}


# ---------- tâches de fond (code avec Claude Code / Wesley) ----------
@router.get("/api/taches")
def lister_taches(req: Request):
    """Celles de cet appareil, puis celles des autres appareils du compte (`distant`, `appareil`)."""
    _verifier(req)
    from .. import partage, taches
    return [taches.resume(t) | {"appareil": MACHINE} for t in taches.lister()] + partage.distants("tache")


@router.get("/api/taches/{tid}")
def lire_tache(tid: str, req: Request):
    _verifier(req)
    from .. import partage, taches
    t = taches.lire(tid) or partage.lire("tache", tid)
    if not t:
        raise HTTPException(404, "Tâche introuvable.")
    return t


def _agir_a_distance(genre: str, tid: str, action: str, params: dict | None = None) -> str:
    """Action sur une tâche / transcription d'un autre appareil : c'est lui qui la fait (ordre chiffré)."""
    from .. import partage
    try:
        return partage.agir(genre, tid, action, params)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/api/taches")
async def creer_tache(req: Request):
    _verifier(req)
    from .. import taches
    d = await req.json()
    if d.get("appareil"):   # sur un autre ordinateur : c'est lui qui la lance, dans SON dossier de projet
        from .. import partage
        try:
            return {"message": await asyncio.to_thread(partage.lancer, d["appareil"], "tache",
                                                       {k: d.get(k, "") for k in ("consigne", "projet", "outil", "titre")}),
                    "distant": True}
        except ValueError as e:
            raise HTTPException(409, str(e))
    try:
        t = await asyncio.to_thread(taches.creer, d.get("consigne", ""), d.get("projet", ""), d.get("outil", "claude_code"), d.get("titre", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return taches.resume(t)


@router.post("/api/taches/{tid}/{action}")
async def agir_tache(tid: str, action: str, req: Request):
    _verifier(req)
    from .. import taches
    if not taches.lire(tid) and action in ("consigne", "arreter", "reprendre"):
        # tâche lancée sur un autre appareil : on lui demande de le faire, sinon on dit pourquoi
        corps = await req.json() if (await req.body()) else {}
        return {"message": await asyncio.to_thread(_agir_a_distance, "tache", tid, action, corps)}
    if action == "consigne":
        return {"message": taches.mettre_a_jour(tid, (await req.json()).get("texte", ""))}
    if action == "arreter":
        return {"message": taches.arreter(tid)}
    if action == "reprendre":
        try:
            return {"message": taches.reprendre(tid)}
        except ValueError as e:
            raise HTTPException(404, str(e))
    if action == "ouvrir":
        t = taches.lire(tid)
        if t and t.get("dossier"):
            from ..plateforme import ouvrir_chemin
            ouvrir_chemin(t["dossier"])
        return {"ok": True}
    raise HTTPException(404, "Action inconnue.")


@router.delete("/api/taches/{tid}")
def supprimer_tache(tid: str, req: Request):
    _verifier(req)
    from .. import taches
    if not taches.lire(tid):
        return {"ok": True, "message": _agir_a_distance("tache", tid, "supprimer")}
    return {"ok": taches.supprimer(tid)}


# ---------- automatisations ----------
@router.get("/api/automatisations")
def lister_automatisations(req: Request):
    _verifier(req)
    from .. import automatisations
    boites = [{"cid": cid, "nom": f"{c.nom} — {c.etiquette()}"} for cid, c in automatisations._boites().items()]
    return {"regles": [{**r, "description": automatisations.decrire(r)} for r in automatisations.lister()], "boites": boites,
            "machine": MACHINE}


@router.post("/api/automatisations")
async def creer_automatisation(req: Request):
    _verifier(req)
    from .. import automatisations
    d = await req.json()
    typ = d.get("type", "mail")
    if typ == "mail" and not (d.get("expediteur") or d.get("sujet") or d.get("contient")):
        raise HTTPException(400, "Indique au moins un expéditeur, un mot du sujet ou un mot du texte.")
    if typ == "horaire" and not d.get("heure"):
        raise HTTPException(400, "Indique l'heure.")
    if typ == "intervalle" and not d.get("minutes"):
        raise HTTPException(400, "Indique l'intervalle en minutes.")
    if typ == "site" and not str(d.get("url") or "").strip():
        raise HTTPException(400, "Indique l'adresse du site ou du serveur.")
    if d.get("action") == "wesley" and not d.get("consigne", "").strip():
        raise HTTPException(400, "Indique ce que Wesley doit faire.")
    automatisations.creer(d.get("nom", ""), d.get("expediteur", ""), d.get("sujet", ""), d.get("contient", ""),
                          d.get("connecteur", ""), d.get("action", "prevenir"), d.get("consigne", ""), typ,
                          d.get("heure", ""), d.get("jours") or [], int(d.get("minutes") or 0),
                          None if d.get("appareil") is None else d.get("appareil"), d.get("message", ""), d.get("phrase", ""),
                          int(d.get("avant") or 15), d.get("dossier", ""), d.get("motif", ""), d.get("url", ""),
                          d.get("condition", ""))
    return lister_automatisations(req)


@router.patch("/api/automatisations/{rid}")
async def modifier_automatisation(rid: str, req: Request):
    _verifier(req)
    from .. import automatisations
    automatisations.modifier(rid, **(await req.json()))
    return lister_automatisations(req)


@router.delete("/api/automatisations/{rid}")
def supprimer_automatisation(rid: str, req: Request):
    _verifier(req)
    from .. import automatisations
    automatisations.supprimer(rid)
    return lister_automatisations(req)


@router.post("/api/automatisations/{rid}/lancer")
def lancer_routine(rid: str, req: Request):
    """Bouton « Lancer » d'une routine : Wesley l'exécute dans la conversation, comme si tu l'avais demandée."""
    _verifier(req)
    from .. import automatisations
    r = next((x for x in automatisations.lister() if x["id"] == rid), None)
    if not r:
        raise HTTPException(404, "Routine introuvable.")
    threading.Thread(target=executer, args=(automatisations.consigne_routine(r),), daemon=True).start()
    return {"ok": True}


@router.post("/api/automatisations/tester")
async def tester_annonce(req: Request):
    """Bouton « Tester la voix » : Wesley parle comme il le fera pour une automatisation."""
    _verifier(req)
    from .. import annonces
    annonces.annoncer("This is a test: this is how I'll let you know." if CONFIG.get("langue") == "en"
                      else "Ceci est un test : c'est comme ça que je te préviendrai.")
    return {"ok": True}


# ---------- liste « À faire » ----------
@router.get("/api/afaire")
def lister_afaire(req: Request):
    _verifier(req)
    from .. import afaire
    return afaire.lister()


@router.post("/api/afaire")
async def creer_afaire(req: Request):
    _verifier(req)
    from .. import afaire
    d = await req.json()
    if not str(d.get("titre", "")).strip():
        raise HTTPException(400, "Indique la tâche.")
    afaire.ajouter(d["titre"], d.get("note", ""), d.get("echeance", ""), d.get("priorite", "normale"), d.get("statut", "a_faire"),
                   rappel=d.get("rappel", ""))
    return afaire.lister()


@router.patch("/api/afaire/{tid}")
async def modifier_afaire(tid: str, req: Request):
    _verifier(req)
    from .. import afaire
    d = await req.json()
    afaire.modifier(tid, **{k: d.get(k) for k in ("titre", "note", "echeance", "rappel", "priorite", "statut")})
    return afaire.lister()


@router.delete("/api/afaire/{tid}")
def supprimer_afaire(tid: str, req: Request):
    _verifier(req)
    from .. import afaire
    if tid == "faits":
        afaire.vider_faits()
    else:
        afaire.supprimer(tid)
    return afaire.lister()
