"""Recherche unique (wesley/recherche.py) : toutes les sources en une question, une source en panne n'empêche pas
les autres de répondre.

Lancer : python -m pytest tests/test_recherche_unique.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import afaire, documents, memoire, recherche, recherche_transcriptions, semantique  # noqa: E402


def _sources(monkeypatch, documents_en_panne=False):
    monkeypatch.setattr(semantique, "encoder", lambda *a, **k: None)   # par les mots : même résultat avec ou sans modèle
    monkeypatch.setattr(memoire, "chercher_detail", lambda q, k_faits=6, k_historique=6: {
        "souvenirs": [{"fid": "f1", "fait": "La Clio est au garage", "categorie": "general", "score": 0.9}],
        "historique": [{"jour": "2026-11-20", "texte": "[10:00] Toi: le garage rappelle lundi", "score": 0.8}]})
    monkeypatch.setattr(recherche_transcriptions, "chercher", lambda q, n=20: [
        {"id": "t1", "titre": "Réunion budget", "date": 1764064800.0, "heure": "00:12", "locuteur": "Paul",
         "texte": "le garage coûte 400 euros", "appareil": ""}])

    def docs(q, k=6):
        if documents_en_panne:
            raise RuntimeError("index illisible")
        return [{"fichier": "C:/Docs/facture.pdf", "page": 2, "texte": "Réparation garage : 400 €", "score": 0.85}]
    monkeypatch.setattr(documents, "chercher", docs)
    monkeypatch.setattr(afaire, "lister", lambda: [
        {"id": "a1", "titre": "Appeler le garage", "note": "", "statut": "a_faire", "echeance": "2026-11-30"},
        {"id": "a2", "titre": "Acheter du pain", "note": "", "statut": "a_faire", "echeance": ""}])


def test_toutes_les_sources_en_une_question(monkeypatch):
    _sources(monkeypatch)
    r = recherche.chercher_partout("garage")
    assert r["souvenirs"][0]["fait"] == "La Clio est au garage"
    assert r["historique"][0]["jour"] == "2026-11-20"
    assert r["transcriptions"][0]["id"] == "t1" and r["transcriptions"][0]["locuteur"] == "Paul"
    assert r["documents"][0]["page"] == 2
    assert [t["id"] for t in r["afaire"]] == ["a1"]        # « Acheter du pain » n'a rien à voir
    assert r["erreurs"] == {}
    texte = recherche.en_texte(r, "garage")
    for morceau in ("Souvenirs", "La Clio", "Transcriptions", "Paul", "facture.pdf (page 2)", "Appeler le garage"):
        assert morceau in texte


def test_une_source_en_panne_n_empeche_pas_les_autres(monkeypatch):
    _sources(monkeypatch, documents_en_panne=True)
    r = recherche.chercher_partout("garage")
    assert r["documents"] == [] and "index illisible" in r["erreurs"]["documents"]
    assert r["souvenirs"] and r["transcriptions"] and r["afaire"]


def test_requete_vide_et_rien_trouve():
    r = recherche.chercher_partout("   ")
    assert all(r[s] == [] for s in recherche.SOURCES)
    assert recherche.en_texte(r, "xyz") == "Rien trouvé sur « xyz »."
