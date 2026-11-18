"""Écoute de fond : Jarvis entend son nom même quand la fenêtre est cachée, puis t'écoute jusqu'au bout.

Deux détecteurs, 100 % locaux :
1. openWakeWord « Hey Jarvis » (prononciation anglaise) : instantané, ~2 % d'un cœur.
2. Pour le français : chaque phrase entendue est découpée (détection d'énergie), puis transcrite par un
   petit modèle Whisper ; si elle commence par « Jarvis » (« Jarvis, ouvre Discord »), c'est pour lui.
Tu parles d'une traite (« Jarvis, ouvre Discord et… ») : rien à attendre après son nom, il écoute en continu
et n'envoie ta demande que lorsque tu te tais pendant CONFIG["silence_fin"] secondes (2,5 s par défaut),
comptées depuis la fin réelle de ta voix (le temps d'analyse du nom n'est pas ajouté).
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
DUREE_DEMANDE_MAX = 120.0   # s de parole au maximum pour une demande
ATTENTE_DEBUT = 8.0         # s pour commencer à parler après « Jarvis » seul
APRES_MAX = 375             # trames (30 s) gardées pendant l'analyse du nom : rien de ce que tu dis n'est perdu

RX_NOM = re.compile(r"^\W*(?:(?:hey|hé|he|eh|et|é|ok|okay|dis|salut|bonjour)\W+)?(?:d[ie]\s?)?(?:j|dj)[ae]r?v[iy](?:s|ce|sse|ss)?\b\W*"
                    r"|^\W*j\.a\.r\.v\.i\.s\.?\W*", re.I)
# Arrêt : « Jarvis… stop / arrête / tais-toi… » n'importe où dans ce qui est entendu (même mêlé à sa propre voix),
# ou un mot d'arrêt dit seul pendant qu'il parle.
MOTS_STOP = r"(?:stop+|arr[êe]te[sz]?(?:[- ]toi)?|annule|tais[- ]toi|taisez[- ]vous|chut+|silence|ça suffit|ca suffit|attends|pause|ferme[- ]la|c'est bon)"
NOM_SOUPLE = r"(?:d[ie]\s?)?(?:j|dj)[ae]r?v[iy](?:s|ce|sse|ss)?"
RX_STOP_PARTOUT = re.compile(NOM_SOUPLE + r"\W{0,3}(?:\w+\W+){0,1}" + MOTS_STOP + r"\b", re.I)
RX_STOP_SEUL = re.compile(r"^\W*" + MOTS_STOP + r"\W*$", re.I)


def silence_fin() -> float:
    return float(CONFIG.get("silence_fin", 2.5))


class Segmenteur:
    """Découpe le flux micro en phrases (début : son au-dessus du bruit ambiant ; fin : silence)."""

    def __init__(self, silence_fin=0.7, duree_min=0.4, duree_max=12.0, bruit=200.0):
        self.silence_fin, self.duree_min, self.duree_max = silence_fin, duree_min, duree_max
        self.bruit = bruit       # niveau du silence ambiant (moyenne glissante)
        self.avant = []          # ~0,3 s gardées avant le début de la phrase
        self.morceaux = None
        self.debut = 0.0
        self.dernier_son = 0.0
        self.t = 0.0             # horloge du flux (secondes d'audio)

    def seuil(self):
        return max(self.bruit * 3.0, 450)

    def deja_en_cours(self, morceaux, suite=()):
        """La personne parle déjà : on continue l'enregistrement à partir de ces morceaux, puis on rejoue
        ce qui a été entendu depuis (le silence est mesuré depuis ta dernière syllabe, pas depuis maintenant)."""
        self.morceaux, self.debut, self.dernier_son = list(morceaux), self.t, self.t
        return self.rejouer(suite)

    def rejouer(self, suite):
        """Ajoute des trames déjà entendues ; renvoie la phrase si elle s'est terminée pendant ce temps."""
        for m in suite:
            phrase = self.ajouter(m)
            if phrase is not None:
                return phrase
        return None

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
    def __init__(self, sur_eveil, sur_commande, transcrire_rapide, sur_stop=None, est_occupe=None):
        """sur_eveil() : nom entendu ; sur_commande(audio float32 | None) : la demande complète ;
        transcrire_rapide(audio float32) -> str : petit Whisper pour reconnaître le nom ;
        sur_stop() : « Jarvis, stop » ; est_occupe() : Jarvis parle ou travaille (mode vigilance)."""
        self.sur_eveil, self.sur_commande, self.rapide = sur_eveil, sur_commande, transcrire_rapide
        self.sur_stop = sur_stop or (lambda: None)
        self.est_occupe = est_occupe or (lambda: False)
        self._fil = None
        self._continuer = False
        self.erreur = ""
        self.synchrone = False       # tests : analyses dans le même fil
        self._reinitialiser()

    def _reinitialiser(self):
        self.seg = Segmenteur()
        self.commande = None         # Segmenteur de la demande en cours (après le nom)
        self.attente_debut = 0.0
        self.dernier_eveil = -10.0
        self._precedent = None       # fin du morceau précédent (vigilance : morceaux qui se chevauchent)
        self._apres_phrase = []      # ce qui est entendu pendant l'analyse d'une phrase (pour ne rien perdre)
        self._analyse_en_cours = False
        self._a_reprendre = None     # (phrase int16, parle_encore) posé par l'analyse quand le nom est reconnu

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

    # --- reconnaissance du nom dans une phrase
    def analyser(self, phrase: np.ndarray):
        audio = phrase.astype(np.float32) / 32768.0
        try:
            texte = self.rapide(audio) or ""
        except Exception:
            traceback.print_exc()
            return None
        if self.est_occupe() and (RX_STOP_PARTOUT.search(texte) or RX_STOP_SEUL.match(texte)):
            self.sur_stop()
            return texte
        if not RX_NOM.match(texte):
            return None
        reste = RX_NOM.sub("", texte).strip()
        if RX_STOP_SEUL.match(reste):     # « Jarvis, stop » alors qu'il ne faisait rien : on coupe quand même
            self.sur_stop()
            return texte
        self.sur_eveil()
        # « Jarvis, ouvre… » : on continue d'écouter la suite ; « Jarvis ? » : on attend que tu parles
        self._a_reprendre = (phrase, len(reste) >= 3)
        return texte

    def _analyser_fond(self, phrase):
        try:
            self.analyser(phrase)
        finally:
            self._analyse_en_cours = False

    def _lancer(self, fn, *args):
        if self.synchrone:
            fn(*args)
        else:
            threading.Thread(target=fn, args=args, daemon=True).start()

    def _ouvrir_commande(self, morceaux=None, suite=()):
        """Nom reconnu : enregistrement de la demande jusqu'à silence_fin() secondes de silence."""
        self.commande = Segmenteur(silence_fin=silence_fin(), duree_max=DUREE_DEMANDE_MAX, bruit=self.seg.bruit)
        self.attente_debut = self.seg.t
        self._precedent = None
        demande = self.commande.deja_en_cours(morceaux, suite) if morceaux else self.commande.rejouer(suite)
        if demande is not None:      # tu t'étais déjà tu assez longtemps pendant l'analyse : on envoie
            self.commande = None
            self._lancer(self.sur_commande, demande.astype(np.float32) / 32768.0)

    def traiter_trame(self, x: np.ndarray, oww=None):
        """Une trame de 80 ms du micro. Toute la logique d'écoute est ici (testable sans micro)."""
        # 1. le nom vient d'être reconnu par l'analyse : on reprend la phrase + ce qui a suivi
        if self._a_reprendre is not None and self.commande is None:
            phrase, parle_encore = self._a_reprendre
            self._a_reprendre = None
            suite = self._apres_phrase
            # la phrase + tout ce que tu as dit pendant l'analyse : une seule demande continue
            self._ouvrir_commande([phrase] if parle_encore else None, suite)
        self._apres_phrase = (self._apres_phrase + [x])[-APRES_MAX:] if self._analyse_en_cours else []

        # 2. enregistrement d'une demande en cours
        if self.commande is not None:
            self.seg.t += len(x) / SR
            demande = self.commande.ajouter(x)
            if demande is not None:
                self.commande = None
                self._lancer(self.sur_commande, demande.astype(np.float32) / 32768.0)
            elif self.commande.morceaux is None and self.seg.t - self.attente_debut > ATTENTE_DEBUT:
                self.commande = None                           # « Jarvis » puis rien
                self._lancer(self.sur_commande, None)
            return

        # 3. détecteur anglais instantané (« Hey Jarvis »)
        if oww is not None and oww.predict(x).get("hey_jarvis", 0) >= CONFIG.get("seuil_eveil", 0.5) \
                and self.seg.t - self.dernier_eveil > 2:
            self.dernier_eveil = self.seg.t
            oww.reset()
            self._lancer(self.sur_eveil)
            self._ouvrir_commande()
            self.seg = Segmenteur(bruit=self.seg.bruit)
            return

        # 4. détecteur français : phrase -> petit Whisper -> commence par « Jarvis » ?
        vigilant = self.est_occupe()
        self.seg.duree_max = 2.5 if vigilant else 12.0   # sa voix couvre les silences : on découpe court
        phrase = self.seg.ajouter(x)
        if phrase is not None:
            if vigilant and self._precedent is not None:
                phrase = np.concatenate([self._precedent, phrase])   # « Jarvis » | « stop » à cheval
            self._precedent = phrase[-SR:] if vigilant else None
            if not self._analyse_en_cours:
                self._analyse_en_cours = True
                self._apres_phrase = []
                self._lancer(self._analyser_fond, phrase)

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
                self._reinitialiser()
                with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=TRAME) as flux:
                    self.erreur = ""
                    while self._continuer:
                        self.traiter_trame(flux.read(TRAME)[0][:, 0].copy(), oww)
            except Exception as e:   # micro débranché, changé… on réessaie
                self.erreur = f"Micro : {e}"
                traceback.print_exc()
                time.sleep(3)
