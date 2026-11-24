"""Wesley lit tes documents : « qu'est-ce que dit mon bail sur le préavis ? », « combien coûtait le devis du
plombier ? », « retrouve le passage sur les congés dans le règlement ».

- Tu choisis des dossiers (Réglages › Documents, ou « Wesley, lis mes documents dans ~/Documents/Admin »).
- Les PDF, Word (.docx), OpenOffice (.odt), textes (.txt, .md, .csv) sont découpés en passages (~1 200 caractères,
  avec la page pour un PDF) et indexés PAR LE SENS, en local (semantique.py) : rien ne sort de ton ordinateur.
- chercher() renvoie les passages les plus utiles avec le fichier et la page : Wesley répond en citant sa source.
- L'index est mis à jour tout seul (fichier ajouté, modifié ou supprimé) : seuls les fichiers changés sont relus.
"""
import json
import os
import re
import threading
import time
import zipfile
from pathlib import Path

from .config import CONFIG, RACINE

EXTENSIONS = {".pdf", ".docx", ".odt", ".txt", ".md", ".csv", ".rtf"}
TAILLE_PASSAGE = 1200
MAX_FICHIER = 50 * 1024 * 1024
MAX_FICHIERS = 5000
INDEX = RACINE / "memoire" / "documents.json"   # {chemin: {"mtime", "taille", "passages": [{"page", "texte"}]}}
_verrou = threading.RLock()
_etat = {"indexation": False, "derniere": 0.0, "erreur": ""}


def dossiers() -> list[str]:
    return [d for d in (CONFIG.get("dossiers_documents") or []) if d]


# ---------- lecture des fichiers ----------
def _texte_xml(xml: str) -> str:
    xml = re.sub(r"</(w:p|text:p|text:h)>", "\n", xml)
    xml = re.sub(r"<(w:tab|text:tab)/>", "\t", xml)
    return re.sub(r"<[^>]+>", "", xml)


def lire(chemin: Path) -> list[tuple[int, str]]:
    """[(page, texte)] : une entrée par page pour un PDF, une seule (page 0) sinon."""
    ext = chemin.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        lecteur = PdfReader(str(chemin))
        if lecteur.is_encrypted:
            try:
                lecteur.decrypt("")
            except Exception:
                return []
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(lecteur.pages)]
    if ext in (".docx", ".odt"):
        with zipfile.ZipFile(chemin) as z:
            xml = z.read("word/document.xml" if ext == ".docx" else "content.xml").decode("utf-8", "ignore")
        import html
        return [(0, html.unescape(_texte_xml(xml)))]
    if ext == ".rtf":
        brut = chemin.read_text(encoding="latin-1", errors="ignore")
        return [(0, re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", brut))]
    return [(0, chemin.read_text(encoding="utf-8", errors="ignore"))]


def decouper(pages: list[tuple[int, str]], taille: int = TAILLE_PASSAGE) -> list[dict]:
    """Passages de ~taille caractères, coupés entre deux paragraphes ou phrases, chacun avec sa page."""
    res = []
    for page, texte in pages:
        texte = re.sub(r"[ \t]+", " ", texte).strip()
        courant = ""
        for bloc in re.split(r"\n\s*\n|(?<=[.!?])\s+(?=[A-ZÀ-Ý])", texte):
            bloc = bloc.strip()
            if not bloc:
                continue
            if courant and len(courant) + len(bloc) > taille:
                res.append({"page": page, "texte": courant})
                courant = ""
            while len(bloc) > taille * 1.5:          # bloc géant sans ponctuation : coupé net
                res.append({"page": page, "texte": bloc[:taille]})
                bloc = bloc[taille:]
            courant = f"{courant}\n{bloc}".strip()
        if courant:
            res.append({"page": page, "texte": courant})
    return res


# ---------- index ----------
def _lire_index() -> dict:
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ecrire_index(ix: dict):
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(ix, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INDEX)


def fichiers(racines: list[str] | None = None) -> list[Path]:
    res = []
    for d in racines if racines is not None else dossiers():
        base = Path(os.path.expanduser(d))
        if not base.is_dir():
            continue
        for racine, sous, noms in os.walk(base):
            sous[:] = [s for s in sous if not s.startswith(".") and s not in ("node_modules", "__pycache__")]
            for n in noms:
                p = Path(racine) / n
                if p.suffix.lower() in EXTENSIONS and not n.startswith((".", "~$")):
                    res.append(p)
                    if len(res) >= MAX_FICHIERS:
                        return res
    return res


def indexer(racines: list[str] | None = None) -> dict:
    """Met l'index à jour : lit les fichiers nouveaux ou modifiés, oublie les supprimés, calcule les vecteurs."""
    from . import semantique
    with _verrou:
        _etat["indexation"] = True
        try:
            ix = _lire_index()
            presents = {}
            for p in fichiers(racines):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_size > MAX_FICHIER:
                    continue
                cle = str(p)
                presents[cle] = True
                deja = ix.get(cle)
                if deja and deja.get("mtime") == st.st_mtime and deja.get("taille") == st.st_size:
                    continue
                try:
                    ix[cle] = {"mtime": st.st_mtime, "taille": st.st_size, "passages": decouper(lire(p))}
                except Exception as e:
                    ix[cle] = {"mtime": st.st_mtime, "taille": st.st_size, "passages": [], "erreur": str(e)[:200]}
            for cle in [c for c in ix if c not in presents]:
                ix.pop(cle)
            _ecrire_index(ix)
            textes = [x["texte"] for d in ix.values() for x in d.get("passages", [])]
            if semantique.disponible() and textes:
                semantique.index("documents").matrice(textes)   # vecteurs calculés une fois, gardés sur disque
            _etat.update(derniere=time.time(), erreur="")
            return {"fichiers": len(ix), "passages": len(textes)}
        except Exception as e:
            _etat["erreur"] = str(e)
            raise
        finally:
            _etat["indexation"] = False


def chercher(question: str, k: int = 6) -> list[dict]:
    """Les passages qui répondent le mieux : {fichier, page, texte, score}."""
    from . import semantique
    ix = _lire_index()
    passages = [(cle, x) for cle, d in ix.items() for x in d.get("passages", [])]
    if not passages:
        return []
    classes = semantique.classer(question, [x["texte"] for _, x in passages], k=k, nom_index="documents", seuil=0.78)
    return [{"fichier": passages[i][0], "page": passages[i][1].get("page") or 0, "texte": passages[i][1]["texte"],
             "score": round(s, 3)} for i, s in classes]


def etat() -> dict:
    ix = _lire_index()
    return {"dossiers": dossiers(), "fichiers": len(ix), "passages": sum(len(d.get("passages", [])) for d in ix.values()),
            "illisibles": [c for c, d in ix.items() if d.get("erreur")][:20], "indexation": _etat["indexation"],
            "derniere": _etat["derniere"], "erreur": _etat["erreur"]}


def ajouter_dossier(chemin: str) -> str:
    from .config import sauver_config
    p = Path(os.path.expanduser(chemin.strip()))
    if not p.is_dir():
        raise ValueError(f"Dossier introuvable : {p}")
    liste = dossiers()
    if str(p) not in liste:
        CONFIG["dossiers_documents"] = liste + [str(p)]
        sauver_config(["dossiers_documents"])
    indexer_en_fond()
    return str(p)


def retirer_dossier(chemin: str):
    from .config import sauver_config
    CONFIG["dossiers_documents"] = [d for d in dossiers() if d != chemin]
    sauver_config(["dossiers_documents"])
    indexer_en_fond()


def indexer_en_fond():
    def fond():
        try:
            from . import semantique
            if not semantique.disponible():
                semantique.telecharger()
            if dossiers() or _lire_index():
                indexer()
        except Exception as e:
            print(f"  (index des documents : {e})")
    threading.Thread(target=fond, daemon=True, name="index-documents").start()


def demarrer():
    """Index à jour au lancement, puis toutes les 30 min (seuls les fichiers changés sont relus)."""
    def boucle():
        time.sleep(120)
        while True:
            indexer_en_fond()
            time.sleep(1800)
    threading.Thread(target=boucle, daemon=True, name="documents").start()
