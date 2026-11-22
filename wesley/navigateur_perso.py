"""Ton navigateur (Safari, Chrome, Edge, Brave, Arc — Mac) : Wesley travaille dans l'onglet que tu as ouvert, là où tu
es déjà connecté, et tu vois ce qu'il fait (l'élément visé est entouré avant chaque clic ou saisie).

Pilotage par AppleScript : il exécute du JavaScript dans l'onglet actif. Il faut l'autoriser une fois dans le
navigateur :
- Safari : Réglages › Avancées › « Afficher les fonctionnalités pour les développeurs web », puis menu
  Développement › « Autoriser JavaScript depuis les Apple Events » ;
- Chrome / Edge / Brave / Arc : menu Affichage › Options pour les développeurs › « Autoriser JavaScript à partir
  des événements Apple ».
macOS demande aussi, la première fois, d'autoriser Wesley à contrôler le navigateur.
Sur Windows, ce pilotage n'existe pas : Wesley passe par l'écran (regarder_ecran, trouver_et_cliquer).
"""
import json
import subprocess
import sys
import time

MAC = sys.platform == "darwin"
NAVIGATEURS = ["Safari", "Google Chrome", "Arc", "Microsoft Edge", "Brave Browser"]
AIDE = {
    "Safari": "Dans Safari : Réglages › Avancées › coche « Afficher les fonctionnalités pour les développeurs web », "
              "puis menu Développement › « Autoriser JavaScript depuis les Apple Events ».",
    "autre": "Dans {nav} : menu Affichage › Options pour les développeurs › « Autoriser JavaScript à partir des événements Apple ».",
}


def _osa(script: str, delai=30) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=delai)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "AppleScript a échoué")
    return r.stdout.strip()


def _ouverts() -> list:
    sortie = _osa('tell application "System Events" to get name of every process whose background only is false')
    return [n for n in NAVIGATEURS if n in [x.strip() for x in sortie.split(",")]]


def navigateur_actif() -> str:
    """Le navigateur au premier plan, sinon le premier navigateur ouvert."""
    if not MAC:
        raise RuntimeError("Le pilotage de ton navigateur n'existe que sur Mac : sur Windows, utilise regarder_ecran "
                           "et trouver_et_cliquer pour agir à l'écran.")
    devant = _osa('tell application "System Events" to get name of first process whose frontmost is true')
    if devant in NAVIGATEURS:
        return devant
    ouverts = _ouverts()
    if not ouverts:
        raise RuntimeError("Aucun navigateur ouvert (Safari, Chrome, Edge, Brave ou Arc).")
    return ouverts[0]


def _echapper(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def js(code: str):
    """Exécute du JavaScript dans l'onglet actif du navigateur de l'utilisateur et renvoie le résultat (JSON)."""
    nav = navigateur_actif()
    enveloppe = f"JSON.stringify((() => {{ try {{ return {{ok: true, v: ({code})}}; }} catch (e) {{ return {{ok: false, v: String(e)}}; }} }})())"
    if nav == "Safari":
        script = f'tell application "Safari" to do JavaScript "{_echapper(enveloppe)}" in current tab of front window'
    else:
        script = f'tell application "{nav}" to execute active tab of front window javascript "{_echapper(enveloppe)}"'
    try:
        sortie = _osa(script)
    except RuntimeError as e:
        m = str(e)
        if "JavaScript" in m or "Apple Events" in m or "Apple events" in m or "-1743" in m or "not allowed" in m.lower():
            raise RuntimeError(f"{nav} ne permet pas encore à Wesley d'agir dans la page. "
                               + (AIDE["Safari"] if nav == "Safari" else AIDE["autre"].format(nav=nav))) from None
        raise
    if not sortie or sortie == "missing value":
        return None
    r = json.loads(sortie)
    if not r.get("ok"):
        raise RuntimeError(r.get("v", "erreur JavaScript")[:300])
    return r.get("v")


def _attendre(delai=12):
    fin = time.time() + delai
    time.sleep(0.6)
    while time.time() < fin:
        try:
            if js("document.readyState") == "complete":
                time.sleep(0.5)
                return
        except Exception:
            pass
        time.sleep(0.4)


# ---------- actions (mêmes réponses que le navigateur de Wesley) ----------
def instantane() -> dict:
    from .navigateur import _JS_INSTANTANE
    v = js(_JS_INSTANTANE.strip().rstrip(";"))
    v["navigateur"] = navigateur_actif()
    return v


def ouvrir(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    nav = navigateur_actif()
    u = _echapper(url)
    _osa(f'tell application "Safari" to set URL of current tab of front window to "{u}"' if nav == "Safari"
         else f'tell application "{nav}" to set URL of active tab of front window to "{u}"')
    _attendre()
    return instantane()


# entoure l'élément visé (halo bleu ~1 s) : l'utilisateur voit ce que Wesley va faire
_SURLIGNER = """(e => { e.scrollIntoView({block: 'center', behavior: 'smooth'}); const r = e.getBoundingClientRect();
  const h = document.createElement('div'); h.setAttribute('data-wesley-halo', '');
  Object.assign(h.style, {position: 'fixed', left: (r.left - 4) + 'px', top: (r.top - 4) + 'px', width: (r.width + 8) + 'px',
    height: (r.height + 8) + 'px', border: '3px solid #3ce8ff', borderRadius: '6px', boxShadow: '0 0 14px #3ce8ff',
    zIndex: 2147483647, pointerEvents: 'none', transition: 'opacity .4s'});
  document.body.appendChild(h); setTimeout(() => { h.style.opacity = 0; setTimeout(() => h.remove(), 450); }, 900); return true; })"""


def _ref(cible: str) -> str:
    cible = str(cible).strip().strip("[]")
    if cible.isdigit():
        return cible
    cle = cible.lower().strip("«» \"'")
    elements = instantane().get("elements", [])
    exacts = [x for x in elements if x["libelle"].lower() == cle]
    if len(exacts) > 1 and len({x.get("href") or x["ref"] for x in exacts}) > 1:
        raise RuntimeError(f"Plusieurs éléments « {cible} » : " + ", ".join(f"[{x['ref']}] {x['type']}" for x in exacts[:8])
                           + ". Précise le numéro.")
    e = exacts[0] if exacts else next((x for x in elements if cle in x["libelle"].lower()), None)
    if not e:
        raise RuntimeError(f"Élément « {cible} » introuvable : regarde la page avec navigateur_voir.")
    return str(e["ref"])


def _sel(ref: str) -> str:
    return f"document.querySelector('[data-wesley-ref=\"{ref}\"]')"


def libelle(cible: str) -> str:
    ref = _ref(cible)
    return js(f"(() => {{ const e = {_sel(ref)}; return e ? (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 80) : ''; }})()") or ""


def cliquer(cible: str) -> dict:
    ref = _ref(cible)
    ok = js(f"(() => {{ const e = {_sel(ref)}; if (!e) return false; ({_SURLIGNER})(e); return true; }})()")
    if not ok:
        raise RuntimeError("L'élément a disparu : regarde de nouveau la page.")
    time.sleep(0.9)   # le temps de voir le halo
    js(f"""(() => {{ const e = {_sel(ref)}; const o = {{bubbles: true, cancelable: true, view: window}};
        for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup']) e.dispatchEvent(new (t.startsWith('pointer') ? PointerEvent : MouseEvent)(t, o));
        e.click(); return true; }})()""")
    _attendre(8)
    return instantane()


def remplir(cible: str, valeur: str) -> dict:
    ref = _ref(cible)
    js(f"(() => {{ const e = {_sel(ref)}; if (e) ({_SURLIGNER})(e); return true; }})()")
    time.sleep(0.6)
    ok = js(f"""(() => {{ const e = {_sel(ref)}; if (!e) return false; e.focus(); const v = {json.dumps(valeur)};
        if (e.tagName === 'SELECT') {{
            const o = [...e.options].find(o => o.text.toLowerCase().includes(v.toLowerCase()) || o.value === v);
            if (!o) throw new Error('option introuvable'); e.value = o.value;
        }} else if (e.isContentEditable) {{ e.textContent = v; }}
        else {{ // valeur posée comme une vraie saisie : les formulaires React / Vue / Angular la voient
            const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, v); }}
        e.dispatchEvent(new Event('input', {{bubbles: true}})); e.dispatchEvent(new Event('change', {{bubbles: true}}));
        return true; }})()""")
    if not ok:
        raise RuntimeError("Champ introuvable : regarde de nouveau la page.")
    return instantane()


def touche(nom: str) -> dict:
    nom = nom.lower().strip()
    if nom in ("entree", "entrée", "enter"):
        avant = js("location.href")
        js("""(() => { const e = document.activeElement || document.body; const o = {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true};
            e.dispatchEvent(new KeyboardEvent('keydown', o)); e.dispatchEvent(new KeyboardEvent('keypress', o)); e.dispatchEvent(new KeyboardEvent('keyup', o));
            return true; })()""")
        _attendre(4)
        if js("location.href") == avant:   # formulaire classique : on l'envoie
            js("(() => { const f = document.activeElement && document.activeElement.form; if (f) { f.requestSubmit ? f.requestSubmit() : f.submit(); } return true; })()")
            _attendre(8)
    else:
        cle = {"tab": "Tab", "echap": "Escape", "échap": "Escape", "bas": "ArrowDown", "haut": "ArrowUp"}.get(nom, nom)
        js(f"(() => {{ const e = document.activeElement || document.body; e.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(cle)}, bubbles: true}})); return true; }})()")
    return instantane()


def capture() -> bytes:
    """Capture de la fenêtre du navigateur (telle que tu la vois)."""
    import tempfile
    from pathlib import Path
    nav = navigateur_actif()
    numero = None
    try:
        import Quartz
        fenetres = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
        for f in fenetres:
            if f.get("kCGWindowOwnerName") == nav and f.get("kCGWindowLayer") == 0 and f.get("kCGWindowBounds", {}).get("Height", 0) > 200:
                numero = f["kCGWindowNumber"]
                break
    except Exception:
        pass
    fichier = Path(tempfile.mkstemp(suffix=".png")[1])
    subprocess.run(["screencapture", "-x", "-o"] + ([f"-l{numero}"] if numero else []) + [str(fichier)], check=True, timeout=20)
    donnees = fichier.read_bytes()
    fichier.unlink(missing_ok=True)
    return donnees


def etat() -> dict:
    if not MAC:
        return {"disponible": False, "raison": "Seulement sur Mac (sur Windows, Wesley agit à l'écran)."}
    try:
        ouverts = _ouverts()
    except Exception as e:
        return {"disponible": False, "raison": str(e)}
    return {"disponible": True, "ouverts": ouverts, "aide": {n: AIDE["Safari"] if n == "Safari" else AIDE["autre"].format(nav=n) for n in NAVIGATEURS}}
