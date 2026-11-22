"""Chargement des modèles Whisper (reconnaissance vocale locale)."""


def charger_whisper(nom, **options):
    """Modèle déjà téléchargé : chargé directement depuis le disque, sans vérification en ligne (qui pouvait
    bloquer longtemps). Sinon, téléchargé une fois depuis Hugging Face."""
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(nom, device="cpu", compute_type="int8", local_files_only=True, **options)
    except Exception:
        return WhisperModel(nom, device="cpu", compute_type="int8", **options)
