"""Tâches et transcriptions visibles sur tous les appareils (wesley/partage.py).

Un élément reste à l'appareil qui l'a créé : depuis un autre appareil, « Reprendre », « Arrêter »… lui sont
demandés par un ordre ; s'il ne peut pas, la raison remonte à l'utilisateur.

Lancer : python -m pytest tests/test_partage.py -q   (pytest + cryptography)
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("cryptography")

from wesley import appareils, partage, taches  # noqa: E402

CLE = os.urandom(32)


class FauxCompte:
    """Remplace wesley.compte : connecté, clé du coffre connue, appels au serveur enregistrés."""
    class ErreurCompte(Exception):
        pass

    def __init__(self, serveur=None):
        self.appels = []
        self.serveur = serveur or []

    def connecte(self):
        return True

    def _cle_coffre(self):
        return CLE

    def _appel(self, methode, chemin, **kw):
        self.appels.append((methode, chemin, kw.get("json")))
        if methode == "GET" and chemin == "/v1/partages":
            return self.serveur
        if methode == "GET" and chemin.startswith("/v1/partages/"):
            genre, eid = chemin.split("/")[3:5]
            x = next(x for x in self.serveur if x["genre"] == genre and x["id"] == eid)
            return x
        return {"ok": True}


@pytest.fixture
def compte(monkeypatch, tmp_path):
    c = FauxCompte()
    monkeypatch.setattr(partage, "_compte", lambda: c)
    monkeypatch.setattr(partage, "RACINE", tmp_path)
    monkeypatch.setattr(taches, "DOSSIER", tmp_path / "taches")
    monkeypatch.setattr(taches, "demarrer", lambda tid: None)   # pas de vrai Claude Code dans les tests
    monkeypatch.setattr(partage, "_sales", {})
    monkeypatch.setattr(partage, "_lancer_fil", lambda: None)
    partage._cache.update(liste=[], lu=0.0, appareils={}, appareils_lu=0.0)
    partage._contenus.clear()
    return c


def _element(genre, eid, appareil_id, **resume):
    return {"genre": genre, "id": eid, "appareil": appareil_id, "moi": False, "modifie": time.time(),
            "resume": partage.chiffrer({"id": eid, "titre": "Réunion PHP", "appareil_nom": "MacBook", "machine": "autre",
                                        **resume}, CLE)}


def _appareils(monkeypatch, **a):
    monkeypatch.setattr(partage, "_appareils", lambda force=False: a)


def test_chiffrement_aller_retour_et_mauvaise_cle():
    contenu = {"segments": [{"texte": "bonjour " * 2000, "locuteur": 1}], "titre": "é"}
    blob = partage.chiffrer(contenu, CLE)
    assert partage.dechiffrer(blob, CLE) == contenu
    assert len(blob) < len(json.dumps(contenu)) / 5    # compressé avant d'être chiffré
    with pytest.raises(Exception):
        partage.dechiffrer(blob, os.urandom(32))       # une autre clé (autre compte, serveur) ne lit rien


def test_les_elements_des_autres_appareils_sont_listes_avec_leur_appareil(compte, monkeypatch):
    compte.serveur = [_element("transcription", "abcd1234", "mac0000000000001", etat="terminee", debut=1.0),
                      _element("tache", "t1", "mac0000000000001", statut="en_cours"),
                      {**_element("transcription", "moi12345", "pc00000000000001"), "moi": True}]
    _appareils(monkeypatch, mac0000000000001={"id": "mac0000000000001", "nom": "MacBook", "en_ligne": True, "accepte": True})
    monkeypatch.setattr(partage, "ids_locaux", lambda genre: [])
    l = partage.distants("transcription")
    assert [(x["id"], x["appareil"], x["distant"], x["en_ligne"]) for x in l] == [("abcd1234", "MacBook", True, True)]
    assert [x["id"] for x in partage.distants("tache")] == ["t1"]


def test_reprendre_sur_un_appareil_eteint_dit_pourquoi(compte, monkeypatch):
    compte.serveur = [_element("transcription", "abcd1234", "mac0000000000001")]
    _appareils(monkeypatch, mac0000000000001={"id": "mac0000000000001", "nom": "MacBook", "en_ligne": False, "accepte": True})
    envoye = []
    monkeypatch.setattr(appareils, "envoyer", lambda *a, **k: envoye.append(a))
    partage.rafraichir()
    with pytest.raises(ValueError) as e:
        partage.agir("transcription", "abcd1234", "reprendre")
    assert "Impossible de reprendre sur MacBook" in str(e.value) and "hors ligne" in str(e.value)
    assert not envoye    # rien n'est envoyé à un appareil éteint


def test_appareil_deconnecte_ou_qui_refuse(compte, monkeypatch):
    compte.serveur = [_element("tache", "t1", "mac0000000000001")]
    _appareils(monkeypatch)
    partage.rafraichir()
    with pytest.raises(ValueError, match="n'est plus connecté à ton compte"):
        partage.agir("tache", "t1", "reprendre")
    _appareils(monkeypatch, mac0000000000001={"id": "mac0000000000001", "nom": "MacBook", "en_ligne": True, "accepte": False})
    with pytest.raises(ValueError, match="refuse les ordres"):
        partage.agir("tache", "t1", "reprendre")


def test_l_appareil_d_origine_relance_ou_explique_son_refus(compte, monkeypatch):
    compte.serveur = [_element("transcription", "abcd1234", "mac0000000000001")]
    _appareils(monkeypatch, mac0000000000001={"id": "mac0000000000001", "nom": "MacBook", "en_ligne": True, "accepte": True})
    partage.rafraichir()
    ordres = []

    def envoyer(cible, contenu, delai=600):
        ordres.append((cible, contenu))
        return {"ok": True, "resultat": "Transcription « Réunion PHP » reprise sur MacBook (le micro).", "appareil": "MacBook"}
    monkeypatch.setattr(appareils, "envoyer", envoyer)
    assert "reprise sur MacBook" in partage.agir("transcription", "abcd1234", "reprendre")
    cible, contenu = ordres[0]
    assert cible == "mac0000000000001" and contenu["type"] == "partage" and contenu["action"] == "reprendre"
    assert "Réunion PHP" in contenu["texte"]   # ce que l'autre appareil affiche s'il demande confirmation

    monkeypatch.setattr(appareils, "envoyer", lambda *a, **k: {"ok": False, "appareil": "MacBook",
                                                              "resultat": "Erreur sur MacBook : Une transcription est déjà en cours : arrête-la d'abord."})
    with pytest.raises(ValueError) as e:
        partage.agir("transcription", "abcd1234", "reprendre")
    assert "MacBook n'a pas pu reprendre" in str(e.value) and "déjà en cours" in str(e.value)

    def sans_reponse(*a, **k):
        raise ValueError("MacBook n'a pas répondu (hors ligne ?).")
    monkeypatch.setattr(appareils, "envoyer", sans_reponse)
    with pytest.raises(ValueError, match="Impossible de reprendre sur MacBook : MacBook n'a pas répondu"):
        partage.agir("transcription", "abcd1234", "reprendre")


def _tache(statut="arretee", tid="t1"):
    t = {"id": tid, "titre": "Corriger le bug", "consigne": "x", "projet": "/p", "outil": "claude_code", "statut": statut,
         "cree": time.time(), "etape": 3, "journal": [], "ajouts": []}
    taches.DOSSIER.mkdir(parents=True, exist_ok=True)
    taches._fichier(tid).write_text(json.dumps(t), encoding="utf-8")
    return t


def test_executer_sur_l_appareil_d_origine_tache(compte):
    _tache("interrompue")
    assert "reprise" in partage.executer({"genre": "tache", "id": "t1", "action": "reprendre"})
    assert taches.lire("t1")["statut"] == "en_cours"
    partage.executer({"genre": "tache", "id": "t1", "action": "arreter"})
    assert taches.lire("t1")["statut"] == "arretee"
    with pytest.raises(ValueError, match="n'existe plus"):
        partage.executer({"genre": "tache", "id": "inconnue", "action": "reprendre"})


def test_executer_transcription_qui_n_est_pas_en_cours(compte, monkeypatch, tmp_path):
    from wesley import transcription
    monkeypatch.setattr(transcription, "DOSSIER_DONNEES", tmp_path / "tr")
    (tmp_path / "tr").mkdir()
    (tmp_path / "tr" / "abcd1234.json").write_text(json.dumps({"id": "abcd1234", "titre": "Réunion", "segments": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="pas en cours"):
        partage.executer({"genre": "transcription", "id": "abcd1234", "action": "arreter"})
    with pytest.raises(ValueError, match="n'existe plus"):
        partage.executer({"genre": "transcription", "id": "zzzz9999", "action": "reprendre"})


def test_publication_et_suppression(compte):
    t = _tache()
    partage.publier("tache", "t1")
    methode, chemin, corps = compte.appels[-1]
    assert (methode, chemin) == ("PUT", "/v1/partages/tache/t1")
    resume, contenu = partage.dechiffrer(corps["resume"], CLE), partage.dechiffrer(corps["contenu"], CLE)
    assert resume["titre"] == t["titre"] and resume["appareil_nom"] and resume["machine"] == partage.identifiant_machine()
    assert contenu["consigne"] == "x"
    taches._fichier("t1").unlink()
    partage.publier("tache", "t1")
    assert compte.appels[-1][:2] == ("POST", "/v1/partages/tache/t1/supprimer")


def test_reconcilier_publie_le_manquant_et_retire_le_supprime(compte, monkeypatch):
    _tache(tid="t1")
    compte.serveur = [{**_element("tache", "vieille", "pc"), "moi": True}]   # supprimée ici pendant que hors ligne
    monkeypatch.setattr(partage, "ids_locaux", lambda genre: ["t1"] if genre == "tache" else [])
    partage.reconcilier()
    assert set(partage._sales) == {("tache", "t1"), ("tache", "vieille")}


def test_un_changement_pendant_l_envoi_n_est_pas_perdu(compte, monkeypatch):
    """La fin d'une transcription signalée pendant que la version précédente part doit repartir ensuite."""
    _tache()
    appels = []

    def publier(genre, eid):
        appels.append(eid)
        if len(appels) == 1:
            partage._sales[(genre, eid)] = time.time()   # nouveau changement signalé pendant l'envoi
    monkeypatch.setattr(partage, "publier", publier)
    partage._sales[("tache", "t1")] = 0
    dormir = iter([None, None, StopIteration])

    def sommeil(_):
        x = next(dormir)
        if x is StopIteration:
            raise StopIteration
    monkeypatch.setattr(partage.time, "sleep", sommeil)
    with pytest.raises(StopIteration):
        partage._boucle()
    assert appels == ["t1", "t1"]
