"""Mémoire long terme : faits sur l'utilisateur + scan du PC + historique des conversations."""
import json
import re
import os
import platform
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from .config import MACHINE, PARTAGE, RACINE

DOSSIER = PARTAGE / "memoire"              # cache local du compte (synchronisé par compte.py)
FAITS = DOSSIER / "faits.json"
HIST = DOSSIER / "historique"              # un fichier par jour ET par PC : jamais deux PC sur le même fichier
SYSTEME = RACINE / "memoire" / "systeme.md"  # le scan reste propre à chaque PC
HIST.mkdir(parents=True, exist_ok=True)
SYSTEME.parent.mkdir(parents=True, exist_ok=True)


def _charger():
    try:
        return json.loads(FAITS.read_text(encoding="utf-8")) if FAITS.exists() else []
    except json.JSONDecodeError:   # fichier en cours de synchronisation : on réessaie une fois
        import time
        time.sleep(0.5)
        return json.loads(FAITS.read_text(encoding="utf-8")) if FAITS.exists() else []


def _sauver(f):
    # écriture atomique : OneDrive ne voit jamais un fichier à moitié écrit
    tmp = FAITS.with_suffix(".tmp")
    tmp.write_text(json.dumps(f, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, FAITS)


# Chaque souvenir : {"fait", "categorie", "date", "fid" (identifiant stable), "modifie" (date de la dernière action)}.
# Toute action (ajout, modification, réutilisation, suppression) part au serveur avec sa date : sur tous les
# appareils, c'est la dernière action qui gagne (voir serveur/app.py).
def _maintenant():
    import time
    return time.time()


def _envoyer(f: dict, action: str):
    from . import compte
    compte.fait_ajoute({**f, "action": action})


def _verrou():
    """Même verrou que la synchro : une modification locale et une mise à jour venue du serveur ne se croisent pas."""
    from .compte import _verrou as v
    return v


def ajouter(fait, categorie="general"):
    with _verrou():
        return _ajouter(fait, categorie)


def _ajouter(fait, categorie):
    f = _charger()
    existant = next((x for x in f if x["fait"].lower() == fait.lower()), None)
    if existant:   # le redire, c'est s'en servir : compte comme une utilisation (le garde s'il a été supprimé ailleurs)
        existant["modifie"] = _maintenant()
        _sauver(f)
        _envoyer(existant, "utilisation")
        return "Déjà en mémoire."
    import uuid
    nouveau = {"fait": fait, "categorie": categorie, "date": datetime.now().strftime("%Y-%m-%d"),
               "fid": uuid.uuid4().hex[:16], "modifie": _maintenant()}
    f.append(nouveau)
    _sauver(f)
    _envoyer(nouveau, "ajout")
    return f"Mémorisé : {fait}"


def modifier(fid, fait, categorie=None):
    with _verrou():
        return _modifier(fid, fait, categorie)


def _modifier(fid, fait, categorie):
    f = _charger()
    x = next((x for x in f if x.get("fid") == fid), None)
    if not x:
        return False
    x.update(fait=fait.strip(), categorie=categorie or x["categorie"], modifie=_maintenant())
    _sauver(f)
    _envoyer(x, "modification")
    return True


def _supprimer_ou(condition) -> int:
    with _verrou():
        return _supprimer_ou_(condition)


def _supprimer_ou_(condition) -> int:
    f = _charger()
    retires = [x for x in f if condition(x)]
    _sauver([x for x in f if not condition(x)])
    from . import compte
    for x in retires:
        compte.fait_supprime(x.get("fid", ""), x["fait"], _maintenant())
    return len(retires)


def supprimer(texte):
    """Outil « oublier » de Wesley : tous les souvenirs qui contiennent ce texte."""
    return f"{_supprimer_ou(lambda x: texte.lower() in x['fait'].lower())} fait(s) oublié(s)."


def supprimer_un(fid="", fait=""):
    """Bouton « Oublier » de l'écran Mémoire : ce souvenir-là, et lui seul."""
    return _supprimer_ou(lambda x: (fid and x.get("fid") == fid) or (not fid and x["fait"] == fait))


def restaurer(fid, fait, categorie):
    with _verrou():
        _restaurer(fid, fait, categorie)


def _restaurer(fid, fait, categorie):
    f = _charger()
    if not any(x.get("fid") == fid for x in f):
        x = {"fait": fait, "categorie": categorie, "date": datetime.now().strftime("%Y-%m-%d"), "fid": fid,
             "modifie": _maintenant()}
        f.append(x)
        _sauver(f)
        _envoyer(x, "restauration")


_utilises: dict = {}   # fid -> dernière utilisation signalée (au plus une fois par heure et par souvenir)


def _signaler_utilisation(faits):
    """Wesley vient de se servir de ces souvenirs : s'ils ont été supprimés ailleurs juste avant, ils restent."""
    t = _maintenant()
    for x in faits:
        fid = x.get("fid")
        if fid and t - _utilises.get(fid, 0) > 3600:
            _utilises[fid] = t
            _envoyer({**x, "modifie": t}, "utilisation")


def chercher(req):
    mots = [m for m in req.lower().split() if len(m) > 2]
    trouves = [x for x in _charger() if any(m in x["fait"].lower() for m in mots)]
    _signaler_utilisation(trouves)
    res = [f"[mémoire] {x['fait']}" for x in trouves]
    for fic in sorted(HIST.glob("*.md"), reverse=True)[:60]:
        for l in fic.read_text(encoding="utf-8").splitlines():
            if any(m in l.lower() for m in mots):
                res.append(f"[{fic.stem}] {l[:250]}")
                if len(res) > 40:
                    return "\n".join(res)
    return "\n".join(res) or "Rien trouvé."


# préférences qui sont en fait des consignes pour Wesley (enregistrées avant la catégorie « consigne »)
_RX_CONSIGNE = re.compile(r"\b(r[ée]pon[ds]|r[ée]ponse|r[ée]pondre|parle|parler|dis-moi|phrase|d[ée]tail|tutoi|vouvoi|appelle[- ]moi|"
                          r"ton |style|r[ée]sum|court|bref|concis|longue|confirm|demande[- ]moi|pr[ée]viens|jamais|toujours|"
                          r"[ée]vite|n'utilise|utilise|langue|anglais|emoji|blague)", re.I)


def consignes() -> list[str]:
    """Ce que l'utilisateur a demandé à Wesley sur sa façon de se comporter : passe avant ses règles par défaut."""
    return [x["fait"] for x in _charger() if x.get("categorie") == "consigne"
            or (x.get("categorie") == "preference" and _RX_CONSIGNE.search(x["fait"]))]


def rappel_consignes() -> str:
    c = consignes()
    if not c:
        return ""
    from .config import CONFIG
    return (f"Consignes de {CONFIG.get('nom_utilisateur') or 'l’utilisateur'} pour cette réponse (elles passent avant tes "
            "règles par défaut ; respecte-les à la lettre) :\n" + "\n".join(f"- {x}" for x in c))


def profil_texte():
    par_cat = {}
    for x in _charger():
        if x.get("categorie") == "consigne":
            continue   # affichées à part, en tête des instructions
        par_cat.setdefault(x["categorie"], []).append(x["fait"])
    txt = "\n".join(f"## {c}\n" + "\n".join(f"- {f}" for f in fs) for c, fs in par_cat.items())
    sysm = SYSTEME.read_text(encoding="utf-8") if SYSTEME.exists() else ""
    sysm = sysm.split("## Applications installées")[0].rstrip()
    return txt, sysm


def journaliser(role, texte):
    ligne = f"[{datetime.now():%H:%M}] {role}: {texte.strip()}"
    with open(HIST / f"{datetime.now():%Y-%m-%d}__{MACHINE}.md", "a", encoding="utf-8") as f:
        f.write(ligne + "\n")
    from . import compte
    compte.ligne_ajoutee(f"{datetime.now():%Y-%m-%d}", ligne)


def fichiers_par_jour():
    """{jour: [fichiers]} — tous PC confondus."""
    jours = {}
    for f in HIST.glob("*.md"):
        jours.setdefault(f.stem.split("__")[0], []).append(f)
    return jours


def lignes_du_jour(fichiers):
    """Fusionne les conversations du jour de tous les PC, dans l'ordre de l'heure."""
    lignes = []
    for f in fichiers:
        pc = f.stem.split("__")[1] if "__" in f.stem else ""
        for l in f.read_text(encoding="utf-8").splitlines():
            lignes.append((l[1:6] if l.startswith("[") else "", pc, l))
    return sorted(lignes, key=lambda x: x[0])


def resume_recent(n_lignes=30):
    jours = fichiers_par_jour()
    lignes = []
    for jour in sorted(jours)[-2:]:
        lignes += [f"({jour}{', ' + pc if pc else ''}) {l[:200]}" for _, pc, l in lignes_du_jour(jours[jour])]
    return "\n".join(lignes[-n_lignes:])


# ---------- Scan du PC ----------

def _vscode_recents():
    from urllib.parse import unquote
    from .plateforme import vscode_stockage
    base = vscode_stockage()
    uris = []
    try:
        d = json.loads((base / "storage.json").read_text(encoding="utf-8"))
        uris += list(d.get("profileAssociations", {}).get("workspaces", {}))
    except Exception:
        pass
    try:
        c = sqlite3.connect(f"file:{base / 'state.vscdb'}?mode=ro", uri=True)
        v = c.execute("SELECT value FROM ItemTable WHERE key='history.recentlyOpenedPathsList'").fetchone()
        c.close()
        if v:
            uris += [e.get("folderUri") or e.get("fileUri") or "" for e in json.loads(v[0])["entries"]]
    except Exception:
        pass
    out = []
    for u in uris:
        if u.startswith("file:///"):
            p = unquote(u[8:]).replace("/", "\\")
            p = p[0].upper() + p[1:]
            if p not in out:
                out.append(p)
    return out[-40:]


def _projets():
    out = []
    for base in [Path.home() / "Desktop", Path.home() / "Documents", Path.home() / "Documents/Perso",
                 Path.home() / "Documents/Godot", Path.home() / "source/repos"]:
        if not base.exists():
            continue
        for d in base.iterdir():
            if d.is_dir() and any((d / m).exists() for m in (".git", "package.json", "pyproject.toml",
                                                               "requirements.txt", "project.godot", "composer.json")):
                out.append(str(d))
    return sorted(set(out))


def scanner_systeme():
    import psutil
    from .outils.systeme import _raccourcis
    def cmd(c):
        try:
            return subprocess.run(c, capture_output=True, text=True, timeout=10, shell=True, **CACHE_FENETRE).stdout.strip()
        except Exception:
            return ""
    from .plateforme import CACHE_FENETRE, MAC, NOM_OS
    import getpass
    gpu = cmd("sysctl -n machdep.cpu.brand_string") if MAC else cmd("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
    apps = sorted({p.stem for p in _raccourcis() if "uninstall" not in p.stem.lower() and "désinstall" not in p.stem.lower()})
    l = [
        f"# {'Mac' if MAC else 'PC'} de l'utilisateur (scanné le {datetime.now():%d/%m/%Y %H:%M})",
        f"- {NOM_OS} : {platform.mac_ver()[0] if MAC else platform.platform()} | Machine : {platform.node()} | Compte : {getpass.getuser()}",
        f"- Dossier perso : {Path.home()}",
        f"- {'Puce' if MAC else 'CPU'} : {gpu if MAC else platform.processor()} ({psutil.cpu_count()} threads) | RAM : "
        f"{psutil.virtual_memory().total/1e9:.0f} Go" + ("" if MAC else f" | GPU : {gpu}"),
        f"- Git : {cmd('git config --global user.name')} | Node : {cmd('node --version')} | Python : "
        f"{cmd('python3 --version') if MAC else cmd('py --version')}",
        "## Projets détectés", *[f"- {p}" for p in _projets()],
        "## Récents dans VS Code", *[f"- {p}" for p in _vscode_recents()],
        "## Applications installées", ", ".join(apps[:250]),
    ]
    SYSTEME.write_text("\n".join(l), encoding="utf-8")
    return SYSTEME
