"""Compte en ligne, appareils du compte et notifications."""
import asyncio
import threading
import webbrowser

from fastapi import APIRouter, HTTPException, Request

from .. import connecteurs, web
from ..config import MACHINE
from ..web import _verifier, diffuser

router = APIRouter()


# ---------- compte en ligne ----------
def _etat_compte():
    from .. import compte
    e = compte.etat()
    return {"connecte": compte.connecte(), "mode": compte.mode(), "email": e.get("email", ""),
            "prenom": e.get("prenom", ""), "serveur": compte.serveur(), "machine": MACHINE, "admin": compte.est_admin(),
            "politique_a_accepter": compte.politique_a_accepter(),
            "url_confidentialite": compte.serveur() + "/mobile/confidentialite.html",
            "url_mentions": compte.serveur() + "/mobile/mentions-legales.html"}


@router.post("/api/ouvrir-lien")
async def ouvrir_lien(req: Request):
    """Ouvre une page dans le navigateur de l'ordinateur (la fenêtre de Wesley n'en est pas un)."""
    _verifier(req)
    from .. import compte
    url = str((await req.json()).get("url", ""))
    # seulement les pages du serveur de comptes et du dépôt GitHub : jamais une adresse quelconque
    if not (url.startswith(compte.serveur() + "/") or url.startswith("https://github.com/")):
        raise HTTPException(400, "Adresse non autorisée.")
    webbrowser.open(url)
    return {"ok": True}


def _apres_connexion():
    """Le compte a changé : nouvelle conversation avec la mémoire et les connecteurs de ce compte."""
    from ..agent import prompt_systeme
    if web.wesley is not None:
        web.wesley.reset()
        web.wesley.messages[0]["content"] = prompt_systeme()
    diffuser(type="reset")
    threading.Thread(target=connecteurs.demarrer_tous, daemon=True).start()


@router.get("/api/compte")
def lire_compte(req: Request):
    _verifier(req)
    return _etat_compte()


@router.post("/api/compte/{action}")
async def agir_compte(action: str, req: Request):
    _verifier(req)
    from .. import compte
    d = await req.json() if action in ("inscription", "connexion", "supprimer") else {}
    try:
        if action == "inscription":
            r = await asyncio.to_thread(compte.inscrire, d.get("email", ""), d.get("mot_de_passe", ""), d.get("prenom", ""),
                                        bool(d.get("politique")))
        elif action == "politique":   # accepte la version actuelle de la politique de confidentialité
            await asyncio.to_thread(compte.accepter_politique)
            r = {}
        elif action == "exporter":    # « Télécharger mes données » : fichier JSON dans Téléchargements
            f = await asyncio.to_thread(compte.exporter_donnees)
            r = {"fichier": str(f)}
            try:
                from ..plateforme import ouvrir_chemin
                ouvrir_chemin(str(f.parent))   # montre le dossier Téléchargements
            except Exception:
                pass
        elif action == "supprimer":   # « Supprimer mon compte » (mot de passe redemandé)
            await asyncio.to_thread(compte.supprimer_compte, d.get("mot_de_passe", ""))
            r = {"supprime": True}
        elif action == "connexion":
            r = await asyncio.to_thread(compte.connecter, d.get("email", ""), d.get("mot_de_passe", ""))
        elif action == "deconnexion":
            await asyncio.to_thread(compte.deconnecter)
            r = {}
        elif action == "importer":   # bouton « Envoyer la mémoire de cet appareil vers mon compte »
            r = {"import": await asyncio.to_thread(compte.importer_appareil)}
            await asyncio.to_thread(compte.synchroniser)
        elif action == "synchroniser":
            await asyncio.to_thread(compte.synchroniser)
            r = {}
        elif action == "local":   # « Utiliser Wesley en local » : pas de compte, rien n'est envoyé
            await asyncio.to_thread(compte.choisir_local)
            r = {}
        elif action == "changer_mode":   # « Passer en ligne » depuis le local (ou l'inverse)
            await asyncio.to_thread(compte.changer_de_mode)
            r = {}
        else:
            raise HTTPException(404, "Action inconnue.")
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))
    if action in ("inscription", "connexion", "deconnexion", "importer", "local", "supprimer"):
        _apres_connexion()
    return {**_etat_compte(), **r}



# ---------- mes appareils ----------
@router.get("/api/appareils")
async def lister_appareils(req: Request):
    _verifier(req)
    from .. import appareils, compte
    liste, erreur = [], ""
    if compte.connecte():
        try:
            liste = await asyncio.to_thread(appareils.lister)
        except compte.ErreurCompte as e:
            erreur = str(e)
    derniere = ""
    try:
        from .. import mises_a_jour
        journal = (await asyncio.to_thread(mises_a_jour.lister)).get("journal") or []
        derniere = journal[0]["version"] if journal else ""
    except Exception:
        pass
    return {"appareils": liste, "reglages": appareils.reglages(), "journal": list(reversed(appareils.journal()))[:100],
            "connecte": compte.connecte(), "mode": compte.mode(), "erreur": erreur, "derniere_version": derniere}


@router.get("/api/appareils/ordinateurs")
def lister_ordinateurs(req: Request):
    """Liste légère des autres ordinateurs du compte (lancer une transcription ou une tâche à distance)."""
    _verifier(req)
    from .. import partage
    return {"ordinateurs": partage.ordinateurs(), "moi": MACHINE}


@router.post("/api/appareils/reglages")
async def regler_appareil(req: Request):
    _verifier(req)
    from .. import appareils
    d = await req.json()
    appareils.regler(d.get("accepte"), d.get("mode"))
    return await lister_appareils(req)


@router.post("/api/appareils/{aid}/deconnecter")
async def deconnecter_un_appareil(aid: str, req: Request):
    _verifier(req)
    from .. import appareils, compte
    moi = next((a for a in await asyncio.to_thread(appareils.lister) if a["moi"]), None)
    if moi and moi["id"] == aid:   # cet appareil-ci : déconnexion complète
        await asyncio.to_thread(compte.deconnecter)
        return {"moi": True}
    try:
        return await asyncio.to_thread(appareils.deconnecter, aid)
    except compte.ErreurCompte as e:
        raise HTTPException(400, str(e))


@router.post("/api/appareils/{aid}/mettre_a_jour")
async def mettre_a_jour_appareil(aid: str, req: Request):
    """Met à jour Wesley sur un autre appareil allumé (il télécharge, s'installe et redémarre)."""
    _verifier(req)
    from .. import appareils
    try:
        r = await asyncio.to_thread(appareils.envoyer, aid, {"type": "mettre_a_jour"}, 120)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"resultat": r.get("resultat", ""), "ok": r.get("ok", False)}


@router.post("/api/appareils/{aid}/demander")
async def demander_appareil(aid: str, req: Request):
    """Depuis l'onglet Appareils : envoyer une demande à un autre appareil et attendre sa réponse."""
    _verifier(req)
    from .. import appareils
    texte = (await req.json()).get("texte", "").strip()
    try:
        r = await asyncio.to_thread(appareils.envoyer, aid, {"type": "demande", "texte": texte}, 600)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"resultat": r.get("resultat", ""), "ok": r.get("ok", False)}


# ---------- notifications (cloche) ----------
@router.get("/api/notifications")
def lire_notifications(req: Request):
    _verifier(req)
    from .. import notifications
    return list(reversed(notifications.lister()))


@router.post("/api/notifications/{action}")
async def agir_notifications(action: str, req: Request):
    _verifier(req)
    from .. import notifications
    if action == "lues":
        d = await req.json()
        notifications.marquer_lues(d.get("ids"))
    elif action == "effacer":
        notifications.effacer()
    return {"ok": True}
