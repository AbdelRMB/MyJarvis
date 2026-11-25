"""Constantes communes de la transcription (fréquence, seuils, modèle de reconnaissance des voix)."""
from __future__ import annotations


from ..config import RACINE


SR = 16000


DOSSIER_MODELES = RACINE / "modeles"
MODELE_LOCUTEURS = "wespeaker_en_voxceleb_CAM++.onnx"   # ~28 Mo, reconnaissance du locuteur (indépendant de la langue)
URL_MODELE_LOCUTEURS = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
                        + MODELE_LOCUTEURS.replace("+", "%2B"))
MODELES_WHISPER = ["auto", "base", "small", "medium", "large-v3-turbo", "large-v3"]   # auto : selon la machine
DUREE_FIABLE = 1.0          # s : en dessous, l'empreinte d'une phrase est trop courte pour être sûre
PAUSE_TOUR = 2.0            # s : au-delà, une nouvelle prise de parole commence (nouvel horodatage)
DUREE_TOUR_MAX = 30.0       # s : un tour de parole affiché ne dépasse pas ~30 s (quelques phrases)
