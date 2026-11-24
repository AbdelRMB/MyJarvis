"""Transcription de réunions : mise en forme, renommage, diarisation, découpage, chaîne complète (sans micro ni modèle).

Lancer : python -m pytest tests -q   (pytest et numpy)
"""
import json
import sys
import time
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wesley import transcription as tr  # noqa: E402
from wesley.config import CONFIG  # noqa: E402

SR = tr.SR


def _session(**k):
    s = {"id": "20261123-100000-abcd", "titre": "Point projet", "debut": time.mktime((2026, 11, 23, 10, 0, 0, 0, 0, -1)),
         "duree": 125.0, "source": "micro", "avec_micro": False, "etat": "terminee", "noms": {},
         "segments": [
             {"debut": 0.0, "fin": 3.0, "locuteur": 1, "texte": "Bonjour à tous."},
             {"debut": 3.2, "fin": 6.0, "locuteur": 1, "texte": "On commence ?"},
             {"debut": 7.0, "fin": 12.5, "locuteur": 2, "texte": "Oui, j'ai les chiffres."},
             {"debut": 65.0, "fin": 70.0, "locuteur": 3, "texte": "Moi aussi."},
             {"debut": 71.0, "fin": 75.0, "locuteur": 1, "texte": "Parfait."},
         ]}
    s.update(k)
    return s


# ---------------------------------------------------------------- mise en forme (pur Python)
def test_horodatage():
    assert tr.horodatage(0) == "00:00"
    assert tr.horodatage(12.7) == "00:12"
    assert tr.horodatage(65) == "01:05"
    assert tr.horodatage(3725) == "1:02:05"
    assert tr.horodatage(-3) == "00:00"


def test_tours_de_parole_regroupe_les_phrases_consecutives():
    tours = tr.tours_de_parole(_session())
    assert [t["locuteur"] for t in tours] == [1, 2, 3, 1]
    assert tours[0]["texte"] == "Bonjour à tous. On commence ?"
    assert tours[0]["debut"] == 0.0 and tours[0]["fin"] == 6.0


def test_export_markdown_et_texte_avec_noms():
    s = tr.renommer(_session(), {"1": "Alice", "2": "  Bob  "})
    md = tr.exporter(s, "md")
    assert md.startswith("# Point projet\n")
    assert "- **Participants** : Alice, Bob, Locuteur 3" in md
    assert "**Alice** · `00:00`" in md and "**Bob** · `00:07`" in md and "**Locuteur 3** · `01:05`" in md
    assert "- **Durée** : 02:05" in md
    txt = tr.exporter(s, "txt")
    assert "[00:00] Alice : Bonjour à tous. On commence ?" in txt
    assert "[01:11] Alice : Parfait." in txt
    assert "**" not in txt


def test_export_vide_et_source_systeme():
    md = tr.exporter(_session(segments=[], source="systeme", avec_micro=True), "md")
    assert "son de l'ordinateur + micro" in md
    assert "rien n'a encore été transcrit" in md


def test_renommer_vider_un_nom_rend_le_numero():
    s = tr.renommer(_session(), {"1": "Alice"})
    assert tr.nom_locuteur(s, 1) == "Alice"
    tr.renommer(s, {"1": "  "})
    assert tr.nom_locuteur(s, 1) == "Locuteur 1"


def test_locuteurs_ordre_d_apparition_et_temps_de_parole():
    ls = tr.locuteurs(tr.renommer(_session(), {"2": "Bob"}))
    assert [l["id"] for l in ls] == [1, 2, 3]
    assert ls[0]["duree"] == pytest.approx(3.0 + 2.8 + 4.0)
    assert ls[0]["phrases"] == 3
    assert ls[1]["nom"] == "Bob"


def test_fusionner_deux_etiquettes_d_une_meme_personne():
    s = tr.renommer(_session(), {"3": "Carla"})
    tr.fusionner(s, 3, 2)
    assert {x["locuteur"] for x in s["segments"]} == {1, 2}
    assert tr.nom_locuteur(s, 2) == "Carla"    # le nom donné suit les phrases
    assert "3" not in s["noms"]
    s2 = tr.renommer(_session(), {"2": "Bob", "3": "Carla"})
    tr.fusionner(s2, 3, 2)
    assert tr.nom_locuteur(s2, 2) == "Bob"     # la cible garde son nom


def test_changer_le_locuteur_d_une_phrase_et_corriger_le_texte():
    s = _session()
    tr.changer_locuteur(s, 4, 2)
    assert s["segments"][4]["locuteur"] == 2
    tr.changer_locuteur(s, 0, 0)               # 0 = nouvelle personne
    assert s["segments"][0]["locuteur"] == 4
    tr.corriger_texte(s, 1, "  On commence ? ")
    assert s["segments"][1]["texte"] == "On commence ?"
    with pytest.raises(ValueError):
        tr.changer_locuteur(s, 99, 1)


def test_renumeroter_et_nom_de_fichier():
    assert tr.renumeroter([7, 7, 3, 9, 3]) == [1, 1, 2, 3, 2]
    assert tr.nom_de_fichier('Réunion : budget/2027 ?') == "Réunion budget 2027"
    assert tr.nom_de_fichier("   ") == "Transcription"


def test_hallucinations_de_whisper_ignorees():
    assert tr._hallucination("Sous-titrage ST' 501")
    assert tr._hallucination("Merci d'avoir regardé cette vidéo !")
    assert not tr._hallucination("Merci à tous pour cette réunion.")


# ---------------------------------------------------------------- diarisation (numpy)
np = pytest.importorskip("numpy")


def _voix(n, centre, bruit=0.15, graine=0):
    r = np.random.default_rng(graine)
    return [centre + r.normal(0, bruit, centre.shape) for _ in range(n)]


@pytest.fixture
def centres():
    r = np.random.default_rng(42)
    return [r.normal(0, 1, 64) for _ in range(3)]


def test_diariseur_en_direct_change_de_locuteur(centres):
    d = tr.Diariseur(seuil=0.5)
    a, b = _voix(3, centres[0], graine=1), _voix(3, centres[1], graine=2)
    suite = [d.attribuer(e) for e in [a[0], a[1], b[0], b[1], a[2], b[2]]]
    assert suite == [1, 1, 2, 2, 1, 2]


def test_diariseur_phrase_courte_garde_le_locuteur_precedent(centres):
    d = tr.Diariseur(seuil=0.5)
    d.attribuer(centres[0])
    d.attribuer(centres[1])
    # phrase trop courte et peu ressemblante : pas de nouveau locuteur, on garde le précédent
    assert d.attribuer(np.random.default_rng(5).normal(0, 1, 64), fiable=False) == 2
    assert len(d.centres) == 2
    # phrase courte mais clairement reconnue
    assert d.attribuer(centres[0], fiable=False) == 1


def test_regrouper_retrouve_les_voix_et_numerote_par_apparition(centres):
    a, b, c = _voix(4, centres[2], graine=3), _voix(4, centres[0], graine=4), _voix(3, centres[1], graine=5)
    emb = [a[0], b[0], a[1], c[0], b[1], a[2], c[1], b[2], a[3], c[2], b[3]]
    attendu = [1, 2, 1, 3, 2, 1, 3, 2, 1, 3, 2]
    assert tr.regrouper(emb, seuil=0.5) == attendu


def test_regrouper_avec_un_nombre_impose(centres):
    a, b, c = _voix(3, centres[0], graine=6), _voix(3, centres[1], graine=7), _voix(3, centres[2], graine=8)
    emb = a + b + c
    assert len(set(tr.regrouper(emb, seuil=0.5))) == 3
    assert len(set(tr.regrouper(emb, seuil=0.5, nombre=2))) == 2
    assert tr.regrouper(emb, seuil=0.5, nombre=3) == [1] * 3 + [2] * 3 + [3] * 3


def test_regrouper_phrases_courtes_et_isolees(centres):
    a, b = _voix(3, centres[0], graine=9), _voix(3, centres[1], graine=10)
    court = centres[1] + np.random.default_rng(11).normal(0, 0.2, 64)
    emb = a + [court] + b
    fiables = [True] * 3 + [False] + [True] * 3
    assert tr.regrouper(emb, 0.5, fiables=fiables) == [1, 1, 1, 2, 2, 2, 2]
    # une seule phrase très courte d'une voix inconnue : rattachée au groupe le plus proche, pas un locuteur à part
    intrus = centres[2]
    res = tr.regrouper(a + [intrus] + b, 0.5, durees=[3, 3, 3, 0.8, 3, 3, 3])
    assert len(set(res)) == 2
    assert tr.regrouper([], 0.5) == []
    assert tr.regrouper([centres[0]], 0.5) == [1]


# Empreintes réalistes (façon CAM++, 192 dimensions) : une voix = une direction ; chaque phrase est bruitée
# d'autant plus qu'elle est courte (2 s : similarité ~0,4 avec une autre phrase de la même voix), la voix dérive
# lentement (la personne se déplace dans la salle) et 10 % des phrases sont aberrantes (rire, bruit, toux).
D = 192


def _unite(v):
    return v / np.linalg.norm(v)


def _personne(r, commun, part=0.3):
    """Voix d'une personne ; « commun » = la même pièce et le même micro (rapproche toutes les voix)."""
    return _unite(np.sqrt(1 - part) * _unite(r.normal(0, 1, D)) + np.sqrt(part) * commun)


def _phrases(r, voix, n, bruit=2.0, derive=0.6):
    d0, d1 = _unite(r.normal(0, 1, D)), _unite(r.normal(0, 1, D))
    for k in range(n):
        t = k / max(1, n - 1)
        centre = _unite(voix + derive * ((1 - t) * d0 + t * d1))
        duree = r.uniform(1.2, 6.0)
        sigma = bruit / np.sqrt(duree * D) * (2.0 if r.random() < 0.1 else 1.0)
        yield centre + r.normal(0, sigma, D), duree


@pytest.mark.parametrize("graine", range(4))
def test_une_seule_voix_bruitee_reste_un_seul_locuteur(graine):
    """Le cas du professeur qui parle seul 18 min : avant, il était découpé en dizaines de locuteurs."""
    r = np.random.default_rng(graine)
    prof = _personne(r, _unite(r.normal(0, 1, D)), 0.2)
    phrases = list(_phrases(r, prof, 300))
    emb, durees = [e for e, _ in phrases], [d for _, d in phrases]
    X = np.stack([tr._normer(e) for e in emb])
    assert (X @ X.T)[np.triu_indices(len(X), 1)].mean() < 0.5      # phrases peu ressemblantes deux à deux
    assert set(tr.regrouper(emb, 0.5, fiables=[d >= 1 for d in durees], durees=durees)) == {1}
    # en direct aussi : au pire un locuteur de trop par moments, vite corrigé par le regroupement régulier
    d = tr.Diariseur(0.5)
    direct = [d.attribuer(e, True, x) for e, x in zip(emb, durees)]
    assert max(direct) <= 3 and set(d.etiquettes) == {1} and len(d.etiquettes) == len(emb)


@pytest.mark.parametrize("graine", range(3))
def test_deux_voix_distinctes_restent_deux(graine):
    r = np.random.default_rng(10 + graine)
    commun = _unite(r.normal(0, 1, D))
    a, b = _personne(r, commun), _personne(r, commun)
    sa, sb = _phrases(r, a, 200), _phrases(r, b, 200)
    emb, durees, qui = [], [], []
    for tour in range(40):              # tours de parole de 1 à 4 phrases
        src, nom = (sa, "a") if tour % 2 == 0 else (sb, "b")
        for _ in range(r.integers(1, 5)):
            e, x = next(src)
            emb.append(e), durees.append(x), qui.append(nom)
    res = tr.regrouper(emb, 0.5, durees=durees)
    assert set(res) == {1, 2}
    justes = sum((l == 1) == (q == "a") for l, q in zip(res, qui))
    assert justes / len(res) >= 0.95


def test_prof_et_eleves_les_eleves_ne_disparaissent_pas():
    """Un prof qui parle beaucoup et deux élèves qui interviennent un peu : trois locuteurs."""
    r = np.random.default_rng(7)
    commun = _unite(r.normal(0, 1, D))
    p, e1, e2 = _personne(r, commun), _personne(r, commun), _personne(r, commun)
    sources = {"p": _phrases(r, p, 400), "e1": _phrases(r, e1, 40, derive=0.3), "e2": _phrases(r, e2, 40, derive=0.3)}
    emb, durees, qui = [], [], []
    for tour in range(60):
        nom = "e1" if tour % 6 == 1 else "e2" if tour % 6 == 4 else "p"
        for _ in range(r.integers(3, 8) if nom == "p" else r.integers(1, 4)):
            e, x = next(sources[nom])
            emb.append(e), durees.append(x), qui.append(nom)
    res = tr.regrouper(emb, 0.5, durees=durees)
    assert len(set(res)) == 3 and res[0] == 1
    for l in set(res):          # chaque locuteur trouvé correspond à une seule personne
        assert len({q for q, x in zip(qui, res) if x == l}) == 1


def test_regrouper_lisse_et_fusionne_les_locuteurs_marginaux(centres):
    # une phrase courte d'une autre « voix » au milieu d'un long passage du même locuteur : lissée
    a = _voix(10, centres[0], graine=12)
    bizarre = centres[0] * 0.3 + centres[1]
    res = tr.regrouper(a[:5] + [bizarre] + a[5:], 0.5, durees=[4] * 5 + [2] + [4] * 5)
    assert set(res) == {1}
    # une seule phrase de 3 s d'une voix inconnue sur 20 min de parole : rattachée, pas un locuteur à part
    long = _voix(300, centres[0], graine=13)
    res = tr.regrouper(long[:150] + [centres[2]] + long[150:], 0.5, durees=[4] * 150 + [3] + [4] * 150)
    assert set(res) == {1}
    # un vrai second locuteur qui parle assez longtemps reste distinct
    b = _voix(10, centres[1], graine=14)
    res = tr.regrouper(a + b + a, 0.5, durees=[4] * 30)
    assert res == [1] * 10 + [2] * 10 + [1] * 10


def test_numeros_sans_trou_apres_fusion_en_direct():
    assert tr.appliquer_fusion([1, 2, 3, 4, 3], 3, 1) == [1, 2, 1, 3, 1]
    assert tr.appliquer_fusion([2, 1], 2, 1) == [1, 1]
    # deux voix en direct qui se révèlent être la même : fusionnées, numérotation compacte
    d = tr.Diariseur(0.5)
    r = np.random.default_rng(3)
    v = _unite(r.normal(0, 1, D))
    autre = _unite(v + 3.0 * _unite(r.normal(0, 1, D)))     # même voix, phrase très déformée
    assert d.attribuer(v, True, 4) == 1
    assert d.attribuer(autre, True, 4) == 2
    for _ in range(6):                          # la voix moyenne de 1 se rapproche de 2 : fusion
        d.attribuer(_unite(v + autre), True, 4)
    assert len(d.centres) == 1 and (2, 1) in d.fusions and d.dernier == 1 and set(d.etiquettes) == {1}


def _contigus(etiquettes):
    """Numéros 1..N sans trou, dans l'ordre de première apparition."""
    ordre = list(dict.fromkeys(etiquettes))
    return ordre == list(range(1, len(ordre) + 1))


def test_renumerotation_apres_12_locuteurs_crees_puis_fusionnes(dossiers):
    """Non-régression (« Locuteur 8, 9, 11, 12 » pour 2-3 personnes) : 12 locuteurs créés en direct puis
    fusionnés ; à chaque étape et après le regroupement final, numéros 1..N contigus par ordre d'apparition."""
    r = np.random.default_rng(22)
    P = [_unite(r.normal(0, 1, D)) for _ in range(3)]          # 3 vraies personnes
    variantes = [_unite(P[k % 3] + 1.6 * _unite(r.normal(0, 1, D))) for k in range(12)]   # phrases très déformées
    nettes = [_unite(P[(i // 5) % 3] + 0.3 * _unite(r.normal(0, 1, D))) for i in range(60)]
    d = tr.Diariseur(0.5)
    vus = []
    for e in variantes + nettes:
        d.attribuer(e, True, 4)
        assert _contigus(d.etiquettes), d.etiquettes
        vus.append(max(d.etiquettes))
    assert max(vus) == 12 and len(d.fusions) >= 5                   # 12 créés, puis fusionnés
    assert sorted(set(d.etiquettes)) == [1, 2, 3]
    emb = variantes + nettes
    final = tr.regrouper_complet(emb, 0.5, 0, [True] * len(emb), [4] * len(emb))
    assert _contigus(final) and len(set(final)) == 3
    # même chose sur une transcription enregistrée avec des numéros troués (8, 9, 11, 12) et une empreinte manquante
    segs = [{"debut": 4 * i, "fin": 4 * i + 3.5, "locuteur": [8, 9, 11, 12][i % 4], "texte": f"P{i}"}
            for i in range(len(emb))]
    s = _session(id="20261123-120000-c0de", segments=segs)
    tr.sauver(s)
    tr.sauver_empreintes(s["id"], [None] + emb[1:], [True] * len(emb), [4] * len(emb))
    res = [x["locuteur"] for x in tr.modifier(s["id"], "regrouper", {"nombre": 0})["segments"]]
    assert _contigus(res) and len(set(res)) == 3
    res = [x["locuteur"] for x in tr.modifier(s["id"], "regrouper", {"nombre": 2})["segments"]]
    assert _contigus(res) and len(set(res)) == 2
    # et une transcription interrompue (Wesley fermé) est renumérotée au redémarrage
    tr.sauver(_session(id="20261123-120500-c0de", etat="en_cours", segments=segs[:8]))
    tr.au_demarrage()
    assert [x["locuteur"] for x in tr.lire("20261123-120500-c0de")["segments"]] == [1, 2, 3, 4] * 2


def test_phrases_sans_empreinte_jamais_perdues():
    """Une empreinte impossible à calculer ne doit plus empêcher le regroupement final (numéros 8, 12…)."""
    r = np.random.default_rng(4)
    a, b = _unite(r.normal(0, 1, D)), _unite(r.normal(0, 1, D))
    emb = [None, a, a, None, b, b, None]
    assert tr.regrouper_complet(emb, 0.5, durees=[4] * 7) == [1, 1, 1, 1, 2, 2, 2]
    assert tr.regrouper_complet([None, None], 0.5) == [1, 1]
    d = tr.Diariseur(0.5)
    assert [d.attribuer(x, True, 4) for x in emb] == [1, 1, 1, 1, 2, 2, 2]
    assert len(d.etiquettes) == 7


def _voix_synthetique(f0, formant, duree=1.5, graine=0):
    """Son voisé : harmoniques de f0 filtrées autour d'un formant (assez pour distinguer deux « voix »)."""
    t = np.arange(int(duree * SR)) / SR
    r = np.random.default_rng(graine)
    x = sum(np.exp(-((k * f0 - formant) / 600) ** 2) * np.sin(2 * np.pi * k * f0 * t + r.uniform(0, 6))
            for k in range(1, 40) if k * f0 < 7000)
    x *= 1 + 0.3 * np.sin(2 * np.pi * 3 * t)     # syllabes
    return (0.3 * x / np.abs(x).max() + r.normal(0, 0.003, len(t))).astype(np.float32)


def test_empreinte_simple_distingue_deux_voix():
    e = tr.EmpreinteSimple()
    grave1, grave2 = e(_voix_synthetique(110, 700, graine=1)), e(_voix_synthetique(115, 700, graine=2))
    aigu = e(_voix_synthetique(230, 2200, graine=3))
    n = tr._normer
    assert float(n(grave1) @ n(grave2)) > float(n(grave1) @ n(aigu))
    assert float(n(grave1) @ n(grave2)) >= e.seuil
    assert e(np.zeros(100, dtype=np.float32)).shape == grave1.shape    # très court : pas d'erreur


# ---------------------------------------------------------------- audio
def test_reechantillonner():
    x = np.sin(np.linspace(0, 100, 48000)).astype(np.float32)
    assert len(tr.reechantillonner(x, 48000)) == 16000
    assert tr.reechantillonner(x, 16000) is not None and len(tr.reechantillonner(x, 16000)) == 48000


def _parole(duree, f=200.0, amp=0.2):
    t = np.arange(int(duree * SR)) / SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def _silence(duree):
    return np.random.default_rng(0).normal(0, 0.0005, int(duree * SR)).astype(np.float32)


def test_decoupeur_coupe_aux_pauses_et_saute_le_silence():
    flux = np.concatenate([_silence(5), _parole(4), _silence(1), _parole(3.5), _silence(1)])
    d, blocs = tr.Decoupeur(), []
    for i in range(0, len(flux), SR // 10):
        b = d.ajouter(flux[i: i + SR // 10])
        if b is not None:
            blocs.append(b)
    fin = d.vider()
    if fin is not None:
        blocs.append(fin)
    assert len(blocs) == 2
    (d1, b1), (d2, b2) = blocs
    # le silence du début n'est pas transcrit (sauf ~1 s gardée avant la voix : début de phrase faible)
    assert 3.5 <= d1 <= 5.0 and len(b1) / SR >= 4.0
    assert abs((d2 - (d1 + len(b1) / SR))) < 1e-6         # les blocs se suivent sans trou
    assert d2 + len(b2) / SR <= 14.6


def test_decoupeur_coupe_un_long_monologue():
    d, blocs = tr.Decoupeur(duree_max=20.0), []
    for i in range(0, 45 * SR, SR // 10):
        b = d.ajouter(_parole(0.1))
        if b is not None:
            blocs.append(b)
    assert [round(len(b) / SR) for _, b in blocs] == [20, 20]


def test_mixeur_cale_sur_l_horloge_et_melange():
    a, b = tr.Tampon("systeme"), tr.Tampon("micro")
    m = tr.Mixeur([a, b])
    m.lire(100.0)
    a.pousser(np.full(800, 0.25, dtype=np.float32))
    b.pousser(np.full(4800, 0.5, dtype=np.float32), 48000)   # rééchantillonné à 16 kHz : 1600 échantillons
    x = m.lire(100.1)
    assert len(x) == 1600
    assert x[0] == pytest.approx(0.75) and x[1000] == pytest.approx(0.5)   # source muette : silence
    assert len(m.lire(100.1)) == 0
    assert len(m.lire(100.6)) == 8000


def test_tampon_jette_le_retard():
    t = tr.Tampon("x")
    for _ in range(50):                 # 5 s d'avance (à-coup de la source) : rien n'est jeté
        t.pousser(np.zeros(SR // 10, dtype=np.float32))
    assert t.taille == 5 * SR and t.perdu == 0
    for _ in range(150):                # 20 s d'avance : le plus ancien est jeté, le retard est borné
        t.pousser(np.zeros(SR // 10, dtype=np.float32))
    assert t.taille <= tr.Tampon.RETARD_MAX * SR and t.perdu > 0


def test_lire_fichier_wav_stereo_44k(tmp_path):
    f = tmp_path / "a.wav"
    x = (np.sin(np.linspace(0, 2000, 44100)) * 10000).astype(np.int16)
    with wave.open(str(f), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(np.stack([x, x], 1).tobytes())
    y = tr.lire_fichier_audio(f)
    assert abs(len(y) - SR) <= 1 and y.dtype == np.float32 and 0.25 < np.abs(y).max() <= 0.31


# ---------------------------------------------------------------- chaîne complète
@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "DOSSIER_DONNEES", tmp_path / "donnees")
    monkeypatch.setitem(CONFIG, "dossier_transcriptions", str(tmp_path / "export"))
    monkeypatch.setitem(CONFIG, "transcription_seuil", 0)
    tr.ecouteurs.clear()
    yield tmp_path
    if tr.en_cours() is not None:
        tr.arreter()
        tr.en_cours() and tr.en_cours().attendre(10)


class FausseEmpreinte:
    """« Voix » = fréquence dominante (grave : personne A, aiguë : personne B)."""
    nom, seuil = "test", 0.5

    def __call__(self, audio):
        spectre = np.abs(np.fft.rfft(audio))
        f = np.argmax(spectre) * SR / len(audio)
        return np.array([1.0, 0.05] if f < 300 else [0.05, 1.0], dtype=np.float32)


def faux_whisper(audio, langue, contexte=""):
    """Une phrase par bloc, qui dit sa durée et sa « voix »."""
    spectre = np.abs(np.fft.rfft(audio))
    f = np.argmax(spectre) * SR / len(audio)
    voix = "grave" if f < 300 else "aiguë"
    return [(0.0, len(audio) / SR, f"Phrase {voix} de {len(audio) / SR:.0f} secondes.")]


def _reunion(tmp_path):
    """A parle 4 s, B 3,5 s, A 3 s (pauses d'une seconde), écrit dans un WAV."""
    x = np.concatenate([_silence(0.5), _parole(4, 150), _silence(1), _parole(3.5, 450), _silence(1),
                        _parole(3, 150), _silence(1)])
    f = tmp_path / "reunion.wav"
    with wave.open(str(f), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return f


def test_transcription_complete_d_un_fichier(dossiers):
    vus = []
    tr.ecouteurs.append(vus.append)
    s = tr.demarrer("fichier", fichier_audio=str(_reunion(dossiers)), langue="fr", titre="Comité",
                    transcrire=faux_whisper, empreinte=FausseEmpreinte())
    assert tr.en_cours() is not None
    with pytest.raises(ValueError):           # une seule à la fois
        tr.demarrer("micro", transcrire=faux_whisper, empreinte=FausseEmpreinte())
    tr.en_cours().attendre(30)
    assert tr.en_cours() is None
    s = tr.lire(s["id"])
    assert s["etat"] == "terminee", s["erreur"]
    assert [x["locuteur"] for x in s["segments"]] == [1, 2, 1]
    assert [x["texte"].split()[1] for x in s["segments"]] == ["grave", "aiguë", "grave"]
    assert s["segments"][0]["debut"] <= 0.6 and 4.9 <= s["segments"][1]["debut"] <= 5.6
    assert s["duree"] == pytest.approx(14.0, abs=0.2)
    assert s["id"] in vus
    # fichier lisible écrit au fil de l'eau dans le dossier des transcriptions
    md = Path(s["fichier"]).read_text(encoding="utf-8")
    assert Path(s["fichier"]).parent == dossiers / "export" and "Comité" in Path(s["fichier"]).name
    assert "**Locuteur 1** · `00:00`" in md and "**Locuteur 2** · `00:05`" in md
    # l'utilisateur nomme les locuteurs : le fichier suit
    tr.modifier(s["id"], "noms", {"noms": {"1": "Alice", "2": "Bob"}})
    assert "**Alice** · `00:00`" in Path(s["fichier"]).read_text(encoding="utf-8")
    exp = tr.enregistrer_sous(s["id"], "txt")
    assert exp.suffix == ".txt" and "] Bob : Phrase aiguë" in exp.read_text(encoding="utf-8")
    # liste, regroupement à nouveau (empreintes gardées), suppression
    assert [r["id"] for r in tr.lister()] == [s["id"]] and tr.lister()[0]["nb_locuteurs"] == 2
    assert tr.regroupable(s["id"])
    s2 = tr.modifier(s["id"], "regrouper", {"nombre": 1})
    assert {x["locuteur"] for x in s2["segments"]} == {1} and s2["noms"] == {}
    s3 = tr.modifier(s["id"], "regrouper", {"nombre": 0})
    assert [x["locuteur"] for x in s3["segments"]] == [1, 2, 1]
    with pytest.raises(ValueError):
        tr.modifier(s["id"], "inconnue", {})
    assert tr.supprimer(s["id"], avec_fichier=True)
    assert not Path(s["fichier"]).exists() and tr.lire(s["id"]) is None and not tr.regroupable(s["id"])


class FausseCapture:
    """Joue un signal dans un Tampon en temps réel (comme un micro)."""

    def __init__(self, tampon, signal):
        self.tampon, self.signal, self.actif = tampon, signal, False

    def demarrer(self):
        import threading
        self.actif = True

        def jouer():
            for i in range(0, len(self.signal), SR // 20):
                if not self.actif:
                    return
                self.tampon.pousser(self.signal[i: i + SR // 20])
                time.sleep(0.05)
        threading.Thread(target=jouer, daemon=True).start()

    def arreter(self):
        self.actif = False


def test_transcription_en_direct_puis_arret(dossiers):
    t = tr.Tampon("micro")
    signal = np.concatenate([_parole(3.2, 150), _silence(0.8), _parole(3.2, 450), _silence(0.8)])
    s = tr.demarrer("micro", langue="fr", transcrire=faux_whisper, empreinte=FausseEmpreinte(),
                    captures=[(FausseCapture(t, signal), t)])
    debut = time.time()
    while time.time() - debut < 15 and len(tr.en_cours().instantane()["segments"]) < 2:
        time.sleep(0.1)
    en_direct = tr.en_cours().instantane()
    assert en_direct["etat"] == "en_cours" and en_direct["niveau"] >= 0
    assert [x["locuteur"] for x in en_direct["segments"]] == [1, 2]
    with pytest.raises(ValueError):
        tr.modifier(s["id"], "noms", {"noms": {"1": "A"}})      # pas pendant l'enregistrement
    assert tr.arreter()["etat"] in ("en_cours", "finalisation")
    tr.en_cours() and tr.en_cours().attendre(10)
    fin = tr.lire(s["id"])
    assert fin["etat"] == "terminee" and fin["source"] == "micro"
    assert fin["duree"] >= 7.5


def test_erreur_de_capture_et_reprise_apres_fermeture(dossiers):
    class Cassee:
        def demarrer(self):
            raise RuntimeError("micro introuvable")

        def arreter(self):
            pass
    s = tr.demarrer("micro", transcrire=faux_whisper, empreinte=FausseEmpreinte(), captures=[(Cassee(), tr.Tampon("m"))])
    debut = time.time()
    while tr.en_cours() is not None and time.time() - debut < 5:
        time.sleep(0.05)
    s = tr.lire(s["id"])
    assert s["etat"] == "erreur" and "micro introuvable" in s["erreur"]
    # Wesley fermé en pleine réunion : au redémarrage, elle est « interrompue » mais garde son texte
    coupee = _session(id="20261123-090000-dcba", etat="en_cours", segments=[
        {"debut": 0, "fin": 2, "locuteur": 3, "texte": "Bonjour."}])
    tr.DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    (tr.DOSSIER_DONNEES / f"{coupee['id']}.json").write_text(json.dumps(coupee), encoding="utf-8")
    tr.au_demarrage()
    r = tr.lire(coupee["id"])
    assert r["etat"] == "interrompue" and r["segments"][0]["locuteur"] == 1 and r["segments"][0]["texte"] == "Bonjour."


def test_identifiants_invalides(dossiers):
    with pytest.raises(ValueError):
        tr._chemin("../../etc/passwd")
    with pytest.raises(ValueError):
        tr.modifier("../x", "noms", {})
    assert not tr.regroupable("../x")


def test_decoupeur_entend_une_voix_lointaine():
    """Réunion physique : quelqu'un parle loin du micro (voix ~5 fois au-dessus d'un bruit de fond faible)."""
    r = np.random.default_rng(1)
    bruit = lambda s: (r.normal(size=int(s * SR)) * 0.001).astype(np.float32)
    t = np.arange(int(2.0 * SR)) / SR
    voix = (0.006 * np.sin(2 * np.pi * 180 * t) * (1 + 0.3 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)
    flux = np.concatenate([bruit(3.0), voix + bruit(2.0), bruit(1.5)])
    d, blocs = tr.Decoupeur(), []
    for i in range(0, len(flux), SR // 10):
        b = d.ajouter(flux[i:i + SR // 10])
        if b:
            blocs.append(b)
    if (b := d.vider()):
        blocs.append(b)
    assert len(blocs) == 1
    debut, audio = blocs[0]
    assert debut <= 3.0 and debut + len(audio) / SR >= 5.0



# ---------------------------------------------------------------- fidélité du texte (Whisper)
from types import SimpleNamespace as _NS  # noqa: E402


def _mot(debut, fin, mot):
    return _NS(start=debut, end=fin, word=mot, probability=0.9)


def _seg(debut, fin, texte, mots=None, lp=-0.3, ns=0.05, cr=1.4):
    return _NS(start=debut, end=fin, text=texte, words=mots, avg_logprob=lp, no_speech_prob=ns, compression_ratio=cr)


def _machine(monkeypatch, ram_go, coeurs):
    import os
    import types
    monkeypatch.setitem(sys.modules, "psutil", types.SimpleNamespace(
        virtual_memory=lambda: types.SimpleNamespace(total=ram_go * 2 ** 30)))
    monkeypatch.setattr(os, "cpu_count", lambda: coeurs)


def test_modele_auto_selon_la_machine(monkeypatch):
    _machine(monkeypatch, 16, 10)
    assert tr.modele_auto() == "large-v3-turbo" and tr.modele_auto("fichier") == "large-v3-turbo"
    _machine(monkeypatch, 8, 4)           # machine moyenne : pas de large-v3-turbo en direct
    assert tr.modele_auto("micro") == "small" and tr.modele_auto("systeme") == "small"
    assert tr.modele_auto("fichier") == "large-v3-turbo"   # un fichier importé n'a pas à suivre le direct
    _machine(monkeypatch, 4, 2)           # machine faible
    assert tr.modele_auto() == "base" and tr.modele_auto("fichier") == "base"
    for ram, coeurs in [(16, 10), (8, 4), (4, 2), (6, 8)]:
        _machine(monkeypatch, ram, coeurs)
        assert tr.modele_auto() in ("large-v3-turbo", "small", "base")


def test_ancien_reglage_de_modele_ne_bloque_pas_le_mode_auto(monkeypatch, dossiers):
    # réglage d'avant 2.4.0 : « small » enregistré d'office à chaque lancement, sans choix réel
    monkeypatch.setitem(CONFIG, "transcription_modele", "small")
    monkeypatch.delitem(CONFIG, "transcription_modele_choisi", raising=False)
    assert tr.modele_par_defaut() == "auto"
    _machine(monkeypatch, 16, 10)
    t = tr.Transcription("micro")
    assert t.session["modele"] == "large-v3-turbo"            # auto résolu selon la machine
    _machine(monkeypatch, 4, 2)
    assert tr.Transcription("micro").session["modele"] == "base"
    # choix explicite de l'utilisateur (2.4.0 et après) : respecté
    monkeypatch.setitem(CONFIG, "transcription_modele_choisi", True)
    assert tr.modele_par_defaut() == "small" and tr.Transcription("micro").session["modele"] == "small"
    monkeypatch.setitem(CONFIG, "transcription_modele", "auto")
    assert tr.Transcription("micro").session["modele"] == "base"
    monkeypatch.setitem(CONFIG, "transcription_modele", "modele-inconnu")
    assert tr.modele_par_defaut() == "auto"
    # un modèle demandé pour cette transcription passe avant le réglage
    assert tr.Transcription("micro", modele="medium").session["modele"] == "medium"


def test_options_whisper_fideles():
    o = tr.options_whisper("fr", "Cours PHP.")
    assert o["language"] == "fr" and o["temperature"] == 0.0 and o["beam_size"] >= 5
    assert o["condition_on_previous_text"] is False and o["vad_filter"] is True and o["word_timestamps"]
    assert o["initial_prompt"] == "Cours PHP." and o["no_speech_threshold"] and o["log_prob_threshold"]
    assert tr.options_whisper("")["language"] is None          # « Auto » : détection de la langue
    assert "auto" in tr.MODELES_WHISPER and tr.modele_auto() in tr.MODELES_WHISPER


def test_segments_douteux_ecartes():
    assert tr.segment_douteux(_seg(0, 2, "a a a a a a a a", cr=3.1))           # boucle
    assert tr.segment_douteux(_seg(0, 2, "Papira cocktail", lp=-1.6))          # très incertain
    assert tr.segment_douteux(_seg(0, 2, "Bonjour", lp=-1.1, ns=0.8))          # du silence
    assert tr.segment_douteux(_seg(0, 1, "Merci.", lp=-0.8))                   # « Merci. » inventé sur un silence
    assert not tr.segment_douteux(_seg(0, 1, "Merci.", lp=-0.2, ns=0.02))      # un vrai « merci »
    assert not tr.segment_douteux(_seg(0, 4, "On crée le setter de la classe."))
    for texte in ["Sous-titres réalisés par la communauté d'Amara.org", "Merci d'avoir regardé cette vidéo !",
                  "Sous-titrage ST' 501", "...", "[Musique]", "♪ ♪"]:
        assert tr._hallucination(texte), texte
    assert not tr._hallucination("Le constructeur appelle trigger_error si le nom est vide.")


def test_sans_boucles_garde_les_vraies_repetitions():
    assert tr.sans_boucles("et donc et donc et donc et donc et donc on passe au setter") == "et donc on passe au setter"
    assert tr.sans_boucles("non, non, je ne crois pas") == "non, non, je ne crois pas"
    assert tr.sans_boucles("très très bien") == "très très bien"
    assert tr.sans_boucles("oui oui oui oui oui oui oui") == "oui"
    texte = "On utilise $this pour accéder à l'attribut, puis on appelle ucfirst sur le nom."
    assert tr.sans_boucles(texte) == texte          # jamais reformulé


def test_decouper_phrases_aux_pauses_et_a_30_secondes():
    mots = [_mot(0.0, 0.4, " Alors"), _mot(0.5, 0.9, " le"), _mot(1.0, 1.6, " getter."),
            _mot(3.0, 3.5, " Et"), _mot(3.6, 4.2, " le"), _mot(4.3, 4.9, " setter.")]
    res = tr.decouper_phrases([_seg(0.0, 4.9, " Alors le getter. Et le setter.", mots)])
    assert res == [(0.0, 1.6, "Alors le getter."), (3.0, 4.9, "Et le setter.")]
    # un long monologue sans pause : coupé en morceaux d'au plus ~30 s, rien de perdu
    longs = [_mot(i * 0.5, i * 0.5 + 0.4, f" mot{i}" + ("." if i % 20 == 19 else "")) for i in range(150)]
    res = tr.decouper_phrases([_seg(0, 75, "…", longs)])
    assert all(f - d <= 30.5 for d, f, _ in res) and len(res) >= 3
    assert " ".join(t for _, _, t in res).split() == [m.word.strip() for m in longs]
    # segments douteux et hallucinations retirés, doublon exact retiré, segment sans horodatage des mots gardé
    res = tr.decouper_phrases([_seg(0, 2, "Bonjour à tous, on commence."), _seg(2, 4, "Bonjour à tous, on commence."),
                               _seg(5, 7, "Sous-titres réalisés par la communauté d'Amara.org"),
                               _seg(8, 10, "zzz", lp=-2.0), _seg(11, 13, " Ouvrez le fichier index.php. ")])
    assert [t for _, _, t in res] == ["Bonjour à tous, on commence.", "Ouvrez le fichier index.php."]


def test_vocabulaire_et_consigne():
    textes = ["On appelle trigger_error ici.", "Puis trigger_error encore, avec $this.", "Le $this pointe sur l'objet."]
    v = tr.vocabulaire("Cours PHP objet", textes, "Wesley, PDO")
    assert v[:2] == ["Wesley", "PDO"]
    assert "trigger_error" in v and "$this" in v and "setter" in v and "ucfirst" in v and "héritage" in v
    assert len(v) == len({x.lower() for x in v})        # pas de doublon (PDO donné et dans le thème)
    c = tr.consigne_whisper("Cours PHP objet", v)
    assert c.startswith("Cours PHP objet.") and "getter" in c and len(c) <= 600
    assert tr.consigne_whisper("Réunion du 23/11/2026 à 10:00", []) == ""      # titre automatique : inutile
    assert tr.vocabulaire("Point budget", []) == []
    # Whisper qui recopie son amorce sur un passage inaudible : écarté
    assert tr.recopie_consigne("Vocabulaire : PHP, $this, getter, setter.", c)
    assert tr.recopie_consigne("Cours PHP objet.", c)
    assert not tr.recopie_consigne("Le getter renvoie le nom.", c)


def test_tours_de_parole_coupes_aux_pauses_et_a_30_s():
    segs = [{"debut": 2.0 + 5 * i, "fin": 6.5 + 5 * i, "locuteur": 1, "texte": f"Phrase {i}."} for i in range(200)]
    s = _session(segments=segs, duree=1050.0)
    tours = tr.tours_de_parole(s)
    assert len(tours) > 30 and all(t["fin"] - t["debut"] <= 30 for t in tours)
    assert " ".join(t["texte"] for t in tours) == " ".join(x["texte"] for x in segs)   # rien de perdu
    assert tours[0]["debut"] == 2.0 and tours[1]["debut"] == segs[len(tours[0]["texte"].split(". "))]["debut"]
    # une pause de plus de 2 s : nouvel horodatage, même locuteur
    s2 = _session(segments=[{"debut": 0, "fin": 3, "locuteur": 1, "texte": "Un."},
                            {"debut": 6, "fin": 8, "locuteur": 1, "texte": "Deux."}])
    assert [t["debut"] for t in tr.tours_de_parole(s2)] == [0, 6]
    md = tr.exporter(s2, "md")
    assert md.count("**Locuteur 1**") == 1 and "`00:06` Deux." in md


def test_extrait_par_parties_sans_rien_perdre():
    segs = [{"debut": 10.0 * i, "fin": 10.0 * i + 8, "locuteur": 1 + i % 2, "texte": f"Phrase numéro {i} " + "x" * 80}
            for i in range(300)]          # 50 minutes, ~30 000 caractères
    s = _session(segments=segs, duree=3000.0)
    premiere = tr.extrait(s)
    assert "Partie 1/" in premiere and "partie=2" in premiere and len(premiere) < 12000
    total = int(premiere.split("Partie 1/")[1].split(" ")[0])
    lu = "".join(tr.extrait(s, partie=p) for p in range(1, total + 1))
    for i in range(300):
        assert f"Phrase numéro {i} " in lu, i
    assert "partie=" not in tr.extrait(s, partie=total)
    # par minutes : de 10 à 12 min
    passage = tr.extrait(s, debut=10, fin=12)
    assert "Passage de 10:00 à 12:00" in passage and "[10:00]" in passage and "[11:50]" in passage
    assert "[09:50]" not in passage and "[12:00]" not in passage
    assert "rien de transcrit" in tr.extrait(_session(segments=[]))


def test_regrouper_session_avec_empreinte_manquante(dossiers):
    r = np.random.default_rng(2)
    a, b = _unite(r.normal(0, 1, D)), _unite(r.normal(0, 1, D))
    s = _session(id="20261123-110000-beef", segments=[
        {"debut": 4 * i, "fin": 4 * i + 3.5, "locuteur": 9, "texte": f"P{i}"} for i in range(6)])
    tr.sauver(s)
    tr.sauver_empreintes(s["id"], [a, None, a, b, None, b], [True] * 6, [3.5] * 6)
    res = tr.modifier(s["id"], "regrouper", {"nombre": 0})
    assert [x["locuteur"] for x in res["segments"]] == [1, 1, 1, 2, 2, 2]


def test_decoupeur_coupe_un_long_bloc_dans_un_creux():
    """Monologue de 25 s sans vraie pause, avec un petit creux (fin de mot) vers 18,5 s : coupé là, pas à 20 s."""
    voix = _parole(25.0)
    voix[int(18.5 * SR): int(18.6 * SR)] *= 0.05
    d, blocs = tr.Decoupeur(duree_max=20.0), []
    for i in range(0, len(voix), SR // 10):
        b = d.ajouter(voix[i: i + SR // 10])
        if b is not None:
            blocs.append(b)
    fin = d.vider()
    assert len(blocs) == 1 and 18.4 <= len(blocs[0][1]) / SR <= 18.7
    assert fin is not None and abs(fin[0] - len(blocs[0][1]) / SR) < 1e-6          # la suite n'est pas perdue
    assert len(blocs[0][1]) + len(fin[1]) == len(voix)


class FausseEmpreinteFragile(FausseEmpreinte):
    """Comme FausseEmpreinte, mais échoue de temps en temps (empreinte impossible à calculer)."""
    n = 0

    def __call__(self, audio):
        FausseEmpreinteFragile.n += 1
        if FausseEmpreinteFragile.n == 2:
            raise RuntimeError("trop court")
        return super().__call__(audio)


def test_rien_de_perdu_entre_le_direct_et_la_fin(dossiers):
    """Le texte du direct est gardé tel quel à la fin, les numéros sont 1, 2… sans trou, même si une
    empreinte vocale a échoué (avant : regroupement final sauté, numéros du direct gardés)."""
    FausseEmpreinteFragile.n = 0
    vus = []
    s = tr.demarrer("fichier", fichier_audio=str(_reunion(dossiers)), langue="fr", titre="Cours PHP objet",
                    transcrire=lambda a, l, c="": vus.append(c) or faux_whisper(a, l, c),
                    empreinte=FausseEmpreinteFragile())
    tr.en_cours().attendre(30)
    fin = tr.lire(s["id"])
    assert fin["etat"] == "terminee" and len(fin["segments"]) == 3
    # la 2e phrase n'a pas d'empreinte : elle suit la précédente, et le regroupement final a bien eu lieu
    assert [x["locuteur"] for x in fin["segments"]] == [1, 1, 1]
    assert tr.regroupable(s["id"])
    assert [x["texte"].split()[1] for x in fin["segments"]] == ["grave", "aiguë", "grave"]
    md = Path(fin["fichier"]).read_text(encoding="utf-8")
    assert all(x["texte"] in md for x in fin["segments"])
    # l'amorce de Whisper contient le titre et le vocabulaire du sujet
    assert vus and vus[0].startswith("Cours PHP objet.") and "setter" in vus[0]
    assert fin["modele"] in tr.MODELES_WHISPER and fin["modele"] != "auto"


# ---------------------------------------------------------------- 2.5.0 : aucune phrase perdue
def test_filtres_ne_jettent_pas_les_vraies_phrases():
    # vraies phrases qui contenaient un mot des filtres : gardées
    for texte in ["Ajoute un sous-titre à la page d'accueil.", "Le sous-titrage de la vidéo est en retard.",
                  "Radio-Canada en a parlé hier soir.",
                  "Sur la chaîne, on dit toujours abonnez-vous à la fin, mais nous on ne le fait pas dans ce cours."]:
        assert not tr._hallucination(texte), texte
    # vraies hallucinations : toujours écartées
    for texte in ["Sous-titres réalisés par la communauté d'Amara.org", "Sous-titrage Société Radio-Canada",
                  "Abonnez-vous à la chaîne !", "Thanks for watching!", "♪ ♪ ♪"]:
        assert tr._hallucination(texte), texte
    # amorce de Whisper : une phrase qui cite un mot du vocabulaire n'est plus prise pour une recopie
    consigne = tr.consigne_whisper("Cours PHP", ["PHP", "getter", "setter", "constructeur"])
    assert not tr.recopie_consigne("le constructeur", consigne)
    assert not tr.recopie_consigne("getter setter", consigne)
    assert not tr.recopie_consigne("On crée le getter et le setter.", consigne)
    assert tr.recopie_consigne("Vocabulaire : PHP, getter", consigne)
    assert tr.recopie_consigne("getter, setter, constructeur.", consigne)
    assert tr.recopie_consigne("Cours PHP.", consigne)


def test_phrase_redite_plus_tard_gardee():
    p = " On passe à la suite du cours."
    segs = [_seg(0.0, 2.0, p), _seg(2.1, 4.0, p), _seg(30.0, 32.0, p)]
    res = tr.decouper_phrases(segs)
    assert [d for d, _, _ in res] == [0.0, 30.0]       # doublon collé écarté, vraie redite gardée


def test_bloc_transcrit_meme_si_whisper_echoue_une_fois(dossiers):
    essais = []

    def capricieux(audio, langue, consigne=""):
        essais.append(consigne)
        if len(essais) == 1:
            raise RuntimeError("mémoire insuffisante")
        return faux_whisper(audio, langue, consigne)
    s = tr.demarrer("fichier", fichier_audio=str(_reunion(dossiers)), langue="fr", titre="Cours PHP",
                    transcrire=capricieux, empreinte=FausseEmpreinte())
    tr.en_cours().attendre(30)
    fin = tr.lire(s["id"])
    assert fin["etat"] == "terminee" and len(fin["segments"]) == 3      # le 1er bloc n'est pas perdu
    assert essais[1] == ""                                              # 2e essai sans amorce


def test_arret_juste_apres_la_derniere_phrase(dossiers):
    """Arrêt pendant que la personne finit sa phrase : le son encore en route est transcrit."""
    t = tr.Tampon("micro")
    capture = FausseCapture(t, np.concatenate([_silence(0.5), _parole(3.0, 150)]))
    s = tr.demarrer("micro", langue="fr", transcrire=faux_whisper, empreinte=FausseEmpreinte(),
                    captures=[(capture, t)])
    while t.recu < int(3.5 * SR) - SR // 20:
        time.sleep(0.01)
    tr.arreter()
    tr.en_cours() and tr.en_cours().attendre(10)
    fin = tr.lire(s["id"])
    assert len(fin["segments"]) == 1
    assert fin["segments"][0]["fin"] >= 3.4 and fin["duree"] >= 3.5


# ---------------------------------------------------------------- 2.5.0 : reprendre une transcription
class FausseEmpreinte3(FausseEmpreinte):
    """Trois voix : grave (< 300 Hz), médium (< 600 Hz), aiguë."""

    def __call__(self, audio):
        f = np.argmax(np.abs(np.fft.rfft(audio))) * SR / len(audio)
        return np.array([1.0, 0.05, 0.05] if f < 300 else [0.05, 1.0, 0.05] if f < 600 else [0.05, 0.05, 1.0],
                        dtype=np.float32)


def _wav(tmp_path, nom, x):
    f = tmp_path / nom
    with wave.open(str(f), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return f


def test_rattacher_garde_les_locuteurs_d_avant():
    # mêmes voix, numérotées autrement par le regroupement : les anciens numéros sont repris, la voix nouvelle = 3
    assert tr.rattacher([1, 2, 1], [2, 1, 2, 1, 3, 2]) == [1, 2, 1, 2, 3, 1]
    # les anciennes phrases gardent leur locuteur même si le regroupement les a mélangées (corrections, noms)
    assert tr.rattacher([1, 2], [1, 1, 1])[:2] == [1, 2]
    # une phrase d'avant de 0,5 s mal regroupée ne suffit pas à rattacher une voix nouvelle de 20 s
    assert tr.rattacher([1, 2], [1, 3, 3, 3], durees=[10, 0.5, 20, 20]) == [1, 2, 3, 3]
    # phrases d'avant sans empreinte : elles ne votent pas ; numéros après le plus grand ancien (depart)
    assert tr.rattacher([1, 2], [1, 1, 1, 2], valides=[False, False, True, True]) == [1, 2, 3, 4]
    assert tr.rattacher([], [1, 2, 1], depart=4) == [5, 6, 5]


def test_reprendre_une_transcription_terminee(dossiers):
    voix = FausseEmpreinte3()
    s = tr.demarrer("fichier", fichier_audio=str(_reunion(dossiers)), langue="fr", titre="Comité",
                    transcrire=faux_whisper, empreinte=voix)
    tr.en_cours().attendre(30)
    avant = tr.modifier(s["id"], "noms", {"noms": {"1": "Alice", "2": "Bob"}})
    assert [x["locuteur"] for x in avant["segments"]] == [1, 2, 1] and avant["etat"] == "terminee"
    with pytest.raises(ValueError):
        tr.reprendre("20990101-000000-0000", transcrire=faux_whisper, empreinte=voix)
    # la suite : Bob (médium), puis une nouvelle personne (aiguë), puis Alice (grave)
    suite = _wav(dossiers, "suite.wav", np.concatenate([_silence(0.5), _parole(3.5, 450), _silence(1),
                                                        _parole(4, 900), _silence(1), _parole(3, 150), _silence(1)]))
    r = tr.reprendre(s["id"], source="fichier", fichier_audio=str(suite), transcrire=faux_whisper, empreinte=voix)
    assert r["id"] == s["id"] and len(r["segments"]) == 3
    with pytest.raises(ValueError):           # une seule à la fois
        tr.reprendre(s["id"], transcrire=faux_whisper, empreinte=voix)
    tr.en_cours().attendre(30)
    fin = tr.lire(s["id"])
    assert fin["etat"] == "terminee", fin["erreur"]
    assert [x["locuteur"] for x in fin["segments"]] == [1, 2, 1, 2, 3, 1]
    assert fin["segments"][:3] == avant["segments"]             # rien d'avant n'a bougé
    assert fin["noms"] == {"1": "Alice", "2": "Bob"} and fin["titre"] == "Comité"
    assert fin["debut"] == avant["debut"]                       # date d'origine gardée
    # horodatage continu : la suite commence après la fin d'avant
    assert all(x["debut"] >= avant["duree"] for x in fin["segments"][3:])
    assert fin["duree"] == pytest.approx(avant["duree"] + 14.0, abs=0.3)
    assert len(fin["reprises"]) == 1 and fin["reprises"][0]["position"] == pytest.approx(avant["duree"], abs=0.1)
    md = Path(fin["fichier"]).read_text(encoding="utf-8")
    assert "Reprise le" in md and "**Alice** · `00:00`" in md and "**Locuteur 3**" in md
    assert md.index(avant["segments"][2]["texte"]) < md.index("Reprise le")      # repère entre les deux parties
    # empreintes de toutes les phrases gardées : « refaire la répartition » marche encore
    assert tr.regroupable(s["id"])
    assert [x["locuteur"] for x in tr.modifier(s["id"], "regrouper", {"nombre": 0})["segments"]] == [1, 2, 1, 2, 3, 1]


def test_reprendre_en_direct_sans_empreintes_d_avant(dossiers):
    """Transcription interrompue d'une ancienne version (pas d'empreintes) : la suite s'ajoute, ses voix
    prennent les numéros suivants, les phrases d'avant ne bougent pas."""
    ancienne = _session(id="20261120-090000-abab", etat="interrompue", duree=0.0)
    tr.sauver(ancienne)
    t = tr.Tampon("micro")
    signal = np.concatenate([_parole(3.2, 150), _silence(0.8), _parole(3.2, 900), _silence(0.8)])
    tr.reprendre(ancienne["id"], transcrire=faux_whisper, empreinte=FausseEmpreinte3(),
                 captures=[(FausseCapture(t, signal), t)])
    debut = time.time()
    while time.time() - debut < 15 and len(tr.en_cours().instantane()["segments"]) < 7:
        time.sleep(0.1)
    en_direct = tr.en_cours().instantane()
    assert en_direct["etat"] == "en_cours" and en_direct["duree"] >= 75.0
    assert [x["locuteur"] for x in en_direct["segments"]] == [1, 1, 2, 3, 1, 4, 5]
    tr.arreter()
    tr.en_cours() and tr.en_cours().attendre(10)
    fin = tr.lire(ancienne["id"])
    assert fin["etat"] == "terminee" and fin["source"] == "micro"
    assert [x["locuteur"] for x in fin["segments"]] == [1, 1, 2, 3, 1, 4, 5]
    assert fin["segments"][:5] == ancienne["segments"]
    assert fin["segments"][5]["debut"] >= 75.0                   # après la dernière phrase d'avant
