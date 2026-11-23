"""Transcription de réunions et de conversations, 100 % locale (onglet « Transcription »).

Deux sources au choix :
- « micro »   : réunion physique, Wesley écoute la pièce ;
- « systeme » : réunion en ligne, le son qui sort de l'ordinateur (macOS : ScreenCaptureKit, sans pilote à
               installer ; Windows : WASAPI loopback). En option, ton micro est mélangé au son du PC pour
               que ta propre voix soit aussi transcrite.

Chaîne de traitement (rien ne quitte l'ordinateur) :
  capture -> Mixeur (16 kHz mono, calé sur l'horloge) -> Decoupeur (blocs coupés aux pauses)
          -> Whisper local (faster-whisper) -> empreinte vocale de chaque phrase (sherpa-onnx, modèle
             WeSpeaker CAM++ téléchargé une fois ; à défaut, empreinte spectrale simple en numpy)
          -> Diariseur (regroupement des voix : Locuteur 1, Locuteur 2…)
À l'arrêt, toutes les phrases sont regroupées une dernière fois (classification hiérarchique), ce qui corrige
les erreurs du regroupement en direct. L'utilisateur renomme et trie ensuite les locuteurs dans l'interface.

Fichiers : RACINE/transcriptions/<id>.json (données) et un fichier Markdown lisible, réécrit au fil de l'eau,
dans ~/Documents/Wesley/Transcriptions (CONFIG["dossier_transcriptions"] pour en changer).
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from .config import CONFIG, RACINE

SR = 16000
DOSSIER_DONNEES = RACINE / "transcriptions"
DOSSIER_MODELES = RACINE / "modeles"
MODELE_LOCUTEURS = "wespeaker_en_voxceleb_CAM++.onnx"   # ~28 Mo, reconnaissance du locuteur (indépendant de la langue)
URL_MODELE_LOCUTEURS = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
                        + MODELE_LOCUTEURS.replace("+", "%2B"))
MODELES_WHISPER = ["base", "small", "medium", "large-v3-turbo"]
DUREE_FIABLE = 1.0          # s : en dessous, l'empreinte d'une phrase est trop courte pour être sûre
ecouteurs: list = []        # fonctions appelées à chaque changement (web.py : diffusion vers l'interface)


# ====================================================================================================
# Mise en forme, renommage, tri (pur Python : testable sans dépendance)
# ====================================================================================================
def horodatage(secondes: float) -> str:
    """12.3 -> « 00:12 » ; 3725 -> « 1:02:05 »."""
    s = int(max(0, secondes))
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def nom_locuteur(session: dict, locuteur) -> str:
    nom = (session.get("noms") or {}).get(str(locuteur), "").strip()
    return nom or f"Locuteur {locuteur}"


def locuteurs(session: dict) -> list[dict]:
    """Locuteurs présents, dans l'ordre d'apparition, avec leur temps de parole."""
    vus: dict[int, dict] = {}
    for s in session.get("segments", []):
        l = int(s["locuteur"])
        e = vus.setdefault(l, {"id": l, "nom": nom_locuteur(session, l), "duree": 0.0, "phrases": 0})
        e["duree"] += max(0.0, s["fin"] - s["debut"])
        e["phrases"] += 1
    for e in vus.values():
        e["duree"] = round(e["duree"], 1)
    return list(vus.values())


def tours_de_parole(session: dict) -> list[dict]:
    """Phrases consécutives d'un même locuteur réunies en un seul tour de parole."""
    tours: list[dict] = []
    for s in session.get("segments", []):
        texte = s["texte"].strip()
        if not texte:
            continue
        if tours and tours[-1]["locuteur"] == s["locuteur"] and s["debut"] - tours[-1]["fin"] < 30:
            tours[-1]["texte"] += " " + texte
            tours[-1]["fin"] = s["fin"]
        else:
            tours.append({"locuteur": s["locuteur"], "debut": s["debut"], "fin": s["fin"], "texte": texte})
    return tours


def exporter(session: dict, format: str = "md") -> str:
    """Transcription complète en Markdown (« md ») ou en texte brut (« txt »)."""
    debut = datetime.fromtimestamp(session.get("debut") or time.time())
    titre = session.get("titre") or "Transcription"
    duree = horodatage(session.get("duree", 0))
    source = {"micro": "micro", "systeme": "son de l'ordinateur", "fichier": "fichier audio importé"}.get(session.get("source"), session.get("source", ""))
    if session.get("source") == "systeme" and session.get("avec_micro"):
        source += " + micro"
    noms = ", ".join(l["nom"] for l in locuteurs(session)) or "—"
    tours = tours_de_parole(session)
    if format == "txt":
        lignes = [titre, debut.strftime("%d/%m/%Y %H:%M") + f" · durée {duree} · source : {source}",
                  f"Participants : {noms}", ""]
        lignes += [f"[{horodatage(t['debut'])}] {nom_locuteur(session, t['locuteur'])} : {t['texte']}" for t in tours]
        return "\n".join(lignes).rstrip() + "\n"
    lignes = [f"# {titre}", "",
              f"- **Date** : {debut.strftime('%d/%m/%Y %H:%M')}",
              f"- **Durée** : {duree}",
              f"- **Source** : {source}",
              f"- **Participants** : {noms}", "", "---", ""]
    for t in tours:
        lignes += [f"**{nom_locuteur(session, t['locuteur'])}** · `{horodatage(t['debut'])}`", "", t["texte"], ""]
    if not tours:
        lignes.append("_(rien n'a encore été transcrit)_")
    return "\n".join(lignes).rstrip() + "\n"


def renommer(session: dict, noms: dict) -> dict:
    """noms : {"1": "Alice", "2": "Bob"} ; un nom vide rend « Locuteur N »."""
    actuels = dict(session.get("noms") or {})
    for k, v in (noms or {}).items():
        v = re.sub(r"\s+", " ", str(v or "")).strip()[:60]
        if v:
            actuels[str(int(k))] = v
        else:
            actuels.pop(str(int(k)), None)
    session["noms"] = actuels
    return session


def fusionner(session: dict, source: int, cible: int) -> dict:
    """Toutes les phrases de « source » passent à « cible » (deux étiquettes pour une même personne)."""
    source, cible = int(source), int(cible)
    if source != cible:
        for s in session.get("segments", []):
            if s["locuteur"] == source:
                s["locuteur"] = cible
        if str(cible) not in (session.get("noms") or {}) and str(source) in (session.get("noms") or {}):
            session["noms"][str(cible)] = session["noms"][str(source)]
        (session.get("noms") or {}).pop(str(source), None)
    return session


def changer_locuteur(session: dict, index: int, locuteur: int) -> dict:
    """Une phrase attribuée à la mauvaise personne. locuteur = 0 : nouveau locuteur."""
    segs = session.get("segments", [])
    if not 0 <= index < len(segs):
        raise ValueError("Phrase introuvable.")
    locuteur = int(locuteur)
    if locuteur <= 0:
        locuteur = max((s["locuteur"] for s in segs), default=0) + 1
    segs[index]["locuteur"] = locuteur
    return session


def corriger_texte(session: dict, index: int, texte: str) -> dict:
    segs = session.get("segments", [])
    if not 0 <= index < len(segs):
        raise ValueError("Phrase introuvable.")
    segs[index]["texte"] = str(texte).strip()
    return session


def renumeroter(etiquettes: list[int]) -> list[int]:
    """Étiquettes quelconques -> 1, 2, 3… dans l'ordre de première apparition."""
    table: dict[int, int] = {}
    return [table.setdefault(e, len(table) + 1) for e in etiquettes]


def nom_de_fichier(texte: str) -> str:
    texte = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", texte)
    return re.sub(r"\s+", " ", texte).strip(" .")[:80] or "Transcription"


# ====================================================================================================
# Diarisation : qui parle ? (numpy)
# ====================================================================================================
def _normer(v):
    import numpy as np
    v = np.nan_to_num(np.asarray(v, dtype=np.float32).ravel())
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


class Diariseur:
    """Regroupement en direct : chaque phrase va au locuteur dont la voix ressemble le plus à la sienne
    (similarité cosinus des empreintes), ou crée un nouveau locuteur si personne n'est assez proche."""

    def __init__(self, seuil: float = 0.5):
        self.seuil = seuil
        self.centres: list = []     # somme des empreintes normées de chaque locuteur
        self.poids: list[float] = []
        self.dernier = 0

    def similarites(self, e):
        import numpy as np
        if not self.centres:
            return np.zeros(0, dtype=np.float32)
        c = np.stack([_normer(x) for x in self.centres])
        return c @ _normer(e)

    def attribuer(self, empreinte, fiable: bool = True) -> int:
        """Renvoie le numéro du locuteur (1, 2…). Phrase trop courte (pas fiable) : locuteur le plus proche
        s'il est clairement reconnu, sinon le précédent, sans modifier les voix connues."""
        e = _normer(empreinte)
        sims = self.similarites(e)
        meilleur = int(sims.argmax()) if len(sims) else -1
        if not fiable:
            if meilleur >= 0 and sims[meilleur] >= self.seuil + 0.1:
                self.dernier = meilleur + 1
            elif not self.dernier:
                self.centres.append(e)
                self.poids.append(0.0)
                self.dernier = len(self.centres)
            return self.dernier
        if meilleur >= 0 and sims[meilleur] >= self.seuil:
            self.centres[meilleur] = self.centres[meilleur] + e
            self.poids[meilleur] += 1
            self.dernier = meilleur + 1
        else:
            self.centres.append(e)
            self.poids.append(1.0)
            self.dernier = len(self.centres)
        return self.dernier


def regrouper(empreintes: list, seuil: float = 0.5, nombre: int = 0, fiables: list[bool] | None = None,
              durees: list[float] | None = None) -> list[int]:
    """Regroupement final de toutes les phrases (classification hiérarchique, lien moyen, cosinus).
    nombre > 0 : exactement ce nombre de locuteurs (si l'utilisateur l'a indiqué). Les phrases courtes
    (fiables[i] False) rejoignent ensuite le groupe le plus proche. Renvoie 1, 2… par ordre d'apparition."""
    import numpy as np
    n = len(empreintes)
    if n == 0:
        return []
    fiables = list(fiables) if fiables is not None else [True] * n
    durees = list(durees) if durees is not None else [1.0] * n
    X = np.stack([_normer(e) for e in empreintes])
    idx = [i for i in range(n) if fiables[i]] or list(range(n))
    groupes = [[i] for i in idx]
    S = X[idx] @ X[idx].T            # similarités entre phrases fiables
    # similarité moyenne entre groupes (lien moyen), mise à jour à chaque fusion
    M = S.astype(np.float64).copy()
    np.fill_diagonal(M, -np.inf)
    taille = [1] * len(groupes)
    actifs = list(range(len(groupes)))
    while len(actifs) > 1:
        sous = M[np.ix_(actifs, actifs)]
        k = int(np.argmax(sous))
        a, b = actifs[k // len(actifs)], actifs[k % len(actifs)]
        meilleure = sous.flat[k]
        if nombre > 0:
            if len(actifs) <= nombre:
                break
        elif meilleure < seuil:
            break
        # fusion de b dans a
        for c in actifs:
            if c not in (a, b):
                M[a, c] = M[c, a] = (M[a, c] * taille[a] + M[b, c] * taille[b]) / (taille[a] + taille[b])
        groupes[a] += groupes[b]
        taille[a] += taille[b]
        actifs.remove(b)
    etiquette = [-1] * n
    for g in actifs:
        for i in groupes[g]:
            etiquette[i] = g
    # tout petits groupes (une seule phrase très courte) : rattachés au groupe le plus proche
    centres = {g: _normer(X[groupes[g]].sum(0)) for g in actifs}
    if nombre <= 0 and len(actifs) > 1:
        for g in list(actifs):
            if len(groupes[g]) == 1 and durees[groupes[g][0]] < 2.0 and len(actifs) > 1:
                autres = [h for h in actifs if h != g]
                proche = max(autres, key=lambda h: float(centres[h] @ X[groupes[g][0]]))
                for i in groupes[g]:
                    etiquette[i] = proche
                groupes[proche] += groupes[g]
                actifs.remove(g)
                centres[proche] = _normer(X[groupes[proche]].sum(0))
    # phrases courtes : groupe le plus proche
    for i in range(n):
        if etiquette[i] < 0:
            etiquette[i] = max(actifs, key=lambda h: float(centres[h] @ X[i]))
    return renumeroter(etiquette)


# ====================================================================================================
# Empreintes vocales
# ====================================================================================================
class EmpreinteSherpa:
    """Empreinte d'un locuteur par un réseau neuronal (WeSpeaker CAM++, ONNX, exécuté par sherpa-onnx)."""
    nom = "sherpa-onnx (CAM++)"
    seuil = 0.5             # similarité cosinus au-dessus de laquelle deux phrases sont de la même voix

    def __init__(self, chemin: Path):
        import sherpa_onnx
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(chemin), num_threads=2, debug=False,
                                                          provider="cpu")
        if not cfg.validate():
            raise RuntimeError("modèle de reconnaissance du locuteur invalide")
        self._ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)

    def __call__(self, audio):
        flux = self._ext.create_stream()
        flux.accept_waveform(SR, audio)
        flux.input_finished()
        import numpy as np
        return np.array(self._ext.compute(flux), dtype=np.float32)


class EmpreinteSimple:
    """Secours sans réseau neuronal : statistiques du spectre (MFCC moyens et écarts-types, hauteur de voix).
    Distingue bien des voix très différentes (homme / femme), moins bien des voix proches."""
    nom = "spectrale simple"
    seuil = 0.95

    def __init__(self):
        import numpy as np
        self.n_fft, self.pas, n_mel = 512, 160, 40
        f = np.linspace(0, SR / 2, self.n_fft // 2 + 1)
        mel = lambda h: 2595 * np.log10(1 + h / 700)
        bornes = 700 * (10 ** (np.linspace(mel(60), mel(7600), n_mel + 2) / 2595) - 1)
        self.banc = np.zeros((n_mel, len(f)), dtype=np.float32)
        for i in range(n_mel):
            g, c, d = bornes[i:i + 3]
            self.banc[i] = np.clip(np.minimum((f - g) / (c - g), (d - f) / (d - c)), 0, None)
        k = np.arange(n_mel)
        self.dct = np.cos(np.pi / n_mel * (k[None, :] + 0.5) * np.arange(1, 21)[:, None]).astype(np.float32)
        self.fenetre = np.hanning(self.n_fft).astype(np.float32)

    def __call__(self, audio):
        import numpy as np
        x = np.asarray(audio, dtype=np.float32)
        if len(x) < self.n_fft:
            x = np.pad(x, (0, self.n_fft - len(x)))
        x = np.append(x[0], x[1:] - 0.97 * x[:-1])
        n = 1 + (len(x) - self.n_fft) // self.pas
        trames = np.lib.stride_tricks.as_strided(x, (n, self.n_fft), (x.strides[0] * self.pas, x.strides[0]))
        energie = (trames ** 2).mean(1)
        garde = energie > max(energie.max() * 0.01, 1e-8)      # trames de voix seulement
        if garde.sum() < 2:
            garde[:] = True
        spectre = np.abs(np.fft.rfft(trames[garde] * self.fenetre)) ** 2
        brut = np.log(spectre @ self.banc.T + 1e-8)       # énergie par bande (échelle de Mel)
        mfcc = brut @ self.dct.T
        # timbre moyen (indépendant du volume), variabilité par bande et par coefficient
        v = np.concatenate([brut.mean(0) - brut.mean(), brut.std(0), mfcc.std(0)])
        return (v - v.mean()).astype(np.float32)


def telecharger_modele_locuteurs() -> Path:
    """Modèle de reconnaissance du locuteur : téléchargé une fois (~28 Mo), puis entièrement hors ligne."""
    chemin = DOSSIER_MODELES / MODELE_LOCUTEURS
    if chemin.exists() and chemin.stat().st_size > 1_000_000:
        return chemin
    import requests
    DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".part")
    with requests.get(URL_MODELE_LOCUTEURS, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for morceau in r.iter_content(1 << 16):
                f.write(morceau)
    tmp.replace(chemin)
    return chemin


def charger_empreinte():
    """Le meilleur extracteur disponible : sherpa-onnx (si installé et modèle téléchargeable), sinon le simple."""
    try:
        return EmpreinteSherpa(telecharger_modele_locuteurs())
    except Exception as e:
        print(f"  (transcription : reconnaissance neuronale des voix indisponible, méthode simple : {e})")
        return EmpreinteSimple()


# ====================================================================================================
# Découpage du flux en blocs (aux pauses)
# ====================================================================================================
class Decoupeur:
    """Accumule le son et rend des blocs (début en s, audio) coupés à une pause, pour que Whisper ait des
    phrases entières et qu'un changement de locuteur tombe le plus souvent entre deux blocs."""

    def __init__(self, duree_min=3.0, duree_max=20.0, pause=0.5):
        self.duree_min, self.duree_max, self.pause = duree_min, duree_max, pause
        self.morceaux: list = []
        self.taille = 0
        self.debut = 0.0            # position (s) du début du bloc en cours dans l'enregistrement
        self.silence = 0.0          # s de silence à la fin du bloc en cours
        self.voix = False           # le bloc contient de la voix
        self.bruit = 0.0015         # niveau du silence ambiant (moyenne glissante)

    def seuil(self):
        # bas exprès : en réunion physique, une voix à l'autre bout de la table arrive faible dans le micro
        # (le filtre de voix de Whisper écarte ensuite le bruit seul)
        return max(self.bruit * 2.5, 0.003)

    def ajouter(self, x) -> tuple[float, object] | None:
        import numpy as np
        if not len(x):
            return None
        rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float32))))
        if rms < self.seuil():
            self.bruit = 0.95 * self.bruit + 0.05 * rms
            self.silence += len(x) / SR
        else:
            self.silence = 0.0
            self.voix = True
        self.morceaux.append(x)
        self.taille += len(x)
        duree = self.taille / SR
        if not self.voix and duree > 2 * self.pause:
            # que du silence : on avance sans rien transcrire (on garde la fin, au cas où une phrase commence)
            garde = int(self.pause * SR)
            tout = np.concatenate(self.morceaux)
            self.debut += (len(tout) - garde) / SR
            self.morceaux, self.taille, self.silence = [tout[-garde:]], garde, min(self.silence, self.pause)
            return None
        if (duree >= self.duree_min and self.silence >= self.pause) or duree >= self.duree_max:
            return self.vider()
        return None

    def vider(self):
        import numpy as np
        if not self.morceaux:
            return None
        bloc, debut, voix = np.concatenate(self.morceaux), self.debut, self.voix
        self.debut += len(bloc) / SR
        self.morceaux, self.taille, self.silence, self.voix = [], 0, 0.0, False
        return (debut, bloc) if voix else None


# ====================================================================================================
# Sources audio
# ====================================================================================================
def reechantillonner(x, sr: float):
    import numpy as np
    x = np.asarray(x, dtype=np.float32)
    if int(sr) == SR or not len(x):
        return x
    n = int(round(len(x) * SR / sr))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class Tampon:
    """File de son d'une source, alimentée par son fil de capture (sûre entre fils)."""

    def __init__(self, nom: str):
        self.nom = nom
        self.morceaux: list = []
        self.taille = 0
        self.verrou = threading.Lock()
        self.erreur = ""
        self.recu = 0               # échantillons reçus (diagnostic : la source envoie-t-elle du son ?)

    def pousser(self, x, sr: float = SR):
        x = reechantillonner(x, sr)
        with self.verrou:
            self.morceaux.append(x)
            self.taille += len(x)
            self.recu += len(x)
            if self.taille > SR * 3:        # en retard de plus de 3 s : on jette le plus ancien
                import numpy as np
                tout = np.concatenate(self.morceaux)[-SR:]
                self.morceaux, self.taille = [tout], len(tout)

    def prendre(self, n: int):
        import numpy as np
        with self.verrou:
            if not self.morceaux:
                return np.zeros(n, dtype=np.float32)
            tout = np.concatenate(self.morceaux)
            pris, reste = tout[:n], tout[n:]
            self.morceaux, self.taille = ([reste] if len(reste) else []), len(reste)
        return np.pad(pris, (0, n - len(pris))) if len(pris) < n else pris


class Mixeur:
    """Mélange les sources et les cale sur l'horloge : une source muette (WASAPI n'envoie rien quand le PC est
    silencieux) devient du silence, et les horodatages restent ceux de la réunion."""

    def __init__(self, tampons: list[Tampon]):
        self.tampons = tampons
        self.t0 = None
        self.emis = 0

    def lire(self, maintenant: float | None = None):
        import numpy as np
        maintenant = time.monotonic() if maintenant is None else maintenant
        if self.t0 is None:
            self.t0 = maintenant
        n = round((maintenant - self.t0) * SR) - self.emis
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        self.emis += n
        x = sum(t.prendre(n) for t in self.tampons)
        return np.clip(x, -1.0, 1.0).astype(np.float32)


class CaptureMicro:
    def __init__(self, tampon: Tampon):
        self.tampon, self._flux = tampon, None

    def demarrer(self):
        import sounddevice as sd

        def rappel(donnees, *_):
            self.tampon.pousser(donnees[:, 0].copy())
        self._flux = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=1600, callback=rappel)
        self._flux.start()

    def arreter(self):
        if self._flux is not None:
            try:
                self._flux.stop()
                self._flux.close()
            finally:
                self._flux = None


class CaptureSystemeMac:
    """Son de tout le Mac par ScreenCaptureKit (macOS 13+, autorisation « Enregistrement de l'écran »).
    Aucun pilote audio virtuel à installer ; le son de Wesley lui-même est exclu."""

    def __init__(self, tampon: Tampon):
        self.tampon, self._flux, self._sortie = tampon, None, None

    def demarrer(self):
        import objc
        import CoreMedia
        import ScreenCaptureKit as SCK
        from Foundation import NSObject
        import numpy as np
        tampon = self.tampon

        global _SortieSCK
        if _SortieSCK is None:
            class SortieAudioWesley(NSObject, protocols=[objc.protocolNamed("SCStreamOutput")]):
                def stream_didOutputSampleBuffer_ofType_(self, flux, tampon_cm, genre):
                    if genre != SCK.SCStreamOutputTypeAudio:
                        return
                    try:
                        bloc = CoreMedia.CMSampleBufferGetDataBuffer(tampon_cm)
                        n = CoreMedia.CMBlockBufferGetDataLength(bloc)
                        _, octets = CoreMedia.CMBlockBufferCopyDataBytes(bloc, 0, n, None)
                        asbd = CoreMedia.CMAudioFormatDescriptionGetStreamBasicDescription(
                            CoreMedia.CMSampleBufferGetFormatDescription(tampon_cm))
                        sr, canaux = float(asbd[0]), max(1, int(asbd[6]))
                        x = np.frombuffer(bytes(octets), dtype=np.float32)
                        if canaux > 1:     # non entrelacé : [gauche…][droite…]
                            x = x[: len(x) // canaux * canaux].reshape(canaux, -1).mean(0)
                        self.tampon_wesley.pousser(x, sr)
                    except Exception as e:
                        self.tampon_wesley.erreur = str(e)
            _SortieSCK = SortieAudioWesley

        attente, res = threading.Event(), {}

        def contenu_recu(contenu, erreur):
            res.update(contenu=contenu, erreur=erreur)
            attente.set()
        SCK.SCShareableContent.getShareableContentWithCompletionHandler_(contenu_recu)
        if not attente.wait(15) or res.get("erreur") or not res.get("contenu"):
            raise RuntimeError("Wesley n'a pas accès au son du Mac : autorise-le dans Réglages Système › "
                               "Confidentialité et sécurité › Enregistrement de l'écran (et de l'audio), "
                               f"puis relance Wesley. ({res.get('erreur') or 'pas de réponse'})")
        ecrans = res["contenu"].displays()
        if not ecrans:
            raise RuntimeError("aucun écran trouvé pour la capture du son")
        filtre = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(ecrans[0], [])
        cfg = SCK.SCStreamConfiguration.alloc().init()
        cfg.setCapturesAudio_(True)
        cfg.setSampleRate_(48000)
        cfg.setChannelCount_(1)
        cfg.setExcludesCurrentProcessAudio_(True)
        cfg.setWidth_(2)                # l'image ne sert pas : la plus petite possible, 1 image/s
        cfg.setHeight_(2)
        cfg.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))
        self._sortie = _SortieSCK.alloc().init()
        self._sortie.tampon_wesley = tampon
        self._flux = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(filtre, cfg, None)
        ok, err = self._flux.addStreamOutput_type_sampleHandlerQueue_error_(self._sortie, SCK.SCStreamOutputTypeAudio, None, None)
        if not ok:
            raise RuntimeError(f"capture du son du Mac impossible : {err}")
        demarre, erreurs = threading.Event(), []

        def lance(erreur):
            if erreur is not None:
                erreurs.append(str(erreur))
            demarre.set()
        self._flux.startCaptureWithCompletionHandler_(lance)
        if not demarre.wait(15) or erreurs:
            raise RuntimeError("capture du son du Mac impossible (autorise « Enregistrement de l'écran » pour "
                               f"Wesley dans Réglages Système) : {erreurs[0] if erreurs else 'pas de réponse'}")

    def arreter(self):
        if self._flux is not None:
            fini = threading.Event()

            def arrete(_erreur):
                fini.set()
            try:
                self._flux.stopCaptureWithCompletionHandler_(arrete)
                fini.wait(5)
            finally:
                self._flux = None


_SortieSCK = None     # classe Objective-C créée une seule fois (on ne peut pas la redéclarer)


class CapturePeripherique:
    """Périphérique d'entrée qui reçoit le son de l'ordinateur (BlackHole, Loopback, Soundflower, VB-Cable,
    « Mixage stéréo »…) : secours si la capture native est impossible."""
    MOTS = ("blackhole", "loopback", "soundflower", "cable output", "vb-audio", "mixage stéréo", "stereo mix",
            "what u hear", "monitor of")

    def __init__(self, tampon: Tampon, index: int):
        self.tampon, self.index, self._flux = tampon, index, None

    @classmethod
    def trouver(cls):
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0 and any(m in d["name"].lower() for m in cls.MOTS):
                return i, d["name"]
        return None

    def demarrer(self):
        import sounddevice as sd
        info = sd.query_devices(self.index)
        sr, canaux = float(info["default_samplerate"]), min(2, int(info["max_input_channels"]))

        def rappel(donnees, *_):
            self.tampon.pousser(donnees.mean(1), sr)
        self._flux = sd.InputStream(device=self.index, samplerate=sr, channels=canaux, dtype="float32",
                                    blocksize=int(sr / 10), callback=rappel)
        self._flux.start()

    def arreter(self):
        if self._flux is not None:
            self._flux.stop()
            self._flux.close()
            self._flux = None


class CaptureSystemeWindows:
    """Son de tout le PC par WASAPI loopback (PyAudioWPatch) : ce que tu entends dans tes haut-parleurs."""

    def __init__(self, tampon: Tampon):
        self.tampon, self._pa, self._flux = tampon, None, None

    def demarrer(self):
        import numpy as np
        import pyaudiowpatch as pyaudio
        self._pa = pa = pyaudio.PyAudio()
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        hp = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if not hp.get("isLoopbackDevice"):
            for d in pa.get_loopback_device_info_generator():
                if hp["name"] in d["name"]:
                    hp = d
                    break
            else:
                raise RuntimeError("pas de sortie audio « loopback » trouvée pour les haut-parleurs par défaut")
        sr, canaux = float(hp["defaultSampleRate"]), max(1, int(hp["maxInputChannels"]))
        tampon = self.tampon

        def rappel(donnees, nb, _info, _etat):
            x = np.frombuffer(donnees, dtype=np.float32)
            if canaux > 1:
                x = x[: len(x) // canaux * canaux].reshape(-1, canaux).mean(1)
            tampon.pousser(x, sr)
            return (None, pyaudio.paContinue)
        self._flux = pa.open(format=pyaudio.paFloat32, channels=canaux, rate=int(sr), input=True,
                             input_device_index=hp["index"], frames_per_buffer=int(sr / 10), stream_callback=rappel)
        self._flux.start_stream()

    def arreter(self):
        try:
            if self._flux is not None:
                self._flux.stop_stream()
                self._flux.close()
        finally:
            self._flux = None
            if self._pa is not None:
                self._pa.terminate()
                self._pa = None


def capture_systeme(tampon: Tampon):
    """Capture native du son de l'ordinateur ; à défaut, un périphérique « loopback » installé."""
    from .plateforme import MAC, WIN
    erreurs = []
    if MAC or WIN:
        try:
            c = CaptureSystemeMac(tampon) if MAC else CaptureSystemeWindows(tampon)
            c.demarrer()
            return c
        except Exception as e:
            erreurs.append(str(e))
    try:
        trouve = CapturePeripherique.trouver()
    except Exception:
        trouve = None
    if trouve:
        c = CapturePeripherique(tampon, trouve[0])
        c.demarrer()
        return c
    raise RuntimeError(erreurs[0] if erreurs else
                       "capture du son de l'ordinateur indisponible : installe un périphérique « loopback » (BlackHole, VB-Cable)")


def lire_fichier_audio(chemin):
    """Fichier audio ou vidéo -> 16 kHz mono float32. WAV par la bibliothèque standard, le reste (mp3, m4a,
    ogg, mp4…) par PyAV, déjà installé avec faster-whisper."""
    import wave
    import numpy as np
    chemin = str(chemin)
    try:
        with wave.open(chemin) as w:
            if w.getsampwidth() in (2, 4):
                brut = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16 if w.getsampwidth() == 2 else np.int32)
                x = brut.reshape(-1, w.getnchannels()).mean(1) / (32768.0 if w.getsampwidth() == 2 else 2 ** 31)
                return reechantillonner(x.astype(np.float32), w.getframerate())
    except (wave.Error, EOFError, OSError):
        pass
    import av
    morceaux = []
    with av.open(chemin) as conteneur:
        if not conteneur.streams.audio:
            raise ValueError("Ce fichier ne contient pas de son.")
        convertisseur = av.AudioResampler(format="flt", layout="mono", rate=SR)
        for trame in conteneur.decode(audio=0):
            for t in convertisseur.resample(trame):
                morceaux.append(t.to_ndarray().ravel())
        for t in convertisseur.resample(None):
            morceaux.append(t.to_ndarray().ravel())
    if not morceaux:
        raise ValueError("Fichier audio vide ou illisible.")
    return np.concatenate(morceaux).astype(np.float32)


# ====================================================================================================
# Session de transcription
# ====================================================================================================
_verrou = threading.RLock()
_en_cours: "Transcription | None" = None
_whisper_cache: dict = {}
_empreinte_cache: list = []


def dossier_export() -> Path:
    d = CONFIG.get("dossier_transcriptions") or str(Path.home() / "Documents" / "Wesley" / "Transcriptions")
    p = Path(d).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _chemin(tid: str) -> Path:
    if not re.fullmatch(r"[\w-]{4,40}", tid or ""):
        raise ValueError("Identifiant de transcription invalide.")
    return DOSSIER_DONNEES / f"{tid}.json"


def lire(tid: str) -> dict | None:
    if _en_cours is not None and _en_cours.session["id"] == tid:
        return _en_cours.instantane()
    try:
        return json.loads(_chemin(tid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sauver(session: dict, fichier_lisible: bool = True):
    DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    tmp = _chemin(session["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_chemin(session["id"]))
    if fichier_lisible:
        try:
            f = Path(session.get("fichier") or "")
            if not session.get("fichier"):
                debut = datetime.fromtimestamp(session["debut"]).strftime("%Y-%m-%d %Hh%M")
                f = dossier_export() / f"{debut} - {nom_de_fichier(session.get('titre', ''))}.md"
                session["fichier"] = str(f)
                tmp.write_text(json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(_chemin(session["id"]))
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(exporter(session, "md"), encoding="utf-8")
        except OSError as e:
            print(f"  (transcription : fichier Markdown non écrit : {e})")


def resume(s: dict) -> dict:
    return {k: s.get(k) for k in ("id", "titre", "debut", "duree", "source", "avec_micro", "etat", "langue",
                                  "modele", "fichier", "erreur")} | {
        "nb_locuteurs": len(locuteurs(s)), "nb_phrases": len(s.get("segments", []))}


def lister() -> list[dict]:
    res = []
    if DOSSIER_DONNEES.exists():
        for f in DOSSIER_DONNEES.glob("*.json"):
            try:
                res.append(resume(json.loads(f.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                pass
    if _en_cours is not None:
        res = [r for r in res if r["id"] != _en_cours.session["id"]] + [resume(_en_cours.instantane())]
    return sorted(res, key=lambda r: r.get("debut") or 0, reverse=True)


def modifier(tid: str, action: str, d: dict) -> dict:
    """Actions de l'utilisateur sur une transcription terminée : renommer, fusionner, attribuer, texte, titre."""
    with _verrou:
        if _en_cours is not None and _en_cours.session["id"] == tid and _en_cours.session["etat"] != "terminee":
            raise ValueError("Attends la fin de la transcription pour la modifier.")
        s = lire(tid)
        if s is None:
            raise ValueError("Transcription introuvable.")
        if action == "noms":
            renommer(s, d.get("noms") or {})
        elif action == "fusionner":
            fusionner(s, int(d["source"]), int(d["cible"]))
        elif action == "locuteur":
            changer_locuteur(s, int(d["index"]), int(d.get("locuteur", 0)))
        elif action == "texte":
            corriger_texte(s, int(d["index"]), d.get("texte", ""))
        elif action == "regrouper":
            regrouper_session(s, int(d.get("nombre") or 0))
        elif action == "titre":
            s["titre"] = str(d.get("titre", "")).strip()[:120] or s["titre"]
        else:
            raise ValueError("Action inconnue.")
        sauver(s)
        _signaler(s["id"])
        return s


def _chemin_empreintes(tid: str) -> Path:
    return _chemin(tid).with_suffix(".npz")


def sauver_empreintes(tid: str, empreintes: list, fiables: list, durees: list):
    """Empreintes vocales de chaque phrase (pas le son) : servent à regrouper à nouveau les locuteurs."""
    import numpy as np
    DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    with open(_chemin_empreintes(tid), "wb") as f:
        np.savez_compressed(f, empreintes=np.stack([_normer(e) for e in empreintes]).astype(np.float32),
                            fiables=np.array(fiables, dtype=bool), durees=np.array(durees, dtype=np.float32))


def regroupable(tid: str) -> bool:
    """Les empreintes vocales sont gardées : on peut refaire la répartition des locuteurs."""
    try:
        return _chemin_empreintes(tid).exists()
    except ValueError:
        return False


def au_demarrage():
    """Wesley a été fermé pendant une transcription : ce qui a été transcrit est gardé, elle est « interrompue »."""
    import shutil
    shutil.rmtree(DOSSIER_DONNEES / "imports", ignore_errors=True)    # fichiers importés non transcrits
    if not DOSSIER_DONNEES.exists():
        return
    for f in DOSSIER_DONNEES.glob("*.json"):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            if s.get("etat") in ("preparation", "en_cours", "finalisation"):
                s["etat"] = "interrompue"
                s["segments"] = [dict(x, locuteur=l) for x, l in
                                 zip(s.get("segments", []), renumeroter([x["locuteur"] for x in s.get("segments", [])]))]
                sauver(s)
        except (OSError, ValueError, KeyError):
            pass


def regrouper_session(session: dict, nombre: int = 0) -> dict:
    """Refait la répartition des locuteurs (nombre > 0 : exactement ce nombre de personnes ; 0 : automatique).
    Les noms donnés sont effacés : les numéros ne désignent plus forcément les mêmes personnes."""
    import numpy as np
    try:
        with np.load(_chemin_empreintes(session["id"])) as z:
            emb, fiables, durees = list(z["empreintes"]), list(z["fiables"]), list(z["durees"])
    except (OSError, KeyError, ValueError):
        raise ValueError("Les empreintes vocales de cette transcription ne sont pas disponibles.")
    segs = session.get("segments", [])
    if len(emb) != len(segs):
        raise ValueError("Les empreintes vocales ne correspondent plus aux phrases de cette transcription.")
    etiquettes = regrouper(emb, float(session.get("seuil") or 0.5), max(0, nombre), fiables, durees)
    for s, l in zip(segs, etiquettes):
        s["locuteur"] = l
    session["noms"] = {}
    session["nb_locuteurs"] = max(0, nombre)
    return session


def supprimer(tid: str, avec_fichier: bool = False) -> bool:
    with _verrou:
        if _en_cours is not None and _en_cours.session["id"] == tid:
            raise ValueError("Arrête d'abord la transcription en cours.")
        s = lire(tid)
        if s is None:
            return False
        if avec_fichier and s.get("fichier"):
            Path(s["fichier"]).unlink(missing_ok=True)
        _chemin(tid).unlink(missing_ok=True)
        _chemin_empreintes(tid).unlink(missing_ok=True)
        _signaler(tid)
        return True


def enregistrer_sous(tid: str, format: str = "md") -> Path:
    """Exporte (noms des locuteurs compris) dans le dossier des transcriptions ; renvoie le chemin."""
    s = lire(tid)
    if s is None:
        raise ValueError("Transcription introuvable.")
    format = "txt" if format == "txt" else "md"
    debut = datetime.fromtimestamp(s["debut"]).strftime("%Y-%m-%d %Hh%M")
    f = dossier_export() / f"{debut} - {nom_de_fichier(s.get('titre', ''))}.{format}"
    f.write_text(exporter(s, format), encoding="utf-8")
    return f


def en_cours() -> "Transcription | None":
    return _en_cours


def _signaler(tid: str):
    for e in list(ecouteurs):
        try:
            e(tid)
        except Exception:
            pass


def _whisper(nom: str):
    if nom not in _whisper_cache:
        from .modeles import charger_whisper
        _whisper_cache.clear()          # un seul modèle de transcription en mémoire à la fois
        _whisper_cache[nom] = charger_whisper(nom, cpu_threads=4)
    return _whisper_cache[nom]


def _empreinte():
    if not _empreinte_cache:
        _empreinte_cache.append(charger_empreinte())
    return _empreinte_cache[0]


class Transcription:
    """Une transcription en cours : capture, découpage, Whisper et diarisation dans un fil de fond."""

    def __init__(self, source="micro", avec_micro=False, langue="fr", modele="", titre="", nb_locuteurs=0,
                 fichier_audio="", transcrire=None, empreinte=None, captures=None):
        """source : « micro », « systeme » ou « fichier » (fichier_audio : enregistrement à transcrire).
        transcrire(audio, langue, contexte) -> [(debut, fin, texte)], empreinte(audio) -> vecteur et
        captures [(objet avec demarrer/arreter, Tampon)] : remplaçables pour les tests (sans micro ni modèle)."""
        maintenant = time.time()
        source = source if source in ("micro", "systeme", "fichier") else "micro"
        self.session = {
            "id": datetime.fromtimestamp(maintenant).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
            "titre": titre.strip()[:120] or ("Réunion du " + datetime.fromtimestamp(maintenant).strftime("%d/%m/%Y à %H:%M")),
            "debut": maintenant, "duree": 0.0, "source": source,
            "avec_micro": bool(avec_micro) and source == "systeme", "langue": langue or "",
            "modele": modele or CONFIG.get("transcription_modele") or CONFIG.get("whisper_modele", "small"),
            "nb_locuteurs": max(0, int(nb_locuteurs or 0)), "etat": "preparation", "erreur": "",
            "segments": [], "noms": {}, "fichier": "", "empreinte": "",
        }
        self._transcrire = transcrire
        self._empreinte_fn = empreinte
        self._captures = captures
        self._continuer = False
        self._fil: threading.Thread | None = None
        self._empreintes: list = []         # une par phrase (pour le regroupement final)
        self.niveau = 0.0                   # niveau sonore (VU-mètre de l'interface)
        self.retard = 0.0                   # s d'audio en attente de transcription
        self.diariseur: Diariseur | None = None
        self._blocs: queue.Queue = queue.Queue()
        self._fichier_audio = fichier_audio
        self.position = 0.0                 # s d'audio déjà lues (avancement d'un fichier importé)

    # --- état lisible par l'interface
    def instantane(self) -> dict:
        with _verrou:
            s = json.loads(json.dumps(self.session))
        s["niveau"], s["retard"] = round(self.niveau, 3), round(self.retard, 1)
        if s["etat"] == "en_cours":
            s["duree"] = round(self.position if s["source"] == "fichier" else time.time() - s["debut"], 1)
        return s

    def demarrer(self):
        self._continuer = True
        self._fil = threading.Thread(target=self._executer, daemon=True, name="transcription")
        self._fil.start()

    def arreter(self):
        self._continuer = False

    def attendre(self, delai=None):
        if self._fil:
            self._fil.join(delai)

    # --- pipeline
    def _preparer(self):
        import numpy as np
        if self._transcrire is None:
            modele = _whisper(self.session["modele"])

            def transcrire(audio, langue, contexte=""):
                crete = float(np.abs(audio).max()) if len(audio) else 0.0
                if 1e-4 < crete < 0.3:      # voix lointaine : volume remonté (jusqu'à x20) pour Whisper
                    audio = audio * min(20.0, 0.5 / crete)
                segs, _ = modele.transcribe(audio, language=langue or None, beam_size=1, vad_filter=True,
                                            condition_on_previous_text=False, initial_prompt=contexte or None,
                                            vad_parameters={"min_silence_duration_ms": 400})
                return [(s.start, s.end, s.text) for s in segs]
            self._transcrire = transcrire
        if self._empreinte_fn is None:
            self._empreinte_fn = _empreinte()
        nom = getattr(self._empreinte_fn, "nom", "")
        seuil = float(CONFIG.get("transcription_seuil") or getattr(self._empreinte_fn, "seuil", 0.5))
        self.diariseur = Diariseur(seuil)
        self.session["empreinte"] = nom
        if self.session["source"] == "fichier":
            self._audio_fichier = lire_fichier_audio(self._fichier_audio)
            self._captures = []
        elif self._captures is None:
            self._captures = []
            if self.session["source"] == "systeme":
                t = Tampon("systeme")
                self._captures.append((capture_systeme(t), t))
                if self.session["avec_micro"]:
                    m = Tampon("micro")
                    c = CaptureMicro(m)
                    c.demarrer()
                    self._captures.append((c, m))
            else:
                t = Tampon("micro")
                c = CaptureMicro(t)
                c.demarrer()
                self._captures.append((c, t))
        else:
            for c, _ in self._captures:
                c.demarrer()

    def _executer(self):
        import numpy as np
        try:
            self._preparer()
        except Exception as e:
            traceback.print_exc()
            self._fin_erreur(str(e))
            return
        with _verrou:
            self.session["etat"] = "en_cours"
            self.session["debut"] = time.time()
        sauver(self.session)
        _signaler(self.session["id"])
        mixeur = Mixeur([t for _, t in self._captures])
        decoupeur = Decoupeur()
        travailleur = threading.Thread(target=self._travailler, daemon=True, name="transcription-whisper")
        travailleur.start()
        fichier = getattr(self, "_audio_fichier", None)
        try:
            while self._continuer:
                if fichier is not None:     # fichier importé : lu d'un coup (sans attendre l'horloge)
                    i = int(self.position * SR)
                    x = fichier[i: i + SR // 10]
                    if not len(x):
                        break
                    self.position += len(x) / SR
                    while self._blocs.qsize() > 3 and self._continuer:   # pas plus vite que Whisper
                        time.sleep(0.05)
                else:
                    time.sleep(0.1)
                    x = mixeur.lire()
                    self.position += len(x) / SR
                if len(x):
                    self.niveau = 0.8 * self.niveau + 0.2 * float(np.sqrt(np.mean(x * x)))
                    bloc = decoupeur.ajouter(x)
                    if bloc is not None:
                        self._blocs.put(bloc)
                for _, t in self._captures:
                    if t.erreur:
                        raise RuntimeError(t.erreur)
        except Exception as e:
            traceback.print_exc()
            self.session["erreur"] = str(e)
        finally:
            for c, _ in self._captures:
                try:
                    c.arreter()
                except Exception:
                    traceback.print_exc()
        with _verrou:
            self.session["duree"] = round(self.position, 1)
            self.session["etat"] = "finalisation"
        _signaler(self.session["id"])
        dernier = decoupeur.vider()
        if dernier is not None:
            self._blocs.put(dernier)
        self._blocs.put(None)
        travailleur.join()
        self._finaliser()

    def _travailler(self):
        """Fil Whisper : transcrit les blocs dans l'ordre, sans bloquer la capture."""
        contexte = ""
        while True:
            bloc = self._blocs.get()
            if bloc is None:
                return
            debut, audio = bloc
            self.retard = sum(len(b[1]) for b in list(self._blocs.queue) if b) / SR
            try:
                phrases = self._transcrire(audio, self.session["langue"], contexte)
            except Exception as e:
                traceback.print_exc()
                self.session["erreur"] = f"Transcription : {e}"
                continue
            nouveaux = []
            for d, f, texte in phrases:
                texte = (texte or "").strip()
                if not texte or _hallucination(texte):
                    continue
                d, f = max(0.0, float(d)), min(len(audio) / SR, float(f))
                morceau = audio[int(d * SR): max(int(f * SR), int(d * SR) + 1)]
                fiable = len(morceau) / SR >= DUREE_FIABLE
                try:
                    e = self._empreinte_fn(morceau if len(morceau) >= SR // 2 else
                                           audio[max(0, int(d * SR) - SR // 4): int(f * SR) + SR // 4])
                    loc = self.diariseur.attribuer(e, fiable)
                except Exception:
                    traceback.print_exc()
                    e, loc = None, self.diariseur.dernier or 1
                self._empreintes.append((e, fiable, f - d))
                nouveaux.append({"debut": round(debut + d, 2), "fin": round(debut + f, 2), "locuteur": loc,
                                 "texte": texte})
                contexte = texte[-200:]
            if nouveaux:
                with _verrou:
                    self.session["segments"].extend(nouveaux)
                sauver(self.session)
                _signaler(self.session["id"])
            self.retard = sum(len(b[1]) for b in list(self._blocs.queue) if b) / SR

    def _finaliser(self):
        """Regroupement final des voix sur toute la réunion, puis fichiers définitifs."""
        segs = self.session["segments"]
        valides = [i for i, (e, _, _) in enumerate(self._empreintes) if e is not None]
        self.session["seuil"] = self.diariseur.seuil
        if len(valides) == len(segs) and segs:
            try:
                sauver_empreintes(self.session["id"], [e for e, _, _ in self._empreintes],
                                  [f for _, f, _ in self._empreintes], [d for _, _, d in self._empreintes])
            except Exception:
                traceback.print_exc()
        if len(valides) >= 2 and len(valides) == len(segs):
            try:
                etiquettes = regrouper([self._empreintes[i][0] for i in valides], self.diariseur.seuil,
                                       self.session["nb_locuteurs"], [self._empreintes[i][1] for i in valides],
                                       [self._empreintes[i][2] for i in valides])
                with _verrou:
                    for i, l in zip(valides, etiquettes):
                        segs[i]["locuteur"] = l
            except Exception:
                traceback.print_exc()
        else:
            with _verrou:
                for s, l in zip(segs, renumeroter([s["locuteur"] for s in segs])):
                    s["locuteur"] = l
        with _verrou:
            self.session["etat"] = "terminee"
        sauver(self.session)
        _liberer(self)
        _signaler(self.session["id"])

    def _fin_erreur(self, message: str):
        with _verrou:
            self.session["etat"], self.session["erreur"] = "erreur", message
        for c, _ in self._captures or []:
            try:
                c.arreter()
            except Exception:
                pass
        sauver(self.session, fichier_lisible=False)
        _liberer(self)
        _signaler(self.session["id"])


# Phrases que Whisper invente sur du silence ou de la musique
_HALLUCINATIONS = re.compile(r"^(sous-titr|sous titr|merci d'avoir regardé|abonnez-vous|thanks for watching|"
                             r"subtitles by|amara\.org|\[musique\]|\(musique\)|♪)", re.I)


def _hallucination(texte: str) -> bool:
    return bool(_HALLUCINATIONS.search(texte.strip()))


def _liberer(t: Transcription):
    global _en_cours
    with _verrou:
        if _en_cours is t:
            _en_cours = None


def demarrer(source="micro", avec_micro=False, langue="", modele="", titre="", nb_locuteurs=0, fichier_audio="",
             **tests) -> dict:
    """Lance une transcription (une seule à la fois) ; renvoie son état."""
    global _en_cours
    with _verrou:
        if _en_cours is not None:
            raise ValueError("Une transcription est déjà en cours : arrête-la d'abord.")
        if modele and modele not in MODELES_WHISPER:
            raise ValueError("Modèle de transcription inconnu.")
        t = Transcription(source, avec_micro, langue if langue is not None else CONFIG.get("langue", "fr"),
                          modele, titre, nb_locuteurs, fichier_audio, **tests)
        _en_cours = t
    t.demarrer()
    return t.instantane()


def arreter() -> dict | None:
    """Arrête la capture ; la fin de la transcription et le regroupement final continuent en fond."""
    t = _en_cours
    if t is None:
        return None
    t.arreter()
    return t.instantane()
