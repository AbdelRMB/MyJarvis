"""Automatisation « quand une transcription se termine » (2.9.0) : la règle reçoit le titre, la durée et le résumé
(ex : « envoie-moi le compte rendu sur Telegram »), après le résumé automatique ou tout de suite sans résumé.

Lancer : python -m pytest tests/test_transcription_finie.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import automatisations, resume_transcription, transcription  # noqa: E402
from wesley.config import CONFIG  # noqa: E402

SESSION = {"id": "t1", "titre": "Réunion budget", "etat": "terminee", "duree": 1830.0,
           "segments": [{"debut": 0, "fin": 3, "locuteur": 1, "texte": "On valide le budget."},
                        {"debut": 4, "fin": 8, "locuteur": 2, "texte": "Paul envoie le devis vendredi."}],
           "resume": {"texte": "Budget validé.", "genre": "reunion", "actions": [{"titre": "Envoyer le devis",
                                                                                   "qui": "Paul", "echeance": "vendredi"}],
                      "nb_phrases": 2}}


def _regles(monkeypatch, *regles):
    monkeypatch.setattr(automatisations, "lister", lambda: list(regles))
    monkeypatch.setattr(automatisations, "_pour_cet_appareil", lambda r: True)
    lances = []
    monkeypatch.setattr(automatisations, "_executer_regle", lambda r, contexte="", resume="": lances.append((r["id"], contexte, resume)))
    return lances


def _regle(rid, contient=""):
    return {"id": rid, "nom": "Compte rendu", "actif": True,
            "declencheur": {"type": "transcription_finie", "contient": contient},
            "action": {"type": "wesley", "consigne": "Envoie-moi le compte rendu sur Telegram."}}


def test_la_regle_recoit_le_resume(monkeypatch):
    monkeypatch.setattr(transcription, "lire", lambda tid: dict(SESSION))
    lances = _regles(monkeypatch, _regle("r1"), _regle("r2", contient="cours"),
                     {**_regle("r3"), "declencheur": {"type": "tache_finie"}})
    automatisations.transcription_finie("t1")
    assert [rid for rid, _, _ in lances] == ["r1"]          # r2 : mot absent du titre ; r3 : autre déclencheur
    _, contexte, resume = lances[0]
    assert "« Réunion budget »" in contexte and "30 min" in contexte and "2 personne(s)" in contexte
    assert "Budget validé." in contexte and "Envoyer le devis (Paul)" in contexte
    assert resume == "Transcription terminée : Réunion budget"


def test_rien_pour_une_transcription_non_terminee(monkeypatch):
    monkeypatch.setattr(transcription, "lire", lambda tid: {**SESSION, "etat": "en_cours"})
    lances = _regles(monkeypatch, _regle("r1"))
    automatisations.transcription_finie("t1")
    assert lances == []


def test_sans_resume_automatique_la_regle_part_tout_de_suite(monkeypatch):
    monkeypatch.setitem(CONFIG, "transcription_resume_auto", False)
    monkeypatch.setattr(transcription, "lire", lambda tid: {**SESSION, "resume": {}})
    appels = []
    monkeypatch.setattr(automatisations, "transcription_finie", appels.append)
    resume_transcription.au_terme("t1")
    assert appels == ["t1"]
