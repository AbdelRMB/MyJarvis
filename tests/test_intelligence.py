"""Intelligence de Wesley : mémoire par le sens, rangement de la mémoire, leçons apprises seul, budget et modèle rapide.

Lancer : python -m pytest tests/test_intelligence.py -q
(les tests qui utilisent le vrai modèle de sens sont sautés s'il n'est pas dans RACINE/modeles)
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import apprentissage, consolidation, memoire, semantique  # noqa: E402
from wesley.config import CONFIG  # noqa: E402


def _fait(texte, cat="general", fid=None, modifie=0.0):
    return {"fait": texte, "categorie": cat, "date": "2026-11-01", "fid": fid or texte[:12], "modifie": modifie}


@pytest.fixture
def faits(monkeypatch):
    stock = []
    monkeypatch.setattr(memoire, "_charger", lambda: stock)
    return stock


# ---------- souvenirs dans les instructions / joints à la demande ----------
def test_peu_de_souvenirs_tous_dans_les_instructions(faits):
    faits += [_fait(f"souvenir {i}") for i in range(10)] + [_fait("Réponds court", "consigne"), _fait("Semaine du…", "journal")]
    assert len(memoire.faits_du_prompt()) == 10   # ni consigne (à part) ni journal


def test_beaucoup_de_souvenirs_l_essentiel_seulement(faits):
    faits += [_fait("Il s'appelle Abdel", "identite", "id1")]
    faits += [_fait(f"souvenir {i}", fid=f"f{i}", modifie=float(i)) for i in range(80)]
    gardes = memoire.faits_du_prompt()
    assert gardes[0]["fid"] == "id1" and len(gardes) < 30
    assert "f79" in {x["fid"] for x in gardes} and "f0" not in {x["fid"] for x in gardes}   # les plus utilisés récemment
    texte, _ = memoire.profil_texte()
    assert "autres souvenirs" in texte and "chercher_memoire" in texte
    assert "souvenir 0" in memoire.profil_texte(complet=True)[0]


def test_rappel_joint_les_souvenirs_utiles_absents_des_instructions(faits, monkeypatch):
    faits += [_fait("Il s'appelle Abdel", "identite", "id1")] + [_fait(f"souvenir {i}", fid=f"f{i}", modifie=float(i)) for i in range(80)]
    faits += [_fait("La Clio est au garage", fid="clio", modifie=-1)]
    vus = []

    def classer(req, textes, k=10, nom_index="", seuil=0.0):
        vus.append(textes)
        return [(textes.index("La Clio est au garage"), 0.9)]
    monkeypatch.setattr(semantique, "classer", classer)
    monkeypatch.setattr(consolidation, "rappel_propositions", lambda: "")
    r = memoire.rappel_pour("ma voiture est prête ?")
    assert "Souvenirs liés à cette demande" in r and "La Clio est au garage" in r
    assert "Il s'appelle Abdel" not in vus[0]   # déjà dans les instructions : pas proposé deux fois


def test_sans_modele_la_recherche_par_mots_marche_encore(monkeypatch):
    monkeypatch.setattr(semantique, "disponible", lambda: False)
    textes = ["La Clio est au garage", "Il aime le café", "Rendez-vous au garage mardi"]
    assert [i for i, _ in semantique.classer("garage", textes)] == [0, 2] or [i for i, _ in semantique.classer("garage", textes)] == [2, 0]
    assert semantique.classer("voiture", textes) == []


modele = pytest.mark.skipif(not semantique.utilisable(), reason="modèle de sens absent (téléchargé au 1er lancement)")


@modele
def test_le_sens_retrouve_le_bon_souvenir():
    faits = ["La Clio d'Abdel est au garage depuis lundi", "Abdel aime le café serré le matin", "Sa sœur s'appelle Inès",
             "Son serveur OVH héberge n8n", "Il joue à Valorant le soir", "Il apprend le japonais"]
    for question, attendu in (("ma voiture est prête ?", 0), ("appelle ma soeur", 2), ("mon VPS est down", 3),
                              ("on joue ce soir ?", 4), ("comment on dit merci en japonais", 5)):
        assert semantique.classer(question, faits, k=1)[0][0] == attendu, question


@modele
def test_index_garde_les_vecteurs_sur_disque(tmp_path, monkeypatch):
    monkeypatch.setattr(semantique, "DOSSIER_INDEX", tmp_path)
    ix = semantique.Index("essai")
    ix.fichier = tmp_path / "index_essai.npz"
    m = ix.matrice(["bonjour", "au revoir"])
    assert m.shape[0] == 2 and ix.fichier.exists()
    ix2 = semantique.Index("essai")
    ix2.fichier = ix.fichier
    appels = []
    monkeypatch.setattr(semantique, "encoder", lambda *a, **k: appels.append(a) or None)
    assert ix2.matrice(["bonjour"]).shape[0] == 1 and not appels   # relu du disque, rien recalculé


# ---------- rangement de la mémoire ----------
@pytest.fixture
def etat(tmp_path, monkeypatch):
    monkeypatch.setattr(consolidation, "FICHIER", tmp_path / "consolidation.json")
    return tmp_path


def test_fusion_des_doublons_et_proposition_pour_une_contradiction(faits, etat, monkeypatch):
    faits += [_fait("Abdel aime le café", fid="a"), _fait("Abdel boit son café serré", fid="b"),
              _fait("Abdel habite à Lyon", fid="c"), _fait("Abdel habite à Paris depuis octobre", fid="d")]
    monkeypatch.setattr(consolidation, "paires", lambda f: ([(0, 1, 0.95)], [(2, 3, 0.9)]))
    reponse = json.dumps({"paires": [{"n": 1, "decision": "fusion", "texte": "Abdel aime le café, serré"},
                                     {"n": 2, "decision": "contradiction", "garder": 2, "question": "Tu habites à Paris maintenant ?"}]})
    modifies, oublies = [], []
    monkeypatch.setattr(memoire, "modifier", lambda fid, t, c=None: modifies.append((fid, t)))
    monkeypatch.setattr(memoire, "supprimer_un", lambda fid="", fait="": oublies.append(fid))
    fusions, contradictions = consolidation.analyser(faits, lambda p: reponse)
    r = consolidation.appliquer(fusions, contradictions)
    assert r == {"fusions": 1, "contradictions": 1}
    assert modifies == [("a", "Abdel aime le café, serré")] and oublies == ["b"]
    p = consolidation.propositions()
    assert len(p) == 1 and p[0]["ancien"] == "Abdel habite à Lyon" and "Paris" in p[0]["question"]
    assert "confirmer_memoire" in consolidation.rappel_propositions()
    # la contradiction n'est appliquée QUE si l'utilisateur accepte
    assert oublies == ["b"]
    consolidation.repondre(p[0]["id"], True)
    assert oublies == ["b", "c"] and consolidation.propositions() == []
    # même contradiction retrouvée plus tard : la question n'est pas reposée
    consolidation.appliquer([], contradictions)
    assert consolidation.propositions() == []


def test_refus_garde_la_memoire(faits, etat, monkeypatch):
    faits += [_fait("Abdel habite à Lyon", fid="c"), _fait("Abdel habite à Paris", fid="d")]
    oublies = []
    monkeypatch.setattr(memoire, "supprimer_un", lambda fid="", fait="": oublies.append(fid))
    consolidation.appliquer([], [(faits[1], faits[0], "Paris ?")])
    consolidation.repondre(consolidation.propositions()[0]["id"], False)
    assert oublies == [] and consolidation.propositions() == []


def test_dans_le_doute_rien_n_est_touche(faits, etat, monkeypatch):
    faits += [_fait("Il aime le foot", fid="a"), _fait("Il aime le tennis", fid="b")]
    monkeypatch.setattr(consolidation, "paires", lambda f: ([], [(0, 1, 0.88)]))
    assert consolidation.analyser(faits, lambda p: '{"paires": [{"n": 1, "decision": "distincts"}]}') == ([], [])
    assert consolidation.analyser(faits, lambda p: "réponse illisible") == ([], [])


def test_resume_de_la_semaine(faits, monkeypatch):
    monkeypatch.setattr(memoire, "fichiers_par_jour", lambda: {"2026-11-16": ["x"], "2026-11-17": ["y"], "2026-11-24": ["z"]})
    monkeypatch.setattr(memoire, "lignes_du_jour", lambda f: [(0, "", f"[10:00] Abdel: ligne {f[0]} {i}") for i in range(4)])
    ajoutes = []
    monkeypatch.setattr(memoire, "ajouter", lambda t, c="general": ajoutes.append((t, c)))
    lundi = consolidation.semaine_a_resumer(date(2026, 11, 24))
    assert lundi == date(2026, 11, 16)
    vus = []
    consolidation.resumer_semaine(lundi, lambda p: (vus.append(p), "Abdel a avancé sur Wesley.")[1])
    assert "ligne x" in vus[0] and "ligne z" not in vus[0]   # seulement la semaine du 16
    assert ajoutes == [("Semaine du 16/11/2026 : Abdel a avancé sur Wesley.", "journal")]
    faits.append(_fait(ajoutes[0][0], "journal"))
    assert consolidation.semaine_a_resumer(date(2026, 11, 24)) is None   # déjà fait


def test_une_fois_par_jour(faits, etat, monkeypatch):
    monkeypatch.setattr(semantique, "disponible", lambda: False)
    monkeypatch.setattr(consolidation, "semaine_a_resumer", lambda: None)
    assert not consolidation.consolider(lambda p: "").get("deja")
    assert consolidation.consolider(lambda p: "").get("deja")


# ---------- leçons apprises seul ----------
@pytest.mark.parametrize("texte", ["non, pas comme ça", "Je t'ai dit de l'ouvrir avec Finder", "c'est faux", "tu t'es trompé de fichier",
                                   "ne mets plus d'emoji", "mais non !"])
def test_correction_reconnue(texte):
    assert apprentissage.corrige(texte)


@pytest.mark.parametrize("texte", ["ouvre Spotify", "merci beaucoup", "notre projet avance"])
def test_pas_une_correction(texte):
    assert not apprentissage.corrige(texte)


def test_echec_puis_reussite():
    assert apprentissage.echec_puis_reussite([("terminal", {}, "Erreur : commande introuvable"), ("ouvrir_application", {}, "OK")])
    assert not apprentissage.echec_puis_reussite([("ouvrir_application", {}, "OK")])
    assert not apprentissage.echec_puis_reussite([("x", {}, "OK"), ("y", {}, "Erreur : réseau")])


def test_lecon_notee_une_seule_fois(faits, monkeypatch):
    monkeypatch.setitem(CONFIG, "apprentissage_auto", True)
    monkeypatch.setattr(semantique, "disponible", lambda: False)
    ajoutees = []

    def ajouter(t, c="general"):
        ajoutees.append((t, c))
        faits.append(_fait(t, c))
    monkeypatch.setattr(memoire, "ajouter", ajouter)
    cerveau = lambda p: '{"lecon": "Pour ouvrir Spotify sur ce Mac : ouvrir_application, pas le terminal."}'
    trace = [("terminal", {"commande": "spotify"}, "Erreur : introuvable"), ("ouvrir_application", {"nom": "Spotify"}, "OK")]
    assert apprentissage.apres_echange("ouvre Spotify", "", trace, "C'est ouvert.", cerveau)
    assert ajoutees[0][1] == "lecon"
    assert not apprentissage.apres_echange("ouvre Spotify", "", trace, "C'est ouvert.", cerveau)   # déjà connue
    assert len(ajoutees) == 1


def test_rien_a_apprendre_sans_signal(monkeypatch):
    monkeypatch.setitem(CONFIG, "apprentissage_auto", True)
    assert not apprentissage.apres_echange("quelle heure est-il ?", "", [], "Il est 10 h.", lambda p: pytest.fail("pas d appel"))
    monkeypatch.setitem(CONFIG, "apprentissage_auto", False)
    assert not apprentissage.apres_echange("non, pas comme ça", "x", [], "ok", lambda p: pytest.fail("désactivé"))


# ---------- budget et modèle rapide (cerveau Claude) ----------
def test_mode_economie_quand_le_budget_est_depasse(tmp_path, monkeypatch):
    pytest.importorskip("anthropic")
    from wesley import claude
    monkeypatch.setattr(claude, "COUTS", tmp_path / "couts.json")
    monkeypatch.setitem(CONFIG, "claude_modele", "claude-sonnet-5-5")
    monkeypatch.setitem(CONFIG, "budget_mensuel", 10)
    mois = time.strftime("%Y-%m")
    (tmp_path / "couts.json").write_text(json.dumps({"jours": {f"{mois}-01": 4.0, "2020-01-01": 99}}), encoding="utf-8")
    assert not claude.en_economie() and claude.modele_conversation() == "claude-sonnet-5-5"
    p = claude._parametres_requete()
    assert p["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in p["betas"]
    (tmp_path / "couts.json").write_text(json.dumps({"jours": {f"{mois}-01": 10.5}}), encoding="utf-8")
    assert claude.en_economie() and claude.modele_conversation() == claude.MODELE_RAPIDE
    p = claude._parametres_requete()
    # Haiku : pas de secours côté serveur, pas de conseiller, outils web de base
    assert p["model"] == claude.MODELE_RAPIDE and "fallbacks" not in p and "server-side-fallback-2026-07-01" not in p["betas"]
    assert "advisor-tool-2026-03-01" not in p["betas"]
    claude._outils_cache = None
    types = {t.get("type") for t in claude.outils_claude()}
    assert "web_search_20250305" in types and "web_search_20260209" not in types and "advisor_20260301" not in types
    monkeypatch.setitem(CONFIG, "budget_mensuel", 0)
    claude._outils_cache = None
    assert not claude.en_economie()


def test_travail_de_fond_sur_le_modele_rapide(monkeypatch):
    pytest.importorskip("anthropic")
    from wesley import claude
    monkeypatch.setitem(CONFIG, "budget_mensuel", 0)
    monkeypatch.setitem(CONFIG, "modele_rapide_fond", True)
    assert claude.modele_fond() == claude.MODELE_RAPIDE
    monkeypatch.setitem(CONFIG, "modele_rapide_fond", False)
    monkeypatch.setitem(CONFIG, "claude_modele", "claude-opus-5-5")
    assert claude.modele_fond() == "claude-opus-5-5"
