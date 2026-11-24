"""Wesley remarque tes habitudes et te propose d'en faire des automatisations, sans jamais les imposer.

Chaque jour (avec le rangement de la mémoire), il relit tes demandes des 3 dernières semaines. Une même demande
(mêmes mots, ou même sens grâce à la recherche par le sens) faite au moins 4 jours différents, à peu près à la même
heure (moins d'une heure d'écart), devient une proposition :
« Tu me demandes “ouvre VS Code et Slack” presque chaque matin vers 9 h. Je le fais tout seul à 9 h ? »
Accepter crée l'automatisation (à heure fixe, sur cet appareil) ; refuser ne la repropose jamais.
"""
import re
import statistics
import unicodedata
from datetime import date, datetime, timedelta

JOURS_ANALYSES = 21
MIN_JOURS = 4
ECART_MAX = 60          # minutes : au-delà, ce n'est pas « à la même heure »
SEUIL_SENS = 0.92       # deux demandes de même sens (« ouvre slack et vs code » / « lance VS Code et Slack »)
_RX_LIGNE = re.compile(r"^\[(\d{2}):(\d{2})\]\s+([^:]{1,40}):\s+(.+)$")
_EXCLUS = re.compile(r"^(oui|non|ok|merci|d'accord|stop|salut|bonjour|bonsoir|coucou|ça va|ca va)\b", re.I)


def _norme(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", t))


def demandes(aujourd_hui: date | None = None, nom: str = "") -> list[tuple[date, int, str]]:
    """(jour, minute de la journée, texte) des demandes de l'utilisateur sur les 3 dernières semaines."""
    from . import memoire
    from .config import CONFIG
    nom = (nom or CONFIG.get("nom_utilisateur") or "").strip().lower()
    fin = aujourd_hui or date.today()
    debut = fin - timedelta(days=JOURS_ANALYSES)
    res = []
    for jour, fichiers in memoire.fichiers_par_jour().items():
        try:
            j = date.fromisoformat(jour)
        except ValueError:
            continue
        if not debut <= j < fin:
            continue
        for _, _, ligne in memoire.lignes_du_jour(fichiers):
            m = _RX_LIGNE.match(ligne)
            if not m or m.group(3).strip().lower() in ("wesley", "jarvis"):
                continue
            if nom and m.group(3).strip().lower() != nom:
                continue
            texte = m.group(4).strip()
            if len(texte) < 8 or _EXCLUS.match(texte) or texte.startswith("["):
                continue
            res.append((j, int(m.group(1)) * 60 + int(m.group(2)), texte))
    return res


def _groupes(dem: list[tuple[date, int, str]]) -> list[list[int]]:
    """Regroupe les demandes identiques (texte normalisé) puis de même sens (si le modèle est là)."""
    from . import semantique
    par_texte: dict = {}
    for i, (_, _, t) in enumerate(dem):
        par_texte.setdefault(_norme(t), []).append(i)
    groupes = list(par_texte.values())
    if len(groupes) > 1 and semantique.disponible():
        try:
            representants = [dem[g[0]][2] for g in groupes]
            m = semantique.index("historique").matrice(representants, garder=False)
            if m is not None:
                sim = m @ m.T
                fusion = list(range(len(groupes)))
                for a in range(len(groupes)):
                    for b in range(a + 1, len(groupes)):
                        if float(sim[a, b]) >= SEUIL_SENS:
                            fusion[b] = fusion[a]
                reunis: dict = {}
                for k, g in enumerate(groupes):
                    racine = k
                    while fusion[racine] != racine:
                        racine = fusion[racine]
                    reunis.setdefault(racine, []).extend(g)
                groupes = list(reunis.values())
        except Exception as e:
            print(f"  (habitudes : {e})")
    return groupes


def detecter(dem: list[tuple[date, int, str]]) -> list[dict]:
    """Habitudes : {texte, heure (HH:MM), jours (0-6), nb_jours}."""
    res = []
    for g in _groupes(dem):
        par_jour: dict = {}
        for i in g:
            j, minute, _ = dem[i]
            par_jour.setdefault(j, minute)          # la 1re fois de la journée
        if len(par_jour) < MIN_JOURS:
            continue
        minutes = sorted(par_jour.values())
        mediane = int(statistics.median(minutes))
        proches = {j: m for j, m in par_jour.items() if abs(m - mediane) <= ECART_MAX}
        if len(proches) < MIN_JOURS:
            continue
        jours_semaine = sorted({j.weekday() for j in proches})
        if set(jours_semaine) <= {0, 1, 2, 3, 4} and len(jours_semaine) >= 3:
            jours_semaine = [0, 1, 2, 3, 4]          # en semaine
        elif len(jours_semaine) >= 5:
            jours_semaine = []                       # tous les jours
        # l'heure proposée : un peu avant l'habitude (arrondie au quart d'heure), pour que ce soit prêt
        h = max(0, mediane - 5) // 15 * 15
        textes = [dem[i][2] for i in g]
        texte = max(set(textes), key=textes.count)
        res.append({"texte": texte, "heure": f"{h // 60:02d}:{h % 60:02d}", "jours": jours_semaine, "nb_jours": len(proches)})
    return sorted(res, key=lambda x: -x["nb_jours"])


def _heure_parlee(heure: str) -> str:
    h, m = int(heure[:2]), int(heure[3:5])
    return f"{h} h" + (f" {m:02d}" if m else "")


def _moment(heure: str) -> str:
    h = int(heure[:2])
    return "chaque matin" if h < 12 else "chaque après-midi" if h < 18 else "chaque soir"


def proposer(aujourd_hui: date | None = None) -> int:
    """Ajoute les nouvelles habitudes aux propositions (écran Mémoire / conversation). Renvoie leur nombre."""
    import time
    import uuid
    from . import automatisations, consolidation
    habitudes = detecter(demandes(aujourd_hui))
    if not habitudes:
        return 0
    existantes = {_norme(r["action"].get("consigne") or "") for r in automatisations.lister()}
    n = 0
    with consolidation._verrou:
        e = consolidation._etat()
        deja = {_norme(p.get("routine", {}).get("consigne", "")) for p in e.get("propositions", []) if p.get("type") == "routine"}
        for h in habitudes[:3]:
            cle = _norme(h["texte"])
            if cle in existantes or cle in deja:
                continue
            quand = "en semaine" if h["jours"] == [0, 1, 2, 3, 4] else "" if not h["jours"] else "le " + ", ".join(
                automatisations.JOURS[j] for j in h["jours"])
            e.setdefault("propositions", []).append({
                "id": uuid.uuid4().hex[:8], "statut": "attente", "date": time.time(), "type": "routine",
                "question": f"Tu me demandes « {h['texte'][:120]} » {_moment(h['heure'])}{' ' + quand if quand else ''} vers "
                            f"{_heure_parlee(h['heure'])}. Je le fais tout seul à cette heure-là ?",
                "ancien": h["texte"], "routine": {"consigne": h["texte"], "heure": h["heure"], "jours": h["jours"]}})
            n += 1
        consolidation._sauver_etat(e)
    return n
