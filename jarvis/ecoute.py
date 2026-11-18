"""Écoute de fond : Jarvis entend son nom même quand la fenêtre est cachée.

Deux détecteurs, 100 % locaux :
1. openWakeWord « Hey Jarvis » (prononciation anglaise) : instantané, ~2 % d'un cœur.
2. Pour le français : chaque phrase entendue est découpée (détection d'énergie), puis transcrite par un
   petit modèle Whisper ; si elle commence par « Jarvis » (« Jarvis, ouvre Discord »), c'est pour lui.
   Dire juste « Jarvis » ouvre la fenêtre et attend la suite.
Rien n'est envoyé nulle part tant que son nom n'a pas été reconnu.
"""
import re
import threading
import time
import traceback

import numpy as np

from .config import CONFIG

TRAME = 1280            # 80 ms à 16 kHz
SR = 16000
# « Jarvis », « Hé/Et/Ok/Dis Jarvis » et les transcriptions approximatives (« Dijavis », « Djarvis », « Jarvice »…)
RX_NOM = re.compile(r"^\W*(?:(?:hey|hé|he|eh|et|é|ok|okay|dis|salut|bonjour)\W+)?(?:d[ie]\s?)?(?:j|dj)[ae]r?v[iy](?:s|ce|sse|ss)?\b\W*"
                    r"|^\W*j\.a\.r\.v\.i\.s\.?\W*", re.I)


class Segmenteur:
    """Découpe le flux micro en phrases (début : son au-dessus du bruit ambiant ; fin : silence)."""

    def __init__(self, silence_fin=0.7, duree_min=0.4, duree_max=12.0):
        self.silence_fin, self.duree_min, self.duree_max = silence_fin, duree_min, duree_max
        self.bruit = 200.0
        self.avant = []          # ~0,3 s gardées avant le début de la phrase
        self.morceaux = None
        self.dernier_son = 0.0
        self.t = 0.0             # horloge du flux (secondes d'audio)

    def seuil(self):
        return max(self.bruit * 3.0, 450)

    def ajouter(self, x: np.ndarray):
        """Renvoie une phrase complète (int16) quand elle se termine, sinon None."""
        self.t += len(x) / SR
        rms = float(np.sqrt(np.mean(x.astype(np.float32) ** 2)))
        if self.morceaux is None:
            self.bruit = 0.97 * self.bruit + 0.03 * min(rms, 3000)
            self.avant = (self.avant + [x])[-4:]
            if rms > self.seuil():
                self.morceaux, self.debut, self.dernier_son = list(self.avant), self.t, self.t
            return None
        self.morceaux.append(x)
        if rms > self.seuil() * 0.7:
            self.dernier_son = self.t
        duree = self.t - self.debut
        if self.t - self.dernier_son > self.silence_fin or duree > self.duree_max:
            phrase, self.morceaux = np.concatenate(self.morceaux), None
            return phrase if duree >= self.duree_min else None
        return None


class EcouteFond:
    def __init__(self, sur_eveil, sur_commande, transcrire_rapide):
        """sur_eveil() : nom entendu ; sur_commande(audio float32 | None) : la demande ;
        transcrire_rapide(audio float32) -> str : petit Whisper pour reconnaître le nom."""
        self.sur_eveil, self.sur_commande, self.rapide = sur_eveil, sur_commande, transcrire_rapide
        self._fil = None
        self._continuer = False
        self._attendre_suite = False
        self._analyse_en_cours = False
        self.erreur = ""

    @property
    def actif(self):
        return bool(self._fil and self._fil.is_alive() and self._continuer)

    def demarrer(self):
        if self.actif:
            return
        self._continuer = True
        self._fil = threading.Thread(target=self._boucle, daemon=True, name="ecoute-fond")
        self._fil.start()

    def arreter(self):
        self._continuer = False

    # --- reconnaissance du nom dans une phrase (fil séparé : la boucle micro ne s'arrête jamais)
    def analyser(self, phrase: np.ndarray):
        audio = phrase.astype(np.float32) / 32768.0
        try:
            texte = self.rapide(audio)
        except Exception:
            traceback.print_exc()
            return None
        if not RX_NOM.match(texte or ""):
            return None
        reste = RX_NOM.sub("", texte).strip()
        self.sur_eveil()
        if len(reste) >= 3:              # « Jarvis, ouvre Discord » : tout est dans la phrase
            self.sur_commande(audio)
        else:                            # « Jarvis ? » : on attend la suite
            self._attendre_suite = True
        return texte

    def _analyser_fond(self, phrase):
        try:
            self.analyser(phrase)
        finally:
            self._analyse_en_cours = False

    def _modele_oww(self):
        from openwakeword.model import Model
        try:
            return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        except Exception:
            from openwakeword.utils import download_models   # 1er lancement sur un PC : ~6 Mo
            download_models(model_names=["hey_jarvis"])
            return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

    def _boucle(self):
        import sounddevice as sd
        try:
            oww = self._modele_oww()
        except Exception as e:
            oww = None
            print(f"  (détecteur « Hey Jarvis » anglais indisponible : {e})")
        while self._continuer:
            try:
                seg = Segmenteur()
                commande = None          # Segmenteur dédié à la demande après le nom
                attente_debut = 0.0
                dernier_eveil = 0.0
                with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=TRAME) as flux:
                    self.erreur = ""
                    while self._continuer:
                        x = flux.read(TRAME)[0][:, 0].copy()
                        maintenant = time.time()
                        if self._attendre_suite and commande is None:
                            self._attendre_suite = False
                            commande, attente_debut = Segmenteur(silence_fin=0.9, duree_max=15), maintenant
                        if commande is not None:
                            phrase = commande.ajouter(x)
                            if phrase is not None:
                                threading.Thread(target=self.sur_commande, args=(phrase.astype(np.float32) / 32768.0,),
                                                 daemon=True).start()
                                commande = None
                            elif commande.morceaux is None and maintenant - attente_debut > 5:
                                threading.Thread(target=self.sur_commande, args=(None,), daemon=True).start()
                                commande = None
                            continue
                        # détecteur anglais instantané
                        if oww is not None and oww.predict(x).get("hey_jarvis", 0) >= CONFIG.get("seuil_eveil", 0.5) \
                                and maintenant - dernier_eveil > 2:
                            dernier_eveil = maintenant
                            oww.reset()
                            seg = Segmenteur()
                            threading.Thread(target=self.sur_eveil, daemon=True).start()
                            commande, attente_debut = Segmenteur(silence_fin=0.9, duree_max=15), maintenant
                            continue
                        # détecteur français : phrase -> petit Whisper -> commence par « Jarvis » ?
                        phrase = seg.ajouter(x)
                        if phrase is not None and not self._analyse_en_cours:
                            self._analyse_en_cours = True
                            threading.Thread(target=self._analyser_fond, args=(phrase,), daemon=True).start()
            except Exception as e:   # micro débranché, changé… on réessaie
                self.erreur = f"Micro : {e}"
                traceback.print_exc()
                time.sleep(3)
