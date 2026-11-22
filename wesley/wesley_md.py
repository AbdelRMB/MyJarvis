"""Fichiers WESLEY.md : les instructions propres à chaque projet, sur le modèle des CLAUDE.md de Claude Code.

Un WESLEY.md à la racine d'un projet (et, si besoin, dans un sous-dossier) contient ce que Wesley doit savoir pour
y travailler : présentation, commandes utiles, conventions, décisions, journal des changements.

- Avant de travailler sur un projet, Wesley le lit EN PREMIER et le suit avant le reste (mémoire, autres fichiers,
  règles par défaut) ; seules la demande de l'utilisateur et ses consignes personnelles passent avant.
- Les tâches de code (Claude Code, Codex, Wesley) le reçoivent dans leur consigne.
- Chaque fois que Wesley code dans un projet, il le tient à jour (et le crée s'il n'existe pas).

Module sans dépendance au reste de Wesley : facile à tester.
"""
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

NOM = "WESLEY.md"
MAX_CARACTERES = 24000          # au-delà, le contenu transmis est tronqué (le fichier, lui, reste entier)
IGNORES = {".git", "node_modules", ".venv", ".venv-mac", "venv", "env", "__pycache__", "dist", "build", ".next",
           ".nuxt", "target", ".idea", ".vscode", ".cache", "vendor", "Pods", ".gradle", ".dart_tool", "coverage"}
MARQUEURS = (".git", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "composer.json",
             "project.godot", "pom.xml", "build.gradle", "Gemfile", "pubspec.yaml", "Makefile")
RUBRIQUES = {   # rubrique de noter() -> titre de section du WESLEY.md
    "changement": "Journal des changements",
    "decision": "Décisions",
    "commande": "Commandes utiles",
    "convention": "Conventions",
}
_lus: set = set()   # projets dont Wesley a lu le WESLEY.md pendant cette session (pour ne pas le rappeler sans cesse)


def _chemin(chemin) -> Path:
    return Path(str(chemin)).expanduser().resolve()


def racine_projet(chemin) -> Path:
    """Racine du projet qui contient `chemin` : le dépôt git le plus proche, sinon le dossier le plus proche qui a
    déjà un WESLEY.md ou un marqueur de projet (package.json, pyproject.toml…), sinon le dossier lui-même."""
    p = _chemin(chemin)
    depart = p if p.is_dir() else p.parent
    maison = Path.home().resolve()
    candidats = [depart, *depart.parents]
    for d in candidats:
        if d == maison or d == Path(d.anchor):
            break
        if (d / ".git").exists():
            return d
    for d in candidats:
        if d == maison or d == Path(d.anchor):
            break
        if (d / NOM).is_file() or any((d / m).exists() for m in MARQUEURS):
            return d
    return depart


def est_dans_un_projet(chemin) -> bool:
    """Vrai si `chemin` est dans un dépôt git ou un dossier de projet reconnu (pas un fichier isolé)."""
    p = _chemin(chemin)
    r = racine_projet(p)
    return (r / ".git").exists() or (r / NOM).is_file() or any((r / m).exists() for m in MARQUEURS)


def fichiers(chemin, cible=None) -> list[Path]:
    """WESLEY.md qui s'appliquent à `cible` (par défaut `chemin`), du plus général au plus précis : celui de la
    racine du projet, puis ceux des sous-dossiers traversés jusqu'à la cible."""
    racine = racine_projet(chemin)
    c = _chemin(cible if cible is not None else chemin)
    c = c if c.is_dir() else c.parent
    dossiers = [racine]
    try:
        rel = c.relative_to(racine)
        d = racine
        for partie in rel.parts:
            d = d / partie
            dossiers.append(d)
    except ValueError:
        pass
    return [d / NOM for d in dossiers if (d / NOM).is_file()]


def autres(chemin, profondeur: int = 4, maximum: int = 30) -> list[Path]:
    """WESLEY.md des sous-dossiers du projet (hors racine) : à lire avant de toucher à ces dossiers."""
    racine = racine_projet(chemin)
    trouves = []

    def parcourir(d: Path, niveau: int):
        if niveau > profondeur or len(trouves) >= maximum:
            return
        try:
            enfants = sorted(x for x in d.iterdir() if x.is_dir() and x.name not in IGNORES and not x.name.startswith("."))
        except OSError:
            return
        for x in enfants:
            if (x / NOM).is_file():
                trouves.append(x / NOM)
            parcourir(x, niveau + 1)

    parcourir(racine, 1)
    return trouves[:maximum]


def _relatif(f: Path, racine: Path) -> str:
    try:
        return f.relative_to(racine).as_posix()
    except ValueError:
        return str(f)


def lire(chemin, cible=None, maximum: int = MAX_CARACTERES) -> str:
    """Contenu des WESLEY.md qui s'appliquent (racine puis sous-dossiers), avec leur chemin. Vide s'il n'y en a pas."""
    racine = racine_projet(chemin)
    morceaux, reste = [], maximum
    for f in fichiers(chemin, cible):
        try:
            texte = f.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if len(texte) > reste:
            texte = texte[:max(reste, 0)] + "\n[… tronqué : lis le fichier entier si besoin]"
        reste -= len(texte)
        morceaux.append(f"--- {_relatif(f, racine)} ---\n{texte}")
    if morceaux:
        _lus.add(str(racine))
    return "\n\n".join(morceaux)


def bloc_consigne(chemin, cible=None) -> str:
    """Bloc à placer en tête de la consigne d'une tâche de code : instructions du projet, à suivre en priorité."""
    racine = racine_projet(chemin)
    contenu = lire(chemin, cible)
    sous = [x for x in autres(chemin) if x not in fichiers(chemin, cible)]
    lignes = []
    if contenu:
        lignes += ["# INSTRUCTIONS DU PROJET (WESLEY.md) — À SUIVRE EN PRIORITÉ",
                   "Lis-les avant tout le reste du projet. Elles passent avant tes habitudes, les autres fichiers du "
                   "projet et les règles par défaut ; seule la demande de l'utilisateur ci-dessous peut les contredire "
                   "explicitement.", "", contenu]
    if sous:
        lignes += ["", "Autres WESLEY.md dans des sous-dossiers (lis celui du dossier avant d'y travailler) : "
                   + ", ".join(_relatif(x, racine) for x in sous)]
    return "\n".join(lignes).strip()


def obligation(chemin) -> str:
    """Rappel à donner à l'agent de code : tenir le WESLEY.md à jour avant le commit final."""
    existe = (racine_projet(chemin) / NOM).is_file()
    debut = ("Tiens à jour le fichier WESLEY.md à la racine du projet" if existe else
             "Ce projet n'a pas encore de WESLEY.md : crée-le à la racine du projet (présentation courte, commandes "
             "utiles, conventions, décisions, journal des changements), puis tiens-le à jour")
    return (f"OBLIGATOIRE : {debut}. Avant le commit final, consignes-y les changements faits (dans « Journal des "
            "changements », avec la date du jour), les décisions prises, les commandes utiles et les conventions "
            "découvertes. Reste concis (pas de copie du code), garde les sections existantes, et ne mets jamais de "
            "secret (mot de passe, clé, jeton) dedans. Committe-le avec le reste.")


# ---------- création / mise à jour ----------
def _lire_json(f: Path) -> dict:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _commandes(racine: Path) -> list[str]:
    """Commandes utiles devinées d'après les fichiers du projet."""
    out = []
    pkg = _lire_json(racine / "package.json")
    if pkg:
        gestionnaire = ("pnpm" if (racine / "pnpm-lock.yaml").exists() else "yarn" if (racine / "yarn.lock").exists()
                        else "bun" if (racine / "bun.lockb").exists() else "npm")
        out.append(f"`{gestionnaire} install` : installer les dépendances")
        for nom in list((pkg.get("scripts") or {}))[:12]:
            out.append(f"`{gestionnaire} run {nom}`")
    if (racine / "pyproject.toml").exists() or (racine / "requirements.txt").exists():
        if (racine / "requirements.txt").exists():
            out.append("`python -m pip install -r requirements.txt` : installer les dépendances")
        if (racine / "tests").is_dir() or (racine / "pytest.ini").exists():
            out.append("`python -m pytest` : lancer les tests")
    if (racine / "Cargo.toml").exists():
        out += ["`cargo build`", "`cargo test`"]
    if (racine / "go.mod").exists():
        out += ["`go build ./...`", "`go test ./...`"]
    if (racine / "composer.json").exists():
        out.append("`composer install`")
    if (racine / "Makefile").exists():
        try:
            cibles = re.findall(r"^([A-Za-z0-9_.-]+):(?!=)", (racine / "Makefile").read_text(encoding="utf-8", errors="replace"), re.M)
            out += [f"`make {c}`" for c in dict.fromkeys(cibles) if not c.startswith(".")][:8]
        except OSError:
            pass
    return out


def _technos(racine: Path) -> list[str]:
    t = []
    pkg = _lire_json(racine / "package.json")
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    for cle, nom in (("next", "Next.js"), ("react", "React"), ("vue", "Vue"), ("svelte", "Svelte"), ("vite", "Vite"),
                     ("typescript", "TypeScript"), ("tailwindcss", "Tailwind CSS"), ("express", "Express")):
        if cle in deps:
            t.append(nom)
    if pkg and not t:
        t.append("Node.js")
    for fichier, nom in (("pyproject.toml", "Python"), ("requirements.txt", "Python"), ("Cargo.toml", "Rust"),
                         ("go.mod", "Go"), ("composer.json", "PHP"), ("project.godot", "Godot"), ("pom.xml", "Java"),
                         ("build.gradle", "Java/Kotlin"), ("Gemfile", "Ruby"), ("pubspec.yaml", "Flutter/Dart")):
        if (racine / fichier).exists() and nom not in t:
            t.append(nom)
    return t


def _resume_readme(racine: Path) -> str:
    for nom in ("README.md", "README.fr.md", "README.txt", "README"):
        f = racine / nom
        if f.is_file():
            try:
                lignes = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            paragraphe = []
            for l in lignes:
                s = l.strip()
                if not s or s.startswith(("#", "!", "[!", "<", "```", "|", "---")):
                    if paragraphe:
                        break
                    continue
                paragraphe.append(s)
            return " ".join(paragraphe)[:400]
    return ""


def modele(chemin) -> str:
    """WESLEY.md de départ, rempli avec ce qu'on peut deviner du projet."""
    racine = racine_projet(chemin)
    technos = _technos(racine)
    resume = _resume_readme(racine)
    commandes = _commandes(racine)
    voir = [n for n in ("CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "README.md") if (racine / n).is_file()]
    l = [f"# {racine.name} — instructions pour Wesley", "",
         "> À lire en premier avant de travailler sur ce projet, et à suivre avant tout le reste.",
         "> Wesley (et les agents de code qu'il pilote) le tiennent à jour à chaque modification du projet.", "",
         "## Présentation", resume or "(à compléter : à quoi sert ce projet, pour qui)"]
    if technos:
        l.append(f"Technologies : {', '.join(technos)}.")
    if voir:
        l.append("Voir aussi : " + ", ".join(voir) + ".")
    l += ["", "## Commandes utiles", *([f"- {c}" for c in commandes] or ["- (à compléter)"]),
          "", "## Conventions", "- (à compléter : style, langue des commits, organisation des dossiers…)",
          "", "## Décisions", "", "## Journal des changements",
          f"- {date.today():%Y-%m-%d} : création de ce WESLEY.md.", ""]
    return "\n".join(l)


def creer(chemin, contenu: str = "", remplacer: bool = False) -> tuple[Path, bool]:
    """Crée le WESLEY.md à la racine du projet (modèle si `contenu` est vide). Renvoie (chemin, créé ?)."""
    f = racine_projet(chemin) / NOM
    if f.exists() and not remplacer:
        return f, False
    texte = contenu.strip() + "\n" if contenu.strip() else modele(chemin)
    f.write_text(texte, encoding="utf-8")
    _lus.add(str(f.parent))
    return f, True


def ajouter_ligne(texte: str, section: str, ligne: str) -> str:
    """Ajoute `ligne` à la fin de la section `## section` (créée à la fin du document si absente)."""
    lignes = texte.rstrip("\n").split("\n") if texte.strip() else []
    titre = re.compile(r"^##\s+" + re.escape(section) + r"\s*$", re.I)
    debut = next((i for i, l in enumerate(lignes) if titre.match(l.strip())), None)
    if debut is None:
        return "\n".join([*lignes, "", f"## {section}", ligne]).lstrip("\n") + "\n"
    fin = next((i for i in range(debut + 1, len(lignes)) if re.match(r"^#{1,2}\s", lignes[i])), len(lignes))
    while fin > debut + 1 and not lignes[fin - 1].strip():   # avant les lignes vides qui séparent les sections
        fin -= 1
    lignes.insert(fin, ligne)
    return "\n".join(lignes) + "\n"


def noter(chemin, note: str, rubrique: str = "changement") -> Path:
    """Consigne une note datée dans le WESLEY.md du projet (le crée d'abord s'il n'existe pas)."""
    f, _ = creer(chemin)
    cle = unicodedata.normalize("NFKD", rubrique.strip().lower()).encode("ascii", "ignore").decode().rstrip("s")
    section = RUBRIQUES.get(cle, RUBRIQUES["changement"])
    note = " ".join(note.split())
    ligne = f"- {date.today():%Y-%m-%d} : {note}" if section == RUBRIQUES["changement"] else f"- {note}"
    f.write_text(ajouter_ligne(f.read_text(encoding="utf-8", errors="replace"), section, ligne), encoding="utf-8")
    return f


def rappel_apres_ecriture(chemin_fichier) -> str:
    """Après qu'un outil de Wesley a écrit dans un projet : rappel (une fois par projet et par session) de lire le
    WESLEY.md s'il ne l'a pas fait, et de le tenir à jour. Vide si ce n'est pas un projet ou déjà rappelé."""
    p = _chemin(chemin_fichier)
    if p.name == NOM or not est_dans_un_projet(p):
        return ""
    racine = racine_projet(p)
    cle = "rappel:" + str(racine)
    if cle in _lus:
        return ""
    _lus.add(cle)
    if (racine / NOM).is_file() and str(racine) not in _lus:
        return (f"\n(Projet {racine.name} : il a un WESLEY.md que tu n'as pas encore lu. Lis-le avec lire_wesley_md et "
                "suis-le, puis consigne tes changements avec noter_wesley_md.)")
    return (f"\n(Projet {racine.name} : consigne ce changement dans son WESLEY.md avec noter_wesley_md"
            + ("" if (racine / NOM).is_file() else ", qui le créera") + ".)")
