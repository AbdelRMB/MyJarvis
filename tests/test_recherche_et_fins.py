"""Recherche dans toutes les transcriptions, notifications de fin et lancement à distance.

Lancer : python -m pytest tests/test_recherche_et_fins.py -q
"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("cryptography")

from wesley import appareils, partage, recherche_transcriptions as rt, transcription as tr  # noqa: E402


def _session(tid, titre, phrases, resume=None):
    segs = [{"debut": i * 40.0, "fin": i * 40.0 + 5, "locuteur": l, "texte": txt} for i, (l, txt) in enumerate(phrases)]
    return {"id": tid, "titre": titre, "debut": time.time(), "duree": 400, "etat": "terminee", "segments": segs,
            "noms": {"1": "Sophie"}, "resume": resume or {}}


def test_mots_sans_accents_ni_mots_vides():
    assert rt.mots("Qu'est-ce qu'on a dit sur le Budget de l'été ?") == ["budget", "ete"]


def test_trouve_le_passage_avec_l_heure_et_la_personne():
    s = _session("r1", "Réunion lundi", [(1, "Bonjour à tous."), (2, "Le budget marketing est dépassé de 20 %."),
                                        (1, "On revoit les budgets vendredi.")])
    res = rt.chercher_dans(s, rt.mots("budget"), "PC")
    assert [(r["locuteur"], r["heure"]) for r in res] == [("Locuteur 2", "00:40"), ("Sophie", "01:20")]   # « budgets » trouvé aussi
    assert rt.chercher_dans(s, rt.mots("budjet"), "PC") == []


def test_au_moins_la_moitie_des_mots_et_bonus_du_titre():
    s = _session("c1", "Cours PHP objet", [(1, "Une interface définit des méthodes."), (1, "Passons aux exercices.")])
    assert len(rt.chercher_dans(s, rt.mots("interface méthodes abstraites"), "")) == 1
    # le sujet n'est que dans le titre : la transcription est quand même proposée
    r = rt.chercher_dans(s, rt.mots("php"), "")
    assert len(r) == 1 and r[0]["heure"] == ""


def test_chercher_partout_local_et_autres_appareils(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "DOSSIER_DONNEES", tmp_path)
    tr.sauver(_session("loc1", "Discussion", [(1, "Les vacances à Lisbonne en juillet.")]), fichier_lisible=False)
    distante = _session("dis1", "Appel", [(1, "Réserver Lisbonne avant mai.")])
    monkeypatch.setattr(partage, "distants", lambda genre: [{"id": "dis1", "appareil": "MacBook"}])
    monkeypatch.setattr(partage, "lire", lambda genre, eid: distante)
    res = rt.chercher("Lisbonne")
    assert {(r["id"], r["appareil"]) for r in res} == {("loc1", partage.MACHINE), ("dis1", "MacBook")}


def _el(genre, eid, **r):
    return {"genre": genre, "resume": {"id": eid, "titre": "T", "appareil_nom": "MacBook", **r}, "appareil_id": "m", "modifie": 0}


def test_fins_seulement_les_changements_d_etat():
    avant = [_el("tache", "t1", statut="en_cours"), _el("transcription", "s1", etat="en_cours"),
             _el("transcription", "s2", etat="terminee", a_resume=False), _el("tache", "t2", statut="terminee")]
    apres = [_el("tache", "t1", statut="terminee", bilan="Bug corrigé"), _el("transcription", "s1", etat="terminee"),
             _el("transcription", "s2", etat="terminee", a_resume=True), _el("tache", "t2", statut="terminee"),
             _el("tache", "t3", statut="terminee")]   # nouvelle et déjà finie : pas de notification
    titres = [t for t, _ in partage.fins(avant, apres)]
    assert titres == ["Tâche terminée sur MacBook", "Transcription terminée sur MacBook", "Résumé prêt : T"]


CLE = os.urandom(32)


class Compte:
    class ErreurCompte(Exception):
        pass

    def connecte(self):
        return True

    def _cle_coffre(self):
        return CLE


def test_lancer_a_distance(monkeypatch):
    monkeypatch.setattr(partage, "_compte", lambda: Compte())
    monkeypatch.setattr(partage, "_appareils", lambda force=False: {
        "mac": {"id": "mac", "nom": "MacBook", "en_ligne": True, "accepte": True},
        "pc2": {"id": "pc2", "nom": "Vieux PC", "en_ligne": False, "accepte": True}})
    envoyes = []

    def envoyer(cible, contenu, delai=600):
        envoyes.append((cible, contenu))
        return {"ok": True, "resultat": "Transcription « Cours » lancée sur MacBook (le micro)."}
    monkeypatch.setattr(appareils, "envoyer", envoyer)
    assert "lancée sur MacBook" in partage.lancer("mac", "transcription", {"source": "micro", "titre": "Cours"})
    assert envoyes[0][1]["action"] == "demarrer" and envoyes[0][1]["id"] == ""
    with pytest.raises(ValueError, match="Impossible de lancer la transcription sur Vieux PC : il est hors ligne"):
        partage.lancer("pc2", "transcription", {})
    with pytest.raises(ValueError, match="n'est plus connecté"):
        partage.lancer("inconnu", "tache", {})
    monkeypatch.setattr(appareils, "envoyer", lambda *a, **k: {"ok": False, "resultat": "Erreur sur MacBook : Une transcription est déjà en cours : arrête-la d'abord."})
    with pytest.raises(ValueError, match="MacBook n'a pas pu lancer la transcription : .*déjà en cours"):
        partage.lancer("mac", "transcription", {})


def test_enregistrement_du_telephone_recu_en_morceaux_puis_transcrit(tmp_path, monkeypatch):
    import base64
    import types
    monkeypatch.setattr(tr, "DOSSIER_DONNEES", tmp_path)
    lances = []
    faux_web = types.SimpleNamespace(_lancer_transcription=lambda f, **k: (lances.append((f, k)), {"titre": k["titre"]})[1])
    monkeypatch.setitem(sys.modules, "wesley.web", faux_web)
    import wesley
    monkeypatch.setattr(wesley, "web", faux_web, raising=False)
    son = os.urandom(10_000)
    morceaux = [son[:4000], son[4000:8000], son[8000:]]
    for i, m in enumerate(morceaux, 1):
        msg = partage.recevoir_audio({"envoi": "ab12cd34ef", "partie": i, "total": 3, "ext": "webm", "titre": "Cours",
                                      "contenu": base64.b64encode(m).decode()})
    assert "le transcrit" in msg and len(lances) == 1
    f, k = lances[0]
    assert f.read_bytes() == son and f.suffix == ".webm" and k["source"] == "fichier" and k["titre"] == "Cours"
    # un morceau du milieu sans le début (Wesley relancé entre-temps) : on demande de renvoyer
    with pytest.raises(ValueError, match="renvoie-le"):
        partage.recevoir_audio({"envoi": "ffff0000aa", "partie": 2, "total": 3, "contenu": ""})
    with pytest.raises(ValueError, match="invalide"):
        partage.recevoir_audio({"envoi": "../../x", "partie": 1, "total": 1, "contenu": ""})
