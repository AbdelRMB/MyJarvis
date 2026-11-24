"""Chargement des modèles Whisper (reconnaissance vocale locale)."""
import sys

APPAREIL = {"dernier": "cpu"}   # où tourne le dernier modèle chargé (affiché dans les journaux et l'onglet Transcription)


def gpu_mac_disponible() -> bool:
    """Puce graphique d'un Mac (MPS) utilisable par CTranslate2 (paquet compilé avec MPS, puce Apple)."""
    if sys.platform != "darwin":
        return False
    try:
        import ctranslate2
        return hasattr(ctranslate2, "get_mps_device_count") and ctranslate2.get_mps_device_count() > 0
    except Exception:
        return False


def _type_calcul_mps() -> str:
    import ctranslate2
    types = ctranslate2.get_supported_compute_types("mps")
    return next(t for t in ("int8_float16", "float16", "int8_float32", "float32") if t in types)


def charger_whisper(nom, gpu: bool = False, **options):
    """Modèle déjà téléchargé : chargé directement depuis le disque, sans vérification en ligne (qui pouvait
    bloquer longtemps). Sinon, téléchargé une fois depuis Hugging Face.
    gpu : sur Mac, essaie la puce graphique (MPS, expérimental, réglage « transcription_gpu ») ; au moindre
    souci, le processeur comme d'habitude."""
    from faster_whisper import WhisperModel
    if gpu and gpu_mac_disponible():
        opts = {k: v for k, v in options.items() if k != "cpu_threads"}
        for local in (True, False):
            try:
                m = WhisperModel(nom, device="mps", compute_type=_type_calcul_mps(), local_files_only=local, **opts)
                APPAREIL["dernier"] = "mps"
                print(f"  Whisper {nom} : puce graphique du Mac (MPS)")
                return m
            except Exception as e:
                if not local:
                    print(f"  (Whisper sur la puce graphique impossible, processeur utilisé : {e})")
    APPAREIL["dernier"] = "cpu"
    try:
        return WhisperModel(nom, device="cpu", compute_type="int8", local_files_only=True, **options)
    except Exception:
        return WhisperModel(nom, device="cpu", compute_type="int8", **options)
