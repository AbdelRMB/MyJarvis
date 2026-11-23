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
    assert 4.0 <= d1 <= 5.0 and len(b1) / SR >= 4.0      # le silence du début n'est pas transcrit
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
    for _ in range(50):
        t.pousser(np.zeros(SR // 10, dtype=np.float32))
    assert t.taille <= 3 * SR


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
