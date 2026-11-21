"""Cerveau « compatible OpenAI » : OpenAI, Gemini, Mistral, DeepSeek, Grok, OpenRouter, Groq, LM Studio…
Même rôle que claude.py. La liste des fournisseurs (adresse, clé, modèles préférés) est dans fournisseurs.py.

- Fournisseur : CONFIG["cerveau"] ; modèle : CONFIG["<id>_modele"] (vide = le meilleur disponible).
- Clé : dans .env (Réglages › Cerveau), copiée dans le coffre chiffré du compte.
- Messages, souvenirs et résultats d'outils sont envoyés au fournisseur choisi (sauf LM Studio / serveur local).
"""
import base64
import io
import json
import os
import re
import time

from . import memoire, outils
from .config import CONFIG
from .fournisseurs import PAR_ID, choisir_modele, garder_modele

_clients: dict = {}


def fournisseur(fid: str | None = None) -> dict:
    fid = fid or CONFIG.get("cerveau")
    return PAR_ID.get(fid) or PAR_ID["openai"]


def _env(fid=None):
    return fournisseur(fid).get("env")


def _cle(fid=None) -> str:
    from . import claude   # lit .env (clés de tous les services)
    claude._lire_env()
    env = _env(fid)
    return os.environ.get(env, "") if env else ""


def url(fid=None) -> str | None:
    f = fournisseur(fid)
    if f["url"] == "perso":
        return (CONFIG.get("perso_url") or "").strip() or None
    return f["url"]


def cle_configuree(fid=None) -> bool:
    f = fournisseur(fid)
    if f["url"] == "perso":
        return bool(url(fid))          # la clé est facultative pour un serveur local
    return bool(_cle(fid)) if f.get("env") else True


def cle_masquee(fid=None) -> str:
    k = _cle(fid)
    return f"{k[:7]}…{k[-4:]}" if len(k) > 12 else ("••••" if k else "")


def definir_cle(cle: str, synchro: bool = True, fid=None):
    """Enregistre la clé dans .env (fichier local) et dans le coffre chiffré du compte."""
    from .claude import ENV
    env = _env(fid)
    if not env:
        return
    cle = cle.strip()
    lignes = [l for l in (ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else [])
              if not l.startswith(env + "=")]
    if cle:
        lignes.append(f"{env}={cle}")
        os.environ[env] = cle
    else:
        os.environ.pop(env, None)
    ENV.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    _clients.clear()
    if synchro:
        from . import compte
        compte.cle_api_modifiee(cle, env)


def client(fid=None):
    f = fournisseur(fid)
    base, cle = url(f["id"]), _cle(f["id"]) or ("lm-studio" if f.get("local") else "sans-cle")
    if f["url"] == "perso" and not base:
        raise RuntimeError("Adresse du service manquante : ajoute-la dans Réglages › Cerveau.")
    k = (f["id"], base, cle)
    if k not in _clients:
        import openai
        en_tetes = {"HTTP-Referer": "https://github.com/AbdelRMB/MyJarvis", "X-Title": "Jarvis"} if f["id"] == "openrouter" else None
        _clients[k] = openai.OpenAI(api_key=cle, base_url=base, default_headers=en_tetes, timeout=120)
    return _clients[k]


def modeles(fid=None) -> list[str]:
    f = fournisseur(fid)
    ids = sorted({(m.id or "").removeprefix("models/") for m in client(f["id"]).models.list().data})
    return [i for i in ids if i and garder_modele(f, i)]


def modele(fid=None) -> str:
    f = fournisseur(fid)
    cle = f"{f['id']}_modele"
    if CONFIG.get(cle):
        return CONFIG[cle]
    import openai
    try:
        choix = choisir_modele(f, modeles(f["id"]))
    except openai.APIConnectionError:
        if f.get("local") or f["url"] == "perso":
            raise RuntimeError(f"{f['nom']} ne répond pas à {url(f['id'])} : lance son serveur, puis réessaie.") from None
        choix = f.get("defaut", "")
    except Exception:
        choix = f.get("defaut", "")
    if not choix:
        raise RuntimeError(f"Aucun modèle trouvé chez {f['nom']} : choisis-en un dans Réglages › Cerveau.")
    CONFIG[cle] = choix
    return choix


def _outils():
    return [{"type": "function", "function": s["function"]} for s in outils.schemas()]


def demander(j, texte, sur_texte=None, sur_outil=None, sur_pensee=None):
    import openai
    f = fournisseur()
    nom, ou = f["nom"], f["cle_ou"].split(".")[0]
    try:
        return _demander(j, texte, sur_texte, sur_outil)
    except openai.AuthenticationError:
        raise RuntimeError(f"Clé API refusée par {nom} : vérifie-la dans Réglages › Cerveau ({ou}).") from None
    except openai.PermissionDeniedError as e:
        raise RuntimeError(f"{nom} refuse l'accès ({getattr(e, 'message', e)}).") from None
    except openai.RateLimitError as e:
        if any(x in str(e).lower() for x in ("quota", "credit", "balance", "insufficient")):
            raise RuntimeError(f"Crédit {nom} épuisé ou limite gratuite atteinte : recharge ton compte ou réessaie plus tard.") from None
        raise RuntimeError(f"Trop de requêtes d'un coup (limite {nom}) : réessaie dans quelques secondes.") from None
    except openai.APIConnectionError:
        if f.get("local") or f["url"] == "perso":
            raise RuntimeError(f"{nom} ne répond pas à {url()} : lance son serveur, puis réessaie.") from None
        raise RuntimeError(f"Impossible de joindre {nom} : vérifie ta connexion Internet.") from None
    except openai.NotFoundError:
        raise RuntimeError(f"Modèle « {modele()} » indisponible chez {nom} : choisis-en un autre dans Réglages › Cerveau.") from None
    except openai.BadRequestError as e:
        msg = str(getattr(e, "message", e))
        if "tool" in msg.lower() or "function" in msg.lower():
            raise RuntimeError(f"Le modèle « {modele()} » ne sait pas utiliser d'outils : choisis-en un autre dans Réglages › Cerveau.") from None
        raise RuntimeError(f"Requête refusée par {nom} : {msg}") from None
    except openai.APIStatusError as e:
        raise RuntimeError(f"Erreur du service {nom} ({e.status_code}) : {getattr(e, 'message', e)}") from None


def _demander(j, texte, sur_texte=None, sur_outil=None):
    f = fournisseur()
    if not cle_configuree():
        raise RuntimeError(f"Clé API {f['nom']} manquante : ajoute-la dans Réglages › Cerveau.")
    memoire.journaliser(CONFIG.get("nom_utilisateur") or "Utilisateur", texte)
    rappel = memoire.rappel_consignes()
    if f["id"] == "openai":
        j.histo_openai.append({"role": "user", "content": texte})
        if rappel:   # ses consignes, juste après sa demande : bien plus respectées qu'en haut des instructions
            j.histo_openai.append({"role": "system", "content": rappel})
    else:
        # plusieurs fournisseurs refusent un message « system » au milieu de la conversation : rappel joint à la demande
        j.histo_openai.append({"role": "user", "content": f"{texte}\n\n({rappel})" if rappel else texte})
    j.arreter = False
    final = ""
    for _ in range(CONFIG["max_etapes_outils"]):
        if j.arreter:
            final += "\n(Tâche interrompue.)"
            break
        flux = client().chat.completions.create(model=modele(), stream=True, tools=_outils(),
                                                messages=[{"role": "system", "content": j.messages[0]["content"]}] + j.histo_openai)
        contenu, appels, interrompu = "", {}, False
        for morceau in flux:
            if j.arreter:
                interrompu = True
                break
            if not morceau.choices:
                continue
            d = morceau.choices[0].delta
            if d is None:
                continue
            if d.content:
                contenu += d.content
                if sur_texte:
                    sur_texte(d.content)
            for tc in d.tool_calls or []:
                # certains fournisseurs (Gemini…) n'envoient pas d'index : un nouvel id = un nouvel appel
                idx = tc.index if tc.index is not None else (
                    len(appels) if tc.id and all(a["id"] != tc.id for a in appels.values()) else max(appels, default=0))
                a = appels.setdefault(idx, {"id": "", "nom": "", "args": ""})
                a["id"] = tc.id or a["id"]
                if tc.function:
                    a["nom"] += tc.function.name or ""
                    a["args"] += tc.function.arguments or ""
        if interrompu:
            final += "\n(Tâche interrompue.)"
            break
        final = contenu or final
        if not appels:
            j.histo_openai.append({"role": "assistant", "content": contenu})
            break
        for i, a in appels.items():
            a["id"] = a["id"] or f"appel_{len(j.histo_openai)}_{i}"
        j.histo_openai.append({"role": "assistant", "content": contenu or None, "tool_calls": [
            {"id": a["id"], "type": "function", "function": {"name": a["nom"], "arguments": a["args"] or "{}"}}
            for a in appels.values()]})
        for a in appels.values():
            try:
                args = json.loads(a["args"] or "{}")
            except ValueError:
                args = {}
            if j.arreter:
                res = "Annulé par l'utilisateur."
            else:
                if sur_outil:
                    sur_outil(a["nom"], args, None)
                res = outils.appeler(a["nom"], args)
                if sur_outil:
                    sur_outil(a["nom"], args, res)
            j.histo_openai.append({"role": "tool", "tool_call_id": a["id"], "content": res or "OK"})
    else:
        final += "\n(J'ai atteint le nombre max d'étapes, dis-moi si je continue.)"
    memoire.journaliser("Jarvis", final)
    return final


def conversation_ui(histo):
    out = []
    for m in histo:
        if m["role"] == "user":
            out.append({"role": "user", "texte": m["content"]})
        elif m["role"] == "assistant" and m.get("content"):
            out.append({"role": "jarvis", "blocs": [{"type": "texte", "texte": m["content"]}]})
    return out


def completer(prompt: str) -> str:
    """Réponse simple, sans outils."""
    r = client().chat.completions.create(model=modele(), messages=[{"role": "user", "content": prompt}])
    return r.choices[0].message.content or ""


def souvenirs(echanges: list[str], faits_actuels: str) -> list[dict]:
    consigne = ("Voici une conversation entre l'utilisateur et son assistant. Extrais UNIQUEMENT les faits NOUVEAUX et DURABLES "
                "sur l'utilisateur (identité, goûts, projets, personnes, habitudes) absents de la mémoire actuelle. Réponds "
                'uniquement en JSON : {"faits": [{"fait": "...", "categorie": "identite|preference|projet|contact|habitude|general"}]} '
                "(liste vide si rien).\n\nMémoire actuelle :\n" + faits_actuels + "\n\nConversation :\n" + "\n".join(echanges[-40:]))
    messages = [{"role": "user", "content": consigne}]
    try:
        r = client().chat.completions.create(model=modele(), response_format={"type": "json_object"}, messages=messages)
    except Exception:   # mode JSON non pris en charge par ce fournisseur : on lit le JSON dans le texte
        r = client().chat.completions.create(model=modele(), messages=messages)
    texte = r.choices[0].message.content or "{}"
    bloc = re.search(r"\{.*\}", texte, re.S)
    try:
        return json.loads(bloc.group(0) if bloc else "{}").get("faits", [])
    except ValueError:
        return []


def vision(question: str, image: bytes) -> str:
    from PIL import Image
    img = Image.open(io.BytesIO(image)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    url_image = "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode()
    try:
        r = client().chat.completions.create(model=modele(), messages=[{"role": "user", "content": [
            {"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": url_image}}]}])
    except Exception as e:
        raise RuntimeError(f"Le modèle « {modele()} » ne lit pas les images ({type(e).__name__}) : "
                           "choisis un modèle avec vision dans Réglages › Cerveau.") from None
    return (r.choices[0].message.content or "").strip()


def tester(fid=None) -> tuple[str, float]:
    t0 = time.time()
    r = client(fid).chat.completions.create(model=modele(fid), messages=[{"role": "user", "content": "Réponds juste : opérationnel."}])
    return (r.choices[0].message.content or "").strip(), time.time() - t0
