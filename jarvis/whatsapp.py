"""WhatsApp : envoyer un message et des images (captures d'écran…) à un contact, par WhatsApp Web dans le navigateur
de Jarvis. Il faut scanner une fois le QR code avec le téléphone (WhatsApp › Appareils connectés) : la session reste.

WhatsApp Web change souvent son interface : les éléments sont cherchés par plusieurs indices (attributs, libellés
français et anglais) plutôt que par une seule adresse fixe.
"""
import json
import time

from . import navigateur

URL = "https://web.whatsapp.com/"


def _js(expr: str):
    return navigateur._js(expr)


def _attendre(expr: str, delai=30) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            if _js(expr):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def ouvrir() -> str:
    """Ouvre WhatsApp Web ; renvoie « ok », « qr » (à scanner) ou « chargement »."""
    try:
        deja = "web.whatsapp.com" in (_js("location.href") or "")
    except Exception:
        deja = False
    if not deja:
        navigateur.ouvrir(URL)
    fin = time.time() + 45
    while time.time() < fin:
        if _js("!!document.querySelector('#side, [data-testid=chat-list], div[aria-label*=\"hat list\"], div[aria-label*=\"iste des discussions\"]')"):
            return "ok"
        if _js("!!document.querySelector('canvas[aria-label*=\"QR\"], div[data-ref] canvas, [data-testid=qrcode]')"):
            return "qr"
        time.sleep(1)
    return "chargement"


_RECHERCHE = ("document.querySelector('#side div[contenteditable=\"true\"]') || "
              "document.querySelector('div[contenteditable=\"true\"][data-tab=\"3\"]') || "
              "[...document.querySelectorAll('div[contenteditable=\"true\"], input')].find(e => /search|recherch/i.test("
              "(e.getAttribute('aria-label') || '') + (e.getAttribute('title') || '') + (e.placeholder || '')))")
_SAISIE = ("document.querySelector('#main footer div[contenteditable=\"true\"]') || "
           "[...document.querySelectorAll('div[contenteditable=\"true\"]')].find(e => /message|tapez|type a/i.test("
           "(e.getAttribute('aria-label') || '') + (e.getAttribute('title') || '') + (e.getAttribute('aria-placeholder') || '')))")


def _taper_dans(expr_element: str, texte: str):
    pos = _js(f"""(() => {{ const e = {expr_element}; if (!e) return null; e.focus(); e.click();
        const r = e.getBoundingClientRect(); return {{x: r.left + 10, y: r.top + r.height / 2}}; }})()""")
    if not pos:
        raise RuntimeError("Zone de saisie WhatsApp introuvable (l'interface a peut-être changé).")
    c = navigateur._onglet()
    for t in ("mousePressed", "mouseReleased"):
        c.envoyer("Input.dispatchMouseEvent", {"type": t, "x": pos["x"], "y": pos["y"], "button": "left", "clickCount": 1})
    c.envoyer("Input.insertText", {"text": texte})


def _entree():
    c = navigateur._onglet()
    c.envoyer("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
    c.envoyer("Input.dispatchKeyEvent", {"type": "char", "key": "Enter", "text": "\r", "unmodifiedText": "\r"})
    c.envoyer("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})


def envoyer(contact: str, message: str = "", fichiers: list | None = None) -> str:
    etat = ouvrir()
    if etat == "qr":
        navigateur.afficher()
        return ("WhatsApp Web demande de scanner le QR code : sur ton téléphone, WhatsApp › Appareils connectés › "
                "Connecter un appareil, puis scanne le code affiché dans le navigateur de Jarvis. Redemande ensuite.")
    if etat != "ok":
        return "WhatsApp Web ne s'est pas chargé : réessaie dans un instant."
    # 1. ouvrir la conversation du contact par la recherche
    _js(f"(() => {{ const e = {_RECHERCHE}; if (e) {{ e.focus(); document.execCommand('selectAll'); document.execCommand('delete'); }} }})()")
    _taper_dans(_RECHERCHE, contact)
    time.sleep(2)
    nom = _js(f"""(() => {{
        const cle = {json.dumps(contact.lower())};
        const items = [...document.querySelectorAll('#pane-side [role=listitem], #pane-side [role=row], [aria-label*="résultats"] [role=listitem], [aria-label*="esults"] [role=listitem]')];
        const titres = items.map(i => [i, (i.querySelector('span[title]') || {{}}).title || '']);
        const exacts = titres.filter(([i, x]) => x.toLowerCase() === cle);
        const partiels = titres.filter(([i, x]) => x.toLowerCase().includes(cle));
        const noms = [...new Set(partiels.map(([i, x]) => x))];
        if (!exacts.length && noms.length > 1) return {plusieurs: noms.slice(0, 8)};
        const t = exacts[0] || partiels[0];
        if (!t) return null;
        const r = t[0].getBoundingClientRect(); window.__jarvisContact = {{x: r.left + r.width / 2, y: r.top + r.height / 2}};
        return t[1]; }})()""")
    if isinstance(nom, dict):
        return f"Plusieurs contacts correspondent à « {contact} » : {', '.join(nom['plusieurs'])}. Demande lequel (nom complet)."
    if not nom:
        return f"Contact « {contact} » introuvable dans WhatsApp : donne son nom tel qu'il est enregistré dans ton téléphone."
    pos = _js("window.__jarvisContact")
    c = navigateur._onglet()
    for t in ("mousePressed", "mouseReleased"):
        c.envoyer("Input.dispatchMouseEvent", {"type": t, "x": pos["x"], "y": pos["y"], "button": "left", "clickCount": 1})
    if not _attendre(f"!!({_SAISIE})", 15):
        return f"La conversation avec {nom} ne s'ouvre pas."
    # 2. pièces jointes : bouton « joindre », puis le champ fichier des photos (sans fenêtre de choix du système)
    if fichiers:
        _js("""(() => { const b = document.querySelector('#main footer [aria-label*="oindre"], #main footer [aria-label*="ttach"], '
              + '#main footer [title*="oindre"], #main footer [title*="ttach"], #main footer span[data-icon*="plus"], #main footer span[data-icon*="attach"]');
              (b && (b.closest('button, [role=button]') || b)).click(); })()""")
        if not _attendre("!!document.querySelector('input[type=file][accept*=\"image\"]')", 8):
            return "Bouton « joindre » de WhatsApp introuvable (l'interface a peut-être changé)."
        navigateur.joindre_fichiers('input[type=file][accept*="image"]', fichiers)
        apercu = ("document.querySelector('[aria-label*=\"nvoyer\"], [aria-label=\"Send\"], span[data-icon=\"send\"], "
                  "span[data-icon=\"wds-ic-send-filled\"]')")
        if not _attendre(f"!!({apercu})", 20):
            return "L'aperçu de la pièce jointe ne s'affiche pas."
        if message:   # légende de l'image
            legende = ("[...document.querySelectorAll('div[contenteditable=\"true\"]')].find(e => /légende|caption|ajouter|add/i.test("
                       "(e.getAttribute('aria-label') || '') + (e.getAttribute('aria-placeholder') || '')))")
            if _js(f"!!({legende})"):
                _taper_dans(legende, message)
                message = ""
        time.sleep(0.5)
        _js(f"(() => {{ const b = {apercu}; (b.closest('button, [role=button]') || b).click(); }})()")
        time.sleep(2.5)
    if message:
        _taper_dans(_SAISIE, message)
        time.sleep(0.3)
        _entree()
        time.sleep(1.5)
    n = len(fichiers or [])
    return f"Envoyé à {nom} sur WhatsApp" + (f" ({n} fichier{'s' if n > 1 else ''})" if n else "") + "."
