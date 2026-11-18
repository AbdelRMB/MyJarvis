"""Contrôle souris, clavier et fenêtres."""
import time

import pyautogui
import pyperclip

from . import outil

pyautogui.FAILSAFE = True   # coup de souris dans le coin haut-gauche = arrêt d'urgence
pyautogui.PAUSE = 0.05


@outil
def souris_deplacer(x: int, y: int):
    """Déplace la souris à des coordonnées écran en pixels.
    x: abscisse
    y: ordonnée"""
    pyautogui.moveTo(x, y, duration=0.2)
    return f"Souris en ({x},{y})"


@outil
def souris_cliquer(x: int = -1, y: int = -1, bouton: str = "left", nombre: int = 1):
    """Clique avec la souris (à la position actuelle si x/y omis).
    x: abscisse (optionnel)
    y: ordonnée (optionnel)
    bouton: left | right | middle
    nombre: 1 = simple clic, 2 = double clic"""
    if x >= 0 and y >= 0:
        pyautogui.click(x, y, clicks=nombre, button=bouton, interval=0.1)
    else:
        pyautogui.click(clicks=nombre, button=bouton, interval=0.1)
    return f"Clic {bouton} x{nombre} en {pyautogui.position()}"


@outil
def souris_glisser(x1: int, y1: int, x2: int, y2: int):
    """Glisser-déposer de (x1,y1) vers (x2,y2).
    x1: départ x
    y1: départ y
    x2: arrivée x
    y2: arrivée y"""
    pyautogui.moveTo(x1, y1)
    pyautogui.dragTo(x2, y2, duration=0.5, button="left")
    return "Glissé."


@outil
def souris_defiler(quantite: int):
    """Fait défiler la molette (positif = haut, négatif = bas).
    quantite: nombre de crans (ex: -5)"""
    pyautogui.scroll(quantite * 120)
    return "Défilé."


@outil
def souris_position():
    """Renvoie la position actuelle de la souris et la taille de l'écran."""
    return f"Souris {tuple(pyautogui.position())}, écran {tuple(pyautogui.size())}"


@outil
def taper_texte(texte: str, entree: bool = False):
    """Tape du texte au clavier dans la fenêtre active (gère les accents via le presse-papier).
    texte: texte à taper
    entree: appuyer sur Entrée après"""
    if texte.isascii():
        pyautogui.write(texte, interval=0.01)
    else:
        ancien = pyperclip.paste()
        pyperclip.copy(texte)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        pyperclip.copy(ancien)
    if entree:
        pyautogui.press("enter")
    return "Tapé."


@outil
def raccourci_clavier(touches: str):
    """Appuie sur une touche ou un raccourci (ex: 'ctrl+s', 'alt+tab', 'win+d', 'enter', 'f5', 'ctrl+shift+p').
    touches: touches séparées par +"""
    ks = [k.strip().lower() for k in touches.split("+")]
    ks = ["win" if k in ("windows", "super") else k for k in ks]
    pyautogui.hotkey(*ks) if len(ks) > 1 else pyautogui.press(ks[0])
    return f"Touches : {touches}"


@outil
def media(action: str):
    """Contrôle le son et la musique.
    action: lecture_pause | suivant | precedent | volume_plus | volume_moins | muet"""
    k = {"lecture_pause": "playpause", "suivant": "nexttrack", "precedent": "prevtrack",
         "volume_plus": "volumeup", "volume_moins": "volumedown", "muet": "volumemute"}.get(action)
    if not k:
        return "Action inconnue."
    for _ in range(5 if "volume_" in action else 1):
        pyautogui.press(k)
    return f"{action} fait."


@outil
def presse_papier(texte: str = ""):
    """Lit le presse-papier (sans argument) ou y écrit du texte.
    texte: texte à copier (optionnel)"""
    if texte:
        pyperclip.copy(texte)
        return "Copié dans le presse-papier."
    return pyperclip.paste() or "(vide)"


@outil
def lister_fenetres():
    """Liste les fenêtres ouvertes avec leur position."""
    import pygetwindow as gw
    out = []
    for w in gw.getAllWindows():
        if w.title.strip() and w.visible and w.width > 50:
            out.append(f"'{w.title}' pos=({w.left},{w.top}) taille={w.width}x{w.height}{' [active]' if w.isActive else ''}")
    return "\n".join(out)


@outil
def gerer_fenetre(titre: str, action: str = "activer"):
    """Active, maximise, minimise, restaure ou ferme une fenêtre (titre partiel).
    titre: partie du titre de la fenêtre
    action: activer | maximiser | minimiser | restaurer | fermer"""
    import pygetwindow as gw
    ws = [w for w in gw.getAllWindows() if titre.lower() in w.title.lower() and w.title.strip()]
    if not ws:
        return "Fenêtre introuvable."
    w = ws[0]
    if action == "activer":
        if w.isMinimized:
            w.restore()
        try:
            w.activate()
        except Exception:
            pyautogui.press("alt"); w.activate()
    elif action == "maximiser": w.maximize()
    elif action == "minimiser": w.minimize()
    elif action == "restaurer": w.restore()
    elif action == "fermer": w.close()
    return f"{action} : {w.title}"


@outil
def cliquer_element(nom: str, fenetre: str = ""):
    """Clique sur un bouton/élément d'interface par son texte via l'accessibilité Windows (plus fiable que les coordonnées).
    nom: texte du bouton/menu/lien
    fenetre: partie du titre de la fenêtre (défaut : fenêtre active)"""
    from pywinauto import Desktop
    d = Desktop(backend="uia")
    if fenetre:
        wins = [w for w in d.windows() if fenetre.lower() in w.window_text().lower()]
        if not wins:
            return "Fenêtre introuvable."
        win = wins[0]
    else:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        win = d.window(handle=hwnd)
    n = nom.lower()
    for el in win.descendants():
        try:
            if n in el.window_text().lower() and el.is_visible():
                r = el.rectangle()
                pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                return f"Cliqué sur '{el.window_text()}' ({el.element_info.control_type})"
        except Exception:
            continue
    return "Élément introuvable. Essaie regarder_ecran ou trouver_et_cliquer."
