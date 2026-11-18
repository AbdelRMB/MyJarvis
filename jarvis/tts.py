"""Synthèse vocale côté serveur.

- edge   : voix neuronales Microsoft (très naturelles, gratuites, nécessitent Internet ;
           le texte des réponses est envoyé à Microsoft pour être lu)
- piper  : voix neuronales 100 % locales (dossier voix/, un .onnx + .onnx.json par voix)
"""
import asyncio
import io
import threading
import wave

from .config import RESSOURCES

DOSSIER_VOIX = RESSOURCES / "voix"

VOIX_EDGE = [
    ("fr-FR-HenriNeural", "Henri — homme, France (rapide, recommandé)"),
    ("fr-FR-RemyMultilingualNeural", "Rémy — homme, France, très expressif (plus lent)"),
    ("fr-CA-ThierryNeural", "Thierry — homme, Québec"),
    ("fr-CA-AntoineNeural", "Antoine — homme, Québec"),
    ("fr-CH-FabriceNeural", "Fabrice — homme, Suisse"),
    ("fr-BE-GerardNeural", "Gérard — homme, Belgique"),
    ("fr-FR-DeniseNeural", "Denise — femme, France"),
    ("fr-FR-VivienneMultilingualNeural", "Vivienne — femme, France, très expressive"),
    ("fr-FR-EloiseNeural", "Éloïse — femme, France"),
    ("en-GB-RyanNeural", "Ryan — homme, anglais britannique (façon film)"),
]

_piper: dict = {}
_piper_verrou = threading.Lock()


def voix_piper():
    return sorted(p.name[:-5] for p in DOSSIER_VOIX.glob("*.onnx"))


def _debit_edge(debit: float) -> str:
    return f"{round((debit - 1) * 100):+d}%"


async def _edge(texte: str, voix: str, debit: float) -> bytes:
    import edge_tts
    audio = bytearray()
    async for c in edge_tts.Communicate(texte, voix, rate=_debit_edge(debit)).stream():
        if c["type"] == "audio":
            audio += c["data"]
    if not audio:
        raise RuntimeError("Aucun audio reçu de Microsoft")
    return bytes(audio)


def _piper_synth(texte: str, voix: str, debit: float) -> bytes:
    from piper import PiperVoice, SynthesisConfig
    if voix not in voix_piper():
        voix = (voix_piper() or [None])[0]
        if not voix:
            raise RuntimeError("Aucune voix Piper installée dans le dossier voix/")
    with _piper_verrou:
        if voix not in _piper:
            _piper[voix] = PiperVoice.load(str(DOSSIER_VOIX / f"{voix}.onnx"))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            _piper[voix].synthesize_wav(texte, w, syn_config=SynthesisConfig(length_scale=1 / max(0.5, debit)))
    return buf.getvalue()


async def synthese(texte: str, moteur: str, voix: str, debit: float) -> tuple[bytes, str, str]:
    """Renvoie (audio, type MIME, moteur réellement utilisé). Bascule sur Piper si Edge échoue."""
    texte = texte.strip()[:1200]
    if moteur == "edge":
        try:
            return await asyncio.wait_for(_edge(texte, voix or VOIX_EDGE[0][0], debit), 15), "audio/mpeg", "edge"
        except Exception:
            if not voix_piper():
                raise
    audio = await asyncio.to_thread(_piper_synth, texte, voix if moteur == "piper" else "", debit)
    return audio, "audio/wav", "piper"


def precharger_piper():
    v = voix_piper()
    if v:
        try:
            _piper_synth("Bonjour.", v[0], 1.0)
        except Exception:
            pass
