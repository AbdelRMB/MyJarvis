"""Automatisations avancées (rendez-vous, fichiers, tâches finies, sites, conditions) et habitudes remarquées.

Lancer : python -m pytest tests/test_automatisations_et_habitudes.py -q
"""
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import automatisations as au, consolidation, habitudes, memoire  # noqa: E402
from wesley.config import MACHINE  # noqa: E402


@pytest.fixture
def regles(monkeypatch):
    stock = []
    monkeypatch.setattr(au, "lister", lambda: stock)
    faits = []
    monkeypatch.setattr(au, "_executer_regle", lambda r, contexte="", resume="": faits.append((r["id"], contexte, resume)))
    return stock, faits


def _regle(type_, **d):
    return {"id": f"r-{type_}", "nom": type_, "actif": True, "appareil": MACHINE,
            "declencheur": {"type": type_, **d}, "action": {"type": "prevenir", "consigne": "", "message": ""}}


def test_rendez_vous_une_seule_fois_et_filtre_par_titre(regles):
    stock, faits = regles
    stock.append(_regle("rendez_vous", avant=15, contient="dentiste"))
    maintenant = datetime(2026, 11, 25, 9, 50)
    evs = [(datetime(2026, 11, 25, 10, 0), "Dentiste Dr Martin", "Lyon"), (datetime(2026, 11, 25, 10, 0), "Réunion équipe", "")]
    au.verifier_rendez_vous(maintenant, evs)
    au.verifier_rendez_vous(maintenant + timedelta(minutes=1), evs)
    assert len(faits) == 1 and "Dentiste Dr Martin" in faits[0][1] and "10:00" in faits[0][1]
    au.verifier_rendez_vous(datetime(2026, 11, 25, 9, 0), [(datetime(2026, 11, 25, 10, 0), "Dentiste 2", "")])
    assert len(faits) == 1   # trop tôt (60 min avant)


def test_nouveau_fichier_seulement_quand_il_a_fini_d_arriver(regles, tmp_path):
    stock, faits = regles
    stock.append(_regle("fichier", dossier=str(tmp_path), motif="*.pdf"))
    (tmp_path / "ancienne.pdf").write_bytes(b"x")
    au._fichiers_vus.clear()
    au.verifier_fichiers()                      # 1er passage : ce qui est là ne compte pas
    (tmp_path / "facture.pdf").write_bytes(b"debut")
    (tmp_path / "photo.jpg").write_bytes(b"x")
    (tmp_path / "gros.pdf.crdownload").write_bytes(b"x")
    au.verifier_fichiers()                      # vu une fois : on attend une taille stable
    assert faits == []
    au.verifier_fichiers()
    assert len(faits) == 1 and "facture.pdf" in faits[0][1]
    au.verifier_fichiers()
    assert len(faits) == 1                      # pas deux fois


def test_tache_finie(regles, monkeypatch):
    stock, faits = regles
    stock.append(_regle("tache_finie"))
    from wesley import partage, taches
    etat = {"statut": "en_cours"}
    monkeypatch.setattr(taches, "lister", lambda: [{"id": "t1", "titre": "Corriger le bug", "statut": etat["statut"], "bilan": "OK"}])
    monkeypatch.setattr(partage, "distants", lambda genre: [])
    au._taches_etat.clear()
    au.verifier_taches()
    au.verifier_taches()
    assert faits == []
    etat["statut"] = "terminee"
    au.verifier_taches()
    assert len(faits) == 1 and "Corriger le bug" in faits[0][1] and "terminée" in faits[0][1]


def test_site_qui_tombe_puis_revient(regles, monkeypatch):
    stock, faits = regles
    stock.append(_regle("site", url="https://exemple.fr", minutes=1))
    annonces = []
    from wesley import annonces as ann
    monkeypatch.setattr(ann, "annoncer", lambda texte, **k: annonces.append(texte))
    au._sites.clear()
    reponses = iter([(True, "HTTP 200"), (False, "ConnectTimeout"), (False, "ConnectTimeout"), (True, "HTTP 200")])
    for _ in range(4):
        au.verifier_sites(lambda url: next(reponses))
        au._sites["r-site"]["dernier"] = 0      # on n'attend pas la minute
    assert len(faits) == 1 and "ConnectTimeout" in faits[0][1]   # une alerte, pas une par vérification
    assert annonces == ["https://exemple.fr répond de nouveau."]


def test_condition_verifiee_par_wesley():
    r = _regle("fichier", condition="seulement si c'est une facture")
    assert au.condition_remplie(r, "Nouveau fichier : facture-EDF.pdf", lambda p: "OUI")
    assert not au.condition_remplie(r, "Nouveau fichier : vacances.pdf", lambda p: "NON, c'est une photo")
    assert au.condition_remplie(_regle("fichier"), "x", lambda p: pytest.fail("sans condition : pas d'appel"))

    def panne(p):
        raise RuntimeError("pas de clé")
    assert not au.condition_remplie(r, "x", panne)   # dans le doute : on ne fait rien


def test_description_des_nouveaux_declencheurs():
    assert "15 min avant un rendez-vous" in au.decrire(_regle("rendez_vous", avant=15))
    d = au.decrire(_regle("fichier", dossier="/x", motif="*.pdf", condition="si c'est une facture"))
    assert "*.pdf" in d and "si c'est une facture" in d
    assert "ne répond plus" in au.decrire(_regle("site", url="https://a.fr", minutes=5))


# ---------- habitudes ----------
def _historique(monkeypatch, lignes_par_jour):
    monkeypatch.setattr(memoire, "fichiers_par_jour", lambda: {j: [j] for j in lignes_par_jour})
    monkeypatch.setattr(memoire, "lignes_du_jour", lambda f: [(l[1:6], "", l) for l in lignes_par_jour[f[0]]])


def test_habitude_remarquee(monkeypatch):
    from wesley import semantique
    monkeypatch.setattr(semantique, "disponible", lambda: False)
    lignes = {}
    for k, jour in enumerate(["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]):
        lignes[jour] = [f"[09:0{k}] Abdel: Ouvre VS Code et Slack", "[09:05] Wesley: C'est ouvert.", f"[14:{10 + k}] Abdel: quelle heure est-il ?"]
    lignes["2026-11-21"] = ["[22:00] Abdel: ouvre VS Code et Slack"]   # un samedi soir : pas « à la même heure »
    _historique(monkeypatch, lignes)
    h = habitudes.detecter(habitudes.demandes(date(2026, 11, 24), "Abdel"))
    assert h and h[0]["texte"].lower() == "ouvre vs code et slack" and h[0]["jours"] == [0, 1, 2, 3, 4]
    assert h[0]["heure"] == "08:45" and h[0]["nb_jours"] == 5   # un peu avant, arrondi au quart d'heure
    assert all("quelle heure" not in x["texte"] for x in h) or len(h) == 2


def test_rien_sous_4_jours(monkeypatch):
    from wesley import semantique
    monkeypatch.setattr(semantique, "disponible", lambda: False)
    _historique(monkeypatch, {f"2026-11-1{k}": ["[09:00] Abdel: lance spotify"] for k in range(6, 9)})
    assert habitudes.detecter(habitudes.demandes(date(2026, 11, 24), "Abdel")) == []


def test_proposition_acceptee_cree_l_automatisation(monkeypatch, tmp_path):
    from wesley import semantique
    monkeypatch.setattr(semantique, "disponible", lambda: False)
    monkeypatch.setattr(consolidation, "FICHIER", tmp_path / "c.json")
    creees = []
    monkeypatch.setattr(au, "lister", lambda: [])
    monkeypatch.setattr(au, "creer", lambda nom, **k: creees.append((nom, k)) or {"nom": nom, "declencheur": {"type": "horaire", "heure": k["heure"], "jours": k["jours"]}, "action": {"type": "wesley", "consigne": k["consigne"]}, "appareil": MACHINE})
    hab = [{"texte": "Ouvre VS Code et Slack", "heure": "08:45", "jours": [0, 1, 2, 3, 4], "nb_jours": 5}]
    monkeypatch.setattr(habitudes, "detecter", lambda dem: hab)
    monkeypatch.setattr(habitudes, "demandes", lambda d=None, nom="": [])
    assert habitudes.proposer() == 1
    p = consolidation.propositions()[0]
    assert p["type"] == "routine" and "8 h 45" in p["question"] and "en semaine" in p["question"]
    assert habitudes.proposer() == 0                       # pas reproposée
    consolidation.repondre(p["id"], True)
    assert creees and creees[0][1]["heure"] == "08:45" and creees[0][1]["type_declencheur"] == "horaire"
