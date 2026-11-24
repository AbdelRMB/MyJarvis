"""« Annule ce que tu viens de faire » (wesley/annulation.py) et « ce que je regarde » (wesley/contexte.py).

Lancer : python -m pytest tests/test_annulation_et_contexte.py -q
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import annulation, contexte  # noqa: E402


@pytest.fixture
def fichiers(tmp_path, monkeypatch):
    monkeypatch.setattr(annulation, "DOSSIER", tmp_path / "annulation")
    monkeypatch.setattr(annulation, "JOURNAL", tmp_path / "annulation" / "journal.json")
    pytest.importorskip("pyautogui")   # les outils de fichiers importent les outils du système
    from wesley.outils import fichiers as f
    return tmp_path, f


def test_annuler_toute_la_derniere_demande(fichiers):
    d, f = fichiers
    (d / "notes.txt").write_text("version 1", encoding="utf-8")
    (d / "a_ranger.pdf").write_bytes(b"pdf")
    (d / "vieux.txt").write_text("à garder", encoding="utf-8")
    annulation.nouvelle_demande("range mes fichiers")
    f.ecrire_fichier(str(d / "notes.txt"), "version 2")
    f.ecrire_fichier(str(d / "nouveau.txt"), "créé par Wesley")
    f.creer_dossier(str(d / "Factures"))
    f.deplacer(str(d / "a_ranger.pdf"), str(d / "Factures"))
    f.supprimer(str(d / "vieux.txt"))
    assert not (d / "vieux.txt").exists() and (d / "Factures" / "a_ranger.pdf").exists()
    res = f.annuler()
    assert (d / "notes.txt").read_text(encoding="utf-8") == "version 1"
    assert not (d / "nouveau.txt").exists()
    assert (d / "a_ranger.pdf").exists() and not (d / "Factures").exists()
    assert (d / "vieux.txt").read_text(encoding="utf-8") == "à garder"
    assert "Restauré" in res and "Remis comme avant" in res
    assert "Rien à annuler" in f.annuler()


def test_seulement_la_derniere_demande(fichiers):
    d, f = fichiers
    annulation.nouvelle_demande("1re")
    f.ecrire_fichier(str(d / "un.txt"), "1")
    annulation.nouvelle_demande("2e")
    f.ecrire_fichier(str(d / "deux.txt"), "2")
    f.annuler()
    assert (d / "un.txt").exists() and not (d / "deux.txt").exists()


def test_ne_jamais_ecraser_ce_qui_est_revenu(fichiers):
    d, f = fichiers
    (d / "a.txt").write_text("x", encoding="utf-8")
    annulation.nouvelle_demande("supprime a")
    f.supprimer(str(d / "a.txt"))
    (d / "a.txt").write_text("nouveau, fait par l'utilisateur", encoding="utf-8")
    assert "je ne l'écrase pas" in f.annuler()
    assert (d / "a.txt").read_text(encoding="utf-8") == "nouveau, fait par l'utilisateur"


def test_menage_apres_14_jours(fichiers, monkeypatch):
    d, f = fichiers
    (d / "b.txt").write_text("x", encoding="utf-8")
    annulation.nouvelle_demande("modifie b")
    f.ecrire_fichier(str(d / "b.txt"), "y")
    j = annulation._lire()
    j[0]["ts"] = time.time() - 15 * 86400
    annulation._ecrire(j)
    annulation.menage()
    assert annulation._lire() == [] and not Path(j[0]["copie"]).exists()


# ---------- ce que je regarde ----------
def test_copier_la_selection_sans_perdre_le_presse_papier():
    pp = {"v": "ancien contenu"}
    sel = contexte.copier_selection(copier=lambda: pp.update(v="texte sélectionné"),
                                    lire=lambda: pp["v"], ecrire=lambda x: pp.update(v=x))
    assert sel == "texte sélectionné" and pp["v"] == "ancien contenu"
    rien = contexte.copier_selection(copier=lambda: None, lire=lambda: pp["v"], ecrire=lambda x: pp.update(v=x))
    assert rien == "" and pp["v"] == "ancien contenu"   # rien de sélectionné


def test_consignes_du_bandeau():
    c = contexte.consigne("corriger", "Je voudrait un rdv", "Gmail - Chrome")
    assert c.startswith("Corrige") and "« Je voudrait un rdv »" in c and "Gmail - Chrome" in c
    assert "regarder_ecran" in contexte.consigne("ecran", "", "Excel")
    assert contexte.consigne("", "un texte", "", "fais-en un tweet").startswith("fais-en un tweet")
