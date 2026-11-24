"""Wesley lit les documents de l'utilisateur (wesley/documents.py) : PDF, Word, textes, découpés et retrouvés.

Lancer : python -m pytest tests/test_documents.py -q   (pypdf pour les PDF)
"""
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import documents, semantique  # noqa: E402


def _pdf(chemin: Path, pages: list[str]):
    """PDF minimal écrit à la main (une police standard, une ligne de texte par page)."""
    objets = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    for i, texte in enumerate(pages):
        n_page, n_contenu = 4 + 2 * i, 5 + 2 * i
        kids.append(f"{n_page} 0 R")
        flux = f"BT /F1 12 Tf 50 750 Td ({texte}) Tj ET"
        objets += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {n_contenu} 0 R "
                   f"/Resources << /Font << /F1 3 0 R >> >> >>",
                   f"<< /Length {len(flux)} >>\nstream\n{flux}\nendstream"]
    objets[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    objets.insert(2, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    sortie, positions = b"%PDF-1.4\n", []
    for i, o in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(sortie)
    sortie += f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode()
    sortie += "".join(f"{p:010d} 00000 n \n" for p in positions).encode()
    sortie += f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    chemin.write_bytes(sortie)


def _docx(chemin: Path, paragraphes: list[str]):
    corps = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphes)
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body>{corps}</w:body></w:document>')


def test_decouper_garde_la_page_et_ne_coupe_pas_les_phrases():
    texte = " ".join(f"Phrase numero {i} du contrat de location." for i in range(80))
    passages = documents.decouper([(3, texte)], taille=300)
    assert len(passages) > 5 and all(p["page"] == 3 for p in passages)
    assert all(p["texte"].endswith(".") for p in passages)
    assert all(len(p["texte"]) <= 450 for p in passages)


def test_lire_pdf_word_texte(tmp_path):
    pytest.importorskip("pypdf")
    _pdf(tmp_path / "bail.pdf", ["Bail de location", "Le preavis est de trois mois pour le locataire"])
    pages = documents.lire(tmp_path / "bail.pdf")
    assert [p for p, _ in pages] == [1, 2] and "preavis" in pages[1][1]
    _docx(tmp_path / "devis.docx", ["Devis plombier", "Total : 480 euros TTC"])
    assert "480 euros" in documents.lire(tmp_path / "devis.docx")[0][1]
    (tmp_path / "notes.md").write_text("# Notes\nLe code du portail est 1234.", encoding="utf-8")
    assert "portail" in documents.lire(tmp_path / "notes.md")[0][1]


def test_indexer_chercher_et_mettre_a_jour(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    monkeypatch.setattr(documents, "INDEX", tmp_path / "index.json")
    monkeypatch.setattr(semantique, "disponible", lambda: False)   # recherche par mots (sans le modèle)
    docs = tmp_path / "docs"
    (docs / "admin").mkdir(parents=True)
    _pdf(docs / "admin" / "bail.pdf", ["Bail de location", "Le preavis est de trois mois pour le locataire"])
    _docx(docs / "devis.docx", ["Devis plombier", "Total : 480 euros TTC"])
    (docs / "photo.jpg").write_bytes(b"x")
    r = documents.indexer([str(docs)])
    assert r["fichiers"] == 2
    res = documents.chercher("preavis locataire")
    assert res and res[0]["fichier"].endswith("bail.pdf") and res[0]["page"] == 2
    # fichier supprimé : oublié ; fichier non modifié : pas relu
    (docs / "devis.docx").unlink()
    lus = []
    vrai_lire = documents.lire
    monkeypatch.setattr(documents, "lire", lambda p: lus.append(p) or vrai_lire(p))
    assert documents.indexer([str(docs)])["fichiers"] == 1 and lus == []


def test_fichier_illisible_ne_bloque_pas(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "INDEX", tmp_path / "index.json")
    monkeypatch.setattr(semantique, "disponible", lambda: False)
    (tmp_path / "casse.docx").write_bytes(b"pas un zip")
    (tmp_path / "ok.txt").write_text("Le wifi s'appelle Maison", encoding="utf-8")
    assert documents.indexer([str(tmp_path)])["fichiers"] == 2
    monkeypatch.setattr(documents, "dossiers", lambda: [str(tmp_path)])
    assert any(x.endswith("casse.docx") for x in documents.etat()["illisibles"])
    assert documents.chercher("wifi")[0]["fichier"].endswith("ok.txt")


@pytest.mark.skipif(not semantique.utilisable(), reason="modèle de sens absent")
def test_par_le_sens(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "INDEX", tmp_path / "index.json")
    monkeypatch.setattr(semantique, "DOSSIER_INDEX", tmp_path)
    semantique._index.clear()
    (tmp_path / "bail.txt").write_text("Le locataire peut quitter le logement avec un délai de trois mois.", encoding="utf-8")
    (tmp_path / "recette.txt").write_text("Faire cuire les pâtes dix minutes dans l'eau salée.", encoding="utf-8")
    documents.indexer([str(tmp_path)])
    assert documents.chercher("combien de temps avant de partir de mon appartement ?")[0]["fichier"].endswith("bail.txt")
