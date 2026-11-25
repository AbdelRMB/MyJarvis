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

from ..config import CONFIG, RACINE
# parties sans état (réexportées : transcription.X reste valable partout)
from .communs import (  # noqa: F401
    SR, DOSSIER_MODELES, MODELE_LOCUTEURS, URL_MODELE_LOCUTEURS, MODELES_WHISPER, DUREE_FIABLE, PAUSE_TOUR,
    DUREE_TOUR_MAX,
)
from .document import (  # noqa: F401
    horodatage, nom_locuteur, locuteurs, tours_de_parole, exporter, extrait, renommer, fusionner,
    changer_locuteur, corriger_texte, renumeroter, nom_de_fichier,
)
from .diarisation import (  # noqa: F401
    DUREE_SOLIDE, DUREE_FENETRE, POIDS_MAX, _normer, _assoupli, _poids, appliquer_fusion, Diariseur,
    rattacher, regrouper_complet, regrouper, EmpreinteSherpa, EmpreinteSimple, telecharger_modele_locuteurs,
    charger_empreinte,
)
from .capture import (  # noqa: F401
    Decoupeur, reechantillonner, Tampon, Mixeur, CaptureMicro, CaptureSystemeMac,
    CapturePeripherique, CaptureSystemeWindows, capture_systeme, lire_fichier_audio,
)
from .fidelite import (  # noqa: F401
    _HALLUCINATIONS, _HALLUCINATIONS_VIDEO, _HALLUCINATIONS_COURTES, PAUSE_DECOUPE, DUREE_PHRASE_MAX,
    _hallucination, modele_auto, modele_par_defaut, options_whisper, segment_douteux, sans_boucles,
    decouper_phrases, VOCABULAIRE_THEMES, _MOT_TECHNIQUE, vocabulaire, consigne_whisper, recopie_consigne,
)

DOSSIER_DONNEES = RACINE / "transcriptions"
ecouteurs: list = []        # fonctions appelées à chaque changement (web.py : diffusion vers l'interface)


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
    """Ligne de la liste (à ne pas confondre avec s["resume"], le résumé du contenu : resume_transcription.py)."""
    r = s.get("resume") or {}
    return {k: s.get(k) for k in ("id", "titre", "debut", "duree", "source", "avec_micro", "etat", "langue",
                                  "modele", "fichier", "erreur")} | {
        "nb_locuteurs": len(locuteurs(s)), "nb_phrases": len(s.get("segments", [])),
        "genre": r.get("genre") if r.get("texte") else "", "a_resume": bool(r.get("texte"))}


def marquer_resume(tid: str, maj: dict, remplacer: bool = False):
    """Range le résumé (ou son état : en cours, erreur) dans la transcription, sans toucher au reste."""
    with _verrou:
        if _en_cours is not None and _en_cours.session["id"] == tid:
            raise ValueError("Attends la fin de la transcription pour la résumer.")
        s = lire(tid)
        if s is None:
            raise ValueError("Transcription introuvable.")
        s["resume"] = dict(maj) if remplacer else {**(s.get("resume") or {}), **maj}
        sauver(s)
    _signaler(tid)


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
    """Empreintes vocales de chaque phrase (pas le son) : servent à regrouper à nouveau les locuteurs.
    Une phrase sans empreinte (calcul impossible) est gardée, marquée non valide."""
    import numpy as np
    exemple = next((e for e in empreintes if e is not None), None)
    if exemple is None:
        return
    vide = np.zeros_like(_normer(exemple))
    DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    with open(_chemin_empreintes(tid), "wb") as f:
        np.savez_compressed(f, empreintes=np.stack([vide if e is None else _normer(e) for e in empreintes]).astype(np.float32),
                            fiables=np.array(fiables, dtype=bool), durees=np.array(durees, dtype=np.float32),
                            valides=np.array([e is not None for e in empreintes], dtype=bool))


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
            if (s.get("resume") or {}).get("en_cours"):    # Wesley fermé pendant le résumé
                s["resume"]["en_cours"] = False
                if s.get("etat") not in ("preparation", "en_cours", "finalisation"):
                    sauver(s)
            if s.get("etat") in ("preparation", "en_cours", "finalisation"):
                s["etat"] = "interrompue"
                s["duree"] = round(max([float(s.get("duree") or 0)] + [float(x["fin"]) for x in s.get("segments", [])]), 1)
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
            valides = list(z["valides"]) if "valides" in z.files else [True] * len(emb)
            emb = [e if v else None for e, v in zip(emb, valides)]
    except (OSError, KeyError, ValueError):
        raise ValueError("Les empreintes vocales de cette transcription ne sont pas disponibles.")
    segs = session.get("segments", [])
    if len(emb) != len(segs):
        raise ValueError("Les empreintes vocales ne correspondent plus aux phrases de cette transcription.")
    etiquettes = regrouper_complet(emb, float(session.get("seuil") or 0.5), max(0, nombre), fiables, durees)
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
    gpu = bool(CONFIG.get("transcription_gpu"))   # Mac : puce graphique (expérimental, repli sur le processeur)
    cle = f"{nom}|{'gpu' if gpu else 'cpu'}"
    if cle not in _whisper_cache:
        from ..modeles import charger_whisper
        _whisper_cache.clear()          # un seul modèle de transcription en mémoire à la fois
        import os
        _whisper_cache[cle] = charger_whisper(nom, gpu=gpu, cpu_threads=max(2, min(8, (os.cpu_count() or 4) - 1)))
    return _whisper_cache[cle]


def _empreinte():
    if not _empreinte_cache:
        _empreinte_cache.append(charger_empreinte())
    return _empreinte_cache[0]


class Transcription:
    """Une transcription en cours : capture, découpage, Whisper et diarisation dans un fil de fond."""

    def __init__(self, source="micro", avec_micro=False, langue="fr", modele="", titre="", nb_locuteurs=0,
                 fichier_audio="", transcrire=None, empreinte=None, captures=None, vocabulaire=""):
        """source : « micro », « systeme » ou « fichier » (fichier_audio : enregistrement à transcrire).
        modele : « auto » (ou vide) = le plus précis que la machine fait tourner ; vocabulaire : mots techniques
        à bien orthographier (séparés par des virgules).
        transcrire(audio, langue, consigne) -> [(debut, fin, texte)], empreinte(audio) -> vecteur et
        captures [(objet avec demarrer/arreter, Tampon)] : remplaçables pour les tests (sans micro ni modèle)."""
        maintenant = time.time()
        source = source if source in ("micro", "systeme", "fichier") else "micro"
        self.session = {
            "id": datetime.fromtimestamp(maintenant).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
            "titre": titre.strip()[:120] or ("Réunion du " + datetime.fromtimestamp(maintenant).strftime("%d/%m/%Y à %H:%M")),
            "debut": maintenant, "duree": 0.0, "source": source,
            "avec_micro": bool(avec_micro) and source == "systeme", "langue": langue or "",
            "modele": modele or modele_par_defaut(),
            "vocabulaire": re.sub(r"\s+", " ", str(vocabulaire or CONFIG.get("transcription_vocabulaire") or ""))[:500],
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
        if self.session["modele"] not in MODELES_WHISPER or self.session["modele"] == "auto":
            self.session["modele"] = modele_auto(source)
        self._fichier_audio = fichier_audio
        self.position = 0.0                 # s depuis le début de la transcription (horodatage du son lu)
        self._anciens: list[int] = []       # reprise : locuteur des phrases déjà écrites (gardé tel quel)
        self._amorce: list = []             # reprise : empreintes des phrases déjà écrites (diariseur amorcé)

    @classmethod
    def reprise(cls, session: dict, source: str = "", avec_micro=None, fichier_audio: str = "", **tests):
        """Reprend une transcription (terminée, interrompue ou en erreur) : la suite s'ajoute à la même
        transcription, horodatée après la fin, avec les mêmes locuteurs (numéros, noms, empreintes vocales)."""
        import numpy as np
        source = source or (session.get("source") if session.get("source") in ("micro", "systeme") else "micro")
        if source == "fichier" and not fichier_audio:
            source = "micro"
        t = cls(source, session.get("avec_micro") if avec_micro is None else avec_micro, session.get("langue", "fr"),
                session.get("modele", ""), session.get("titre", ""), session.get("nb_locuteurs", 0), fichier_audio,
                vocabulaire=session.get("vocabulaire", ""), **tests)
        s = t.session | json.loads(json.dumps(session))     # champs absents des anciennes versions : par défaut
        s["id"] = session["id"]
        segs = s.setdefault("segments", [])
        reprise_a = round(max([float(s.get("duree") or 0)] + [float(x["fin"]) for x in segs]), 1)
        s.update(source=t.session["source"], avec_micro=t.session["avec_micro"], modele=t.session["modele"],
                 etat="preparation", erreur="", duree=reprise_a,
                 reprises=list(s.get("reprises") or []) + [{"position": reprise_a, "date": time.time()}])
        t.session = s
        t.position = reprise_a
        t._anciens = [int(x["locuteur"]) for x in segs]
        # empreintes des phrases d'avant (si elles ont été gardées et viennent du même extracteur)
        amorce = [(None, False, max(0.0, x["fin"] - x["debut"])) for x in segs]
        try:
            with np.load(_chemin_empreintes(s["id"])) as z:
                emb, fi, du = list(z["empreintes"]), list(z["fiables"]), list(z["durees"])
                va = list(z["valides"]) if "valides" in z.files else [True] * len(emb)
            if len(emb) == len(segs):
                amorce = [(e if v else None, bool(f), float(d)) for e, f, d, v in zip(emb, fi, du, va)]
        except (OSError, KeyError, ValueError):
            pass
        t._amorce = amorce
        t._empreintes = list(amorce)
        return t

    # --- état lisible par l'interface
    def instantane(self) -> dict:
        with _verrou:
            s = json.loads(json.dumps(self.session))
        s["niveau"], s["retard"] = round(self.niveau, 3), round(self.retard, 1)
        if s["etat"] == "en_cours":
            s["duree"] = round(self.position, 1)     # reprise : durée d'avant comprise
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

            import inspect
            try:
                acceptes = set(inspect.signature(modele.transcribe).parameters)
            except (TypeError, ValueError):
                acceptes = None

            def transcrire(audio, langue, consigne=""):
                crete = float(np.abs(audio).max()) if len(audio) else 0.0
                if 1e-4 < crete < 0.3:      # voix lointaine : volume remonté (jusqu'à x20) pour Whisper
                    audio = audio * min(20.0, 0.5 / crete)
                options = options_whisper(langue, consigne)
                if acceptes is not None:        # anciennes versions de faster-whisper : options inconnues retirées
                    options = {k: v for k, v in options.items() if k in acceptes}
                segs, _ = modele.transcribe(audio, **options)
                return decouper_phrases(segs)
            self._transcrire = transcrire
        if self._empreinte_fn is None:
            self._empreinte_fn = _empreinte()
        nom = getattr(self._empreinte_fn, "nom", "")
        seuil = float(CONFIG.get("transcription_seuil") or getattr(self._empreinte_fn, "seuil", 0.5))
        self.diariseur = Diariseur(seuil, self.session["nb_locuteurs"])
        if self._amorce:
            ancien = self.session.get("empreinte") or ""
            dims = {len(np.ravel(e)) for e, _, _ in self._amorce if e is not None}
            if ancien != nom or len(dims) > 1:
                # autre extracteur de voix qu'à l'époque : empreintes incomparables, les voix de la suite
                # deviennent de nouveaux locuteurs (les phrases d'avant gardent les leurs)
                self._amorce = [(None, False, d) for _, _, d in self._amorce]
                self._empreintes = list(self._amorce)
            self.diariseur.amorcer(self._amorce)
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
            if not self._anciens and not self.session.get("reprises"):
                self.session["debut"] = time.time()     # reprise : la date de début reste celle d'origine
        sauver(self.session)
        _signaler(self.session["id"])
        mixeur = Mixeur([t for _, t in self._captures])
        decoupeur = Decoupeur()
        decoupeur.debut = self.position         # reprise : l'horodatage continue après la fin
        travailleur = threading.Thread(target=self._travailler, daemon=True, name="transcription-whisper")
        travailleur.start()
        fichier = getattr(self, "_audio_fichier", None)
        lu = 0                                  # échantillons du fichier importé déjà lus

        def traiter(x):
            if len(x):
                self.niveau = 0.8 * self.niveau + 0.2 * float(np.sqrt(np.mean(x * x)))
                bloc = decoupeur.ajouter(x)
                if bloc is not None:
                    self._blocs.put(bloc)
        try:
            while self._continuer:
                if fichier is not None:     # fichier importé : lu d'un coup (sans attendre l'horloge)
                    x = fichier[lu: lu + SR // 10]
                    if not len(x):
                        break
                    lu += len(x)
                    self.position += len(x) / SR
                    while self._blocs.qsize() > 3 and self._continuer:   # pas plus vite que Whisper
                        time.sleep(0.05)
                else:
                    time.sleep(0.1)
                    x = mixeur.lire()
                    self.position += len(x) / SR
                traiter(x)
                for _, t in self._captures:
                    if t.erreur:
                        raise RuntimeError(t.erreur)
            if fichier is None:
                # arrêt demandé juste après un mot : le son encore en route (latence de la carte son, ~0,3 s)
                # est lu avant de couper, sinon la fin de la dernière phrase manquait
                time.sleep(0.3)
                x = mixeur.lire()
                self.position += len(x) / SR
                traiter(x)
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

    def _consigne(self) -> str:
        """Amorce de Whisper : titre + vocabulaire (donné, déjà entendu, du sujet). Jamais le texte précédent :
        une erreur ou une boucle s'y propagerait."""
        with _verrou:
            textes = [x["texte"] for x in self.session["segments"][-300:]]
        return consigne_whisper(self.session["titre"],
                                vocabulaire(self.session["titre"], textes, self.session.get("vocabulaire", "")))

    def _travailler(self):
        """Fil Whisper : transcrit les blocs dans l'ordre, sans bloquer la capture."""
        while True:
            bloc = self._blocs.get()
            if bloc is None:
                return
            debut, audio = bloc
            self.retard = sum(len(b[1]) for b in list(self._blocs.queue) if b) / SR
            consigne = self._consigne()
            try:
                phrases = self._transcrire(audio, self.session["langue"], consigne)
            except Exception:
                # une erreur passagère (mémoire, décodage) ne doit pas faire perdre tout le bloc : 2e essai sans amorce
                traceback.print_exc()
                try:
                    phrases = self._transcrire(audio, self.session["langue"], "")
                    consigne = ""
                except Exception as e:
                    traceback.print_exc()
                    self.session["erreur"] = f"Transcription : {e}"
                    continue
            nouveaux = []
            for d, f, texte in phrases:
                texte = (texte or "").strip()
                if not texte or _hallucination(texte) or recopie_consigne(texte, consigne):
                    continue
                d = min(max(0.0, float(d)), max(0.0, len(audio) / SR - 0.01))
                f = min(len(audio) / SR, float(f))
                if f <= d:
                    f = min(len(audio) / SR, d + 0.01)
                fiable = f - d >= DUREE_FIABLE
                # empreinte sur au moins 1,5 s (élargie dans le bloc, coupé aux pauses : même voix le plus souvent)
                manque = max(0.0, 1.5 - (f - d)) / 2
                i0, i1 = int(max(0.0, d - manque) * SR), int(min(len(audio) / SR, f + manque) * SR)
                try:
                    e = self._empreinte_fn(audio[i0: max(i1, i0 + 1)])
                except Exception:
                    traceback.print_exc()
                    e = None
                self.diariseur.attribuer(e, fiable, f - d)
                self._empreintes.append((e, fiable, f - d))
                nouveaux.append({"debut": round(debut + d, 2), "fin": round(debut + f, 2), "locuteur": 1,
                                 "texte": texte})
            if nouveaux:
                with _verrou:
                    segs = self.session["segments"]
                    segs.extend(nouveaux)
                    # locuteurs à jour de toutes les phrases (fusions et regroupements réguliers du direct) ;
                    # reprise : celles d'avant gardent le leur
                    n0 = len(self._anciens)
                    for x, l in zip(segs[n0:], self._suite(self.diariseur.etiquettes, self.diariseur.historique)):
                        x["locuteur"] = l
                    self.session["duree"] = round(max(self.session.get("duree") or 0, debut + len(audio) / SR), 1)
                sauver(self.session)
                _signaler(self.session["id"])
            self.retard = sum(len(b[1]) for b in list(self._blocs.queue) if b) / SR

    def _suite(self, etiquettes: list[int], historique: list) -> list[int]:
        """Locuteurs des phrases de cette session (après les len(self._anciens) d'une reprise), d'après le
        regroupement `etiquettes` (aligné sur `historique` : (empreinte, fiable, durée)), qui couvre aussi les
        phrases d'avant si le diariseur a été amorcé avec."""
        n0 = len(self._anciens)
        nouvelles = len(self.session["segments"]) - n0
        base = len(etiquettes) - nouvelles          # n0 (amorcé) ou 0 (pas d'empreintes d'avant)
        anciens = self._anciens if base == n0 else []
        res = rattacher(anciens, list(etiquettes), [e is not None for e, _, _ in historique],
                        [d for _, _, d in historique], depart=max(self._anciens, default=0))
        return res[base:]

    def _finaliser(self):
        """Regroupement final des voix sur toute la réunion (aucune phrase laissée de côté, numéros 1, 2, 3…
        sans trou), puis fichiers définitifs. Le texte du direct est gardé tel quel."""
        segs = self.session["segments"]
        self.session["seuil"] = self.diariseur.seuil
        if segs and len(self._empreintes) == len(segs):
            try:
                sauver_empreintes(self.session["id"], [e for e, _, _ in self._empreintes],
                                  [f for _, f, _ in self._empreintes], [d for _, _, d in self._empreintes])
            except Exception:
                traceback.print_exc()
            try:
                etiquettes = self._suite(
                    regrouper_complet([e for e, _, _ in self._empreintes], self.diariseur.seuil,
                                      self.session["nb_locuteurs"], [f for _, f, _ in self._empreintes],
                                      [d for _, _, d in self._empreintes]), self._empreintes)
            except Exception:
                traceback.print_exc()
                etiquettes = None
        else:
            etiquettes = None
        n0 = len(self._anciens)
        if etiquettes is None:      # pas de regroupement final possible : numéros du direct, sans trou
            etiquettes = [x["locuteur"] for x in segs[n0:]] if n0 else renumeroter([x["locuteur"] for x in segs])
        with _verrou:
            for x, l in zip(segs[n0:], etiquettes):
                x["locuteur"] = l
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


def _liberer(t: Transcription):
    global _en_cours
    with _verrou:
        if _en_cours is t:
            _en_cours = None


def demarrer(source="micro", avec_micro=False, langue=None, modele="", titre="", nb_locuteurs=0, fichier_audio="",
             vocabulaire="", **tests) -> dict:
    """Lance une transcription (une seule à la fois) ; renvoie son état. langue : None = celle de Wesley
    (français par défaut), « » = détection automatique."""
    global _en_cours
    with _verrou:
        if _en_cours is not None:
            raise ValueError("Une transcription est déjà en cours : arrête-la d'abord.")
        if modele and modele not in MODELES_WHISPER:
            raise ValueError("Modèle de transcription inconnu.")
        t = Transcription(source, avec_micro, langue if langue is not None else (CONFIG.get("langue") or "fr"),
                          modele, titre, nb_locuteurs, fichier_audio, vocabulaire=vocabulaire, **tests)
        _en_cours = t
    t.demarrer()
    return t.instantane()


def reprendre(tid: str, source: str = "", avec_micro=None, fichier_audio: str = "", **tests) -> dict:
    """Reprend une transcription déjà faite (terminée, interrompue ou en erreur) : la suite s'écrit à la fin de
    la même transcription, mêmes locuteurs, horodatage continu. source vide = celle d'origine (micro pour un
    fichier importé) ; « fichier » + fichier_audio : un enregistrement à ajouter à la suite."""
    global _en_cours
    with _verrou:
        if _en_cours is not None:
            raise ValueError("Une transcription est déjà en cours : arrête-la d'abord.")
        s = lire(tid)
        if s is None:
            raise ValueError("Transcription introuvable.")
        t = Transcription.reprise(s, source, avec_micro, fichier_audio, **tests)
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
