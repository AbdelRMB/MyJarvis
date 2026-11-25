"""Sources audio et découpage du flux : micro, son de l'ordinateur (macOS ScreenCaptureKit, Windows WASAPI
loopback), fichier importé, mixage 16 kHz et blocs coupés aux pauses."""
from __future__ import annotations

import threading
import time

from .communs import SR


# ====================================================================================================
# Découpage du flux en blocs (aux pauses)
# ====================================================================================================
class Decoupeur:
    """Accumule le son et rend des blocs (début en s, audio) coupés à une pause, pour que Whisper ait des
    phrases entières et qu'un changement de locuteur tombe le plus souvent entre deux blocs."""

    GARDE = 1.0                 # s de silence gardées avant une reprise de parole (début de phrase faible)

    def __init__(self, duree_min=3.0, duree_max=20.0, pause=0.5):
        self.duree_min, self.duree_max, self.pause = duree_min, duree_max, pause
        self.morceaux: list = []
        self.taille = 0
        self.debut = 0.0            # position (s) du début du bloc en cours dans l'enregistrement
        self.silence = 0.0          # s de calme à la fin du bloc en cours (pour couper aux pauses)
        self.voix = False           # le bloc contient autre chose que du silence : il ira à Whisper
        self.bruit = 0.001          # plancher de bruit ambiant (suit les creux, remonte lentement)
        self.parole = 0.0           # niveau moyen de la voix entendue (moyenne glissante)
        self.ecarte = 0.0           # s de silence non envoyées à Whisper (diagnostic)

    def seuil(self):
        """Seuil des pauses (où couper un bloc) : bas exprès, une voix lointaine arrive faible. Jamais plus de la
        moitié du niveau de la voix : sinon une voix très faible serait « en pause » en permanence et coupée
        toutes les 3 s au milieu des mots."""
        s = max(self.bruit * 2.5, 0.003)
        if self.parole:
            s = min(s, self.parole * 0.5)
        return max(s, self.seuil_voix())

    def seuil_voix(self):
        """En dessous : silence, jamais envoyé à Whisper. Juste au-dessus du plancher de bruit : une voix
        faible (fond de salle, visio à bas volume) part toujours à Whisper, dont le VAD trie ensuite."""
        return max(self.bruit * 1.6, 0.0004)

    def ajouter(self, x) -> tuple[float, object] | None:
        import numpy as np
        if not len(x):
            return None
        rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float32))))
        # plancher de bruit : descend vite dans les creux, monte lentement (+3 %/s). Avant, il suivait la
        # moyenne des morceaux « calmes » : une voix faible le faisait grimper, le seuil montait avec, et toute
        # la parole faible était prise pour du silence et jetée avant Whisper.
        self.bruit = 0.5 * (self.bruit + rms) if rms < self.bruit else min(rms, self.bruit * 1.003)
        if rms < self.seuil():
            self.silence += len(x) / SR
        else:
            self.silence = 0.0
        if rms >= self.seuil_voix():
            self.voix = True
            self.parole = rms if not self.parole else 0.95 * self.parole + 0.05 * rms
        self.morceaux.append(x)
        self.taille += len(x)
        duree = self.taille / SR
        if not self.voix and duree > self.GARDE + self.pause:
            # que du silence : on avance sans rien transcrire (on garde la fin, au cas où une phrase commence)
            garde = int(self.GARDE * SR)
            tout = np.concatenate(self.morceaux)
            self.debut += (len(tout) - garde) / SR
            self.ecarte += (len(tout) - garde) / SR
            self.morceaux, self.taille, self.silence = [tout[-garde:]], garde, min(self.silence, self.GARDE)
            return None
        if duree >= self.duree_min and self.silence >= self.pause:
            return self.vider()
        if duree >= self.duree_max:
            return self._couper_au_creux()
        return None

    def _couper_au_creux(self):
        """Bloc trop long sans pause nette : coupé au moment le plus calme des 3 dernières secondes (entre deux
        mots), pas au milieu d'un mot ; la suite commence le bloc suivant."""
        import numpy as np
        tout = np.concatenate(self.morceaux)
        trame = SR // 20
        zone = tout[max(0, len(tout) - 3 * SR):]
        n = len(zone) // trame
        coupe = len(tout)
        if n >= 4:
            rms = np.sqrt(np.mean(np.square(zone[:n * trame].reshape(n, trame), dtype=np.float32), axis=1))
            k = int(np.argmin(rms))
            if rms[k] < 0.5 * float(np.median(rms)):     # vrai creux (sinon : coupe à la fin, comme avant)
                coupe = len(tout) - len(zone) + (k + 1) * trame
        debut = self.debut
        bloc, reste = tout[:coupe], tout[coupe:]
        self.debut += len(bloc) / SR
        self.morceaux, self.taille = ([reste], len(reste)) if len(reste) else ([], 0)
        self.silence, self.voix = 0.0, bool(len(reste))
        return debut, bloc

    def vider(self):
        import numpy as np
        if not self.morceaux:
            return None
        bloc, debut, voix = np.concatenate(self.morceaux), self.debut, self.voix
        self.debut += len(bloc) / SR
        self.morceaux, self.taille, self.silence, self.voix = [], 0, 0.0, False
        if not voix:
            self.ecarte += len(bloc) / SR
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
        self.perdu = 0.0            # s jetées parce que la source avait trop d'avance (diagnostic)

    RETARD_MAX = 15.0           # s d'avance tolérées (horloge de la carte son un peu plus rapide que le Mac)

    def pousser(self, x, sr: float = SR):
        x = reechantillonner(x, sr)
        with self.verrou:
            self.morceaux.append(x)
            self.taille += len(x)
            self.recu += len(x)
            if self.taille > SR * self.RETARD_MAX:
                # très en retard : on jette le plus ancien (gardé 3 s). Avant, la limite était de 3 s et on ne
                # gardait que la dernière seconde : un simple à-coup de la source faisait perdre 2 s de parole.
                import numpy as np
                tout = np.concatenate(self.morceaux)
                self.perdu += (len(tout) - 3 * SR) / SR
                tout = tout[-3 * SR:]
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
    from ..plateforme import MAC, WIN
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
