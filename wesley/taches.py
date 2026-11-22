"""Tâches de fond : Wesley code (ou fait coder Claude Code) pendant que tu continues à lui parler.

Une tâche = une consigne + un projet + un outil (« claude_code » ou « wesley »). Elle travaille sur SA branche,
dans une copie de travail séparée (git worktree) : tes fichiers en cours ne bougent pas.

Wesley la pilote comme un chef de projet : il lance Claude Code en mode automatique, lit le résultat de chaque
étape, répond à ses questions, relance ce qui a été refusé, demande des corrections, et ne s'arrête que quand la
demande est réalisée (ou que tu l'arrêtes). Tu peux ajouter ou changer la consigne pendant qu'elle tourne : l'étape
en cours est interrompue et la tâche reprend avec ta nouvelle consigne.

Tout est journalisé (onglet Tâches). Les tâches vivent sur cet appareil (RACINE/taches/).
"""
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from .config import CONFIG, RACINE
from .plateforme import CACHE_FENETRE

DOSSIER = RACINE / "taches"
MAX_ETAPES = 40
OUTILS_CLAUDE = "Bash Edit MultiEdit Write Read Glob Grep NotebookEdit WebFetch WebSearch TodoWrite Task"
_verrou = threading.RLock()
_actives: dict = {}   # id -> {"proc": Popen | None, "reveil": Event}


# ---------- stockage ----------
def _fichier(tid):
    return DOSSIER / f"{tid}.json"


def lire(tid) -> dict | None:
    try:
        return json.loads(_fichier(tid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _sauver(t: dict):
    DOSSIER.mkdir(parents=True, exist_ok=True)
    t["maj"] = time.time()
    tmp = _fichier(t["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _fichier(t["id"]))
    _diffuser(t["id"])


def lister() -> list:
    if not DOSSIER.exists():
        return []
    taches = [x for x in (lire(f.stem) for f in DOSSIER.glob("*.json")) if x]
    return sorted(taches, key=lambda x: x["cree"], reverse=True)


def resume(t: dict) -> dict:
    return {k: t.get(k) for k in ("id", "titre", "statut", "outil", "projet", "branche", "dossier", "cree", "maj",
                                  "etape", "bilan")} | {"nb_journal": len(t.get("journal", []))}


def _diffuser(tid):
    try:
        from . import web
        web.diffuser(type="tache_maj", id=tid)
    except Exception:
        pass


def _noter(t: dict, genre: str, texte: str):
    """Journal de la tâche : info, claude, outil, wesley (ce que Wesley répond à Claude Code), utilisateur, erreur."""
    t.setdefault("journal", []).append({"ts": time.time(), "genre": genre, "texte": texte[:8000]})
    t["journal"] = t["journal"][-3000:]
    _sauver(t)


# ---------- création / mise à jour / arrêt ----------
def _slug(texte):
    s = re.sub(r"[^a-z0-9]+", "-", texte.lower().encode("ascii", "ignore").decode())[:30].strip("-")
    return s or "tache"


def creer(consigne: str, projet: str, outil: str = "claude_code", titre: str = "", ticket: int = 0) -> dict:
    chemin = Path(os.path.expanduser(projet.strip())).resolve()
    if not chemin.is_dir():
        raise ValueError(f"Dossier de projet introuvable : {chemin}")
    outil = outil if outil in ("claude_code", "codex", "wesley") else "claude_code"
    if outil != "wesley":
        from . import agents_code, notifications
        msg = agents_code.probleme(agents_code.etat(outil))
        if msg and "expire dans" not in msg:   # pas installé / pas connecté / expiré : on prévient au lieu d'échouer
            notifications.ajouter(f"Tâche non lancée : {titre or consigne[:60]}", msg, genre="alerte", vue="reglages", systeme=True)
            raise ValueError(msg)
    tid = uuid.uuid4().hex[:8]
    t = {"id": tid, "titre": titre.strip() or consigne.strip()[:60], "consigne": consigne.strip(), "projet": str(chemin),
         "outil": outil, "statut": "en_cours",
         "cree": time.time(), "etape": 0, "session": "", "branche": "", "dossier": "", "ajouts": [], "bilan": "",
         "journal": [], "ticket": int(ticket or 0)}
    _sauver(t)
    _noter(t, "utilisateur", consigne)
    demarrer(tid)
    return t


def mettre_a_jour(tid: str, texte: str) -> str:
    """Nouvelle consigne pendant la tâche : prise en compte tout de suite (l'étape en cours est interrompue)."""
    with _verrou:
        t = lire(tid)
        if not t:
            return "Tâche introuvable."
        t.setdefault("ajouts", []).append(texte.strip())
        _noter(t, "utilisateur", "Mise à jour : " + texte.strip())
        if t["statut"] in ("terminee", "echec", "arretee", "interrompue"):
            t["statut"] = "en_cours"
            _sauver(t)
            demarrer(tid)
            return "Tâche relancée avec la nouvelle consigne."
    a = _actives.get(tid)
    if a:
        _interrompre(a)
    return "Consigne ajoutée : la tâche la prend en compte maintenant."


def arreter(tid: str) -> str:
    with _verrou:
        t = lire(tid)
        if not t:
            return "Tâche introuvable."
        t["statut"] = "arretee"
        _noter(t, "info", "Tâche arrêtée à la demande de l'utilisateur.")
    a = _actives.get(tid)
    if a:
        a["stop"] = True
        _interrompre(a)
    return "Tâche arrêtée."


def supprimer(tid: str) -> bool:
    arreter(tid)
    try:
        _fichier(tid).unlink()
        return True
    except OSError:
        return False


def _interrompre(a):
    a["interrompu"] = True
    p = a.get("proc")
    if p and p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGINT) if hasattr(os, "killpg") else p.terminate()
        except Exception:
            p.terminate()


def au_demarrage():
    """Tâches qui tournaient quand Wesley s'est fermé : marquées interrompues (bouton Reprendre)."""
    for t in lister():
        if t["statut"] == "en_cours":
            t["statut"] = "interrompue"
            _noter(t, "info", "Wesley a été fermé pendant la tâche : clique « Reprendre » pour continuer.")


def demarrer(tid: str):
    if tid in _actives:
        return
    _actives[tid] = {"proc": None, "stop": False, "interrompu": False}
    threading.Thread(target=_piloter, args=(tid,), daemon=True, name=f"tache-{tid}").start()


# ---------- branche / copie de travail ----------
def _git(dossier, *args, verifier=True):
    r = subprocess.run(["git", "-C", str(dossier), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", **CACHE_FENETRE)
    if verifier and r.returncode:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout.strip()


def _preparer(t: dict):
    if t.get("dossier") and Path(t["dossier"]).is_dir():
        return
    projet = Path(t["projet"])
    if subprocess.run(["git", "-C", str(projet), "rev-parse", "--is-inside-work-tree"], capture_output=True, **CACHE_FENETRE).returncode:
        t["dossier"], t["branche"] = str(projet), ""
        _noter(t, "info", "Ce dossier n'est pas un dépôt git : travail directement dedans, sans branche.")
        return
    racine = Path(_git(projet, "rev-parse", "--show-toplevel"))
    branche = f"wesley/{_slug(t['titre'])}-{t['id'][:4]}"
    dossier = racine.parent / f"{racine.name}-wesley-{t['id'][:6]}"
    t["base"] = _git(racine, "rev-parse", "HEAD")
    _git(racine, "worktree", "add", "-b", branche, str(dossier), "HEAD")
    t["dossier"], t["branche"] = str(dossier), branche
    _noter(t, "info", f"Branche « {branche} » créée, copie de travail : {dossier}")


# ---------- pilotage ----------
def _consignes(t):
    ajouts = "\n".join(f"- {a}" for a in t.get("ajouts", []))
    return t["consigne"] + (f"\n\nPrécisions / changements demandés ensuite par l'utilisateur (prioritaires) :\n{ajouts}" if ajouts else "")


def _premier_message(t):
    return (f"{_consignes(t)}\n\n"
            "Travaille en autonomie complète dans ce dossier"
            + (f" (branche git « {t['branche']} »)" if t["branche"] else "") + ". "
            "Ne pose pas de question bloquante : prends des décisions raisonnables et indique-les. "
            "Teste ce que tu fais quand c'est possible. Fais des commits clairs au fur et à mesure. "
            "À la fin, résume ce que tu as fait et ce qui reste éventuellement à faire.")


def _claude(t, a, message) -> dict:
    """Une étape de Claude Code (mode automatique). Renvoie {texte, erreur, refus, interrompu}."""
    from . import agents_code
    exe = agents_code.executable("claude_code") or str(Path.home() / ".local/bin/claude")
    cmd = [exe, "-p", message, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits", "--allowedTools", OUTILS_CLAUDE]
    if t.get("session"):
        cmd += ["--resume", t["session"]]
    p = subprocess.Popen(cmd, cwd=t["dossier"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         text=True, encoding="utf-8", errors="replace", bufsize=1, start_new_session=True, env=agents_code._env(), **CACHE_FENETRE)
    a["proc"] = p
    res = {"texte": "", "erreur": False, "refus": [], "interrompu": False}
    for ligne in p.stdout:
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        typ = e.get("type")
        if typ == "system" and e.get("subtype") == "init" and e.get("session_id"):
            t["session"] = e["session_id"]
        elif typ == "assistant":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "text" and b.get("text", "").strip():
                    _noter(t, "claude", b["text"])
                elif b.get("type") == "tool_use":
                    i = b.get("input") or {}
                    detail = i.get("command") or i.get("file_path") or i.get("pattern") or i.get("description") or ""
                    _noter(t, "outil", f"{b.get('name')} {str(detail)[:300]}".strip())
        elif typ == "result":
            res.update(texte=str(e.get("result") or ""), erreur=bool(e.get("is_error")),
                       refus=[d.get("tool_name", "") for d in (e.get("permission_denials") or [])])
            t["session"] = e.get("session_id") or t.get("session", "")
            if e.get("is_error") and any(m in str(e.get("result", "")).lower() for m in ("login", "auth", "credential", "/login")):
                from . import notifications
                notifications.ajouter("Connexion Claude Code", "Claude Code n'est plus connecté : reconnecte-le dans Réglages › Code.",
                                      genre="alerte", vue="reglages", systeme=True)
    p.wait()
    a["proc"] = None
    res["interrompu"] = a.get("interrompu", False)
    return res


def _codex(t, a, message) -> dict:
    """Une étape de Codex (OpenAI) en mode automatique. Reprend la session si possible."""
    import tempfile
    from . import agents_code
    exe = agents_code.executable("codex")
    sortie = Path(tempfile.mkstemp(suffix=".txt")[1])
    base = [exe, "exec", "--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox",
            "-C", t["dossier"], "-o", str(sortie)]
    cmd = base + (["resume", t["session"], message] if t.get("session") else [message])
    res = {"texte": "", "erreur": False, "refus": [], "interrompu": False}
    for essai in (1, 2):
        p = subprocess.Popen(cmd, cwd=t["dossier"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1, start_new_session=True, env=agents_code._env(), **CACHE_FENETRE)
        a["proc"] = p
        lignes_brutes = []
        for ligne in p.stdout:
            try:
                e = json.loads(ligne)
            except ValueError:
                lignes_brutes.append(ligne)
                continue
            for cle in ("thread_id", "session_id", "conversation_id"):
                if isinstance(e.get(cle), str):
                    t["session"] = e[cle]
            it = e.get("item") or {}
            if e.get("type", "").endswith("completed") and it:
                if it.get("type") in ("agent_message", "assistant_message") and it.get("text"):
                    _noter(t, "claude", it["text"])
                elif it.get("type") == "command_execution":
                    _noter(t, "outil", f"Bash {it.get('command', '')[:300]}")
                elif it.get("type") == "file_change":
                    _noter(t, "outil", "Fichiers : " + ", ".join(c.get("path", "") for c in it.get("changes", []))[:300])
        p.wait()
        a["proc"] = None
        res["texte"] = sortie.read_text(encoding="utf-8", errors="replace") if sortie.exists() else ""
        if p.returncode == 0 or a.get("interrompu") or essai == 2 or not t.get("session"):
            res["erreur"] = p.returncode != 0
            if p.returncode and not res["texte"]:
                res["texte"] = "".join(lignes_brutes)[-3000:]
            break
        # reprise impossible : nouvelle session avec tout le contexte
        t["session"] = ""
        cmd = base + [f"{_consignes(t)}\n\nOù en est le travail (bilan) : {t.get('bilan') or '—'}\n\n{message}"]
    sortie.unlink(missing_ok=True)
    res["interrompu"] = a.get("interrompu", False)
    if res["erreur"] and ("login" in res["texte"].lower() or "auth" in res["texte"].lower()):
        from . import notifications
        notifications.ajouter("Connexion Codex", "Codex n'est plus connecté : reconnecte-le dans Réglages › Code.",
                              genre="alerte", vue="reglages", systeme=True)
    return res


def _wesley_etape(t, a, message) -> dict:
    """Variante « Wesley code lui-même » : une instance séparée de Wesley, avec ses outils."""
    from .agent import Wesley
    if not a.get("agent"):
        a["agent"] = Wesley()
    texte = a["agent"].demander(f"[Tâche de fond, dossier de travail : {t['dossier']}]\n{message}")
    return {"texte": texte, "erreur": False, "refus": [], "interrompu": False}


def _decider(t, res, changements: str) -> dict:
    """Wesley, chef de projet : la demande est-elle réalisée ? Sinon, quoi répondre à Claude Code ?"""
    from .agent import completer
    prompt = (
        "Tu es Wesley et tu pilotes Claude Code (un agent de code) pour l'utilisateur. Décide de la suite.\n\n"
        f"DEMANDE DE L'UTILISATEUR :\n{_consignes(t)}\n\n"
        f"DERNIÈRE RÉPONSE DE L'AGENT :\n{res['texte'][-6000:] or '(vide)'}\n\n"
        + (f"OUTILS REFUSÉS À L'AGENT : {', '.join(res['refus'])}\n\n" if res["refus"] else "")
        + f"FICHIERS MODIFIÉS DANS LA BRANCHE (git) :\n{changements[-3000:] or '(aucun)'}\n\n"
        "Réponds UNIQUEMENT en JSON : {\"termine\": true|false, \"message\": \"...\", \"bilan\": \"...\"}\n"
        "- termine = true seulement si TOUTE la demande est réalisée (et testée si possible).\n"
        "- message = ce que tu envoies à l'agent pour continuer : réponds à ses questions (décide à la place de "
        "l'utilisateur, de façon raisonnable et cohérente avec la demande), accorde-lui ce dont il a besoin, "
        "demande de corriger les erreurs, de tester, de finir, de committer.\n"
        "- bilan = 1 à 3 phrases pour l'utilisateur sur l'état actuel.")
    brut = completer(prompt)
    m = re.search(r"\{.*\}", brut, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    return {"termine": bool(d.get("termine")), "message": str(d.get("message") or "Continue jusqu'à ce que la demande soit entièrement réalisée."),
            "bilan": str(d.get("bilan") or "")}


def _changements(t) -> str:
    """Ce que la tâche a changé : fichiers non committés + commits de la branche + résumé du diff."""
    if not t.get("branche"):
        return ""
    base = t.get("base") or "HEAD~1"
    return "\n".join(x for x in (
        _git(t["dossier"], "status", "--short", verifier=False),
        _git(t["dossier"], "log", "--oneline", f"{base}..HEAD", verifier=False),
        _git(t["dossier"], "diff", "--stat", base, verifier=False)) if x)


def _piloter(tid: str):
    a = _actives[tid]
    try:
        t = lire(tid)
        _preparer(t)
        message = _premier_message(t) if not t.get("session") else (
            "Reprends la tâche là où tu en étais." + (f"\n\nNouvelles consignes :\n{_consignes(t)}" if t.get("ajouts") else ""))
        nb_ajouts = len(t.get("ajouts", []))
        while t["etape"] < MAX_ETAPES:
            if a["stop"] or (lire(tid) or {}).get("statut") == "arretee":
                return
            t["etape"] += 1
            nom_agent = {"claude_code": "Claude Code", "codex": "Codex"}.get(t["outil"], "Wesley")
            _noter(t, "wesley", message if t["etape"] > 1 else f"Lancement de {nom_agent} : {message[:500]}")
            a["interrompu"] = False
            res = (_claude(t, a, message) if t["outil"] == "claude_code" else _codex(t, a, message) if t["outil"] == "codex"
                   else _wesley_etape(t, a, message))
            t = {**(lire(tid) or t), "session": t.get("session", ""), "etape": t["etape"], "dossier": t["dossier"],
                 "branche": t["branche"]}
            if a["stop"] or t.get("statut") == "arretee":
                return
            if len(t.get("ajouts", [])) > nb_ajouts:   # l'utilisateur a changé la consigne pendant l'étape
                nouveaux = t["ajouts"][nb_ajouts:]
                nb_ajouts = len(t["ajouts"])
                message = ("STOP sur ce que tu faisais : l'utilisateur a changé la consigne. Prends en compte ceci "
                           "(prioritaire sur la demande initiale) :\n" + "\n".join(f"- {x}" for x in nouveaux))
                continue
            if res["interrompu"]:
                continue
            d = _decider(t, res, _changements(t))
            t["bilan"] = d["bilan"] or t.get("bilan", "")
            if d["bilan"]:
                _noter(t, "info", "Bilan : " + d["bilan"])
            if d["termine"]:
                _finir(t, "terminee")
                return
            message = d["message"]
        _finir(t, "echec", f"Arrêt après {MAX_ETAPES} étapes sans aboutir.")
    except Exception as e:
        traceback.print_exc()
        t = lire(tid) or {"id": tid}
        _noter(t, "erreur", f"{type(e).__name__} : {e}")
        _finir(t, "echec")
    finally:
        _actives.pop(tid, None)


def _finir(t, statut, raison=""):
    if t.get("branche"):
        if _git(t["dossier"], "status", "--porcelain", verifier=False):
            _git(t["dossier"], "add", "-A", "--", ".", ":!**/__pycache__/**", ":!**/*.pyc", ":!**/node_modules/**",
                 ":!**/.DS_Store", ":!**/.venv/**", ":!**/dist/**", ":!**/build/**", verifier=False)
            _git(t["dossier"], "commit", "-m", f"Wesley : {t['titre']}", verifier=False)
    t["statut"] = statut
    _noter(t, "info", raison or ("Tâche terminée." if statut == "terminee" else "Tâche arrêtée."))
    try:
        from . import annonces
        if statut == "terminee" and t.get("ticket"):
            annonces.annoncer(f"Le correctif du ticket {t['ticket']} est prêt sur la branche {t.get('branche') or '?'}.",
                              titre=f"Ticket n°{t['ticket']}", vue="taches", genre="succes",
                              detail=(t.get("bilan", "") + "\n\nRelis-le, fusionne-le et publie la version ; puis dis « marque le "
                                      f"ticket {t['ticket']} résolu » pour prévenir l'utilisateur."))
        elif statut == "terminee":
            annonces.annoncer(("Task finished: " if CONFIG.get("langue") == "en" else "Tâche terminée : ") + t["titre"],
                              vue="taches", genre="succes", detail=t.get("bilan", ""))
        elif statut == "echec":
            annonces.annoncer(("Task failed: " if CONFIG.get("langue") == "en" else "La tâche a échoué : ") + t["titre"],
                              vue="taches", genre="erreur", detail=raison or t.get("bilan", ""))
    except Exception:
        pass
