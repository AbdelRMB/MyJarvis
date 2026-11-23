"""Tickets : un administrateur peut clore, répondre et supprimer en POST (le proxy Apache bloque PATCH et DELETE).

Lancer : cd serveur && WESLEY_DB=/tmp/wesley-test.db python -m pytest tests -q
"""
import os
import secrets
import sys
import tempfile
import time

os.environ.setdefault("WESLEY_DB", os.path.join(tempfile.mkdtemp(), "wesley.db"))
os.environ["WESLEY_CLE_APPLI"] = "cle-test"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as serveur  # noqa: E402

client = TestClient(serveur.app)


def _compte(admin: bool) -> dict:
    """Crée un utilisateur et sa session directement en base ; renvoie les en-têtes de l'appli de bureau."""
    jeton = secrets.token_urlsafe(24)
    with serveur.db() as c:
        uid = c.execute("INSERT INTO utilisateurs (email, prenom, auth_sel, auth_hash, cree, admin) VALUES (?, ?, ?, ?, ?, ?)",
                        (f"{jeton}@test.fr", "Test", b"s", b"h", time.time(), int(admin))).lastrowid
        c.execute("INSERT INTO sessions (jeton_hash, utilisateur, appareil, cree, vu) VALUES (?, ?, '', ?, ?)",
                  (serveur._empreinte(jeton), uid, time.time(), time.time()))
    return {"Authorization": f"Bearer {jeton}", "X-Wesley-Appli": "cle-test", "User-Agent": "Wesley"}


@pytest.fixture
def comptes():
    serveur._essais.clear()
    return _compte(admin=False), _compte(admin=True)


def _ticket(h) -> int:
    r = client.post("/v1/tickets", headers=h, json={"genre": "bug", "titre": "Erreur : KeyError 'x'",
                                                    "description": "--- Rapport automatique ---"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _statut(h_admin, tid):
    return next(t for t in client.get("/v1/admin/tickets", headers=h_admin).json() if t["id"] == tid)


def test_resoudre_un_ticket_en_post(comptes):
    auteur, admin = comptes
    tid = _ticket(auteur)
    r = client.post(f"/v1/admin/tickets/{tid}", headers=admin,
                    json={"statut": "resolu", "reponse": "Corrigé dans la version 2.2.1."})
    assert r.status_code == 200, r.text
    t = _statut(admin, tid)
    assert t["statut"] == "resolu" and t["reponse"] == "Corrigé dans la version 2.2.1."
    # l'auteur voit la réponse
    assert next(x for x in client.get("/v1/tickets", headers=auteur).json() if x["id"] == tid)["statut"] == "resolu"


def test_patch_reste_accepte(comptes):
    auteur, admin = comptes
    tid = _ticket(auteur)
    assert client.patch(f"/v1/admin/tickets/{tid}", headers=admin, json={"statut": "en_cours"}).status_code == 200
    assert _statut(admin, tid)["statut"] == "en_cours"


def test_ticket_introuvable_message_clair(comptes):
    _, admin = comptes
    r = client.post("/v1/admin/tickets/999999", headers=admin, json={"statut": "resolu"})
    assert r.status_code == 404
    assert r.json()["detail"] == "Ticket introuvable."


def test_statut_inconnu(comptes):
    auteur, admin = comptes
    tid = _ticket(auteur)
    assert client.post(f"/v1/admin/tickets/{tid}", headers=admin, json={"statut": "clos"}).status_code == 400


def test_reserve_aux_administrateurs(comptes):
    auteur, _ = comptes
    tid = _ticket(auteur)
    assert client.post(f"/v1/admin/tickets/{tid}", headers=auteur, json={"statut": "resolu"}).status_code == 403


def test_supprimer_en_post(comptes):
    auteur, admin = comptes
    tid = _ticket(auteur)
    assert client.post(f"/v1/admin/tickets/{tid}/supprimer", headers=admin).status_code == 200
    assert all(t["id"] != tid for t in client.get("/v1/admin/tickets", headers=admin).json())
