"""La mémoire se range toute seule (une fois par jour, en fond).

1. Doublons : deux souvenirs qui disent la même chose (« aime le café » / « boit du café serré ») sont fusionnés en
   un seul, plus complet. Sans risque : rien n'est perdu, le texte fusionné garde toutes les informations.
2. Contradictions : un souvenir devenu faux (ancienne adresse, ancien travail…) n'est JAMAIS changé tout seul :
   Wesley prépare une proposition (« remplacer “habite à Lyon” par “habite à Paris” ? ») que l'utilisateur accepte
   ou refuse (écran Mémoire, ou Wesley la lui pose une fois dans la conversation).
3. Résumé de la semaine : chaque semaine passée devient un souvenir « journal » (ce qui a été fait, décidé,
   appris), retrouvé par le sens quand on parle du passé (« qu'est-ce que j'ai fait la semaine du 10 ? »).

Les paires candidates viennent de la recherche par le sens (semantique.py) ; le cerveau de Wesley décide. Sans
modèle ou sans cerveau disponible, rien n'est fait (on réessaie plus tard).
"""
import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta

from .config import RACINE

FICHIER = RACINE / "memoire" / "consolidation.json"
SEUIL_DOUBLON = 0.93        # similarité de sens au-delà de laquelle deux souvenirs disent sans doute la même chose
SEUIL_VOISIN = 0.86         # assez proches pour parler du même sujet (contradiction possible)
MAX_PAIRES = 30
_verrou = threading.Lock()


def _etat() -> dict:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _sauver_etat(e: dict):
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- propositions à confirmer par l'utilisateur ----------
def propositions() -> list[dict]:
    return [p for p in _etat().get("propositions", []) if p.get("statut") == "attente"]


def repondre(pid: str, accepte: bool) -> str:
    """L'utilisateur accepte (le souvenir est remplacé ou oublié) ou refuse une proposition."""
    from . import memoire
    with _verrou:
        e = _etat()
        p = next((x for x in e.get("propositions", []) if x["id"] == pid and x.get("statut") == "attente"), None)
        if p is None:
            return "Proposition introuvable (déjà traitée ?)."
        p["statut"] = "acceptee" if accepte else "refusee"
        _sauver_etat(e)
    if p.get("type") == "routine":   # habitude remarquée (habitudes.py)
        if not accepte:
            return "D'accord, je ne te le proposerai plus."
        from . import automatisations
        r = p["routine"]
        regle = automatisations.creer(f"Habitude : {r['consigne'][:40]}", action="wesley", consigne=r["consigne"],
                                      type_declencheur="horaire", heure=r["heure"], jours=r.get("jours") or [])
        return f"C'est noté : {automatisations.decrire(regle)}"
    if not accepte:
        return "D'accord, je garde ma mémoire telle quelle."
    if p.get("nouveau"):
        memoire.modifier(p["fid"], p["nouveau"])
        for autre in p.get("oublier", []):
            memoire.supprimer_un(fid=autre)
        return f"Mémoire mise à jour : {p['nouveau']}"
    memoire.supprimer_un(fid=p["fid"])
    return f"Oublié : {p['ancien']}"


def rappel_propositions() -> str:
    """Pour la conversation : Wesley pose la question une fois, l'utilisateur répond, Wesley appelle repondre."""
    ps = propositions()[:3]
    if not ps:
        return ""
    return ("Mémoire à vérifier (demande-le à l'utilisateur en une phrase à la fin de ta réponse, puis applique sa réponse "
            "avec l'outil confirmer_memoire) :\n" + "\n".join(f"- [{p['id']}] {p['question']}" for p in ps))


# ---------- analyse ----------
def paires(faits: list[dict]) -> tuple[list, list]:
    """(doublons probables, voisins à vérifier) d'après la similarité de sens. Listes de (i, j, score)."""
    from . import semantique
    if len(faits) < 2:
        return [], []
    m = semantique.index("faits").matrice([x["fait"] for x in faits])
    if m is None:
        return [], []
    sim = m @ m.T
    doublons, voisins = [], []
    for i in range(len(faits)):
        for j in range(i + 1, len(faits)):
            s = float(sim[i, j])
            if faits[i].get("categorie") == "journal" or faits[j].get("categorie") == "journal":
                continue
            if s >= SEUIL_DOUBLON:
                doublons.append((i, j, s))
            elif s >= SEUIL_VOISIN and faits[i].get("categorie") == faits[j].get("categorie"):
                voisins.append((i, j, s))
    doublons.sort(key=lambda x: -x[2])
    voisins.sort(key=lambda x: -x[2])
    return doublons[:MAX_PAIRES], voisins[:MAX_PAIRES]


def _json(reponse: str):
    m = re.search(r"\{.*\}", reponse or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


CONSIGNE = """Tu ranges la mémoire d'un assistant personnel : des souvenirs sur son utilisateur.
Voici des paires de souvenirs proches. Pour chaque paire, décide :
- "fusion" : ils disent la même chose ou se complètent sans se contredire → donne "texte", UN souvenir qui garde
  TOUTES les informations des deux (aucune perte), court, à la 3e personne comme les originaux ;
- "contradiction" : l'un rend l'autre faux (adresse, travail, situation, préférence qui a changé) → donne "garder"
  (1 ou 2 : le plus récent ou le plus probable d'après les dates) et "question", une question courte à poser à
  l'utilisateur pour confirmer (ex : « Tu habites maintenant à Paris, plus à Lyon ? ») ;
- "distincts" : ce sont deux informations différentes → rien à faire.
Dans le doute, "distincts". Réponds UNIQUEMENT en JSON : {{"paires": [{{"n": 1, "decision": "...", "texte": "...",
"garder": 1, "question": "..."}}]}}

{paires}"""


def analyser(faits: list[dict], completer) -> tuple[list, list]:
    """Demande au cerveau quoi faire des paires proches. Renvoie (fusions, contradictions)."""
    doublons, voisins = paires(faits)
    candidats = doublons + voisins
    if not candidats:
        return [], []
    texte = "\n".join(f"{n}. (1) [{faits[i].get('date', '')}] {faits[i]['fait']}\n   (2) [{faits[j].get('date', '')}] {faits[j]['fait']}"
                      for n, (i, j, _) in enumerate(candidats, 1))
    d = _json(completer(CONSIGNE.format(paires=texte)))
    fusions, contradictions, vus = [], [], set()
    for r in d.get("paires") or []:
        try:
            i, j, _ = candidats[int(r.get("n")) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        if i in vus or j in vus:
            continue   # un souvenir n'entre que dans une seule opération par passage
        if r.get("decision") == "fusion" and str(r.get("texte") or "").strip():
            fusions.append((faits[i], faits[j], str(r["texte"]).strip()[:500]))
            vus |= {i, j}
        elif r.get("decision") == "contradiction" and str(r.get("question") or "").strip():
            garde, perime = (faits[j], faits[i]) if int(r.get("garder") or 2) == 2 else (faits[i], faits[j])
            contradictions.append((garde, perime, str(r["question"]).strip()[:200]))
            vus |= {i, j}
    return fusions, contradictions


def appliquer(fusions: list, contradictions: list) -> dict:
    from . import memoire
    for a, b, texte in fusions:
        memoire.modifier(a["fid"], texte)
        memoire.supprimer_un(fid=b["fid"])
    with _verrou:
        e = _etat()
        deja = {(p.get("fid"), p.get("ancien")) for p in e.get("propositions", [])}
        for garde, perime, question in contradictions:
            if (perime.get("fid"), perime["fait"]) in deja:
                continue   # déjà demandé (même refusé : on ne repose pas la question)
            e.setdefault("propositions", []).append({
                "id": uuid.uuid4().hex[:8], "statut": "attente", "date": time.time(), "question": question,
                "fid": perime["fid"], "ancien": perime["fait"], "nouveau": "", "garde": garde["fait"]})
        e["propositions"] = e.get("propositions", [])[-100:]
        _sauver_etat(e)
    if contradictions:
        try:
            from . import notifications
            notifications.ajouter("Mémoire à vérifier", "\n".join(q for _, _, q in contradictions[:3]), genre="info", vue="memoire")
        except Exception:
            pass
    return {"fusions": len(fusions), "contradictions": len(contradictions)}


# ---------- résumé de la semaine ----------
def semaine_a_resumer(aujourd_hui: date | None = None) -> date | None:
    """Lundi de la semaine dernière, si son résumé n'existe pas encore (souvenir « journal »)."""
    from . import memoire
    j = aujourd_hui or date.today()
    lundi = j - timedelta(days=j.weekday() + 7)
    cle = f"Semaine du {lundi:%d/%m/%Y}"
    if any(x.get("categorie") == "journal" and x["fait"].startswith(cle) for x in memoire._charger()):
        return None
    return lundi


def resumer_semaine(lundi: date, completer) -> str | None:
    from . import memoire
    jours = {(lundi + timedelta(days=k)).isoformat() for k in range(7)}
    lignes = []
    par_jour = memoire.fichiers_par_jour()
    for jour in sorted(par_jour):
        if jour in jours:
            lignes += [f"({jour}) {l[:300]}" for _, _, l in memoire.lignes_du_jour(par_jour[jour])]
    if len(lignes) < 6:
        return None   # semaine presque vide : rien à résumer
    texte = "\n".join(lignes)[-30000:]
    r = completer("Voici les conversations d'une semaine entre un utilisateur et son assistant Wesley. Écris en 3 à 6 "
                  "phrases courtes, à la 3e personne, ce qui compte pour s'en souvenir plus tard : ce que l'utilisateur a "
                  "fait ou demandé, les décisions, projets avancés, problèmes réglés, choses apprises sur lui. Pas de "
                  "détails techniques inutiles, rien d'inventé. Réponds avec le texte seul.\n\n" + texte)
    r = (r or "").strip()
    if not r:
        return None
    fait = f"Semaine du {lundi:%d/%m/%Y} : {' '.join(r.split())}"[:1500]
    memoire.ajouter(fait, "journal")
    return fait


# ---------- passage quotidien ----------
def consolider(completer=None, forcer: bool = False) -> dict:
    """Range la mémoire (doublons, contradictions, résumé de la semaine passée). Une fois par jour au plus."""
    from . import memoire, semantique
    e = _etat()
    if not forcer and e.get("dernier") == date.today().isoformat():
        return {"deja": True}
    if completer is None:
        from .agent import completer
    res = {"fusions": 0, "contradictions": 0, "semaine": None}
    if semantique.disponible():
        fusions, contradictions = analyser(memoire._charger(), completer)
        res.update(appliquer(fusions, contradictions))
    lundi = semaine_a_resumer()
    if lundi:
        res["semaine"] = resumer_semaine(lundi, completer)
    try:
        from . import habitudes
        res["habitudes"] = habitudes.proposer()
    except Exception as ex:
        print(f"  (habitudes : {ex})")
    e = _etat()
    e["dernier"] = date.today().isoformat()
    e["resultat"] = {**res, "date": datetime.now().isoformat(timespec="minutes")}
    _sauver_etat(e)
    return res


def demarrer():
    """En fond : quelques minutes après le lancement, puis toutes les 6 h (une fois par jour au plus)."""
    def boucle():
        import random
        time.sleep(300 + random.randint(0, 600))   # pas en même temps sur tous les appareils, ni au démarrage
        while True:
            try:
                r = consolider()
                if not r.get("deja"):
                    print(f"  Mémoire rangée : {r}")
            except Exception as ex:
                print(f"  (rangement de la mémoire : {ex})")   # pas de cerveau, hors ligne… : on réessaie plus tard
            time.sleep(6 * 3600)
    threading.Thread(target=boucle, daemon=True, name="consolidation").start()
