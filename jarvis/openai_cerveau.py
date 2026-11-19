"""Cerveau OpenAI (API) : même rôle que claude.py, pour ceux qui ont une clé API OpenAI.

- Clé : OPENAI_API_KEY dans .env (Réglages › Cerveau), copiée dans le coffre chiffré du compte.
- Modèle : choisi dans la liste des modèles de ta clé (lue chez OpenAI), sinon le meilleur disponible.
- Messages, souvenirs et résultats d'outils sont envoyés à OpenAI.
"""
import base64
import io
import json
import os
import time

from . import memoire, outils
from .config import CONFIG

_client = None
PREFERES = ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"]   # par ordre de préférence, si disponibles avec ta clé
EXCLUS = ("audio", "realtime", "tts", "transcribe", "image", "embedding", "search", "moderation", "dall", "whisper")


def cle_configuree() -> bool:
    from . import claude   # lit .env (clés des deux services)
    claude._lire_env()
    return bool(os.environ.get("OPENAI_API_KEY"))


def cle_masquee() -> str:
    k = os.environ.get("OPENAI_API_KEY", "")
    return f"{k[:7]}…{k[-4:]}" if len(k) > 12 else ""


def definir_cle(cle: str, synchro: bool = True):
    """Enregistre la clé dans .env (fichier local) et dans le coffre chiffré du compte."""
    global _client
    from .claude import ENV
    cle = cle.strip()
    lignes = [l for l in (ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else [])
              if not l.startswith("OPENAI_API_KEY=")]
    if cle:
        lignes.append(f"OPENAI_API_KEY={cle}")
        os.environ["OPENAI_API_KEY"] = cle
    else:
        os.environ.pop("OPENAI_API_KEY", None)
    ENV.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    _client = None
    if synchro:
        from . import compte
        compte.cle_api_modifiee(cle, "OPENAI_API_KEY")


def client():
    global _client
    if _client is None:
        import openai
        _client = openai.OpenAI()
    return _client


def modeles() -> list[str]:
    ids = sorted(m.id for m in client().models.list().data)
    return [i for i in ids if (i.startswith("gpt-") or i[:2] in ("o1", "o3", "o4", "o5")) and not any(x in i for x in EXCLUS)]


def modele() -> str:
    if CONFIG.get("openai_modele"):
        return CONFIG["openai_modele"]
    try:
        dispo = modeles()
        choix = next((m for m in PREFERES if m in dispo), dispo[0] if dispo else "gpt-4o")
    except Exception:
        choix = "gpt-4o"
    CONFIG["openai_modele"] = choix
    return choix


def _outils():
    return [{"type": "function", "function": s["function"]} for s in outils.schemas()]


def demander(j, texte, sur_texte=None, sur_outil=None, sur_pensee=None):
    import openai
    try:
        return _demander(j, texte, sur_texte, sur_outil)
    except openai.AuthenticationError:
        raise RuntimeError("Clé API refusée par OpenAI : vérifie-la dans Réglages > Cerveau.") from None
    except openai.RateLimitError as e:
        if "quota" in str(e).lower():
            raise RuntimeError("Crédit OpenAI épuisé : recharge sur platform.openai.com (Billing).") from None
        raise RuntimeError("Trop de requêtes d'un coup (limite OpenAI) : réessaie dans quelques secondes.") from None
    except openai.APIConnectionError:
        raise RuntimeError("Impossible de joindre OpenAI : vérifie ta connexion Internet.") from None
    except openai.NotFoundError:
        raise RuntimeError(f"Modèle « {modele()} » indisponible avec ta clé : choisis-en un autre dans Réglages > Cerveau.") from None
    except openai.APIStatusError as e:
        raise RuntimeError(f"Erreur du service OpenAI ({e.status_code}) : {getattr(e, 'message', e)}") from None


def _demander(j, texte, sur_texte=None, sur_outil=None):
    if not cle_configuree():
        raise RuntimeError("Clé API OpenAI manquante : ajoute-la dans Réglages > Cerveau.")
    memoire.journaliser("Utilisateur", texte)
    j.histo_openai.append({"role": "user", "content": texte})
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
            if d.content:
                contenu += d.content
                if sur_texte:
                    sur_texte(d.content)
            for tc in d.tool_calls or []:
                a = appels.setdefault(tc.index, {"id": "", "nom": "", "args": ""})
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


def souvenirs(echanges: list[str], faits_actuels: str) -> list[dict]:
    r = client().chat.completions.create(model=modele(), response_format={"type": "json_object"}, messages=[{
        "role": "user", "content":
        "Voici une conversation entre l'utilisateur et son assistant. Extrais UNIQUEMENT les faits NOUVEAUX et DURABLES sur "
        "l'utilisateur (identité, goûts, projets, personnes, habitudes) absents de la mémoire actuelle. Réponds en JSON : "
        '{"faits": [{"fait": "...", "categorie": "identite|preference|projet|contact|habitude|general"}]} (liste vide si rien).'
        "\n\nMémoire actuelle :\n" + faits_actuels + "\n\nConversation :\n" + "\n".join(echanges[-40:])}])
    try:
        return json.loads(r.choices[0].message.content or "{}").get("faits", [])
    except ValueError:
        return []


def vision(question: str, image: bytes) -> str:
    from PIL import Image
    img = Image.open(io.BytesIO(image)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    url = "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode()
    r = client().chat.completions.create(model=modele(), messages=[{"role": "user", "content": [
        {"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": url}}]}])
    return (r.choices[0].message.content or "").strip()


def tester() -> tuple[str, float]:
    t0 = time.time()
    r = client().chat.completions.create(model=modele(), messages=[{"role": "user", "content": "Réponds juste : opérationnel."}])
    return (r.choices[0].message.content or "").strip(), time.time() - t0
