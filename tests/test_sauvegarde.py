"""Sauvegarde complète et restauration (wesley/sauvegarde.py) : fichier chiffré, mot de passe obligatoire,
restauration qui ajoute ce qui manque sans rien écraser.

Lancer : python -m pytest tests/test_sauvegarde.py -q   (cryptography)
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("cryptography")

from wesley import afaire, automatisations, compte, config, memoire, sauvegarde, transcription  # noqa: E402


def _installer(base: Path, monkeypatch):
    """Un « appareil » complet dans base : dossier du compte, mémoire, transcriptions."""
    partage = base / "compte"
    (partage / "memoire" / "historique").mkdir(parents=True)
    monkeypatch.setattr(config, "PARTAGE", partage)
    monkeypatch.setattr(config, "PROFIL", partage / "profil.json")
    monkeypatch.setattr(memoire, "DOSSIER", partage / "memoire")
    monkeypatch.setattr(memoire, "FAITS", partage / "memoire" / "faits.json")
    monkeypatch.setattr(memoire, "HIST", partage / "memoire" / "historique")
    monkeypatch.setattr(transcription, "DOSSIER_DONNEES", base / "transcriptions")
    return partage


@pytest.fixture(autouse=True)
def _hors_ligne(monkeypatch):
    monkeypatch.setattr(compte, "connecte", lambda: False)
    monkeypatch.setattr(memoire, "_envoyer", lambda *a, **k: None, raising=False)


def test_sauvegarder_puis_restaurer_sur_un_autre_appareil(tmp_path, monkeypatch):
    # appareil A : des souvenirs, une conversation, une tâche, une automatisation, une transcription
    a = _installer(tmp_path / "A", monkeypatch)
    memoire.ajouter("La Clio est au garage", "general")
    memoire.ajouter("Prénom : Alice", "identite")
    (a / "memoire" / "historique" / "2026-11-20__PC-A.md").write_text("[10:00] Toi: bonjour Wesley\n", encoding="utf-8")
    afaire.ajouter("Appeler le garage")
    (a / "automatisations.json").write_text(json.dumps([{"id": "r1", "nom": "Matin", "actif": True}]), encoding="utf-8")
    (a / "profil.json").write_text(json.dumps({"prenom": "Alice"}), encoding="utf-8")
    (tmp_path / "A" / "transcriptions").mkdir()
    (tmp_path / "A" / "transcriptions" / "t1.json").write_text(json.dumps({"id": "t1", "titre": "Cours"}), encoding="utf-8")
    (tmp_path / "A" / "transcriptions" / "t1.npz").write_bytes(b"empreintes")

    r = sauvegarde.creer("motdepasse-solide", dossier=tmp_path)
    fichier = Path(r["fichier"])
    assert fichier.suffix == ".wesley" and r["contenu"] == {"souvenirs": 2, "jours": 1, "transcriptions": 1}
    blob = fichier.read_bytes()
    assert b"Clio" not in blob and b"Cours" not in blob   # chiffré

    # appareil B : déjà un souvenir (en commun) et une tâche à lui
    b = _installer(tmp_path / "B", monkeypatch)
    memoire.ajouter("La Clio est au garage", "general")
    afaire.ajouter("Acheter du pain")
    res = sauvegarde.restaurer(blob, "motdepasse-solide")
    assert res["repris"] == {"souvenirs": 1, "historique": 1, "afaire": 1, "automatisations": 1, "sites": 0,
                             "profil": True, "transcriptions": 1}
    assert res["manifeste"]["contenu"]["souvenirs"] == 2
    assert sorted(x["fait"] for x in memoire._charger()) == ["La Clio est au garage", "Prénom : Alice"]
    assert sorted(t["titre"] for t in afaire.lister()) == ["Acheter du pain", "Appeler le garage"]
    assert [x["id"] for x in automatisations.lister()] == ["r1"]
    assert (b / "memoire" / "historique" / "2026-11-20__PC-A.md").read_text(encoding="utf-8") == "[10:00] Toi: bonjour Wesley\n"
    assert (tmp_path / "B" / "transcriptions" / "t1.npz").exists()

    # restaurer une 2e fois : rien de nouveau, rien en double
    res = sauvegarde.restaurer(blob, "motdepasse-solide")
    assert res["repris"] == {"souvenirs": 0, "historique": 0, "afaire": 0, "automatisations": 0, "sites": 0,
                             "profil": False, "transcriptions": 0}
    assert len(afaire.lister()) == 2 and len(memoire._charger()) == 2


def test_mot_de_passe_obligatoire_et_verifie(tmp_path, monkeypatch):
    _installer(tmp_path / "A", monkeypatch)
    with pytest.raises(sauvegarde.ErreurSauvegarde, match="au moins"):
        sauvegarde.creer("court", dossier=tmp_path)
    blob = Path(sauvegarde.creer("motdepasse-solide", dossier=tmp_path)["fichier"]).read_bytes()
    with pytest.raises(sauvegarde.ErreurSauvegarde, match="Mot de passe incorrect"):
        sauvegarde.restaurer(blob, "mauvais-mot-de-passe")
    with pytest.raises(sauvegarde.ErreurSauvegarde, match="pas une sauvegarde"):
        sauvegarde.restaurer(b"PK\x03\x04 un zip quelconque", "motdepasse-solide")


def test_archive_piegee_refusee(tmp_path, monkeypatch):
    import io
    import zipfile
    _installer(tmp_path / "A", monkeypatch)
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("manifeste.json", "{}")
        z.writestr("../../hors-du-dossier.txt", "piège")
    with pytest.raises(sauvegarde.ErreurSauvegarde, match="invalide"):
        sauvegarde.restaurer(sauvegarde.chiffrer(tampon.getvalue(), "motdepasse-solide"), "motdepasse-solide")
