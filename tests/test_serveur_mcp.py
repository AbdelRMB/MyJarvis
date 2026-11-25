"""Wesley comme serveur MCP (wesley/serveur_mcp.py) : un vrai client MCP liste les outils exposés et en appelle un ;
sans la bonne clé, le serveur refuse.

Lancer : python -m pytest tests/test_serveur_mcp.py -q   (mcp et uvicorn : requirements.txt)
"""
import asyncio
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("mcp")
uvicorn = pytest.importorskip("uvicorn")
httpx = pytest.importorskip("httpx")

from wesley import outils, recherche, serveur_mcp  # noqa: E402
from wesley.outils import memoire_outils  # noqa: E402,F401  (enregistre chercher_partout, memoriser…)

CLE = "wesley-cle-de-test"


@pytest.fixture
def serveur(monkeypatch, tmp_path):
    monkeypatch.setattr(serveur_mcp, "FICHIER", tmp_path / "mcp.json")
    monkeypatch.setattr(recherche, "chercher_partout", lambda q, n=6: {
        "souvenirs": [{"fid": "f1", "fait": f"Souvenir sur {q}", "categorie": "general"}], "historique": [],
        "transcriptions": [], "documents": [], "afaire": [], "erreurs": {}})
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(serveur_mcp, "PORT", port)
    srv = uvicorn.Server(uvicorn.Config(serveur_mcp.creer_application(CLE), host="127.0.0.1", port=port,
                                        log_level="warning", log_config=None, lifespan="on"))
    fil = threading.Thread(target=srv.run, daemon=True)
    fil.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    srv.should_exit = True
    fil.join(5)


async def _session(url, cle):
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
    async with streamable_http_client(url, http_client=create_mcp_http_client(
            headers={"Authorization": f"Bearer {cle}"})) as flux:
        async with ClientSession(flux[0], flux[1]) as s:
            await s.initialize()
            outils_mcp = (await s.list_tools()).tools
            res = await s.call_tool("chercher_partout", {"requete": "la voiture"})
            return outils_mcp, res


def test_client_mcp_liste_et_appelle_les_outils(serveur):
    outils_mcp, res = asyncio.run(_session(serveur, CLE))
    noms = {t.name for t in outils_mcp}
    assert {"chercher_partout", "memoriser", "lire_transcription", "ajouter_a_faire"} <= noms
    # jamais d'outil qui agit sur l'ordinateur
    assert not noms & {"executer_commande", "cliquer", "ecrire_fichier", "supprimer_fichier", "taper_texte"}
    assert set(noms) <= set(serveur_mcp.OUTILS_EXPOSES)
    assert outils_mcp[0].input_schema["type"] == "object"
    texte = res.content[0].text
    assert "Souvenir sur la voiture" in texte and not res.is_error


def test_sans_la_cle_le_serveur_refuse(serveur):
    r = httpx.post(serveur, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                   headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 401
    r = httpx.post(serveur, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                   headers={"Accept": "application/json, text/event-stream", "Authorization": "Bearer mauvaise"})
    assert r.status_code == 401


def test_cle_et_reglage_propres_a_l_appareil(monkeypatch, tmp_path):
    monkeypatch.setattr(serveur_mcp, "FICHIER", tmp_path / "mcp.json")
    monkeypatch.setattr(serveur_mcp, "demarrer", lambda: None)
    k = serveur_mcp.cle()
    assert k.startswith("wesley-") and serveur_mcp.cle() == k
    assert not serveur_mcp.actif()
    e = serveur_mcp.regler(True)
    assert e["actif"] and serveur_mcp.actif()
    assert k in e["claude_code"] and e["url"].endswith("/mcp") and "mcp-remote" in e["claude_desktop"]
    assert serveur_mcp.regenerer_cle() != k
    assert outils.OUTILS   # les outils de Wesley sont chargés pour le serveur
