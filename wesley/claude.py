"""Cerveau Claude (API Anthropic) — alternative à Ollama, choisie dans Réglages > Cerveau.

- Clé API : variable ANTHROPIC_API_KEY, ou fichier .env à la racine de Wesley (écrit depuis l'interface).
- Historique « append-only » : on ne retouche jamais les messages déjà envoyés (sinon le cache de prompt
  et les blocs de réflexion deviennent invalides).
- Cache de prompt automatique : instructions + 52 outils + historique sont relus ~10x moins cher.
- Coûts suivis dans logs/couts.json (estimation à partir des tokens facturés).
"""
import base64
import io
import json
import os
import threading
import time
from datetime import datetime

from . import memoire, outils
from .config import CONFIG, RACINE

ENV = RACINE / ".env"
COUTS = RACINE / "logs" / "couts.json"

MODELES = {
    "claude-sonnet-5-5": "Sonnet 5.5 — intelligent et rapide (recommandé)",
    "claude-haiku-5-5": "Haiku 5.5 — très économique, moins fiable avec les outils",
    "claude-opus-5-5": "Opus 5.5 — le plus intelligent, ~2x plus cher",
}
# $ par million de tokens : entrée, sortie, écriture cache (5 min), lecture cache.
# Haiku/Opus : écriture cache estimée à 1,25x l'entrée.
PRIX = {
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
}

_client = None
_verrou_couts = threading.Lock()
MAX_ETAPES = 60          # actions par demande (les longues tâches ne sont plus coupées à 25)
CONSEILLER = "claude-opus-5-5"   # modèle plus puissant consulté par Sonnet sur les décisions difficiles
# outils web de Wesley remplacés par la recherche web native de Claude (meilleurs résultats, sources citées)
OUTILS_WEB_REMPLACES = {"recherche_web", "lire_page_web", "actualites"}

# Effort « auto » : le réglage par défaut passe de « low » fixe à « auto » (une seule fois, à la mise à jour)
if not CONFIG.get("effort_auto_migre"):
    if CONFIG.get("claude_effort") == "low":
        CONFIG["claude_effort"] = "auto"
    CONFIG["effort_auto_migre"] = True
    try:
        from .config import sauver_config
        sauver_config(["claude_effort", "effort_auto_migre"])
    except Exception:
        pass


# ---------- clé API ----------
def _lire_env():
    if ENV.exists():
        for ligne in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.strip().startswith("#"):
                k, v = ligne.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_lire_env()


def cle_configuree() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def cle_masquee() -> str:
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    return f"{k[:7]}…{k[-4:]}" if len(k) > 12 else ""


def definir_cle(cle: str, synchro: bool = True):
    """Enregistre la clé dans .env (fichier local, jamais envoyé ailleurs qu'à Anthropic)."""
    global _client
    cle = cle.strip()
    lignes = [l for l in (ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else [])
              if not l.startswith("ANTHROPIC_API_KEY=")]
    if cle:
        lignes.append(f"ANTHROPIC_API_KEY={cle}")
        os.environ["ANTHROPIC_API_KEY"] = cle
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    ENV.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    _client = None
    if synchro:   # la clé rejoint le coffre chiffré du compte (lisible sur tes autres appareils seulement)
        from . import compte
        compte.cle_api_modifiee(cle)


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(max_retries=2, timeout=120)
    return _client


# ---------- coûts ----------
def _lire_couts():
    try:
        return json.loads(COUTS.read_text(encoding="utf-8"))
    except Exception:
        return {"total": 0.0, "appels": 0, "jours": {}}


def enregistrer_cout(usage, modele: str) -> float:
    e, s, ce, cl = PRIX.get(modele, PRIX["claude-sonnet-5-5"])
    cout = ((usage.input_tokens or 0) * e + (usage.output_tokens or 0) * s
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * ce
            + (getattr(usage, "cache_read_input_tokens", 0) or 0) * cl) / 1e6
    with _verrou_couts:
        c = _lire_couts()
        jour = f"{datetime.now():%Y-%m-%d}"
        c["total"] = c.get("total", 0) + cout
        c["appels"] = c.get("appels", 0) + 1
        c.setdefault("jours", {})[jour] = c["jours"].get(jour, 0) + cout
        COUTS.parent.mkdir(exist_ok=True)
        COUTS.write_text(json.dumps(c, indent=1), encoding="utf-8")
    return cout


def resume_couts():
    c = _lire_couts()
    return {"total": round(c.get("total", 0), 4), "appels": c.get("appels", 0),
            "aujourdhui": round(c.get("jours", {}).get(f"{datetime.now():%Y-%m-%d}", 0), 4)}


def _journal_perf(rep, ttft, duree, cout):
    u = rep.usage
    try:
        with open(RACINE / "logs" / "perf.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} claude={rep.model} 1er_token={ttft:.1f}s total={duree:.1f}s "
                    f"entree={u.input_tokens} cache_lu={getattr(u, 'cache_read_input_tokens', 0)} "
                    f"cache_ecrit={getattr(u, 'cache_creation_input_tokens', 0)} sortie={u.output_tokens} "
                    f"cout={cout * 100:.3f}c$ stop={rep.stop_reason}\n")
    except Exception:
        pass


# ---------- conversation ----------
_outils_cache, _outils_version = None, -1


def _web_natif() -> bool:
    return bool(CONFIG.get("recherche_web_native", True))


def _avec_conseiller() -> bool:
    # le conseiller doit être au moins aussi puissant : utile seulement quand le cerveau est Sonnet
    return bool(CONFIG.get("conseiller", True)) and CONFIG["claude_modele"] == "claude-sonnet-5-5"


def outils_claude():
    """Les outils au format Anthropic (ordre stable = cache stable ; recalculé si un connecteur ou un réglage change)."""
    global _outils_cache, _outils_version
    cle = (outils.VERSION, _web_natif(), _avec_conseiller())
    if _outils_cache is None or _outils_version != cle:
        liste = [{"name": f["name"], "description": f["description"], "input_schema": f["parameters"]}
                 for f in (s["function"] for s in outils.schemas())
                 if not (_web_natif() and f["name"] in OUTILS_WEB_REMPLACES)]
        if _web_natif():   # recherche et lecture de pages par Anthropic : filtrage dynamique, sources citées
            liste += [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6},
                      {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 6}]
        if _avec_conseiller():
            liste.append({"type": "advisor_20260301", "name": "advisor", "model": CONSEILLER, "max_uses": 2,
                          "caching": {"type": "ephemeral", "ttl": "5m"}})
        _outils_cache, _outils_version = liste, cle
    return _outils_cache


# ---------- effort automatique : réfléchir plus quand la demande le mérite ----------
import re as _re

_RX_TRES = _re.compile(r"r[ée]fl[ée]chis (bien|vraiment|longtemps)|en profondeur|approfondi|analyse (compl[èe]te|d[ée]taill[ée]e)|"
                       r"prends ton temps|think hard|in depth", _re.I)
_RX_ELEVE = _re.compile(r"\b(cod[eé]|code|d[ée]velopp|corrig|d[ée]bug|bug|analys|compar|planifi|organis|pr[ée]pare|r[ée]dig|"
                        r"[ée]cris (un|une|le|la|moi)|strat[ée]gi|optimis|explique pourquoi|pourquoi|diagnosti|conseil|"
                        r"r[ée]sous|calcul|estime|configure|installe|migr|automatis|routine|plan|budget|r[ée]sum[ée] (de|du|des)|"
                        r"debug|fix|analy[sz]e|compare|plan|write a|why|explain)|tu (en )?penses|ton avis|je devrais|faut-il|vaut-il mieux|"
                        r"what do you think|should i", _re.I)


def effort_pour(texte: str) -> str:
    """Choisit l'effort de réflexion selon la demande : bas pour une conversation ou une commande simple
    (réactif à l'oral), élevé pour une tâche en plusieurs étapes, très élevé si on lui demande de bien réfléchir."""
    t = texte.strip()
    if _RX_TRES.search(t):
        return "xhigh"
    if len(t) > 280 or _RX_ELEVE.search(t) or t.count("?") > 1 or _re.search(r"\b(puis|ensuite|et apr[èe]s|then)\b", t, _re.I):
        return "high"
    if len(t) > 120:
        return "medium"
    return "low"


def _effort_de_base() -> str:
    e = CONFIG.get("claude_effort") or "auto"
    return "low" if e == "auto" else e


def _parametres_requete():
    betas = ["server-side-fallback-2026-07-01", "thinking-binding-controls-2026-08-01",
             "mid-conversation-output-config-2026-07-01", "mid-conversation-system-clear-at-2026-08-21"]
    if _avec_conseiller():
        betas.append("advisor-tool-2026-03-01")
    return dict(
        model=CONFIG["claude_modele"],
        max_tokens=32000,
        # réflexion adaptative : à effort « low », le modèle saute la réflexion sur les demandes simples (réactif à l'oral)
        # la mémoire (dans les instructions) peut changer en cours de conversation (synchro entre appareils) :
        # les anciens blocs de réflexion sont alors ignorés au lieu de faire échouer la requête
        thinking={"type": "adaptive", "display": "summarized",
                  "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
        # effort « auto » : la base reste fixe (cache intact) et chaque demande ajuste l'effort par un message système
        output_config={"effort": _effort_de_base()},
        cache_control={"type": "ephemeral"},   # met en cache tout le début de conversation, automatiquement
        # si le modèle refuse une demande (faux positif de sécurité), l'API la rejoue sur un modèle de secours
        betas=betas,
        fallbacks="default",
    )


def demander(j, texte, sur_texte=None, sur_outil=None, sur_pensee=None):
    """Boucle agent avec Claude, avec des messages d'erreur compréhensibles."""
    import anthropic
    try:
        return _demander(j, texte, sur_texte, sur_outil, sur_pensee)
    except anthropic.AuthenticationError:
        raise RuntimeError("Clé API refusée par Anthropic : vérifie-la dans Réglages > Cerveau.") from None
    except anthropic.PermissionDeniedError:
        raise RuntimeError("Cette clé n'a pas accès à ce modèle.") from None
    except anthropic.RateLimitError:
        raise RuntimeError("Trop de requêtes d'un coup (limite Anthropic) : réessaie dans quelques secondes.") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("Impossible de joindre Anthropic : vérifie ta connexion Internet "
                           "(ou repasse sur Ollama dans Réglages > Cerveau).") from None
    except anthropic.BadRequestError as e:
        if "credit" in str(e).lower() or "balance" in str(e).lower():
            raise RuntimeError("Crédit API épuisé : recharge sur platform.claude.com (Billing).") from None
        raise RuntimeError(f"Requête refusée par l'API : {getattr(e, 'message', e)}") from None
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Erreur du service Anthropic ({e.status_code}) : réessaie dans un instant.") from None


def _demander(j, texte, sur_texte=None, sur_outil=None, sur_pensee=None):
    """Boucle agent avec Claude : streaming, appels d'outils, jusqu'à la réponse finale."""
    if not cle_configuree():
        raise RuntimeError("Clé API Claude manquante : ajoute-la dans Réglages > Cerveau.")
    memoire.journaliser(CONFIG.get("nom_utilisateur") or "Utilisateur", texte)
    j.histo_claude.append({"role": "user", "content": texte})
    # placé juste après la demande : règle l'effort de CETTE réponse ; ajouté à la suite (jamais retiré) pour garder
    # le cache et les blocs de réflexion valides. Un effort réglé ainsi tient jusqu'au suivant, d'où le suivi.
    reglage = CONFIG.get("claude_effort") or "auto"
    effort = effort_pour(texte) if reglage == "auto" else reglage
    if effort != (getattr(j, "effort_claude", None) or _effort_de_base()):
        j.histo_claude.append({"role": "system", "content": [], "output_config": {"effort": effort}})
        j.effort_claude = effort
    # ses consignes (« réponds en une phrase »…) rappelées pour CE tour : visibles maintenant, effacées (gratuites)
    # dès le message suivant, et jamais retirées de l'historique (cache et réflexion restent valides)
    rappel = memoire.rappel_consignes()
    if rappel:
        j.histo_claude.append({"role": "system", "clear_at": "next_user_message", "content": rappel})
    j.arreter = False
    final = ""
    for _ in range(max(CONFIG["max_etapes_outils"], MAX_ETAPES)):
        if j.arreter:
            final += "\n(Tâche interrompue.)"
            break
        t0, ttft, interrompu = time.time(), None, False
        with client().beta.messages.stream(system=j.messages[0]["content"], tools=outils_claude(),
                                           messages=j.histo_claude, **_parametres_requete()) as flux:
            for ev in flux:
                if j.arreter:
                    interrompu = True
                    break
                if ev.type == "content_block_delta":
                    if ev.delta.type == "text_delta":
                        ttft = ttft or time.time() - t0
                        if sur_texte:
                            sur_texte(ev.delta.text)
                    elif ev.delta.type == "thinking_delta" and sur_pensee:
                        sur_pensee(ev.delta.thinking)
            rep = None if interrompu else flux.get_final_message()
        if rep is None:   # arrêté en plein flux : rien n'est ajouté à l'historique (il reste valide)
            final += "\n(Tâche interrompue.)"
            break
        cout = enregistrer_cout(rep.usage, rep.model or CONFIG["claude_modele"])
        _journal_perf(rep, ttft or time.time() - t0, time.time() - t0, cout)
        # on renvoie le tour tel quel (blocs de réflexion compris) : ne jamais le modifier
        j.histo_claude.append({"role": "assistant", "content": rep.content})
        texte_tour = "".join(b.text for b in rep.content if b.type == "text")
        final = texte_tour or final

        if rep.stop_reason == "refusal":
            msg = "Je ne peux pas faire ça (refus de sécurité du modèle)."
            if sur_texte:
                sur_texte(msg)
            final = msg
            break
        appels = [b for b in rep.content if b.type == "tool_use"]
        if rep.stop_reason == "max_tokens" and appels:
            final += "\n(Réponse coupée avant la fin de l'action, je ne l'exécute pas.)"
            break
        if rep.stop_reason == "pause_turn":
            continue
        if not appels:
            break
        resultats = []
        for a in appels:
            args = a.input if isinstance(a.input, dict) else {}
            if j.arreter:
                resultats.append({"type": "tool_result", "tool_use_id": a.id, "content": "Annulé par l'utilisateur.",
                                  "is_error": True})
                continue
            if sur_outil:
                sur_outil(a.name, args, None)
            res = outils.appeler(a.name, args)
            if sur_outil:
                sur_outil(a.name, args, res)
            resultats.append({"type": "tool_result", "tool_use_id": a.id, "content": res or "OK",
                              "is_error": res.startswith("Erreur")})
        # tous les résultats d'un même tour dans UN seul message
        j.histo_claude.append({"role": "user", "content": resultats})
        if rappel:   # les résultats d'actions effacent le rappel précédent : on le redonne pour la suite du tour
            j.histo_claude.append({"role": "system", "clear_at": "next_user_message", "content": rappel})
    else:
        final += "\n(J'ai atteint le nombre max d'étapes, dis-moi si je continue.)"
    memoire.journaliser("Wesley", final)
    return final


def conversation_ui(histo):
    """Convertit l'historique Claude au format de l'interface (pour restaurer après rechargement)."""
    out = []
    for m in histo:
        c = m["content"]
        if m["role"] == "system":   # réglage d'effort : invisible dans l'interface
            continue
        if m["role"] == "user":
            if isinstance(c, str):
                out.append({"role": "user", "texte": c})
            elif out and out[-1]["role"] == "wesley":
                for r in c:
                    for b in out[-1]["blocs"]:
                        if b["type"] == "outil" and b.get("_id") == r.get("tool_use_id"):
                            b["resultat"] = str(r.get("content", ""))[:600]
                            b["erreur"] = bool(r.get("is_error"))
        else:
            if not out or out[-1]["role"] != "wesley":
                out.append({"role": "wesley", "blocs": []})
            for b in c:
                if b.type == "text" and b.text:
                    out[-1]["blocs"].append({"type": "texte", "texte": b.text})
                elif b.type == "tool_use":
                    out[-1]["blocs"].append({"type": "outil", "_id": b.id, "nom": b.name, "resultat": None,
                                             "args": {k: str(v)[:200] for k, v in (b.input or {}).items()}})
    for m in out:
        for b in m.get("blocs", []):
            b.pop("_id", None)
    return out


def souvenirs(echanges: list[str], faits_actuels: str) -> list[dict]:
    """Fin de session : extrait les faits nouveaux et durables (sortie JSON garantie)."""
    r = client().messages.create(
        model=CONFIG["claude_modele"], max_tokens=4000, output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": {
                "type": "object", "additionalProperties": False, "required": ["faits"],
                "properties": {"faits": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["fait", "categorie"],
                    "properties": {"fait": {"type": "string"}, "categorie": {
                        "type": "string", "enum": ["identite", "preference", "projet", "contact", "habitude", "general", "consigne"]}}}}}}}},
        messages=[{"role": "user", "content":
                   "Voici une conversation entre l'utilisateur et son assistant. Extrais UNIQUEMENT les faits NOUVEAUX et "
                   "DURABLES sur l'utilisateur (identité, goûts, projets, personnes, habitudes) absents de la mémoire actuelle, "
                   "et les CONSIGNES qu'il a données sur la façon dont l'assistant doit se comporter ou répondre (catégorie consigne). "
                   "Liste vide s'il n'y a rien.\n\nMémoire actuelle :\n" + faits_actuels +
                   "\n\nConversation :\n" + "\n".join(echanges[-40:])}])
    enregistrer_cout(r.usage, CONFIG["claude_modele"])
    if r.stop_reason == "refusal":
        return []
    texte = next((b.text for b in r.content if b.type == "text"), "{}")
    return json.loads(texte).get("faits", [])


def vision(question: str, image: bytes) -> str:
    """Analyse d'image par Claude (remplace le modèle de vision local quand le cerveau est Claude)."""
    from PIL import Image
    img = Image.open(io.BytesIO(image)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    r = client().messages.create(
        model=CONFIG["claude_modele"], max_tokens=4000, output_config={"effort": "low"},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.standard_b64encode(buf.getvalue()).decode()}},
            {"type": "text", "text": question}]}])
    enregistrer_cout(r.usage, CONFIG["claude_modele"])
    if r.stop_reason == "refusal":
        return "Analyse d'image refusée par le modèle."
    return "".join(b.text for b in r.content if b.type == "text").strip()
