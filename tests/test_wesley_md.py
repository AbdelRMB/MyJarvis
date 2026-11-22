"""WESLEY.md : instructions propres à chaque projet (lecture, création, journal, tâches de code).

Lancer : python -m pytest tests -q   (seul pytest est nécessaire)
"""
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import wesley_md  # noqa: E402


def _git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


@pytest.fixture
def depot(tmp_path):
    d = tmp_path / "monprojet"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "test@example.com")
    _git(d, "config", "user.name", "Test")
    (d / "package.json").write_text(json.dumps({"name": "monprojet", "scripts": {"dev": "vite", "test": "vitest"},
                                                "dependencies": {"react": "19"}}), encoding="utf-8")
    (d / "README.md").write_text("# Mon projet\n\nUne appli pour suivre les courses.\n", encoding="utf-8")
    (d / "src" / "api").mkdir(parents=True)
    (d / "src" / "api" / "index.ts").write_text("export {}\n", encoding="utf-8")
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "-m", "init")
    wesley_md._lus.clear()
    return d


def test_racine_trouvee_depuis_un_sous_dossier(depot):
    assert wesley_md.racine_projet(depot / "src" / "api") == depot.resolve()
    assert wesley_md.racine_projet(depot / "src" / "api" / "index.ts") == depot.resolve()


def test_sans_wesley_md(depot):
    assert wesley_md.fichiers(depot) == []
    assert wesley_md.lire(depot) == ""
    assert wesley_md.bloc_consigne(depot) == ""
    assert "n'a pas encore de WESLEY.md" in wesley_md.obligation(depot)


def test_racine_puis_sous_dossiers_concernes(depot):
    (depot / "WESLEY.md").write_text("Règle racine : commits en français.", encoding="utf-8")
    (depot / "src" / "api" / "WESLEY.md").write_text("Règle API : pas de console.log.", encoding="utf-8")
    (depot / "docs").mkdir()
    (depot / "docs" / "WESLEY.md").write_text("Règle docs.", encoding="utf-8")
    # depuis la racine : seulement celui de la racine, les autres sont signalés
    assert [f.name for f in wesley_md.fichiers(depot)] == ["WESLEY.md"]
    bloc = wesley_md.bloc_consigne(depot)
    assert "Règle racine" in bloc and "Règle API" not in bloc
    assert "src/api/WESLEY.md" in bloc and "docs/WESLEY.md" in bloc
    assert bloc.startswith("# INSTRUCTIONS DU PROJET (WESLEY.md)")
    # en ciblant src/api : racine puis sous-dossier, dans cet ordre
    texte = wesley_md.lire(depot, depot / "src" / "api")
    assert texte.index("Règle racine") < texte.index("Règle API")
    assert "--- src/api/WESLEY.md ---" in texte
    assert "Tiens à jour le fichier WESLEY.md" in wesley_md.obligation(depot)


def test_contenu_tronque(depot):
    (depot / "WESLEY.md").write_text("x" * 50000, encoding="utf-8")
    assert len(wesley_md.lire(depot, maximum=1000)) < 1200
    assert "tronqué" in wesley_md.lire(depot, maximum=1000)


def test_modele_devine_le_projet(depot):
    m = wesley_md.modele(depot)
    assert m.startswith("# monprojet — instructions pour Wesley")
    assert "Une appli pour suivre les courses." in m
    assert "React" in m and "`npm run dev`" in m and "`npm run test`" in m
    for section in ("## Présentation", "## Commandes utiles", "## Conventions", "## Décisions", "## Journal des changements"):
        assert section in m


def test_creer_ne_remplace_pas_sans_demande(depot):
    f, cree = wesley_md.creer(depot / "src")
    assert cree and f == depot.resolve() / "WESLEY.md"
    f.write_text("Mon contenu", encoding="utf-8")
    _, cree = wesley_md.creer(depot)
    assert not cree and f.read_text(encoding="utf-8") == "Mon contenu"
    _, cree = wesley_md.creer(depot, "Nouveau", remplacer=True)
    assert cree and f.read_text(encoding="utf-8") == "Nouveau\n"


def test_noter_dans_la_bonne_section(depot):
    wesley_md.creer(depot)
    wesley_md.noter(depot, "Ajout de la page Profil", "changement")
    wesley_md.noter(depot, "On garde Zustand pour l'état", "décisions")
    wesley_md.noter(depot, "`npm run lint` avant chaque commit", "commande")
    texte = (depot / "WESLEY.md").read_text(encoding="utf-8")
    journal = texte.split("## Journal des changements")[1]
    assert f"- {date.today():%Y-%m-%d} : Ajout de la page Profil" in journal
    decisions = texte.split("## Décisions")[1].split("## ")[0]
    assert "- On garde Zustand pour l'état" in decisions
    commandes = texte.split("## Commandes utiles")[1].split("## ")[0]
    assert commandes.rstrip().endswith("- `npm run lint` avant chaque commit")


def test_noter_cree_le_fichier_et_la_section(depot):
    (depot / "WESLEY.md").write_text("# Projet\n\nRègles maison.\n", encoding="utf-8")
    wesley_md.noter(depot, "Premier changement")
    texte = (depot / "WESLEY.md").read_text(encoding="utf-8")
    assert texte.startswith("# Projet\n\nRègles maison.\n\n## Journal des changements\n- ")


def test_ajouter_ligne_avant_la_section_suivante():
    texte = "# T\n\n## A\n- a1\n\n## B\n- b1\n"
    assert wesley_md.ajouter_ligne(texte, "A", "- a2") == "# T\n\n## A\n- a1\n- a2\n\n## B\n- b1\n"


def test_rappel_apres_ecriture_une_seule_fois(depot, tmp_path):
    f = depot / "src" / "api" / "index.ts"
    r = wesley_md.rappel_apres_ecriture(f)
    assert "noter_wesley_md" in r and "qui le créera" in r
    assert wesley_md.rappel_apres_ecriture(f) == ""            # déjà rappelé pour ce projet
    isole = tmp_path / "isole" / "notes.txt"
    isole.parent.mkdir()
    isole.write_text("x")
    assert wesley_md.rappel_apres_ecriture(isole) == ""        # pas un projet


def test_rappel_demande_de_lire_le_wesley_md(depot):
    (depot / "WESLEY.md").write_text("Règles", encoding="utf-8")
    assert "pas encore lu" in wesley_md.rappel_apres_ecriture(depot / "src" / "api" / "index.ts")
    wesley_md._lus.clear()
    wesley_md.lire(depot)
    assert "pas encore lu" not in wesley_md.rappel_apres_ecriture(depot / "src" / "api" / "index.ts")


# ---------- tâches de code ----------
@pytest.fixture
def taches(tmp_path, monkeypatch):
    from wesley import taches as module
    monkeypatch.setattr(module, "DOSSIER", tmp_path / "taches")
    monkeypatch.setattr(module, "_diffuser", lambda tid: None)
    return module


def _tache(taches, projet, **kw):
    t = {"id": "abcdef12", "titre": "Ajouter le profil", "consigne": "Ajoute une page Profil", "projet": str(projet),
         "outil": "claude_code", "statut": "en_cours", "cree": time.time() - 5, "etape": 0, "session": "",
         "branche": "", "dossier": "", "ajouts": [], "bilan": "", "journal": [], "ticket": 0, **kw}
    taches._sauver(t)
    return t


def test_consigne_de_tache_transmet_le_wesley_md(depot, taches):
    (depot / "WESLEY.md").write_text("Règle racine : tests obligatoires.", encoding="utf-8")   # pas committé
    (depot / "src" / "api" / "WESLEY.md").write_text("Règle API.", encoding="utf-8")
    t = _tache(taches, depot / "src" / "api")
    taches._preparer(t)
    try:
        assert t["sous_dossier"] == "src/api"
        assert (Path(t["dossier"]) / "WESLEY.md").is_file()          # recopié dans la copie de travail
        msg = taches._premier_message(t)
        assert msg.index("INSTRUCTIONS DU PROJET") < msg.index("Règle racine") < msg.index("Règle API") \
            < msg.index("# DEMANDE DE L'UTILISATEUR") < msg.index("Ajoute une page Profil")
        assert "OBLIGATOIRE : Tiens à jour le fichier WESLEY.md" in msg
        assert t["wesley_md"] == ["WESLEY.md", "src/api/WESLEY.md"]
        # une simple copie ne compte pas comme une mise à jour
        assert not taches._wesley_md_a_jour(t)
        wesley_md.noter(t["dossier"], "Page Profil ajoutée")
        assert taches._wesley_md_a_jour(t)
    finally:
        _git(depot, "worktree", "remove", "--force", t["dossier"])


def test_sans_wesley_md_la_tache_doit_le_creer_et_wesley_complete(depot, taches):
    t = _tache(taches, depot)
    taches._preparer(t)
    try:
        msg = taches._premier_message(t)
        assert "INSTRUCTIONS DU PROJET" not in msg
        assert "n'a pas encore de WESLEY.md : crée-le" in msg
        assert not taches._wesley_md_a_jour(t)
        t["bilan"] = "Page Profil ajoutée et testée."
        taches._finir(t, "terminee")      # l'agent l'a oublié : Wesley le crée et le committe avec le reste
        f = Path(t["dossier"]) / "WESLEY.md"
        assert "Ajouter le profil — Page Profil ajoutée et testée." in f.read_text(encoding="utf-8")
        assert "WESLEY.md" in subprocess.run(["git", "-C", t["dossier"], "show", "--name-only", "HEAD"],
                                             capture_output=True, text=True).stdout
    finally:
        _git(depot, "worktree", "remove", "--force", t["dossier"])


def test_dossier_hors_git(tmp_path, taches):
    d = tmp_path / "script"
    d.mkdir()
    (d / "main.py").write_text("print(1)\n")
    t = _tache(taches, d)
    taches._preparer(t)
    assert t["dossier"] == str(d) and not t["branche"]
    assert not taches._wesley_md_a_jour(t)
    taches._finir(t, "terminee")
    assert (d / "WESLEY.md").is_file()
    assert taches._wesley_md_a_jour(t)
    assert "wesley_md" in taches.resume(t)
