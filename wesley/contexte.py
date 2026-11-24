"""« Ce que je regarde » : Ctrl+Alt+E (⌃⌥E sur Mac) dans n'importe quelle appli.

Wesley copie le texte sélectionné (sans perdre ce qu'il y avait dans le presse-papier), note la fenêtre active et
s'ouvre avec un bandeau : Explique / Corrige / Réponds / Traduis / Résume. Sans sélection, il propose de regarder
l'écran. Plus besoin de copier-coller vers Wesley.
"""
import sys
import time

DERNIER: dict = {}


def fenetre_active() -> str:
    """Titre de la fenêtre au premier plan (Windows) ou nom de l'appli (Mac)."""
    try:
        if sys.platform == "win32":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            tampon = ctypes.create_unicode_buffer(n + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, tampon, n + 1)
            return tampon.value
        if sys.platform == "darwin":
            import subprocess
            return subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of first process '
                                                      'whose frontmost is true'], capture_output=True, text=True,
                                  timeout=3).stdout.strip()
    except Exception:
        pass
    return ""


def copier_selection(copier=None, lire=None, ecrire=None) -> str:
    """Le texte sélectionné dans l'appli au premier plan (Ctrl+C / Cmd+C simulé), presse-papier d'avant remis."""
    if lire is None or ecrire is None:
        import pyperclip
        lire = lire or pyperclip.paste
        ecrire = ecrire or pyperclip.copy
    try:
        avant = lire()
    except Exception:
        avant = ""
    marqueur = f"__wesley_{time.time()}__"
    try:
        ecrire(marqueur)
    except Exception:
        return ""
    (copier or _ctrl_c)()
    texte = ""
    for _ in range(10):            # l'appli met parfois un instant à remplir le presse-papier
        time.sleep(0.05)
        try:
            texte = lire()
        except Exception:
            texte = ""
        if texte != marqueur:
            break
    try:
        ecrire(avant)
    except Exception:
        pass
    return "" if texte == marqueur else (texte or "").strip()


def _ctrl_c():
    from pynput.keyboard import Controller, Key
    k = Controller()
    for t in (Key.ctrl, Key.alt, Key.shift, Key.cmd):   # touches encore enfoncées du raccourci
        try:
            k.release(t)
        except Exception:
            pass
    mod = Key.cmd if sys.platform == "darwin" else Key.ctrl
    with k.pressed(mod):
        k.press("c")
        k.release("c")


def capturer() -> dict:
    """Appelé par le raccourci : sélection + fenêtre, envoyés à l'interface qui s'ouvre."""
    fen = fenetre_active()
    sel = copier_selection()
    DERNIER.clear()
    DERNIER.update(selection=sel[:20000], fenetre=fen[:200], ts=time.time())
    return dict(DERNIER)


ACTIONS = {
    "expliquer": "Explique-moi simplement",
    "corriger": "Corrige (orthographe, grammaire, clarté) et donne-moi la version corrigée prête à coller de",
    "repondre": "Rédige une réponse adaptée à",
    "traduire": "Traduis (en anglais si c'est en français, sinon en français)",
    "resumer": "Résume en quelques points",
}


def consigne(action: str, selection: str, fenetre: str, precision: str = "") -> str:
    """La demande envoyée à Wesley pour une action du bandeau."""
    ou = f" (dans « {fenetre} »)" if fenetre else ""
    if not selection:
        return f"Regarde mon écran{ou} avec regarder_ecran et " + (precision or "dis-moi ce que tu vois et comment m'aider.")
    debut = ACTIONS.get(action) or precision or "Voici un texte"
    return f"{debut} ce texte que j'ai sélectionné{ou}" + (f" ({precision})" if precision and action in ACTIONS else "") \
        + f" :\n\n« {selection} »"
