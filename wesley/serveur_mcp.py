"""Wesley comme serveur MCP : Claude Desktop, Claude Code ou tout autre client MCP peuvent interroger sa mémoire,
ses transcriptions, tes documents et ta liste À faire.

Désactivé par défaut (Réglages › Application). Une fois activé :
- serveur HTTP « streamable » sur http://127.0.0.1:7778/mcp, uniquement sur cet ordinateur (jamais sur le réseau) ;
- chaque requête doit porter « Authorization: Bearer <clé> » ; la clé est propre à cet appareil (fichier mcp.json
  dans le dossier des données, jamais synchronisée) et peut être régénérée ;
- seuls quelques outils sûrs sont exposés (lecture, plus ajouter un souvenir ou une tâche) : jamais la souris, le
  clavier, les fichiers, les commandes ni les connecteurs. Chaque appel est noté dans le journal (onglet Activité).
"""
import asyncio
import functools
import json
import os
import secrets
import threading

from .config import RACINE

PORT = int(os.environ.get("WESLEY_MCP_PORT", 7778))
HOTE = "127.0.0.1"
FICHIER = RACINE / "mcp.json"

# outils de Wesley exposés aux autres assistants (noms de wesley/outils)
OUTILS_EXPOSES = [
    "chercher_partout", "chercher_memoire", "lister_souvenirs", "memoriser",
    "chercher_transcriptions", "lister_transcriptions", "lire_transcription", "resumer_transcription",
    "chercher_dans_documents", "lister_a_faire", "ajouter_a_faire",
]
INSTRUCTIONS = ("Wesley est l'assistant personnel de l'utilisateur, sur son ordinateur. Il connaît l'utilisateur "
                "(souvenirs), garde ses transcriptions de cours et de réunions, lit ses documents et tient sa liste "
                "À faire. Commence par chercher_partout quand tu ne sais pas où se trouve l'information.")

_etat: dict = {"serveur": None, "fil": None, "erreur": ""}
_verrou = threading.Lock()


# ---------- réglage et clé (propres à cet appareil) ----------
def _lire() -> dict:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ecrire(d: dict):
    FICHIER.write_text(json.dumps(d, indent=1), encoding="utf-8")


def actif() -> bool:
    return bool(_lire().get("actif"))


def cle() -> str:
    d = _lire()
    if not d.get("cle"):
        d["cle"] = "wesley-" + secrets.token_urlsafe(24)
        _ecrire(d)
    return d["cle"]


def regenerer_cle() -> str:
    d = _lire()
    d["cle"] = "wesley-" + secrets.token_urlsafe(24)
    _ecrire(d)
    return d["cle"]


def url() -> str:
    return f"http://{HOTE}:{PORT}/mcp"


def etat() -> dict:
    k = cle()
    return {"actif": actif(), "en_marche": en_marche(), "url": url(), "cle": k, "erreur": _etat["erreur"],
            "outils": OUTILS_EXPOSES,
            "claude_code": f'claude mcp add --transport http wesley {url()} --header "Authorization: Bearer {k}"',
            "claude_desktop": json.dumps({"mcpServers": {"wesley": {
                "command": "npx", "args": ["-y", "mcp-remote", url(), "--header", "Authorization:${AUTH_HEADER}"],
                "env": {"AUTH_HEADER": f"Bearer {k}"}}}}, indent=2)}


# ---------- serveur ----------
def _outil(nom: str):
    """Fonction async pour le SDK MCP, avec la signature et la description de l'outil de Wesley."""
    from . import outils
    o = outils.OUTILS[nom]
    fn = o["fn"]

    @functools.wraps(fn)
    async def appel(**kwargs):
        return await asyncio.to_thread(outils._appeler, nom, kwargs)
    proprietes = o["schema"]["function"]["parameters"]["properties"]
    detail = "\n".join(f"{k}: {v['description']}" for k, v in proprietes.items() if v.get("description") != k)
    return appel, o["schema"]["function"]["description"] + ("\n" + detail if detail else "")


def creer_application(cle_attendue: str | None = None):
    """Application ASGI : serveur MCP (outils exposés) derrière la vérification de la clé."""
    from mcp.server.mcpserver import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
    from . import outils
    from .outils import afaire_outils, documents_outils, memoire_outils, transcription_outils  # noqa: F401
    from .version import VERSION
    serveur = MCPServer(name="wesley", title="Wesley", instructions=INSTRUCTIONS, version=VERSION, log_level="WARNING")
    for nom in OUTILS_EXPOSES:
        if nom in outils.OUTILS and "fn" in outils.OUTILS[nom]:
            fn, desc = _outil(nom)
            serveur.add_tool(fn, name=nom, description=desc, structured_output=False)
    hotes = [f"{HOTE}:{PORT}", f"localhost:{PORT}", HOTE, "localhost"]
    app_mcp = serveur.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True, json_response=True, host=HOTE,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hotes,
                                                     allowed_origins=[f"http://{h}" for h in hotes]))
    attendue = (cle_attendue or cle()).encode()

    async def garde(scope, receive, send):
        if scope["type"] == "http":
            entetes = dict(scope.get("headers") or [])
            fourni = entetes.get(b"authorization", b"").removeprefix(b"Bearer ").strip()
            if not secrets.compare_digest(fourni, attendue):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": b'{"error":"cle Wesley manquante ou invalide"}'})
                return
        await app_mcp(scope, receive, send)
    return garde


def en_marche() -> bool:
    s = _etat["serveur"]
    return bool(s and s.started and not s.should_exit)


def demarrer():
    """Lance le serveur dans un fil (sans effet s'il tourne déjà)."""
    import uvicorn
    with _verrou:
        if en_marche():
            return
        _etat["erreur"] = ""
        try:
            config = uvicorn.Config(creer_application(), host=HOTE, port=PORT, log_level="warning", log_config=None,
                                    lifespan="on")
            serveur = uvicorn.Server(config)
        except Exception as e:
            _etat["erreur"] = str(e)
            return

        def tourner():
            try:
                serveur.run()
            except BaseException as e:   # port déjà pris (SystemExit d'uvicorn), dépendance absente…
                _etat["erreur"] = str(e) or f"le port {PORT} est déjà utilisé"
        _etat["serveur"] = serveur
        _etat["fil"] = threading.Thread(target=tourner, daemon=True, name="serveur-mcp")
        _etat["fil"].start()


def arreter():
    with _verrou:
        s = _etat["serveur"]
        if s:
            s.should_exit = True
        _etat["serveur"] = None


def regler(activer: bool) -> dict:
    d = _lire()
    d["actif"] = bool(activer)
    _ecrire(d)
    arreter()
    if activer:
        demarrer()
    return etat()


def au_demarrage():
    if actif():
        demarrer()
