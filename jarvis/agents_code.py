"""Agents de code pilotés par Jarvis dans les tâches de fond : Claude Code (Anthropic) et Codex (OpenAI).

Pour chacun : installé ?, connecté ?, avec quel compte, et quand la connexion expire. Boutons Installer /
Connecter / Déconnecter dans Réglages › Code. Jarvis vérifie régulièrement et te prévient (notification) si
une connexion a expiré ou expire bientôt ; une tâche ne démarre pas sans connexion valide.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

WIN = sys.platform == "win32"
NOMS = {"claude_code": "Claude Code", "codex": "Codex (OpenAI)"}
_PATH_EN_PLUS = [str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin",
                 str(Path(os.environ.get("APPDATA", "")) / "npm") if WIN else ""]


def _env():
    """L'appli lancée depuis le Finder / au démarrage a un PATH minimal : on ajoute les dossiers habituels."""
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([p for p in _PATH_EN_PLUS if p] + [e.get("PATH", "")])
    # Les clés API de Jarvis (cerveau) ne doivent PAS être vues par Claude Code / Codex : sinon ils les utilisent
    # à la place de ton compte connecté (abonnement Claude Pro/Max, ChatGPT) et tout est facturé sur la clé API.
    for cle in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        e.pop(cle, None)
    return e


def executable(agent: str) -> str:
    nom = {"claude_code": "claude", "codex": "codex"}[agent]
    return shutil.which(nom, path=_env()["PATH"]) or ""


def _lancer(args, timeout=20) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=_env(),
                          creationflags=0x08000000 if WIN else 0)


def _jwt_exp(jeton: str) -> float:
    try:
        charge = jeton.split(".")[1]
        return float(json.loads(base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4))).get("exp", 0))
    except Exception:
        return 0


def etat(agent: str) -> dict:
    """{installe, connecte, compte, plan, expiration (ISO ou ""), erreur}."""
    exe = executable(agent)
    e = {"agent": agent, "nom": NOMS[agent], "installe": bool(exe), "connecte": False, "compte": "", "plan": "",
         "expiration": "", "renouvellement_auto": False, "erreur": ""}
    if not exe:
        return e
    try:
        if agent == "claude_code":
            d = json.loads(_lancer([exe, "auth", "status", "--json"]).stdout or "{}")
            e.update(connecte=bool(d.get("loggedIn")), compte=d.get("email") or d.get("orgName") or "",
                     plan=d.get("planTier") or d.get("subscriptionType") or d.get("authMethod") or "",
                     expiration=d.get("loginExpiresAt") or "")
        else:
            r = _lancer([exe, "login", "status"])
            texte = (r.stdout + r.stderr).strip()
            e["connecte"] = r.returncode == 0 and "not logged in" not in texte.lower()
            e["plan"] = texte.splitlines()[0][:80] if texte else ""
            auth = Path.home() / ".codex" / "auth.json"
            if auth.exists():
                a = json.loads(auth.read_text())
                jetons = a.get("tokens") or {}
                exp = _jwt_exp(jetons.get("access_token", "")) or _jwt_exp(jetons.get("id_token", ""))
                if exp:
                    e["expiration"] = datetime.fromtimestamp(exp, timezone.utc).isoformat()
                e["renouvellement_auto"] = bool(jetons.get("refresh_token"))
                try:
                    idt = jetons.get("id_token", "").split(".")[1]
                    e["compte"] = json.loads(base64.urlsafe_b64decode(idt + "=" * (-len(idt) % 4))).get("email", "")
                except Exception:
                    pass
                if a.get("OPENAI_API_KEY") and not e["compte"]:
                    e["compte"] = "clé API OpenAI"
    except Exception as x:
        e["erreur"] = f"{type(x).__name__} : {x}"[:200]
    return e


def connecter(agent: str) -> str:
    """Ouvre la connexion dans le navigateur (compte Claude / compte ChatGPT). On vérifie ensuite avec etat()."""
    exe = executable(agent)
    if not exe:
        return f"{NOMS[agent]} n'est pas installé."
    args = [exe, "auth", "login"] if agent == "claude_code" else [exe, "login"]
    subprocess.Popen(args, env=_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=not WIN, creationflags=0x08000000 if WIN else 0)
    return "Connexion ouverte dans ton navigateur : termine-la, puis reviens ici."


def deconnecter(agent: str) -> str:
    exe = executable(agent)
    if exe:
        _lancer([exe, "auth", "logout"] if agent == "claude_code" else [exe, "logout"])
    return "Déconnecté."


def installer(agent: str) -> str:
    """Installe l'agent (script officiel pour Claude Code, npm pour Codex)."""
    if agent == "claude_code":
        cmd = (["powershell", "-NoProfile", "-Command", "irm https://claude.ai/install.ps1 | iex"] if WIN
               else ["bash", "-lc", "curl -fsSL https://claude.ai/install.sh | bash"])
    else:
        npm = shutil.which("npm", path=_env()["PATH"])
        if not npm:
            return "Il faut Node.js pour installer Codex : installe-le (nodejs.org), puis réessaie."
        cmd = [npm, "install", "-g", "@openai/codex"]
    r = _lancer(cmd, timeout=600)
    return "Installé." if r.returncode == 0 and executable(agent) else f"Échec de l'installation : {(r.stderr or r.stdout)[-400:]}"


def probleme(e: dict) -> str:
    """Message à afficher si l'agent ne peut pas être utilisé maintenant (ou bientôt)."""
    if not e["installe"]:
        return f"{e['nom']} n'est pas installé (Réglages › Code)."
    if not e["connecte"]:
        return f"{e['nom']} n'est pas connecté : reconnecte-le dans Réglages › Code."
    if e["expiration"] and not e["renouvellement_auto"]:
        try:
            reste = datetime.fromisoformat(e["expiration"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
            if reste.total_seconds() < 0:
                return f"La connexion de {e['nom']} a expiré : reconnecte-le dans Réglages › Code."
            if reste.days < 3:
                return f"La connexion de {e['nom']} expire dans {max(1, int(reste.total_seconds() // 3600))} h : pense à la renouveler (Réglages › Code)."
        except ValueError:
            pass
    return ""


_surveillance = {"lancee": False, "deja": set()}


def surveiller():
    """Toutes les 6 h : prévient (notification) si un agent installé n'est plus connecté ou expire bientôt."""
    if _surveillance["lancee"]:
        return
    _surveillance["lancee"] = True

    def boucle():
        time.sleep(60)
        while True:
            for agent in NOMS:
                try:
                    e = etat(agent)
                    msg = probleme(e) if e["installe"] else ""
                    cle = (agent, msg)
                    if msg and cle not in _surveillance["deja"]:
                        _surveillance["deja"].add(cle)
                        from . import notifications
                        notifications.ajouter(f"Connexion {e['nom']}", msg, genre="alerte", vue="reglages", systeme=True)
                except Exception:
                    pass
            time.sleep(6 * 3600)
    threading.Thread(target=boucle, daemon=True, name="surveillance-agents").start()
