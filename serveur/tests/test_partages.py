"""Partages : les tâches et transcriptions d'un appareil sont visibles (chiffrées) sur tous les appareils du compte.

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

from fastapi.testclient import TestClient  # noqa: E402

import app as serveur  # noqa: E402

client = TestClient(serveur.app)


def _session(uid: int) -> dict:
    jeton = secrets.token_urlsafe(24)
    with serveur.db() as c:
        c.execute("INSERT INTO sessions (jeton_hash, utilisateur, appareil, cree, vu) VALUES (?, ?, '', ?, ?)",
                  (serveur._empreinte(jeton), uid, time.time(), time.time()))
    return {"Authorization": f"Bearer {jeton}", "X-Wesley-Appli": "cle-test", "User-Agent": "Wesley"}


def _utilisateur() -> int:
    with serveur.db() as c:
        return c.execute("INSERT INTO utilisateurs (email, prenom, auth_sel, auth_hash, cree) VALUES (?, ?, ?, ?, ?)",
                         (f"{secrets.token_hex(6)}@test.fr", "Test", b"s", b"h", time.time())).lastrowid


def test_un_element_publie_par_le_pc_est_visible_sur_le_mac():
    uid = _utilisateur()
    pc, mac = _session(uid), _session(uid)
    r = client.put("/v1/partages/transcription/ab12cd34", headers=pc, json={"resume": "R1", "contenu": "C1"})
    assert r.status_code == 200, r.text
    vu_du_mac = client.get("/v1/partages", headers=mac).json()
    assert [(x["genre"], x["id"], x["resume"], x["moi"]) for x in vu_du_mac] == [("transcription", "ab12cd34", "R1", False)]
    assert "contenu" not in vu_du_mac[0]   # la liste reste légère : le contenu se lit à la demande
    assert client.get("/v1/partages", headers=pc).json()[0]["moi"] is True
    d = client.get("/v1/partages/transcription/ab12cd34", headers=mac).json()
    assert d["contenu"] == "C1" and d["appareil"] == vu_du_mac[0]["appareil"]


def test_les_autres_comptes_ne_voient_rien():
    a, b = _session(_utilisateur()), _session(_utilisateur())
    client.put("/v1/partages/tache/t1", headers=a, json={"resume": "R", "contenu": "C"})
    assert client.get("/v1/partages", headers=b).json() == []
    assert client.get("/v1/partages/tache/t1", headers=b).status_code == 404


def test_suppression_et_filtre_par_genre():
    uid = _utilisateur()
    h = _session(uid)
    client.put("/v1/partages/tache/t1", headers=h, json={"resume": "R", "contenu": "C"})
    client.put("/v1/partages/transcription/s1", headers=h, json={"resume": "R", "contenu": "C"})
    assert [x["id"] for x in client.get("/v1/partages?genre=tache", headers=h).json()] == ["t1"]
    assert client.post("/v1/partages/tache/t1/supprimer", headers=h).json() == {"ok": True}
    assert [x["id"] for x in client.get("/v1/partages", headers=h).json()] == ["s1"]
    assert client.get("/v1/partages/tache/t1", headers=h).status_code == 404
    # republier après suppression le fait revenir
    client.put("/v1/partages/tache/t1", headers=h, json={"resume": "R2", "contenu": "C2"})
    assert client.get("/v1/partages/tache/t1", headers=h).json()["resume"] == "R2"


def test_genre_ou_identifiant_invalide():
    h = _session(_utilisateur())
    assert client.put("/v1/partages/fichier/x", headers=h, json={"resume": "R"}).status_code == 404
    assert client.put("/v1/partages/tache/..%2Fx", headers=h, json={"resume": "R"}).status_code == 404


def test_attendre_signale_un_partage_modifie_ou_supprime():
    uid = _utilisateur()
    pc, mac = _session(uid), _session(uid)
    revision = client.get("/v1/attendre?depuis=0", headers=mac).json()["revision"]
    client.put("/v1/partages/tache/t9", headers=pc, json={"resume": "R", "contenu": "C"})
    r = client.get(f"/v1/attendre?depuis={revision}&partages=0", headers=mac).json()
    assert r["partages"] > 0 and r["change"] is False   # pas de synchro complète de la mémoire pour un partage
    vu = r["partages"]
    time.sleep(0.01)
    client.post("/v1/partages/tache/t9/supprimer", headers=pc)
    r2 = client.get(f"/v1/attendre?depuis={revision}&partages={vu}", headers=mac).json()
    assert r2["partages"] > vu
    # anciennes versions : sans le paramètre, rien ne change pour elles
    assert client.get("/v1/attendre?depuis=0", headers=mac).json()["partages"] == -1


def test_republier_depuis_une_nouvelle_session_change_le_proprietaire():
    """Reconnexion de l'appareil (nouvelle session) : ses éléments le suivent, les ordres iront au bon endroit."""
    uid = _utilisateur()
    ancienne, nouvelle, mac = _session(uid), _session(uid), _session(uid)
    client.put("/v1/partages/tache/t5", headers=ancienne, json={"resume": "R", "contenu": "C"})
    avant = client.get("/v1/partages", headers=mac).json()[0]["appareil"]
    client.put("/v1/partages/tache/t5", headers=nouvelle, json={"resume": "R", "contenu": "C"})
    apres = client.get("/v1/partages", headers=mac).json()[0]["appareil"]
    assert avant != apres and client.get("/v1/partages", headers=nouvelle).json()[0]["moi"] is True
