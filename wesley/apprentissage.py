"""Wesley apprend de ses erreurs tout seul, sans attendre qu'on lui demande de « retenir une leçon ».

Après chaque échange, en fond, deux signaux :
1. L'utilisateur le corrige (« non, pas comme ça », « je t'ai dit de… », « c'est faux », « tu t'es trompé »…).
2. Une méthode a échoué (outil en erreur) puis une autre a marché dans le même échange.

Alors le cerveau (modèle rapide) relit l'échange et dit s'il y a une leçon RÉUTILISABLE (« Sur ce Mac, Spotify
s'ouvre avec ouvrir_application, pas avec le terminal », « Abdel veut les montants en euros HT »). Elle rejoint la
mémoire en catégorie « lecon », sauf si une leçon qui dit la même chose existe déjà (recherche par le sens).
Les leçons sont ensuite données à Wesley avec chaque demande qui leur ressemble (memoire.rappel_pour).
"""
import json
import re
import threading

from .config import CONFIG

_RX_CORRECTION = re.compile(
    r"^\s*(non\b|nan\b|mais non|pas (comme [çc]a|[çc]a)|c'est (faux|pas [çc]a|pas ce que)|tu (t'es|t'as|as) (tromp|mal|oubli)|"
    r"je t'ai (dit|demand)|je (te )?l'ai (d[ée]j[àa] )?dit|arr[êe]te de|ne (fais|mets|dis) (plus|pas)|"
    r"ce n'est pas (ce que|[çc]a)|faux\b|mauvais|recommence|pas du tout|j'ai dit|no\b|that's wrong|i told you|"
    r"don't|stop doing)|\b(je t'ai dit|je t'avais dit|combien de fois|toujours pas|encore une fois)\b", re.I)
_RX_ERREUR = re.compile(r"^(erreur|error|impossible|échec|echec|introuvable|traceback|exception)|"
                        r"\b(n'existe pas|not found|permission denied|refus[ée]|a échoué|failed)\b", re.I)
SEUIL_DOUBLON = 0.92
_verrou = threading.Lock()


def corrige(texte: str) -> bool:
    return bool(_RX_CORRECTION.search(texte or ""))


def echec_puis_reussite(trace: list[tuple[str, dict, str]]) -> bool:
    """Un outil en erreur, puis au moins un outil réussi après lui."""
    vu_erreur = False
    for _, _, res in trace:
        if _RX_ERREUR.search(str(res or "")[:300]):
            vu_erreur = True
        elif vu_erreur:
            return True
    return False


def _resume_trace(trace) -> str:
    return "\n".join(f"- {nom}({json.dumps(args, ensure_ascii=False)[:200]}) → {str(res or '')[:300]}"
                     for nom, args, res in trace[-15:])


CONSIGNE = """Tu es Wesley, assistant personnel de {nom}. Relis cet échange et dis s'il contient une LEÇON
RÉUTILISABLE pour la suite : une méthode qui marche (après un échec), ou une façon de faire que {nom} veut (après
une correction). Une leçon est une règle courte, concrète, valable la prochaine fois dans une situation semblable,
écrite à l'impératif ou à la 3e personne, qui dit QUOI faire (ex : « Pour ouvrir Spotify sur ce Mac : ouvrir_application('Spotify'), pas le terminal. »,
« {nom} veut les prix en euros TTC. »). Pas de leçon si : simple malentendu ponctuel, erreur réseau passagère,
information sur {nom} sans rapport avec ta façon de faire, ou rien de généralisable.
Réponds UNIQUEMENT en JSON : {{"lecon": "..."}} ou {{"lecon": ""}}.

{contexte}"""


def analyser(texte: str, precedente: str, trace: list, finale: str, completer) -> str:
    """La leçon à retenir de cet échange, ou « »."""
    contexte = ((f"TA RÉPONSE PRÉCÉDENTE :\n{precedente[-1500:]}\n\n" if precedente else "")
                + f"MESSAGE DE {CONFIG.get('nom_utilisateur') or 'L’UTILISATEUR'} :\n{texte[-1500:]}\n\n"
                + (f"TES ACTIONS (outil → résultat) :\n{_resume_trace(trace)}\n\n" if trace else "")
                + f"TA RÉPONSE FINALE :\n{finale[-1500:]}")
    r = completer(CONSIGNE.format(nom=CONFIG.get("nom_utilisateur") or "l'utilisateur", contexte=contexte))
    m = re.search(r"\{.*\}", r or "", re.S)
    try:
        lecon = str(json.loads(m.group(0)).get("lecon") or "").strip() if m else ""
    except ValueError:
        return ""
    return lecon[:400] if len(lecon) > 10 else ""


def deja_connue(lecon: str) -> bool:
    from . import memoire, semantique
    lecons = [x["fait"] for x in memoire._charger() if x.get("categorie") == "lecon"]
    if not lecons:
        return False
    if any(lecon.lower() == x.lower() for x in lecons):
        return True
    try:
        m = semantique.index("faits").matrice(lecons)
        q = semantique.encoder([lecon])
        if m is not None and q is not None:
            return float((m @ q[0]).max()) >= SEUIL_DOUBLON
    except Exception:
        pass
    return False


def apres_echange(texte: str, precedente: str, trace: list, finale: str, completer=None) -> str:
    """Appelé en fond après chaque échange. Renvoie la leçon notée (ou « »)."""
    if not CONFIG.get("apprentissage_auto", True) or not finale:
        return ""
    if not (corrige(texte) and precedente) and not echec_puis_reussite(trace):
        return ""
    if completer is None:
        from .agent import completer
    with _verrou:   # un apprentissage à la fois
        lecon = analyser(texte, precedente, trace, finale, completer)
        if not lecon or deja_connue(lecon):
            return ""
        from . import memoire
        memoire.ajouter(lecon, "lecon")
        print(f"  Leçon apprise : {lecon}")
        return lecon


def en_fond(texte: str, precedente: str, trace: list, finale: str):
    def fond():
        try:
            apres_echange(texte, precedente, list(trace), finale)
        except Exception as e:
            print(f"  (apprentissage : {e})")
    threading.Thread(target=fond, daemon=True, name="apprentissage").start()
