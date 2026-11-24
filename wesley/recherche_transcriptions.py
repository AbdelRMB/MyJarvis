"""Chercher dans toutes les transcriptions (de cet appareil et des autres appareils du compte) :
« qu'est-ce qu'on a dit sur le budget ? », « le cours où le prof parlait des interfaces »…

Recherche par mots (sans accents ni majuscules, mots courants ignorés) dans les prises de parole, les titres et les
résumés. Chaque résultat donne la transcription, l'heure, la personne et l'extrait, pour que Wesley réponde
précisément ou ouvre le bon passage. Les transcriptions des autres appareils sont lues dans leur dernière version
publiée (wesley/partage.py), même si l'appareil est éteint.
"""
import re
import unicodedata

MOTS_VIDES = set("""le la les un une des du de d l au aux et ou mais donc or ni car que qui quoi dont ou est sont
a ai as avons avez ont ce cet cette ces se sa son ses mon ma mes ton ta tes leur leurs nous vous ils elles il elle on
je tu en y ne pas plus pour par sur dans avec sans sous chez comme quand si tout tous toute toutes tres bien fait
dit dire qu ca cela ceci est-ce the of and to in is it that this was for on with as be at by an are or from""".split())


def normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def mots(requete: str) -> list[str]:
    return [m for m in re.findall(r"[\w$]+", normaliser(requete)) if len(m) >= 2 and m not in MOTS_VIDES]


def _racine(m: str) -> str:
    """Pluriels et formes proches : « budgets » trouve « budget », « interfaces » trouve « interface »."""
    return m[:-1] if len(m) > 4 and m.endswith(("s", "x")) else m


def score(texte_norm: str, cles: list[str]) -> int:
    """Nombre de mots de la requête présents (au début d'un mot), plus un bonus si l'expression entière y est."""
    s = sum(1 for c in cles if re.search(r"(?<![\w$])" + re.escape(_racine(c)), texte_norm))
    if len(cles) > 1 and " ".join(cles) in texte_norm:
        s += len(cles)
    return s


def chercher_dans(session: dict, cles: list[str], appareil: str = "") -> list[dict]:
    """Prises de parole d'une transcription qui correspondent ; le titre et le résumé comptent aussi."""
    from .transcription import horodatage, nom_locuteur, tours_de_parole
    res = []
    titre = session.get("titre") or ""
    bonus = score(normaliser(titre + " " + ((session.get("resume") or {}).get("texte") or "")), cles) > 0
    mini = max(1, (len(cles) + 1) // 2)    # au moins la moitié des mots
    for t in tours_de_parole(session):
        s = score(normaliser(t["texte"]), cles)
        if s >= mini:
            res.append({"id": session.get("id"), "titre": titre, "appareil": appareil, "debut": t["debut"],
                        "heure": horodatage(t["debut"]), "locuteur": nom_locuteur(session, t["locuteur"]),
                        "texte": t["texte"][:600], "score": s + (1 if bonus else 0), "date": session.get("debut") or 0})
    if not res and bonus:   # le sujet est dans le titre ou le résumé : on renvoie la transcription elle-même
        r = (session.get("resume") or {}).get("texte") or ""
        res.append({"id": session.get("id"), "titre": titre, "appareil": appareil, "debut": 0, "heure": "", "locuteur": "",
                    "texte": (r.split("\n\n")[0] if r else "")[:600], "score": 1, "date": session.get("debut") or 0})
    return res


def chercher(requete: str, limite: int = 20) -> list[dict]:
    """Toutes les transcriptions, de tous les appareils. Résultats les plus pertinents puis les plus récents."""
    from . import partage, transcription
    from .config import MACHINE
    cles = mots(requete)
    if not cles:
        return []
    res = []
    for r in transcription.lister():
        try:
            s = transcription.lire(r["id"])
        except ValueError:
            s = None
        if s:
            res += chercher_dans(s, cles, MACHINE)
    for r in partage.distants("transcription"):
        try:
            s = partage.lire("transcription", r["id"])
        except Exception:
            s = None
        if s:
            res += chercher_dans(s, cles, r.get("appareil", ""))
    res.sort(key=lambda x: (-x["score"], -x["date"], x["debut"]))
    return res[:limite]
