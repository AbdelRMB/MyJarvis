"""Résumé d'une transcription (wesley/resume_transcription.py) : cours, réunion, discussion… avec un cerveau simulé.

Lancer : python -m pytest tests/test_resume_transcription.py -q
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import afaire, resume_transcription as rt, transcription as tr  # noqa: E402
from wesley.config import CONFIG  # noqa: E402

REPONSE_COURS = """Cours d'introduction à la programmation objet en PHP.

### Notions
- **Classe** : modèle d'objet [00:12]
- **$this** : l'objet courant [03:40]

### Devoirs
- Exercices 3 et 4 pour lundi

```json
{"genre": "cours", "titre": "PHP objet", "actions": [{"titre": "Faire les exercices 3 et 4", "qui": "élèves", "echeance": "2026-11-30"}]}
```"""


def _session(n=12, tid="abcd1234", **extra):
    segs = [{"debut": i * 10.0, "fin": i * 10.0 + 8, "locuteur": 1 + (i % 2), "texte": f"Phrase numéro {i} du cours."}
            for i in range(n)]
    return {"id": tid, "titre": "Cours PHP", "debut": time.time(), "duree": n * 10.0, "source": "micro", "etat": "terminee",
            "segments": segs, "noms": {"1": "Prof"}, **extra}


@pytest.fixture
def dossier(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "DOSSIER_DONNEES", tmp_path / "tr")
    monkeypatch.setitem(CONFIG, "dossier_transcriptions", str(tmp_path / "docs"))
    return tmp_path


def test_analyser_separe_le_resume_et_le_json():
    r = rt.analyser(REPONSE_COURS)
    assert r["genre"] == "cours" and r["titre"] == "PHP objet"
    assert r["texte"].startswith("Cours d'introduction") and "```" not in r["texte"]
    assert r["actions"] == [{"titre": "Faire les exercices 3 et 4", "qui": "élèves", "echeance": "2026-11-30"}]


def test_analyser_tolere_un_modele_qui_oublie_le_json():
    r = rt.analyser("Une discussion entre amis sur les vacances.\n\n- Destination : Lisbonne")
    assert r["genre"] == "autre" and r["actions"] == [] and "Lisbonne" in r["texte"]
    r = rt.analyser('Résumé.\n{"genre": "discussion", "actions": [{"titre": "x", "echeance": "vendredi"}]}')
    assert r["genre"] == "discussion" and r["actions"][0]["echeance"] == ""   # date invalide écartée
    assert rt.analyser('Résumé.\n```json\n{"genre": "inconnu"}\n```')["genre"] == "autre"


def test_morceaux_ne_coupent_jamais_une_ligne():
    texte = "\n".join(f"[00:{i:02d}] Locuteur 1 : " + "mot " * 50 for i in range(60))
    parts = rt.morceaux(texte, taille=2000)
    assert len(parts) > 1 and "\n".join(parts) == texte
    assert all(len(p) <= 2000 + 300 for p in parts)


def test_le_texte_envoye_au_cerveau_garde_les_noms_et_les_heures():
    vus = []
    rt.generer(_session(), completer=lambda p: (vus.append(p), REPONSE_COURS)[1])
    assert len(vus) == 1
    assert "Prof : Phrase numéro 0" in vus[0] and "Locuteur 2 :" in vus[0] and "[00:10]" in vus[0]
    assert "pas forcément une réunion" in vus[0]     # le résumé s'adapte : cours, discussion, appel…


def test_longue_transcription_resumee_par_parties(monkeypatch):
    monkeypatch.setattr(rt, "TAILLE_MORCEAU", 3000)
    appels = []

    def cerveau(p):
        appels.append(p)
        return "notes de la partie" if "Prends des notes" in p else REPONSE_COURS
    r = rt.generer(_session(400), completer=cerveau)
    assert len(appels) > 2 and "NOTES, PARTIE 1" in appels[-1]
    assert r["genre"] == "cours" and r["nb_phrases"] == 400


def test_rien_a_resumer():
    with pytest.raises(ValueError, match="rien à résumer"):
        rt.generer(_session(0), completer=lambda p: "x")
    assert not rt.resumable(_session(2))
    assert rt.resumable(_session(12))


def test_resume_auto_range_le_resume_et_ajoute_les_taches_une_seule_fois(dossier, monkeypatch):
    tr.sauver(_session(), fichier_lisible=False)
    ajoutees = []
    monkeypatch.setattr(afaire, "ajouter", lambda titre, **k: ajoutees.append((titre, k)) or {})
    r = rt.resumer("abcd1234", auto=True, completer=lambda p: REPONSE_COURS)
    assert r["afaire_ajoutees"] == 1
    assert ajoutees[0][0] == "Faire les exercices 3 et 4" and ajoutees[0][1]["echeance"] == "2026-11-30"
    s = tr.lire("abcd1234")
    assert s["resume"]["genre"] == "cours" and not s["resume"].get("en_cours")
    assert tr.resume(s)["a_resume"] and tr.resume(s)["genre"] == "cours"
    # refaire le résumé n'ajoute pas les tâches une deuxième fois
    rt.resumer("abcd1234", auto=True, completer=lambda p: REPONSE_COURS)
    assert len(ajoutees) == 1


def test_reglage_taches_desactive(dossier, monkeypatch):
    tr.sauver(_session(), fichier_lisible=False)
    monkeypatch.setitem(CONFIG, "transcription_actions_afaire", False)
    monkeypatch.setattr(afaire, "ajouter", lambda *a, **k: pytest.fail("ne doit rien ajouter"))
    assert not rt.resumer("abcd1234", auto=True, completer=lambda p: REPONSE_COURS).get("afaire_ajoutees")


def test_erreur_du_cerveau_gardee_et_ancien_resume_conserve(dossier):
    tr.sauver(_session(resume={"texte": "Ancien résumé", "genre": "cours"}), fichier_lisible=False)

    def panne(p):
        raise RuntimeError("clé API invalide")
    with pytest.raises(RuntimeError):
        rt.resumer("abcd1234", completer=panne)
    r = tr.lire("abcd1234")["resume"]
    assert r["texte"] == "Ancien résumé" and "clé API invalide" in r["erreur"] and not r["en_cours"]


def test_pas_de_resume_pendant_l_enregistrement(dossier):
    tr.sauver(_session(etat="en_cours"), fichier_lisible=False)
    with pytest.raises(ValueError, match="Attends la fin"):
        rt.resumer("abcd1234", completer=lambda p: REPONSE_COURS)


def test_export_avec_le_resume_en_tete():
    s = _session(resume=rt.analyser(REPONSE_COURS))
    md = tr.exporter(s, "md")
    assert md.index("## Résumé (cours)") < md.index("## Transcription") < md.index("Phrase numéro 0")
    assert "- [ ] Faire les exercices 3 et 4 (élèves) — pour le 2026-11-30" in md
    txt = tr.exporter(s, "txt")
    assert "Résumé (cours)" in txt and "##" not in txt
    assert "Résumé" not in tr.exporter(_session(), "md")   # sans résumé : export inchangé


def test_au_terme_respecte_le_reglage(dossier, monkeypatch):
    tr.sauver(_session(), fichier_lisible=False)
    lances = []
    monkeypatch.setattr(rt, "resumer", lambda tid, auto=False: lances.append(tid))
    monkeypatch.setitem(CONFIG, "transcription_resume_auto", False)
    rt.au_terme("abcd1234")
    monkeypatch.setitem(CONFIG, "transcription_resume_auto", True)
    tr.sauver(_session(n=2, tid="court123"), fichier_lisible=False)
    rt.au_terme("court123")            # trop court : pas de résumé
    time.sleep(0.2)
    assert lances == []
    rt.au_terme("abcd1234")
    for _ in range(50):
        if lances:
            break
        time.sleep(0.02)
    assert lances == ["abcd1234"]
