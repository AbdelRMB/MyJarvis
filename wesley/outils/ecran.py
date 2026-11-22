"""Vision : Wesley regarde l'écran avec le modèle multimodal."""
import io
import json
import re
from datetime import datetime
from pathlib import Path

import ollama
import pyautogui
from PIL import ImageGrab

from . import outil
from ..config import CONFIG

from ..config import RACINE
CAPTURES = RACINE / "captures"
CAPTURES.mkdir(exist_ok=True)


def _capture(largeur=1280):
    img = ImageGrab.grab(all_screens=False)
    w, h = img.size
    if w > largeur:
        img = img.resize((largeur, int(h * largeur / w)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), (w, h)


def _vision(prompt, image):
    if CONFIG.get("cerveau") == "claude":
        from ..claude import vision
        return vision(prompt, image)
    from ..fournisseurs import est_compatible
    if est_compatible(CONFIG.get("cerveau")):
        from ..openai_cerveau import vision
        return vision(prompt, image)
    r = ollama.chat(model=CONFIG["modele_vision"], think=False,
                    options={"num_ctx": 8192, "temperature": 0.2},
                    messages=[{"role": "user", "content": prompt, "images": [image]}])
    return r.message.content.strip()


@outil
def regarder_ecran(question: str = "Décris précisément ce qui est affiché à l'écran."):
    """Prend une capture de l'écran et l'analyse (voir ce qui est ouvert, lire du texte, comprendre une erreur).
    question: ce qu'il faut chercher ou décrire"""
    img, _ = _capture()
    return _vision(question, img)


@outil
def trouver_et_cliquer(description: str, bouton: str = "left", nombre: int = 1):
    """Repère visuellement un élément à l'écran et clique dessus (si cliquer_element échoue).
    description: ce qu'il faut cliquer (ex: 'le bouton bleu Envoyer')
    bouton: left | right
    nombre: 1 ou 2 (double clic)"""
    img, (w, h) = _capture()
    rep = _vision(
        f"Trouve dans cette capture d'écran : {description}. Réponds UNIQUEMENT en JSON "
        '{"x": <0-1000>, "y": <0-1000>, "trouve": true|false} avec des coordonnées normalisées '
        "(0,0 = coin haut-gauche, 1000,1000 = coin bas-droit) du centre de l'élément.", img)
    m = re.search(r"\{.*?\}", rep, re.S)
    if not m:
        return f"Pas compris la réponse vision : {rep}"
    d = json.loads(m.group(0))
    if not d.get("trouve", True):
        return "Élément non trouvé à l'écran."
    # clic en points d'écran : sur Mac Retina la capture fait 2x la taille logique
    lw, lh = pyautogui.size()
    x, y = int(d["x"] * lw / 1000), int(d["y"] * lh / 1000)
    pyautogui.click(x, y, clicks=nombre, button=bouton, interval=0.1)
    return f"Cliqué en ({x},{y}). Vérifie avec regarder_ecran si besoin."


@outil
def capture_ecran():
    """Enregistre une capture d'écran dans un fichier et renvoie son chemin."""
    p = CAPTURES / f"capture_{datetime.now():%Y%m%d_%H%M%S}.png"
    ImageGrab.grab().save(p)
    return str(p)


@outil
def analyser_image(chemin: str, question: str = "Décris cette image."):
    """Analyse une image du disque (photo, capture, schéma).
    chemin: chemin de l'image
    question: question sur l'image"""
    return _vision(question, Path(chemin).read_bytes())
