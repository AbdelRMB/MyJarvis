"""Navigateur de Jarvis : une fenêtre Chrome (ou Edge / Brave) qu'il pilote lui-même, avec son propre profil.

- Tu t'y connectes une fois à tes sites (entreprise, SSO, 2FA…) : les sessions restent dans son profil.
- Pilotage par le protocole de débogage de Chrome (CDP, le même que Playwright) : ouvrir une page, la « voir » sous
  forme de liste d'éléments numérotés (liens, boutons, champs), cliquer, remplir, appuyer sur une touche, capturer.
- Démonstration : pendant que tu fais une tâche, il enregistre tes clics et les champs remplis (jamais les mots de
  passe) pour en faire une procédure.
Pas de Chrome / Edge / Brave sur l'ordinateur : « Chrome for Testing » (Chrome officiel de Google pour
l'automatisation, ~150 Mo) se télécharge depuis l'écran Sites.
"""
import io
import itertools
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import requests

from .config import RACINE

MAC, WIN = sys.platform == "darwin", sys.platform == "win32"
PORT = 9333
DOSSIER = (Path.home() / "Library" / "Application Support" / "Jarvis" / "navigateur" if MAC
           else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Jarvis" / "navigateur")
PROFIL = DOSSIER / "profil"
CFT = DOSSIER / "chrome"
INSTALL = {"en_cours": False, "pct": 0, "erreur": ""}

_CANDIDATS_MAC = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"]
_CANDIDATS_WIN = [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                  r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                  r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
                  r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                  r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
                  r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"]


# ---------- trouver / installer un navigateur ----------
def executable() -> str:
    if MAC:
        trouves = list(CFT.glob("*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"))
        for c in _CANDIDATS_MAC + [str(p) for p in trouves]:
            if os.path.exists(c):
                return c
    elif WIN:
        for c in [os.path.expandvars(x) for x in _CANDIDATS_WIN] + [str(p) for p in CFT.glob("*/chrome.exe")]:
            if os.path.exists(c):
                return c
    return ""


def installer_chrome():
    if INSTALL["en_cours"]:
        return
    INSTALL.update(en_cours=True, pct=0, erreur="")
    threading.Thread(target=_installer_chrome, daemon=True, name="installation-chrome").start()


def _installer_chrome():
    try:
        import platform
        plateforme = ("mac-arm64" if platform.machine() == "arm64" else "mac-x64") if MAC else "win64"
        infos = requests.get("https://googlechromelabs.github.io/chrome-for-testing/"
                             "last-known-good-versions-with-downloads.json", timeout=30).json()
        url = next(d["url"] for d in infos["channels"]["Stable"]["downloads"]["chrome"] if d["platform"] == plateforme)
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total, recu, buf = int(r.headers.get("content-length") or 0), 0, io.BytesIO()
            for bloc in r.iter_content(1 << 20):
                buf.write(bloc)
                recu += len(bloc)
                INSTALL["pct"] = int(recu * 95 / total) if total else 50
        shutil.rmtree(CFT, ignore_errors=True)
        CFT.mkdir(parents=True, exist_ok=True)
        if MAC:   # ditto garde les liens symboliques et les droits du paquet .app (zipfile les perd)
            z = DOSSIER / "chrome.zip"
            z.write_bytes(buf.getvalue())
            subprocess.run(["ditto", "-x", "-k", str(z), str(CFT)], check=True)
            z.unlink()
        else:
            zipfile.ZipFile(buf).extractall(CFT)
        if not executable():
            raise RuntimeError("Chrome téléchargé mais introuvable après l'extraction.")
        INSTALL["pct"] = 100
    except Exception as e:
        INSTALL["erreur"] = str(e)[:500]
    finally:
        INSTALL["en_cours"] = False


# ---------- connexion CDP ----------
class _Cdp:
    """Connexion au protocole de débogage d'un onglet. Un fil lit en continu : réponses et événements."""

    def __init__(self, ws_url: str):
        from websockets.sync.client import connect
        self.ws = connect(ws_url, max_size=64 * 1024 * 1024, open_timeout=10)
        self.ids = itertools.count(1)
        self.attente: dict = {}
        self.ecouteurs: dict = {}
        self.verrou = threading.Lock()
        self.ouvert = True
        threading.Thread(target=self._lire, daemon=True, name="cdp").start()

    def _lire(self):
        try:
            for brut in self.ws:
                m = json.loads(brut)
                if "id" in m and m["id"] in self.attente:
                    self.attente.pop(m["id"]).put(m)
                elif "method" in m:
                    for f in list(self.ecouteurs.get(m["method"], [])):
                        try:
                            f(m.get("params", {}))
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            self.ouvert = False
            for q in list(self.attente.values()):
                q.put({"error": {"message": "connexion au navigateur perdue"}})

    def envoyer(self, methode: str, params=None, delai=30):
        q = queue.Queue()
        i = next(self.ids)
        self.attente[i] = q
        with self.verrou:
            self.ws.send(json.dumps({"id": i, "method": methode, "params": params or {}}))
        try:
            r = q.get(timeout=delai)
        except queue.Empty:
            self.attente.pop(i, None)
            raise RuntimeError(f"le navigateur ne répond pas ({methode})")
        if "error" in r:
            raise RuntimeError(r["error"].get("message", str(r["error"])))
        return r.get("result", {})

    def ecouter(self, methode: str, fonction):
        self.ecouteurs.setdefault(methode, []).append(fonction)


_etat = {"proc": None, "cdp": None, "cible": None}
_verrou = threading.Lock()


def _api(chemin: str, methode="GET"):
    return requests.request(methode, f"http://127.0.0.1:{PORT}{chemin}", timeout=5).json()


def _repond() -> bool:
    try:
        _api("/json/version")
        return True
    except Exception:
        return False


def demarrer() -> str:
    """Lance la fenêtre du navigateur de Jarvis (si besoin) et renvoie un message d'état."""
    with _verrou:
        if _repond():
            return "ok"
        exe = executable()
        if not exe:
            raise RuntimeError("Aucun navigateur compatible (Chrome, Edge, Brave) : télécharge celui de Jarvis dans l'écran Sites.")
        PROFIL.mkdir(parents=True, exist_ok=True)
        _etat["proc"] = subprocess.Popen(
            [exe, f"--remote-debugging-port={PORT}", "--remote-allow-origins=*", f"--user-data-dir={PROFIL}",
             "--no-first-run", "--no-default-browser-check", "--disable-features=Translate", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if WIN else 0)
        for _ in range(60):
            if _repond():
                _etat["cdp"] = None
                return "ok"
            time.sleep(0.25)
        raise RuntimeError("Le navigateur de Jarvis ne démarre pas.")


def _onglet() -> _Cdp:
    """Connexion à l'onglet actif (le premier onglet « page » visible)."""
    demarrer()
    c = _etat["cdp"]
    if c is not None and c.ouvert:
        try:
            cibles = [t["id"] for t in _api("/json/list") if t.get("type") == "page"]
            if _etat["cible"] in cibles:
                return c
        except Exception:
            pass
    pages = [t for t in _api("/json/list") if t.get("type") == "page"]
    if not pages:
        pages = [_api("/json/new?about:blank", "PUT")]
    t = pages[0]
    if c is not None:
        try:
            c.ws.close()
        except Exception:
            pass
    c = _Cdp(t["webSocketDebuggerUrl"])
    for dom in ("Page.enable", "Runtime.enable"):
        c.envoyer(dom)
    try:   # la fenêtre est souvent derrière : sans ça, Chrome ne donne pas le focus aux champs
        c.envoyer("Emulation.setFocusEmulationEnabled", {"enabled": True})
    except Exception:
        pass
    _etat.update(cdp=c, cible=t["id"])
    _rebrancher_enregistrement(c)
    return c


def _js(expression: str, delai=30):
    r = _onglet().envoyer("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}, delai)
    if r.get("exceptionDetails"):
        raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", "erreur JavaScript")[:300])
    return r.get("result", {}).get("value")


def _attendre_chargement(delai=20):
    fin = time.time() + delai
    time.sleep(0.4)
    while time.time() < fin:
        try:
            if _js("document.readyState") == "complete":
                time.sleep(0.6)   # applis web : laisse le temps au contenu dynamique d'arriver
                return
        except Exception:
            pass
        time.sleep(0.3)


# ---------- actions ----------
def ouvrir(url: str) -> dict:
    if not url.startswith(("http://", "https://", "about:", "file:")):
        url = "https://" + url
    _onglet().envoyer("Page.navigate", {"url": url})
    _attendre_chargement()
    return instantane()


_JS_INSTANTANE = r"""
(() => {
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const propre = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 90);
  const libelle = (e) => {
    if (e.getAttribute('aria-label')) return propre(e.getAttribute('aria-label'));
    if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l) return propre(l.innerText); }
    const l = e.closest('label'); if (l && l !== e) return propre(l.innerText);
    return propre(e.innerText || e.value && e.type !== 'password' && e.value || e.placeholder || e.title || e.name || e.alt ||
                  (e.querySelector('img[alt]') || {}).alt || '');
  };
  document.querySelectorAll('[data-jarvis-ref]').forEach(e => e.removeAttribute('data-jarvis-ref'));
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [role=tab], ' +
              '[role=menuitem], [role=checkbox], [role=option], [role=combobox], [onclick], [contenteditable=true], summary';
  const elements = []; let n = 0;
  for (const e of document.querySelectorAll(sel)) {
    if (!visible(e) || n >= 250) continue;
    n++; e.setAttribute('data-jarvis-ref', n);
    const tag = e.tagName.toLowerCase();
    const d = { ref: n, type: e.getAttribute('role') || (tag === 'input' ? 'champ ' + (e.type || 'texte') : tag === 'a' ? 'lien' : tag),
                libelle: libelle(e) };
    if (tag === 'a') d.href = e.href;
    if (tag === 'select') d.options = [...e.options].slice(0, 15).map(o => propre(o.text));
    if (['input', 'textarea'].includes(tag) && e.type !== 'password' && e.value) d.valeur = propre(e.value);
    if (e.disabled) d.desactive = true;
    elements.push(d);
  }
  const titres = [...document.querySelectorAll('h1, h2, h3')].filter(visible).slice(0, 25).map(h => propre(h.innerText));
  const texte = ((document.querySelector('main') || document.body).innerText || '').replace(/\s+/g, ' ').slice(0, 2500);
  return { url: location.href, titre: document.title, titres, elements, texte };
})()
"""


def instantane() -> dict:
    """La page vue par Jarvis : adresse, titre, titres, éléments interactifs numérotés, début du texte."""
    return _js(_JS_INSTANTANE)


def decrire(v: dict, max_elements=150) -> str:
    lignes = [f"Page : {v.get('titre') or '(sans titre)'} — {v.get('url')}"]
    if v.get("titres"):
        lignes.append("Titres : " + " | ".join(v["titres"][:12]))
    lignes.append("Éléments (utilise le numéro pour cliquer ou remplir) :")
    for e in v.get("elements", [])[:max_elements]:
        extra = ""
        if e.get("options"):
            extra = f" options: {', '.join(e['options'])}"
        if e.get("valeur"):
            extra += f" (valeur : {e['valeur']})"
        if e.get("desactive"):
            extra += " (désactivé)"
        lignes.append(f"[{e['ref']}] {e['type']} « {e['libelle']} »{extra}")
    if v.get("texte"):
        lignes.append("\nTexte de la page (début) : " + v["texte"][:1500])
    return "\n".join(lignes)


def _element(cible: str) -> dict:
    """Trouve un élément par son numéro ([12]) ou par son libellé (mêmes libellés que navigateur_voir : texte, étiquette
    du champ, aria-label, placeholder…) ; renvoie sa position et son libellé."""
    cible = str(cible).strip().strip("[]")
    if not cible.isdigit():
        cle = cible.lower().strip("«» \"'")
        elements = instantane().get("elements", [])
        exacts = [x for x in elements if x["libelle"].lower() == cle]
        if len(exacts) > 1 and len({x.get("href") or x["ref"] for x in exacts}) > 1:   # même lien en double : pas ambigu
            raise RuntimeError(f"Plusieurs éléments « {cible} » : " + ", ".join(f"[{x['ref']}] {x['type']}" for x in exacts[:8])
                               + ". Précise le numéro.")
        e = exacts[0] if exacts else next((x for x in elements if cle in x["libelle"].lower()), None)
        if not e:
            raise RuntimeError(f"Élément « {cible} » introuvable : regarde la page avec navigateur_voir.")
        cible = str(e["ref"])
    r = _js(f"""(() => {{ const e = document.querySelector('[data-jarvis-ref="{cible}"]'); if (!e) return null;
        e.scrollIntoView({{block: 'center'}}); const r = e.getBoundingClientRect();
        return {{ref: {cible}, x: r.left + r.width / 2, y: r.top + r.height / 2, tag: e.tagName.toLowerCase(), type: e.type || '',
                 libelle: (e.innerText || e.value || e.getAttribute('aria-label') || e.placeholder || e.name || '').trim().slice(0, 80)}}; }})()""")
    if not r:
        raise RuntimeError(f"Élément « {cible} » introuvable : la page a changé, regarde-la avec navigateur_voir.")
    return r


def cliquer(cible: str) -> dict:
    e = _element(cible)
    c = _onglet()
    for t in ("mousePressed", "mouseReleased"):   # vrais clics (les applis web ignorent souvent el.click())
        c.envoyer("Input.dispatchMouseEvent", {"type": t, "x": e["x"], "y": e["y"], "button": "left", "clickCount": 1})
    _attendre_chargement(8)
    return instantane()


def remplir(cible: str, valeur: str) -> dict:
    e = _element(cible)
    cible = str(e["ref"])
    if e["tag"] == "select":
        _js(f"""(() => {{ const s = document.querySelector('[data-jarvis-ref="{cible}"]');
            const o = [...s.options].find(o => o.text.toLowerCase().includes({json.dumps(valeur.lower())}) || o.value === {json.dumps(valeur)});
            if (!o) throw new Error('option introuvable'); s.value = o.value;
            s.dispatchEvent(new Event('input', {{bubbles: true}})); s.dispatchEvent(new Event('change', {{bubbles: true}})); }})()""")
        return instantane()
    c = _onglet()
    for t in ("mousePressed", "mouseReleased"):
        c.envoyer("Input.dispatchMouseEvent", {"type": t, "x": e["x"], "y": e["y"], "button": "left", "clickCount": 1})
    ref = json.dumps(str(cible).strip().strip("[]"))
    _js(f"""(() => {{ const r = {ref}; const e = /^\\d+$/.test(r) ? document.querySelector(`[data-jarvis-ref="${{r}}"]`)
            : document.activeElement; if (!e) return; e.focus();
            if ('select' in e) e.select(); else if (e.isContentEditable) document.execCommand('selectAll'); }})()""")
    c.envoyer("Input.insertText", {"text": valeur})   # saisie « réelle » : les formulaires React/Vue la voient
    return instantane()


_TOUCHES = {"entree": ("Enter", 13, "\r"), "entrée": ("Enter", 13, "\r"), "enter": ("Enter", 13, "\r"),
            "tab": ("Tab", 9, ""), "echap": ("Escape", 27, ""), "échap": ("Escape", 27, ""), "escape": ("Escape", 27, ""),
            "bas": ("ArrowDown", 40, ""), "haut": ("ArrowUp", 38, ""), "retour": ("Backspace", 8, "")}


def touche(nom: str) -> dict:
    cle, code, texte = _TOUCHES.get(nom.lower().strip(), (nom, 0, ""))
    c = _onglet()
    avant = _js("location.href")
    # comme un vrai clavier : touche enfoncée, caractère (« \r » pour Entrée), touche relâchée
    c.envoyer("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": cle, "code": cle, "windowsVirtualKeyCode": code,
                                         "nativeVirtualKeyCode": code})
    if texte:
        c.envoyer("Input.dispatchKeyEvent", {"type": "char", "key": cle, "text": texte, "unmodifiedText": texte})
    c.envoyer("Input.dispatchKeyEvent", {"type": "keyUp", "key": cle, "code": cle, "windowsVirtualKeyCode": code,
                                         "nativeVirtualKeyCode": code})
    _attendre_chargement(8)
    if cle == "Enter" and _js("location.href") == avant:
        # certains formulaires ignorent la touche simulée : on envoie le formulaire du champ actif
        _js("(() => { const f = document.activeElement && document.activeElement.form; if (f) f.requestSubmit ? f.requestSubmit() : f.submit(); })()")
        _attendre_chargement(8)
    return instantane()


def capture() -> bytes:
    import base64
    return base64.b64decode(_onglet().envoyer("Page.captureScreenshot", {"format": "png"})["data"])


def afficher():
    """Met la fenêtre du navigateur au premier plan (pour que l'utilisateur s'y connecte ou fasse sa démonstration)."""
    c = _onglet()
    try:
        c.envoyer("Page.bringToFront")
    except Exception:
        pass


# ---------- enregistrement d'une démonstration ----------
ENREG = {"actif": False, "etapes": [], "site": "", "ids": set(), "jeton": ""}
_JS_ENREG = r"""
(() => {
  if (window.__jarvisEnreg === '__JETON__') return; window.__jarvisEnreg = '__JETON__';
  const propre = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 90);
  const lib = (e) => propre(e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].innerText) ||
                            e.innerText || e.placeholder || e.title || e.name || e.alt ||
                            (e.querySelector && (e.querySelector('img[alt]') || {}).alt) || e.value || '');
  // chaque étape est aussi gardée dans l'onglet (sessionStorage) et renvoyée au chargement de la page suivante :
  // un clic qui change de page peut partir avant que son message n'arrive (Jarvis ignore les doublons)
  // seulement les étapes de CET enregistrement (un ancien peut rester dans la mémoire de l'onglet d'un autre site)
  const file = () => { try { return JSON.parse(sessionStorage.__jarvisFile || '[]').filter(d => d.jeton === '__JETON__'); } catch (x) { return []; } };
  const poster = (d) => { try { window.jarvisNote(JSON.stringify(d)); } catch (x) {} };
  const envoyer = (d) => {
    d = {...d, jeton: '__JETON__', id: Date.now() + '-' + Math.random().toString(36).slice(2), url: location.href, titre: document.title};
    try { sessionStorage.__jarvisFile = JSON.stringify([...file(), d].slice(-80)); } catch (x) {}
    poster(d);
  };
  file().forEach(poster);
  document.addEventListener('click', (ev) => {
    const e = ev.target.closest('a, button, [role], input[type=submit], input[type=button], input[type=checkbox], input[type=radio], summary, [onclick]') || ev.target;
    // un clic pour entrer dans un champ n'est pas une étape : la saisie qui suit l'est
    if (['TEXTAREA', 'SELECT'].includes(e.tagName) || (e.tagName === 'INPUT' && !['submit', 'button', 'checkbox', 'radio', 'image'].includes(e.type))) return;
    envoyer({ action: 'clic', element: e.tagName.toLowerCase(), libelle: lib(e) });
  }, true);
  const saisie = (ev) => {
    const e = ev.target; if (!e || !e.tagName || !['INPUT', 'TEXTAREA', 'SELECT'].includes(e.tagName)) return;
    if (['submit', 'button', 'checkbox', 'radio'].includes(e.type)) return;
    const secret = e.type === 'password' || /pass|mdp|secret|token|cvc|cvv|iban|carte/i.test(e.name + e.id);
    envoyer({ action: 'saisie', element: e.tagName.toLowerCase(), libelle: lib(e),
              valeur: secret ? '(secret, non enregistré)' : (e.tagName === 'SELECT' ? e.options[e.selectedIndex]?.text : propre(e.value)) });
  };
  let minuteur = null;
  document.addEventListener('change', saisie, true);
  document.addEventListener('input', (ev) => { clearTimeout(minuteur); minuteur = setTimeout(() => saisie(ev), 700); }, true);
  window.__jarvisFinSaisie = () => { const e = document.activeElement; if (e) saisie({target: e}); };
})();
"""


def _rebrancher_enregistrement(c: _Cdp):
    if not ENREG["actif"]:
        return

    def note(p):
        if p.get("name") != "jarvisNote":
            return
        try:
            d = json.loads(p["payload"])
        except ValueError:
            return
        if d.get("id") in ENREG["ids"]:
            return   # renvoyée au chargement de la page suivante : déjà reçue
        ENREG["ids"].add(d.get("id"))
        e = ENREG["etapes"]
        if e and d["action"] == "saisie" and e[-1].get("action") == "saisie" and e[-1].get("libelle") == d.get("libelle"):
            e[-1] = d   # même champ modifié plusieurs fois : on garde la dernière valeur
        else:
            e.append(d)
    c.ecouter("Runtime.bindingCalled", note)
    c.envoyer("Runtime.addBinding", {"name": "jarvisNote"})
    js = _JS_ENREG.replace("__JETON__", ENREG["jeton"])
    c.envoyer("Page.addScriptToEvaluateOnNewDocument", {"source": js})
    c.envoyer("Runtime.evaluate", {"expression": js})


def demarrer_enregistrement(site: str):
    import uuid
    ENREG.update(actif=True, etapes=[], site=site, ids=set(), jeton=uuid.uuid4().hex[:12])
    try:
        _js("sessionStorage.removeItem('__jarvisFile')")
    except Exception:
        pass
    _etat["cdp"] = None   # reconnexion : branche l'écoute des clics
    _onglet()
    afficher()


def arreter_enregistrement() -> list:
    try:   # le champ en cours de saisie compte aussi
        _js("window.__jarvisFinSaisie && window.__jarvisFinSaisie()")
        time.sleep(0.6)
    except Exception:
        pass
    ENREG["actif"] = False
    etapes = ENREG["etapes"]
    _etat["cdp"] = None
    return etapes


def etat() -> dict:
    return {"executable": executable(), "ouvert": _repond(), "installation": INSTALL,
            "enregistrement": {"actif": ENREG["actif"], "site": ENREG["site"], "etapes": len(ENREG["etapes"])}}
