"""Transcription de réunions et de conversations, 100 % locale (onglet « Transcription »).

Deux sources au choix :
- « micro »   : réunion physique, Wesley écoute la pièce ;
- « systeme » : réunion en ligne, le son qui sort de l'ordinateur (macOS : ScreenCaptureKit, sans pilote à
               installer ; Windows : WASAPI loopback). En option, ton micro est mélangé au son du PC pour
               que ta propre voix soit aussi transcrite.

Chaîne de traitement (rien ne quitte l'ordinateur) :
  capture -> Mixeur (16 kHz mono, calé sur l'horloge) -> Decoupeur (blocs coupés aux pauses)
          -> Whisper local (faster-whisper) -> empreinte vocale de chaque phrase (sherpa-onnx, modèle
             WeSpeaker CAM++ téléchargé une fois ; à défaut, empreinte spectrale simple en numpy)
          -> Diariseur (regroupement des voix : Locuteur 1, Locuteur 2…)
À l'arrêt, toutes les phrases sont regroupées une dernière fois (classification hiérarchique), ce qui corrige
les erreurs du regroupement en direct. L'utilisateur renomme et trie ensuite les locuteurs dans l'interface.

Fichiers : RACINE/transcriptions/<id>.json (données) et un fichier Markdown lisible, réécrit au fil de l'eau,
dans ~/Documents/Wesley/Transcriptions (CONFIG["dossier_transcriptions"] pour en changer).
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from .config import CONFIG, RACINE

SR = 16000
DOSSIER_DONNEES = RACINE / "transcriptions"
DOSSIER_MODELES = RACINE / "modeles"
MODELE_LOCUTEURS = "wespeaker_en_voxceleb_CAM++.onnx"   # ~28 Mo, reconnaissance du locuteur (indépendant de la langue)
URL_MODELE_LOCUTEURS = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
                        + MODELE_LOCUTEURS.replace("+", "%2B"))
MODELES_WHISPER = ["auto", "base", "small", "medium", "large-v3-turbo", "large-v3"]   # auto : selon la machine
DUREE_FIABLE = 1.0          # s : en dessous, l'empreinte d'une phrase est trop courte pour être sûre
PAUSE_TOUR = 2.0            # s : au-delà, une nouvelle prise de parole commence (nouvel horodatage)
DUREE_TOUR_MAX = 30.0       # s : un tour de parole affiché ne dépasse pas ~30 s (quelques phrases)
ecouteurs: list = []        # fonctions appelées à chaque changement (web.py : diffusion vers l'interface)


# ====================================================================================================
# Mise en forme, renommage, tri (pur Python : testable sans dépendance)
# ====================================================================================================
def horodatage(secondes: float) -> str:
    """12.3 -> « 00:12 » ; 3725 -> « 1:02:05 »."""
    s = int(max(0, secondes))
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def nom_locuteur(session: dict, locuteur) -> str:
    nom = (session.get("noms") or {}).get(str(locuteur), "").strip()
    return nom or f"Locuteur {locuteur}"


def locuteurs(session: dict) -> list[dict]:
    """Locuteurs présents, dans l'ordre d'apparition, avec leur temps de parole."""
    vus: dict[int, dict] = {}
    for s in session.get("segments", []):
        l = int(s["locuteur"])
        e = vus.setdefault(l, {"id": l, "nom": nom_locuteur(session, l), "duree": 0.0, "phrases": 0})
        e["duree"] += max(0.0, s["fin"] - s["debut"])
        e["phrases"] += 1
    for e in vus.values():
        e["duree"] = round(e["duree"], 1)
    return list(vus.values())


def tours_de_parole(session: dict) -> list[dict]:
    """Phrases consécutives d'un même locuteur réunies en un tour de parole, coupé à chaque pause
    (PAUSE_TOUR) et au plus ~DUREE_TOUR_MAX s : horodatage fidèle, jamais un bloc de 15 minutes."""
    tours: list[dict] = []
    reprises = [float(r.get("position", 0)) for r in session.get("reprises") or []]
    for s in session.get("segments", []):
        texte = s["texte"].strip()
        if not texte:
            continue
        if tours and tours[-1]["locuteur"] == s["locuteur"] and s["debut"] - tours[-1]["fin"] < PAUSE_TOUR \
                and s["fin"] - tours[-1]["debut"] <= DUREE_TOUR_MAX \
                and not any(tours[-1]["debut"] < p <= s["debut"] for p in reprises):   # jamais à cheval sur une reprise
            tours[-1]["texte"] += " " + texte
            tours[-1]["fin"] = s["fin"]
        else:
            tours.append({"locuteur": s["locuteur"], "debut": s["debut"], "fin": s["fin"], "texte": texte})
    return tours


def exporter(session: dict, format: str = "md") -> str:
    """Transcription complète en Markdown (« md ») ou en texte brut (« txt »)."""
    debut = datetime.fromtimestamp(session.get("debut") or time.time())
    titre = session.get("titre") or "Transcription"
    duree = horodatage(session.get("duree", 0))
    source = {"micro": "micro", "systeme": "son de l'ordinateur", "fichier": "fichier audio importé"}.get(session.get("source"), session.get("source", ""))
    if session.get("source") == "systeme" and session.get("avec_micro"):
        source += " + micro"
    noms = ", ".join(l["nom"] for l in locuteurs(session)) or "—"
    tours = tours_de_parole(session)
    reprises = sorted(session.get("reprises") or [], key=lambda r: r.get("position", 0))

    def reprise_avant(i):
        """Repère « Reprise le … » avant le premier tour de parole qui suit chaque reprise."""
        res = []
        for r in reprises:
            p = float(r.get("position", 0))
            if tours[i]["debut"] >= p and (i == 0 or tours[i - 1]["debut"] < p):
                res.append(f"Reprise le {datetime.fromtimestamp(r.get('date') or 0).strftime('%d/%m/%Y à %H:%M')}"
                           f" ({horodatage(p)})")
        return res
    if format == "txt":
        lignes = [titre, debut.strftime("%d/%m/%Y %H:%M") + f" · durée {duree} · source : {source}",
                  f"Participants : {noms}", ""]
        for i, t in enumerate(tours):
            lignes += [f"— {r} —" for r in reprise_avant(i)]
            lignes.append(f"[{horodatage(t['debut'])}] {nom_locuteur(session, t['locuteur'])} : {t['texte']}")
        return "\n".join(lignes).rstrip() + "\n"
    lignes = [f"# {titre}", "",
              f"- **Date** : {debut.strftime('%d/%m/%Y %H:%M')}",
              f"- **Durée** : {duree}",
              f"- **Source** : {source}",
              f"- **Participants** : {noms}", "", "---", ""]
    for i, t in enumerate(tours):
        marques = reprise_avant(i)
        lignes += [x for r in marques for x in (f"_— {r} —_", "")]
        if i and tours[i - 1]["locuteur"] == t["locuteur"] and not marques:     # même personne : l'heure suffit
            lignes += [f"`{horodatage(t['debut'])}` {t['texte']}", ""]
        else:
            lignes += [f"**{nom_locuteur(session, t['locuteur'])}** · `{horodatage(t['debut'])}`", "", t["texte"], ""]
    if not tours:
        lignes.append("_(rien n'a encore été transcrit)_")
    return "\n".join(lignes).rstrip() + "\n"


def extrait(session: dict, debut: float = 0, fin: float = 0, partie: int = 1, taille: int = 9000) -> str:
    """Transcription en texte, par parties de ~taille caractères (jamais une ligne coupée, rien de perdu) :
    debut / fin en minutes (fin 0 = jusqu'au bout), partie = 1, 2… L'en-tête dit s'il reste une suite."""
    debut_s, fin_s = max(0.0, float(debut or 0)) * 60, float(fin or 0) * 60
    tours = [t for t in tours_de_parole(session) if t["fin"] > debut_s and (fin_s <= 0 or t["debut"] < fin_s)]
    lignes = [f"[{horodatage(t['debut'])}] {nom_locuteur(session, t['locuteur'])} : {t['texte']}" for t in tours]
    parties: list[list[str]] = [[]]
    longueur = 0
    for l in lignes:
        if parties[-1] and longueur + len(l) + 1 > taille:
            parties.append([])
            longueur = 0
        parties[-1].append(l)
        longueur += len(l) + 1
    total = len(parties)
    partie = min(max(1, int(partie or 1)), total)
    date = datetime.fromtimestamp(session.get("debut") or time.time()).strftime("%d/%m/%Y %H:%M")
    noms = ", ".join(l["nom"] for l in locuteurs(session)) or "—"
    tete = [f"{session.get('titre') or 'Transcription'} · {date} · durée {horodatage(session.get('duree', 0))}",
            f"Participants : {noms}"]
    if debut_s or fin_s > 0:
        tete.append(f"Passage de {horodatage(debut_s)} à {horodatage(fin_s) if fin_s > 0 else 'la fin'}")
    if total > 1:
        tete.append(f"Partie {partie}/{total} ({len(lignes)} prises de parole au total)")
    corps = parties[partie - 1] or ["(rien de transcrit sur ce passage)"]
    pied = [f"[Suite : partie={partie + 1} (sur {total}). Lis toutes les parties avant de résumer.]"] if partie < total else []
    return "\n".join(tete + [""] + corps + ([""] + pied if pied else [])) + "\n"


def renommer(session: dict, noms: dict) -> dict:
    """noms : {"1": "Alice", "2": "Bob"} ; un nom vide rend « Locuteur N »."""
    actuels = dict(session.get("noms") or {})
    for k, v in (noms or {}).items():
        v = re.sub(r"\s+", " ", str(v or "")).strip()[:60]
        if v:
            actuels[str(int(k))] = v
        else:
            actuels.pop(str(int(k)), None)
    session["noms"] = actuels
    return session


def fusionner(session: dict, source: int, cible: int) -> dict:
    """Toutes les phrases de « source » passent à « cible » (deux étiquettes pour une même personne)."""
    source, cible = int(source), int(cible)
    if source != cible:
        for s in session.get("segments", []):
            if s["locuteur"] == source:
                s["locuteur"] = cible
        if str(cible) not in (session.get("noms") or {}) and str(source) in (session.get("noms") or {}):
            session["noms"][str(cible)] = session["noms"][str(source)]
        (session.get("noms") or {}).pop(str(source), None)
    return session


def changer_locuteur(session: dict, index: int, locuteur: int) -> dict:
    """Une phrase attribuée à la mauvaise personne. locuteur = 0 : nouveau locuteur."""
    segs = session.get("segments", [])
    if not 0 <= index < len(segs):
        raise ValueError("Phrase introuvable.")
    locuteur = int(locuteur)
    if locuteur <= 0:
        locuteur = max((s["locuteur"] for s in segs), default=0) + 1
    segs[index]["locuteur"] = locuteur
    return session


def corriger_texte(session: dict, index: int, texte: str) -> dict:
    segs = session.get("segments", [])
    if not 0 <= index < len(segs):
        raise ValueError("Phrase introuvable.")
    segs[index]["texte"] = str(texte).strip()
    return session


def renumeroter(etiquettes: list[int]) -> list[int]:
    """Étiquettes quelconques -> 1, 2, 3… dans l'ordre de première apparition."""
    table: dict[int, int] = {}
    return [table.setdefault(e, len(table) + 1) for e in etiquettes]


def nom_de_fichier(texte: str) -> str:
    texte = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", texte)
    return re.sub(r"\s+", " ", texte).strip(" .")[:80] or "Transcription"


# ====================================================================================================
# Diarisation : qui parle ? (numpy)
# ====================================================================================================
DUREE_SOLIDE = 3.0          # s : il faut au moins ça de parole (phrase ou phrases consécutives) pour créer un locuteur
DUREE_FENETRE = 12.0        # s : phrases consécutives d'une même voix réunies en une fenêtre avant le regroupement final
POIDS_MAX = 10.0            # s : poids maximal d'une phrase dans la voix moyenne d'un locuteur


def _normer(v):
    import numpy as np
    v = np.nan_to_num(np.asarray(v, dtype=np.float32).ravel())
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


def _assoupli(seuil: float, facteur: float) -> float:
    """Seuil de similarité « facteur » fois plus tolérant, mesuré en distance (1 - cosinus) : même effet pour
    les deux extracteurs, dont les échelles diffèrent (CAM++ : 0,5 ; spectral : 0,95)."""
    return 1.0 - facteur * (1.0 - seuil)


def _poids(duree: float, fiable: bool = True) -> float:
    """Poids d'une phrase dans une voix moyenne : sa durée (bornée). Une phrase longue donne une empreinte
    plus sûre ; une phrase trop courte (pas fiable) ne compte presque pas."""
    return min(max(float(duree), 0.3), POIDS_MAX) if fiable else 0.1


def appliquer_fusion(etiquettes: list[int], source: int, cible: int) -> list[int]:
    """Le locuteur « source » rejoint « cible » ; les numéros au-dessus de source descendent d'un cran
    (pas de trou : Locuteur 1, 2, 3…)."""
    out = []
    for l in etiquettes:
        l = cible if l == source else l
        out.append(l - 1 if l > source else l)
    return out


class Diariseur:
    """Regroupement en direct : chaque phrase va au locuteur dont la voix moyenne (pondérée par la durée)
    ressemble le plus à la sienne. Un nouveau locuteur n'est créé que sur une phrase longue (≥ DUREE_SOLIDE)
    vraiment différente ; une phrase courte incertaine reste au locuteur précédent (on ne change pas de voix
    toutes les 2 s). Deux locuteurs dont les voix moyennes se rejoignent sont fusionnés, et régulièrement
    toutes les phrases sont regroupées à nouveau (comme à l'arrêt) : self.etiquettes donne alors le locuteur
    à jour de chaque phrase déjà écrite (numéros 1, 2, 3… sans trou)."""

    def __init__(self, seuil: float = 0.5, nombre: int = 0):
        self.seuil, self.nombre = seuil, max(0, int(nombre or 0))
        self.centres: list = []     # somme des empreintes normées × durée, par locuteur
        self.poids: list[float] = []
        self.dernier = 0
        self.fusions: list[tuple[int, int]] = []    # (source, cible) : deux locuteurs reconnus comme un seul
        self.historique: list = []                  # (empreinte normée ou None, fiable, durée) par phrase
        self.etiquettes: list[int] = []             # locuteur actuel de chaque phrase
        self._regroupe = 0                          # nombre de phrases au dernier regroupement complet

    def similarites(self, e):
        import numpy as np
        if not self.centres:
            return np.zeros(0, dtype=np.float32)
        c = np.stack([_normer(x) for x in self.centres])
        return c @ _normer(e)

    def attribuer(self, empreinte, fiable: bool = True, duree: float | None = None) -> int:
        """Renvoie le numéro du locuteur (1, 2…). duree : longueur de la phrase en s (None : phrase longue).
        empreinte None (calcul impossible) : la phrase reste au locuteur précédent."""
        duree = DUREE_SOLIDE if duree is None else float(duree)
        if empreinte is None:
            self.historique.append((None, False, duree))
            self.etiquettes.append(self.dernier or 1)
            self.dernier = self.dernier or 1
            return self.dernier
        e = _normer(empreinte)
        sims = self.similarites(e).astype(float)
        if len(sims) and self.dernier:
            sims[self.dernier - 1] += 0.1 * (1.0 - self.seuil)     # continuité : le locuteur précédent est favorisé
        meilleur = int(sims.argmax()) if len(sims) else -1
        if meilleur >= 0 and sims[meilleur] >= _assoupli(self.seuil, 1.2):
            if fiable:
                self.centres[meilleur] = self.centres[meilleur] + e * _poids(duree)
                self.poids[meilleur] += _poids(duree)
            self.dernier = meilleur + 1
        elif not self.centres or (fiable and duree >= DUREE_SOLIDE):
            self.centres.append(e * _poids(duree, fiable))
            self.poids.append(_poids(duree, fiable))
            self.dernier = len(self.centres)
        # sinon : phrase courte d'une voix incertaine, elle reste au locuteur précédent
        self.historique.append((e, fiable, duree))
        self.etiquettes.append(self.dernier)
        self._fusionner_proches()
        n = len(self.historique)
        if n - self._regroupe >= max(10, n // 20):    # régulièrement (de plus en plus espacé) : tout regrouper
            self.regrouper_tout()
        return self.dernier

    def _fusionner_proches(self):
        """Deux locuteurs du direct dont les voix moyennes sont devenues semblables = une seule personne."""
        import numpy as np
        while len(self.centres) > 1:
            c = np.stack([_normer(x) for x in self.centres])
            s = c @ c.T
            np.fill_diagonal(s, -np.inf)
            k = int(np.argmax(s))
            i, j = sorted((k // len(c), k % len(c)))
            if s[i, j] < self.seuil:
                return
            self.centres[i] = self.centres[i] + self.centres[j]
            self.poids[i] += self.poids[j]
            del self.centres[j], self.poids[j]
            self.fusions.append((j + 1, i + 1))
            self.dernier = appliquer_fusion([self.dernier], j + 1, i + 1)[0]
            self.etiquettes = appliquer_fusion(self.etiquettes, j + 1, i + 1)

    def regrouper_tout(self):
        """Regroupement complet des phrases déjà entendues ; les voix moyennes repartent de ce résultat."""
        self._regroupe = len(self.historique)
        e, f, d = zip(*self.historique)
        self.etiquettes = regrouper_complet(list(e), self.seuil, self.nombre, list(f), list(d))
        nb = max(self.etiquettes)
        self.centres = []
        self.poids = []
        for l in range(1, nb + 1):
            somme, poids = None, 0.0
            for (x, fi, du), et in zip(self.historique, self.etiquettes):
                if et == l and x is not None:
                    p = _poids(du, fi)
                    somme = x * p if somme is None else somme + x * p
                    poids += p
            self.centres.append(somme)
            self.poids.append(poids)
        self.dernier = self.etiquettes[-1]

    def amorcer(self, historique: list):
        """Reprise d'une transcription : les phrases déjà écrites (empreinte ou None, fiable, durée) servent de
        point de départ, pour que la suite retrouve les mêmes voix."""
        self.historique = [(None if e is None else _normer(e), bool(f), float(d)) for e, f, d in historique]
        if any(e is not None for e, _, _ in self.historique):
            self.regrouper_tout()
        else:
            self.historique, self.etiquettes = [], []


def rattacher(anciens: list[int], etiquettes: list[int], valides: list[bool] | None = None,
              durees: list[float] | None = None, depart: int = 0) -> list[int]:
    """Reprise : etiquettes = regroupement de toutes les phrases (les len(anciens) premières sont celles d'avant).
    Les anciennes phrases gardent leur locuteur (noms, fusions et corrections de l'utilisateur compris) ; une voix
    regroupée avec des phrases d'avant prend leur locuteur (le plus présent, en durée), une voix nouvelle prend
    le numéro suivant (N+1, N+2… par ordre d'apparition ; N = depart s'il est plus grand). Renvoie le locuteur
    de chaque phrase."""
    n0 = len(anciens)
    valides = list(valides) if valides is not None else [True] * len(etiquettes)
    durees = list(durees) if durees is not None else [1.0] * len(etiquettes)
    votes: dict[int, dict[int, float]] = {}
    total: dict[int, float] = {}
    for i, l in enumerate(etiquettes):
        d = max(0.1, float(durees[i]))
        total[l] = total.get(l, 0.0) + d
        if i < n0 and valides[i]:
            votes.setdefault(l, {})
            votes[l][anciens[i]] = votes[l].get(anciens[i], 0.0) + d
    table: dict[int, int] = {}
    for l, v in votes.items():
        ancien, d = max(v.items(), key=lambda x: x[1])
        # quelques phrases d'avant mal placées ne suffisent pas à rattacher une voix nouvelle
        if d >= min(DUREE_SOLIDE, 0.25 * total[l]):
            table[l] = ancien
    suivant = max([int(a) for a in anciens] + [int(depart)])
    res = list(anciens)
    for l in etiquettes[n0:]:
        if l not in table:
            suivant += 1
            table[l] = suivant
        res.append(table[l])
    return res


def regrouper_complet(empreintes: list, seuil: float = 0.5, nombre: int = 0, fiables: list | None = None,
                      durees: list | None = None) -> list[int]:
    """regrouper() qui accepte des phrases sans empreinte (None) : elles prennent le locuteur de la phrase
    précédente (ou suivante). Aucune phrase n'est laissée de côté ; numéros 1, 2, 3… sans trou."""
    n = len(empreintes)
    fiables = list(fiables) if fiables is not None else [True] * n
    durees = list(durees) if durees is not None else [1.0] * n
    valides = [i for i in range(n) if empreintes[i] is not None]
    if not valides:
        return [1] * n
    res = regrouper([empreintes[i] for i in valides], seuil, nombre, [fiables[i] for i in valides],
                    [durees[i] for i in valides])
    et = [0] * n
    for i, l in zip(valides, res):
        et[i] = l
    for i in range(n):              # sans empreinte : locuteur précédent
        if not et[i] and i:
            et[i] = et[i - 1]
    for i in range(n - 1, -1, -1):  # au tout début : locuteur suivant
        if not et[i]:
            et[i] = et[i + 1] if i + 1 < n else 1
    return renumeroter(et)


def regrouper(empreintes: list, seuil: float = 0.5, nombre: int = 0, fiables: list[bool] | None = None,
              durees: list[float] | None = None) -> list[int]:
    """Regroupement final de toutes les phrases. Renvoie 1, 2… par ordre d'apparition, sans trou.
    1. Fenêtres : phrases consécutives d'une même voix réunies (jusqu'à DUREE_FENETRE s) ; l'empreinte d'une
       fenêtre (moyenne pondérée par la durée) est bien plus sûre que celle d'une phrase de 2 s.
    2. Seules les fenêtres d'au moins DUREE_SOLIDE s créent des locuteurs : classification hiérarchique sur
       les voix moyennes (centroïdes pondérés par la durée, qui se précisent à chaque fusion, contrairement à
       la moyenne des similarités entre phrases). nombre > 0 : exactement ce nombre de locuteurs.
    3. Les fenêtres courtes rejoignent la voix la plus proche.
    4. Locuteurs marginaux (très peu de temps de parole, voix pas nettement différente) fusionnés.
    5. Lissage : un passage court entouré d'un même locuteur, sans voix nettement différente, lui revient."""
    import numpy as np
    n = len(empreintes)
    if n == 0:
        return []
    fiables = [bool(f) for f in fiables] if fiables is not None else [True] * n
    durees_l = [max(0.0, float(d)) for d in durees] if durees is not None else [1.0] * n
    duree = np.array(durees_l)
    X = np.stack([_normer(e) for e in empreintes]).astype(np.float64)
    w = np.array([_poids(d, f) for d, f in zip(durees_l, fiables)])
    parole = np.where(fiables, duree, 0.0)          # durée qui compte comme preuve d'une voix
    WX = w[:, None] * X

    def unites(M):
        nm = np.linalg.norm(M, axis=-1, keepdims=True)
        return M / np.maximum(nm, 1e-12)

    # 1. fenêtres de phrases consécutives d'une même voix
    fenetre = np.zeros(n, dtype=int)
    courant, duree_c = WX[0].copy(), duree[0]
    for i in range(1, n):
        if float(unites(courant) @ X[i]) >= seuil and duree_c + duree[i] <= DUREE_FENETRE:
            fenetre[i] = fenetre[i - 1]
            courant += WX[i]
            duree_c += duree[i]
        else:
            fenetre[i] = fenetre[i - 1] + 1
            courant, duree_c = WX[i].copy(), duree[i]
    nf = int(fenetre[-1]) + 1
    V = np.zeros((nf, X.shape[1]))
    np.add.at(V, fenetre, WX)
    duree_f = np.bincount(fenetre, parole, minlength=nf)

    # 2. classification hiérarchique des fenêtres assez longues
    solides = np.where(duree_f >= DUREE_SOLIDE)[0]
    if duree_f[solides].sum() < 0.5 * duree_f.sum() or len(solides) < max(1, nombre):
        solides = np.where(duree_f > 0)[0]
        if len(solides) < max(1, nombre):
            solides = np.arange(nf)
    k = len(solides)
    C = V[solides].copy()                   # somme pondérée des empreintes de chaque groupe
    U = unites(C)
    groupe = np.arange(k)                   # groupe de chaque fenêtre solide
    actif = np.ones(k, dtype=bool)
    S = (U @ U.T).astype(np.float32)
    np.fill_diagonal(S, -np.inf)
    meilleur = S.argmax(1) if k > 1 else np.zeros(k, dtype=int)
    valeur = S[np.arange(k), meilleur] if k > 1 else np.full(k, -np.inf)
    limite = _assoupli(seuil, 1.1)
    nb = k
    while nb > 1:
        ia = int(np.argmax(np.where(actif, valeur, -np.inf)))
        if nombre > 0:
            if nb <= nombre:
                break
        elif valeur[ia] < limite:
            break
        a, b = sorted((ia, int(meilleur[ia])))
        C[a] += C[b]
        U[a] = unites(C[a])
        groupe[groupe == b] = a
        actif[b] = False
        nb -= 1
        S[b, :] = S[:, b] = -np.inf
        ligne = (U @ U[a]).astype(np.float32)
        ligne[~actif] = -np.inf
        ligne[a] = -np.inf
        S[a, :] = S[:, a] = ligne
        meilleur[a] = int(ligne.argmax())
        valeur[a] = ligne[meilleur[a]]
        for j in np.where(actif & ((meilleur == a) | (meilleur == b)))[0]:
            if j != a:
                meilleur[j] = int(S[j].argmax())
                valeur[j] = S[j, meilleur[j]]
        mieux = actif & (ligne > valeur)
        meilleur[mieux], valeur[mieux] = a, ligne[mieux]
    groupes = np.where(actif)[0]

    # 3. toutes les fenêtres : groupe trouvé, ou voix la plus proche pour les fenêtres courtes
    etiquette_f = np.full(nf, -1)
    etiquette_f[solides] = groupe
    reste = np.where(etiquette_f < 0)[0]
    if len(reste):
        proches = (unites(V[reste]) @ unites(C[groupes]).T).argmax(1)
        etiquette_f[reste] = groupes[proches]
    et = etiquette_f[fenetre]

    def voix(et):
        G = np.zeros((int(et.max()) + 1, X.shape[1]))
        np.add.at(G, et, WX)
        return unites(G)

    # 4. locuteurs marginaux : rattachés à la voix la plus proche si elle n'est pas nettement différente
    if nombre <= 0:
        total = float(parole.sum()) or float(duree.sum())
        petit = min(15.0, 0.03 * total)                 # peu de temps de parole : fusionné si la voix est proche
        infime = min(2 * DUREE_SOLIDE, 0.01 * total)    # quasi rien (une phrase sur une longue réunion) : fusionné
        garde: set = set()
        while True:
            presents = np.unique(et)
            temps = np.bincount(et, parole)
            candidats = [g for g in presents if temps[g] < petit and g not in garde]
            if len(presents) < 2 or not candidats:
                break
            g = min(candidats, key=lambda h: temps[h])
            G = voix(et)
            autres = [h for h in presents if h != g]
            sims = G[autres] @ G[g]
            h = autres[int(sims.argmax())]
            if temps[g] < infime or float(sims.max()) >= _assoupli(seuil, 1.6):
                et[et == g] = h
            else:
                garde.add(g)

    # 5. lissage temporel
    G = voix(et)
    cumul = np.vstack([np.zeros(X.shape[1]), np.cumsum(WX, 0)])
    marge = 0.5 * (1.0 - seuil)
    debuts = [0] + [i for i in range(1, n) if et[i] != et[i - 1]]
    passages = [[d, f, int(et[d])] for d, f in zip(debuts, debuts[1:] + [n])]
    for p in range(1, len(passages) - 1):
        d, f, l = passages[p]
        voisin = passages[p - 1][2]
        if voisin != passages[p + 1][2] or voisin == l or duree[d:f].sum() >= DUREE_SOLIDE:
            continue
        if nombre > 0 and int((et == l).sum()) == f - d:
            continue        # nombre imposé : on ne fait pas disparaître un locuteur
        v = unites(cumul[f] - cumul[d])
        if float(G[voisin] @ v) >= float(G[l] @ v) - marge:
            et[d:f] = voisin
            passages[p][2] = voisin
    return renumeroter([int(x) for x in et])


# ====================================================================================================
# Empreintes vocales
# ====================================================================================================
class EmpreinteSherpa:
    """Empreinte d'un locuteur par un réseau neuronal (WeSpeaker CAM++, ONNX, exécuté par sherpa-onnx)."""
    nom = "sherpa-onnx (CAM++)"
    seuil = 0.5             # similarité cosinus au-dessus de laquelle deux phrases sont de la même voix

    def __init__(self, chemin: Path):
        import sherpa_onnx
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(chemin), num_threads=2, debug=False,
                                                          provider="cpu")
        if not cfg.validate():
            raise RuntimeError("modèle de reconnaissance du locuteur invalide")
        self._ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)

    def __call__(self, audio):
        flux = self._ext.create_stream()
        flux.accept_waveform(SR, audio)
        flux.input_finished()
        import numpy as np
        return np.array(self._ext.compute(flux), dtype=np.float32)


class EmpreinteSimple:
    """Secours sans réseau neuronal : statistiques du spectre (MFCC moyens et écarts-types, hauteur de voix).
    Distingue bien des voix très différentes (homme / femme), moins bien des voix proches."""
    nom = "spectrale simple"
    seuil = 0.95

    def __init__(self):
        import numpy as np
        self.n_fft, self.pas, n_mel = 512, 160, 40
        f = np.linspace(0, SR / 2, self.n_fft // 2 + 1)
        mel = lambda h: 2595 * np.log10(1 + h / 700)
        bornes = 700 * (10 ** (np.linspace(mel(60), mel(7600), n_mel + 2) / 2595) - 1)
        self.banc = np.zeros((n_mel, len(f)), dtype=np.float32)
        for i in range(n_mel):
            g, c, d = bornes[i:i + 3]
            self.banc[i] = np.clip(np.minimum((f - g) / (c - g), (d - f) / (d - c)), 0, None)
        k = np.arange(n_mel)
        self.dct = np.cos(np.pi / n_mel * (k[None, :] + 0.5) * np.arange(1, 21)[:, None]).astype(np.float32)
        self.fenetre = np.hanning(self.n_fft).astype(np.float32)

    def __call__(self, audio):
        import numpy as np
        x = np.asarray(audio, dtype=np.float32)
        if len(x) < self.n_fft:
            x = np.pad(x, (0, self.n_fft - len(x)))
        x = np.append(x[0], x[1:] - 0.97 * x[:-1])
        n = 1 + (len(x) - self.n_fft) // self.pas
        trames = np.lib.stride_tricks.as_strided(x, (n, self.n_fft), (x.strides[0] * self.pas, x.strides[0]))
        energie = (trames ** 2).mean(1)
        garde = energie > max(energie.max() * 0.01, 1e-8)      # trames de voix seulement
        if garde.sum() < 2:
            garde[:] = True
        spectre = np.abs(np.fft.rfft(trames[garde] * self.fenetre)) ** 2
        brut = np.log(spectre @ self.banc.T + 1e-8)       # énergie par bande (échelle de Mel)
        mfcc = brut @ self.dct.T
        # timbre moyen (indépendant du volume), variabilité par bande et par coefficient
        v = np.concatenate([brut.mean(0) - brut.mean(), brut.std(0), mfcc.std(0)])
        return (v - v.mean()).astype(np.float32)


def telecharger_modele_locuteurs() -> Path:
    """Modèle de reconnaissance du locuteur : téléchargé une fois (~28 Mo), puis entièrement hors ligne."""
    chemin = DOSSIER_MODELES / MODELE_LOCUTEURS
    if chemin.exists() and chemin.stat().st_size > 1_000_000:
        return chemin
    import requests
    DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".part")
    with requests.get(URL_MODELE_LOCUTEURS, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for morceau in r.iter_content(1 << 16):
                f.write(morceau)
    tmp.replace(chemin)
    return chemin


def charger_empreinte():
    """Le meilleur extracteur disponible : sherpa-onnx (si installé et modèle téléchargeable), sinon le simple."""
    try:
        return EmpreinteSherpa(telecharger_modele_locuteurs())
    except Exception as e:
        print(f"  (transcription : reconnaissance neuronale des voix indisponible, méthode simple : {e})")
        return EmpreinteSimple()


# ====================================================================================================
# Découpage du flux en blocs (aux pauses)
# ====================================================================================================
class Decoupeur:
    """Accumule le son et rend des blocs (début en s, audio) coupés à une pause, pour que Whisper ait des
    phrases entières et qu'un changement de locuteur tombe le plus souvent entre deux blocs."""

    GARDE = 1.0                 # s de silence gardées avant une reprise de parole (début de phrase faible)

    def __init__(self, duree_min=3.0, duree_max=20.0, pause=0.5):
        self.duree_min, self.duree_max, self.pause = duree_min, duree_max, pause
        self.morceaux: list = []
        self.taille = 0
        self.debut = 0.0            # position (s) du début du bloc en cours dans l'enregistrement
        self.silence = 0.0          # s de calme à la fin du bloc en cours (pour couper aux pauses)
        self.voix = False           # le bloc contient autre chose que du silence : il ira à Whisper
        self.bruit = 0.001          # plancher de bruit ambiant (suit les creux, remonte lentement)
        self.parole = 0.0           # niveau moyen de la voix entendue (moyenne glissante)
        self.ecarte = 0.0           # s de silence non envoyées à Whisper (diagnostic)

    def seuil(self):
        """Seuil des pauses (où couper un bloc) : bas exprès, une voix lointaine arrive faible. Jamais plus de la
        moitié du niveau de la voix : sinon une voix très faible serait « en pause » en permanence et coupée
        toutes les 3 s au milieu des mots."""
        s = max(self.bruit * 2.5, 0.003)
        if self.parole:
            s = min(s, self.parole * 0.5)
        return max(s, self.seuil_voix())

    def seuil_voix(self):
        """En dessous : silence, jamais envoyé à Whisper. Juste au-dessus du plancher de bruit : une voix
        faible (fond de salle, visio à bas volume) part toujours à Whisper, dont le VAD trie ensuite."""
        return max(self.bruit * 1.6, 0.0004)

    def ajouter(self, x) -> tuple[float, object] | None:
        import numpy as np
        if not len(x):
            return None
        rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float32))))
        # plancher de bruit : descend vite dans les creux, monte lentement (+3 %/s). Avant, il suivait la
        # moyenne des morceaux « calmes » : une voix faible le faisait grimper, le seuil montait avec, et toute
        # la parole faible était prise pour du silence et jetée avant Whisper.
        self.bruit = 0.5 * (self.bruit + rms) if rms < self.bruit else min(rms, self.bruit * 1.003)
        if rms < self.seuil():
            self.silence += len(x) / SR
        else:
            self.silence = 0.0
        if rms >= self.seuil_voix():
            self.voix = True
            self.parole = rms if not self.parole else 0.95 * self.parole + 0.05 * rms
        self.morceaux.append(x)
        self.taille += len(x)
        duree = self.taille / SR
        if not self.voix and duree > self.GARDE + self.pause:
            # que du silence : on avance sans rien transcrire (on garde la fin, au cas où une phrase commence)
            garde = int(self.GARDE * SR)
            tout = np.concatenate(self.morceaux)
            self.debut += (len(tout) - garde) / SR
            self.ecarte += (len(tout) - garde) / SR
            self.morceaux, self.taille, self.silence = [tout[-garde:]], garde, min(self.silence, self.GARDE)
            return None
        if duree >= self.duree_min and self.silence >= self.pause:
            return self.vider()
        if duree >= self.duree_max:
            return self._couper_au_creux()
        return None

    def _couper_au_creux(self):
        """Bloc trop long sans pause nette : coupé au moment le plus calme des 3 dernières secondes (entre deux
        mots), pas au milieu d'un mot ; la suite commence le bloc suivant."""
        import numpy as np
        tout = np.concatenate(self.morceaux)
        trame = SR // 20
        zone = tout[max(0, len(tout) - 3 * SR):]
        n = len(zone) // trame
        coupe = len(tout)
        if n >= 4:
            rms = np.sqrt(np.mean(np.square(zone[:n * trame].reshape(n, trame), dtype=np.float32), axis=1))
            k = int(np.argmin(rms))
            if rms[k] < 0.5 * float(np.median(rms)):     # vrai creux (sinon : coupe à la fin, comme avant)
                coupe = len(tout) - len(zone) + (k + 1) * trame
        debut = self.debut
        bloc, reste = tout[:coupe], tout[coupe:]
        self.debut += len(bloc) / SR
        self.morceaux, self.taille = ([reste], len(reste)) if len(reste) else ([], 0)
        self.silence, self.voix = 0.0, bool(len(reste))
        return debut, bloc

    def vider(self):
        import numpy as np
        if not self.morceaux:
            return None
        bloc, debut, voix = np.concatenate(self.morceaux), self.debut, self.voix
        self.debut += len(bloc) / SR
        self.morceaux, self.taille, self.silence, self.voix = [], 0, 0.0, False
        if not voix:
            self.ecarte += len(bloc) / SR
        return (debut, bloc) if voix else None


# ====================================================================================================
# Sources audio
# ====================================================================================================
def reechantillonner(x, sr: float):
    import numpy as np
    x = np.asarray(x, dtype=np.float32)
    if int(sr) == SR or not len(x):
        return x
    n = int(round(len(x) * SR / sr))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class Tampon:
    """File de son d'une source, alimentée par son fil de capture (sûre entre fils)."""

    def __init__(self, nom: str):
        self.nom = nom
        self.morceaux: list = []
        self.taille = 0
        self.verrou = threading.Lock()
        self.erreur = ""
        self.recu = 0               # échantillons reçus (diagnostic : la source envoie-t-elle du son ?)
        self.perdu = 0.0            # s jetées parce que la source avait trop d'avance (diagnostic)

    RETARD_MAX = 15.0           # s d'avance tolérées (horloge de la carte son un peu plus rapide que le Mac)

    def pousser(self, x, sr: float = SR):
        x = reechantillonner(x, sr)
        with self.verrou:
            self.morceaux.append(x)
            self.taille += len(x)
            self.recu += len(x)
            if self.taille > SR * self.RETARD_MAX:
                # très en retard : on jette le plus ancien (gardé 3 s). Avant, la limite était de 3 s et on ne
                # gardait que la dernière seconde : un simple à-coup de la source faisait perdre 2 s de parole.
                import numpy as np
                tout = np.concatenate(self.morceaux)
                self.perdu += (len(tout) - 3 * SR) / SR
                tout = tout[-3 * SR:]
                self.morceaux, self.taille = [tout], len(tout)

    def prendre(self, n: int):
        import numpy as np
        with self.verrou:
            if not self.morceaux:
                return np.zeros(n, dtype=np.float32)
            tout = np.concatenate(self.morceaux)
            pris, reste = tout[:n], tout[n:]
            self.morceaux, self.taille = ([reste] if len(reste) else []), len(reste)
        return np.pad(pris, (0, n - len(pris))) if len(pris) < n else pris


class Mixeur:
    """Mélange les sources et les cale sur l'horloge : une source muette (WASAPI n'envoie rien quand le PC est
    silencieux) devient du silence, et les horodatages restent ceux de la réunion."""

    def __init__(self, tampons: list[Tampon]):
        self.tampons = tampons
        self.t0 = None
        self.emis = 0

    def lire(self, maintenant: float | None = None):
        import numpy as np
        maintenant = time.monotonic() if maintenant is None else maintenant
        if self.t0 is None:
            self.t0 = maintenant
        n = round((maintenant - self.t0) * SR) - self.emis
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        self.emis += n
        x = sum(t.prendre(n) for t in self.tampons)
        return np.clip(x, -1.0, 1.0).astype(np.float32)


class CaptureMicro:
    def __init__(self, tampon: Tampon):
        self.tampon, self._flux = tampon, None

    def demarrer(self):
        import sounddevice as sd

        def rappel(donnees, *_):
            self.tampon.pousser(donnees[:, 0].copy())
        self._flux = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=1600, callback=rappel)
        self._flux.start()

    def arreter(self):
        if self._flux is not None:
            try:
                self._flux.stop()
                self._flux.close()
            finally:
                self._flux = None


class CaptureSystemeMac:
    """Son de tout le Mac par ScreenCaptureKit (macOS 13+, autorisation « Enregistrement de l'écran »).
    Aucun pilote audio virtuel à installer ; le son de Wesley lui-même est exclu."""

    def __init__(self, tampon: Tampon):
        self.tampon, self._flux, self._sortie = tampon, None, None

    def demarrer(self):
        import objc
        import CoreMedia
        import ScreenCaptureKit as SCK
        from Foundation import NSObject
        import numpy as np
        tampon = self.tampon

        global _SortieSCK
        if _SortieSCK is None:
            class SortieAudioWesley(NSObject, protocols=[objc.protocolNamed("SCStreamOutput")]):
                def stream_didOutputSampleBuffer_ofType_(self, flux, tampon_cm, genre):
                    if genre != SCK.SCStreamOutputTypeAudio:
                        return
                    try:
                        bloc = CoreMedia.CMSampleBufferGetDataBuffer(tampon_cm)
                        n = CoreMedia.CMBlockBufferGetDataLength(bloc)
                        _, octets = CoreMedia.CMBlockBufferCopyDataBytes(bloc, 0, n, None)
                        asbd = CoreMedia.CMAudioFormatDescriptionGetStreamBasicDescription(
                            CoreMedia.CMSampleBufferGetFormatDescription(tampon_cm))
                        sr, canaux = float(asbd[0]), max(1, int(asbd[6]))
                        x = np.frombuffer(bytes(octets), dtype=np.float32)
                        if canaux > 1:     # non entrelacé : [gauche…][droite…]
                            x = x[: len(x) // canaux * canaux].reshape(canaux, -1).mean(0)
                        self.tampon_wesley.pousser(x, sr)
                    except Exception as e:
                        self.tampon_wesley.erreur = str(e)
            _SortieSCK = SortieAudioWesley

        attente, res = threading.Event(), {}

        def contenu_recu(contenu, erreur):
            res.update(contenu=contenu, erreur=erreur)
            attente.set()
        SCK.SCShareableContent.getShareableContentWithCompletionHandler_(contenu_recu)
        if not attente.wait(15) or res.get("erreur") or not res.get("contenu"):
            raise RuntimeError("Wesley n'a pas accès au son du Mac : autorise-le dans Réglages Système › "
                               "Confidentialité et sécurité › Enregistrement de l'écran (et de l'audio), "
                               f"puis relance Wesley. ({res.get('erreur') or 'pas de réponse'})")
        ecrans = res["contenu"].displays()
        if not ecrans:
            raise RuntimeError("aucun écran trouvé pour la capture du son")
        filtre = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(ecrans[0], [])
        cfg = SCK.SCStreamConfiguration.alloc().init()
        cfg.setCapturesAudio_(True)
        cfg.setSampleRate_(48000)
        cfg.setChannelCount_(1)
        cfg.setExcludesCurrentProcessAudio_(True)
        cfg.setWidth_(2)                # l'image ne sert pas : la plus petite possible, 1 image/s
        cfg.setHeight_(2)
        cfg.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))
        self._sortie = _SortieSCK.alloc().init()
        self._sortie.tampon_wesley = tampon
        self._flux = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(filtre, cfg, None)
        ok, err = self._flux.addStreamOutput_type_sampleHandlerQueue_error_(self._sortie, SCK.SCStreamOutputTypeAudio, None, None)
        if not ok:
            raise RuntimeError(f"capture du son du Mac impossible : {err}")
        demarre, erreurs = threading.Event(), []

        def lance(erreur):
            if erreur is not None:
                erreurs.append(str(erreur))
            demarre.set()
        self._flux.startCaptureWithCompletionHandler_(lance)
        if not demarre.wait(15) or erreurs:
            raise RuntimeError("capture du son du Mac impossible (autorise « Enregistrement de l'écran » pour "
                               f"Wesley dans Réglages Système) : {erreurs[0] if erreurs else 'pas de réponse'}")

    def arreter(self):
        if self._flux is not None:
            fini = threading.Event()

            def arrete(_erreur):
                fini.set()
            try:
                self._flux.stopCaptureWithCompletionHandler_(arrete)
                fini.wait(5)
            finally:
                self._flux = None


_SortieSCK = None     # classe Objective-C créée une seule fois (on ne peut pas la redéclarer)


class CapturePeripherique:
    """Périphérique d'entrée qui reçoit le son de l'ordinateur (BlackHole, Loopback, Soundflower, VB-Cable,
    « Mixage stéréo »…) : secours si la capture native est impossible."""
    MOTS = ("blackhole", "loopback", "soundflower", "cable output", "vb-audio", "mixage stéréo", "stereo mix",
            "what u hear", "monitor of")

    def __init__(self, tampon: Tampon, index: int):
        self.tampon, self.index, self._flux = tampon, index, None

    @classmethod
    def trouver(cls):
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0 and any(m in d["name"].lower() for m in cls.MOTS):
                return i, d["name"]
        return None

    def demarrer(self):
        import sounddevice as sd
        info = sd.query_devices(self.index)
        sr, canaux = float(info["default_samplerate"]), min(2, int(info["max_input_channels"]))

        def rappel(donnees, *_):
            self.tampon.pousser(donnees.mean(1), sr)
        self._flux = sd.InputStream(device=self.index, samplerate=sr, channels=canaux, dtype="float32",
                                    blocksize=int(sr / 10), callback=rappel)
        self._flux.start()

    def arreter(self):
        if self._flux is not None:
            self._flux.stop()
            self._flux.close()
            self._flux = None


class CaptureSystemeWindows:
    """Son de tout le PC par WASAPI loopback (PyAudioWPatch) : ce que tu entends dans tes haut-parleurs."""

    def __init__(self, tampon: Tampon):
        self.tampon, self._pa, self._flux = tampon, None, None

    def demarrer(self):
        import numpy as np
        import pyaudiowpatch as pyaudio
        self._pa = pa = pyaudio.PyAudio()
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        hp = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if not hp.get("isLoopbackDevice"):
            for d in pa.get_loopback_device_info_generator():
                if hp["name"] in d["name"]:
                    hp = d
                    break
            else:
                raise RuntimeError("pas de sortie audio « loopback » trouvée pour les haut-parleurs par défaut")
        sr, canaux = float(hp["defaultSampleRate"]), max(1, int(hp["maxInputChannels"]))
        tampon = self.tampon

        def rappel(donnees, nb, _info, _etat):
            x = np.frombuffer(donnees, dtype=np.float32)
            if canaux > 1:
                x = x[: len(x) // canaux * canaux].reshape(-1, canaux).mean(1)
            tampon.pousser(x, sr)
            return (None, pyaudio.paContinue)
        self._flux = pa.open(format=pyaudio.paFloat32, channels=canaux, rate=int(sr), input=True,
                             input_device_index=hp["index"], frames_per_buffer=int(sr / 10), stream_callback=rappel)
        self._flux.start_stream()

    def arreter(self):
        try:
            if self._flux is not None:
                self._flux.stop_stream()
                self._flux.close()
        finally:
            self._flux = None
            if self._pa is not None:
                self._pa.terminate()
                self._pa = None


def capture_systeme(tampon: Tampon):
    """Capture native du son de l'ordinateur ; à défaut, un périphérique « loopback » installé."""
    from .plateforme import MAC, WIN
    erreurs = []
    if MAC or WIN:
        try:
            c = CaptureSystemeMac(tampon) if MAC else CaptureSystemeWindows(tampon)
            c.demarrer()
            return c
        except Exception as e:
            erreurs.append(str(e))
    try:
        trouve = CapturePeripherique.trouver()
    except Exception:
        trouve = None
    if trouve:
        c = CapturePeripherique(tampon, trouve[0])
        c.demarrer()
        return c
    raise RuntimeError(erreurs[0] if erreurs else
                       "capture du son de l'ordinateur indisponible : installe un périphérique « loopback » (BlackHole, VB-Cable)")


def lire_fichier_audio(chemin):
    """Fichier audio ou vidéo -> 16 kHz mono float32. WAV par la bibliothèque standard, le reste (mp3, m4a,
    ogg, mp4…) par PyAV, déjà installé avec faster-whisper."""
    import wave
    import numpy as np
    chemin = str(chemin)
    try:
        with wave.open(chemin) as w:
            if w.getsampwidth() in (2, 4):
                brut = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16 if w.getsampwidth() == 2 else np.int32)
                x = brut.reshape(-1, w.getnchannels()).mean(1) / (32768.0 if w.getsampwidth() == 2 else 2 ** 31)
                return reechantillonner(x.astype(np.float32), w.getframerate())
    except (wave.Error, EOFError, OSError):
        pass
    import av
    morceaux = []
    with av.open(chemin) as conteneur:
        if not conteneur.streams.audio:
            raise ValueError("Ce fichier ne contient pas de son.")
        convertisseur = av.AudioResampler(format="flt", layout="mono", rate=SR)
        for trame in conteneur.decode(audio=0):
            for t in convertisseur.resample(trame):
                morceaux.append(t.to_ndarray().ravel())
        for t in convertisseur.resample(None):
            morceaux.append(t.to_ndarray().ravel())
    if not morceaux:
        raise ValueError("Fichier audio vide ou illisible.")
    return np.concatenate(morceaux).astype(np.float32)


# ====================================================================================================
# Session de transcription
# ====================================================================================================
_verrou = threading.RLock()
_en_cours: "Transcription | None" = None
_whisper_cache: dict = {}
_empreinte_cache: list = []


def dossier_export() -> Path:
    d = CONFIG.get("dossier_transcriptions") or str(Path.home() / "Documents" / "Wesley" / "Transcriptions")
    p = Path(d).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _chemin(tid: str) -> Path:
    if not re.fullmatch(r"[\w-]{4,40}", tid or ""):
        raise ValueError("Identifiant de transcription invalide.")
    return DOSSIER_DONNEES / f"{tid}.json"


def lire(tid: str) -> dict | None:
    if _en_cours is not None and _en_cours.session["id"] == tid:
        return _en_cours.instantane()
    try:
        return json.loads(_chemin(tid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sauver(session: dict, fichier_lisible: bool = True):
    DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    tmp = _chemin(session["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_chemin(session["id"]))
    if fichier_lisible:
        try:
            f = Path(session.get("fichier") or "")
            if not session.get("fichier"):
                debut = datetime.fromtimestamp(session["debut"]).strftime("%Y-%m-%d %Hh%M")
                f = dossier_export() / f"{debut} - {nom_de_fichier(session.get('titre', ''))}.md"
                session["fichier"] = str(f)
                tmp.write_text(json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(_chemin(session["id"]))
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(exporter(session, "md"), encoding="utf-8")
        except OSError as e:
            print(f"  (transcription : fichier Markdown non écrit : {e})")


def resume(s: dict) -> dict:
    return {k: s.get(k) for k in ("id", "titre", "debut", "duree", "source", "avec_micro", "etat", "langue",
                                  "modele", "fichier", "erreur")} | {
        "nb_locuteurs": len(locuteurs(s)), "nb_phrases": len(s.get("segments", []))}


def lister() -> list[dict]:
    res = []
    if DOSSIER_DONNEES.exists():
        for f in DOSSIER_DONNEES.glob("*.json"):
            try:
                res.append(resume(json.loads(f.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                pass
    if _en_cours is not None:
        res = [r for r in res if r["id"] != _en_cours.session["id"]] + [resume(_en_cours.instantane())]
    return sorted(res, key=lambda r: r.get("debut") or 0, reverse=True)


def modifier(tid: str, action: str, d: dict) -> dict:
    """Actions de l'utilisateur sur une transcription terminée : renommer, fusionner, attribuer, texte, titre."""
    with _verrou:
        if _en_cours is not None and _en_cours.session["id"] == tid and _en_cours.session["etat"] != "terminee":
            raise ValueError("Attends la fin de la transcription pour la modifier.")
        s = lire(tid)
        if s is None:
            raise ValueError("Transcription introuvable.")
        if action == "noms":
            renommer(s, d.get("noms") or {})
        elif action == "fusionner":
            fusionner(s, int(d["source"]), int(d["cible"]))
        elif action == "locuteur":
            changer_locuteur(s, int(d["index"]), int(d.get("locuteur", 0)))
        elif action == "texte":
            corriger_texte(s, int(d["index"]), d.get("texte", ""))
        elif action == "regrouper":
            regrouper_session(s, int(d.get("nombre") or 0))
        elif action == "titre":
            s["titre"] = str(d.get("titre", "")).strip()[:120] or s["titre"]
        else:
            raise ValueError("Action inconnue.")
        sauver(s)
        _signaler(s["id"])
        return s


def _chemin_empreintes(tid: str) -> Path:
    return _chemin(tid).with_suffix(".npz")


def sauver_empreintes(tid: str, empreintes: list, fiables: list, durees: list):
    """Empreintes vocales de chaque phrase (pas le son) : servent à regrouper à nouveau les locuteurs.
    Une phrase sans empreinte (calcul impossible) est gardée, marquée non valide."""
    import numpy as np
    exemple = next((e for e in empreintes if e is not None), None)
    if exemple is None:
        return
    vide = np.zeros_like(_normer(exemple))
    DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    with open(_chemin_empreintes(tid), "wb") as f:
        np.savez_compressed(f, empreintes=np.stack([vide if e is None else _normer(e) for e in empreintes]).astype(np.float32),
                            fiables=np.array(fiables, dtype=bool), durees=np.array(durees, dtype=np.float32),
                            valides=np.array([e is not None for e in empreintes], dtype=bool))


def regroupable(tid: str) -> bool:
    """Les empreintes vocales sont gardées : on peut refaire la répartition des locuteurs."""
    try:
        return _chemin_empreintes(tid).exists()
    except ValueError:
        return False


def au_demarrage():
    """Wesley a été fermé pendant une transcription : ce qui a été transcrit est gardé, elle est « interrompue »."""
    import shutil
    shutil.rmtree(DOSSIER_DONNEES / "imports", ignore_errors=True)    # fichiers importés non transcrits
    if not DOSSIER_DONNEES.exists():
        return
    for f in DOSSIER_DONNEES.glob("*.json"):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            if s.get("etat") in ("preparation", "en_cours", "finalisation"):
                s["etat"] = "interrompue"
                s["duree"] = round(max([float(s.get("duree") or 0)] + [float(x["fin"]) for x in s.get("segments", [])]), 1)
                s["segments"] = [dict(x, locuteur=l) for x, l in
                                 zip(s.get("segments", []), renumeroter([x["locuteur"] for x in s.get("segments", [])]))]
                sauver(s)
        except (OSError, ValueError, KeyError):
            pass


def regrouper_session(session: dict, nombre: int = 0) -> dict:
    """Refait la répartition des locuteurs (nombre > 0 : exactement ce nombre de personnes ; 0 : automatique).
    Les noms donnés sont effacés : les numéros ne désignent plus forcément les mêmes personnes."""
    import numpy as np
    try:
        with np.load(_chemin_empreintes(session["id"])) as z:
            emb, fiables, durees = list(z["empreintes"]), list(z["fiables"]), list(z["durees"])
            valides = list(z["valides"]) if "valides" in z.files else [True] * len(emb)
            emb = [e if v else None for e, v in zip(emb, valides)]
    except (OSError, KeyError, ValueError):
        raise ValueError("Les empreintes vocales de cette transcription ne sont pas disponibles.")
    segs = session.get("segments", [])
    if len(emb) != len(segs):
        raise ValueError("Les empreintes vocales ne correspondent plus aux phrases de cette transcription.")
    etiquettes = regrouper_complet(emb, float(session.get("seuil") or 0.5), max(0, nombre), fiables, durees)
    for s, l in zip(segs, etiquettes):
        s["locuteur"] = l
    session["noms"] = {}
    session["nb_locuteurs"] = max(0, nombre)
    return session


def supprimer(tid: str, avec_fichier: bool = False) -> bool:
    with _verrou:
        if _en_cours is not None and _en_cours.session["id"] == tid:
            raise ValueError("Arrête d'abord la transcription en cours.")
        s = lire(tid)
        if s is None:
            return False
        if avec_fichier and s.get("fichier"):
            Path(s["fichier"]).unlink(missing_ok=True)
        _chemin(tid).unlink(missing_ok=True)
        _chemin_empreintes(tid).unlink(missing_ok=True)
        _signaler(tid)
        return True


def enregistrer_sous(tid: str, format: str = "md") -> Path:
    """Exporte (noms des locuteurs compris) dans le dossier des transcriptions ; renvoie le chemin."""
    s = lire(tid)
    if s is None:
        raise ValueError("Transcription introuvable.")
    format = "txt" if format == "txt" else "md"
    debut = datetime.fromtimestamp(s["debut"]).strftime("%Y-%m-%d %Hh%M")
    f = dossier_export() / f"{debut} - {nom_de_fichier(s.get('titre', ''))}.{format}"
    f.write_text(exporter(s, format), encoding="utf-8")
    return f


def en_cours() -> "Transcription | None":
    return _en_cours


def _signaler(tid: str):
    for e in list(ecouteurs):
        try:
            e(tid)
        except Exception:
            pass


def _whisper(nom: str):
    if nom not in _whisper_cache:
        from .modeles import charger_whisper
        _whisper_cache.clear()          # un seul modèle de transcription en mémoire à la fois
        import os
        _whisper_cache[nom] = charger_whisper(nom, cpu_threads=max(2, min(8, (os.cpu_count() or 4) - 1)))
    return _whisper_cache[nom]


def _empreinte():
    if not _empreinte_cache:
        _empreinte_cache.append(charger_empreinte())
    return _empreinte_cache[0]


class Transcription:
    """Une transcription en cours : capture, découpage, Whisper et diarisation dans un fil de fond."""

    def __init__(self, source="micro", avec_micro=False, langue="fr", modele="", titre="", nb_locuteurs=0,
                 fichier_audio="", transcrire=None, empreinte=None, captures=None, vocabulaire=""):
        """source : « micro », « systeme » ou « fichier » (fichier_audio : enregistrement à transcrire).
        modele : « auto » (ou vide) = le plus précis que la machine fait tourner ; vocabulaire : mots techniques
        à bien orthographier (séparés par des virgules).
        transcrire(audio, langue, consigne) -> [(debut, fin, texte)], empreinte(audio) -> vecteur et
        captures [(objet avec demarrer/arreter, Tampon)] : remplaçables pour les tests (sans micro ni modèle)."""
        maintenant = time.time()
        source = source if source in ("micro", "systeme", "fichier") else "micro"
        self.session = {
            "id": datetime.fromtimestamp(maintenant).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
            "titre": titre.strip()[:120] or ("Réunion du " + datetime.fromtimestamp(maintenant).strftime("%d/%m/%Y à %H:%M")),
            "debut": maintenant, "duree": 0.0, "source": source,
            "avec_micro": bool(avec_micro) and source == "systeme", "langue": langue or "",
            "modele": modele or modele_par_defaut(),
            "vocabulaire": re.sub(r"\s+", " ", str(vocabulaire or CONFIG.get("transcription_vocabulaire") or ""))[:500],
            "nb_locuteurs": max(0, int(nb_locuteurs or 0)), "etat": "preparation", "erreur": "",
            "segments": [], "noms": {}, "fichier": "", "empreinte": "",
        }
        self._transcrire = transcrire
        self._empreinte_fn = empreinte
        self._captures = captures
        self._continuer = False
        self._fil: threading.Thread | None = None
        self._empreintes: list = []         # une par phrase (pour le regroupement final)
        self.niveau = 0.0                   # niveau sonore (VU-mètre de l'interface)
        self.retard = 0.0                   # s d'audio en attente de transcription
        self.diariseur: Diariseur | None = None
        self._blocs: queue.Queue = queue.Queue()
        if self.session["modele"] not in MODELES_WHISPER or self.session["modele"] == "auto":
            self.session["modele"] = modele_auto(source)
        self._fichier_audio = fichier_audio
        self.position = 0.0                 # s depuis le début de la transcription (horodatage du son lu)
        self._anciens: list[int] = []       # reprise : locuteur des phrases déjà écrites (gardé tel quel)
        self._amorce: list = []             # reprise : empreintes des phrases déjà écrites (diariseur amorcé)

    @classmethod
    def reprise(cls, session: dict, source: str = "", avec_micro=None, fichier_audio: str = "", **tests):
        """Reprend une transcription (terminée, interrompue ou en erreur) : la suite s'ajoute à la même
        transcription, horodatée après la fin, avec les mêmes locuteurs (numéros, noms, empreintes vocales)."""
        import numpy as np
        source = source or (session.get("source") if session.get("source") in ("micro", "systeme") else "micro")
        if source == "fichier" and not fichier_audio:
            source = "micro"
        t = cls(source, session.get("avec_micro") if avec_micro is None else avec_micro, session.get("langue", "fr"),
                session.get("modele", ""), session.get("titre", ""), session.get("nb_locuteurs", 0), fichier_audio,
                vocabulaire=session.get("vocabulaire", ""), **tests)
        s = t.session | json.loads(json.dumps(session))     # champs absents des anciennes versions : par défaut
        s["id"] = session["id"]
        segs = s.setdefault("segments", [])
        reprise_a = round(max([float(s.get("duree") or 0)] + [float(x["fin"]) for x in segs]), 1)
        s.update(source=t.session["source"], avec_micro=t.session["avec_micro"], modele=t.session["modele"],
                 etat="preparation", erreur="", duree=reprise_a,
                 reprises=list(s.get("reprises") or []) + [{"position": reprise_a, "date": time.time()}])
        t.session = s
        t.position = reprise_a
        t._anciens = [int(x["locuteur"]) for x in segs]
        # empreintes des phrases d'avant (si elles ont été gardées et viennent du même extracteur)
        amorce = [(None, False, max(0.0, x["fin"] - x["debut"])) for x in segs]
        try:
            with np.load(_chemin_empreintes(s["id"])) as z:
                emb, fi, du = list(z["empreintes"]), list(z["fiables"]), list(z["durees"])
                va = list(z["valides"]) if "valides" in z.files else [True] * len(emb)
            if len(emb) == len(segs):
                amorce = [(e if v else None, bool(f), float(d)) for e, f, d, v in zip(emb, fi, du, va)]
        except (OSError, KeyError, ValueError):
            pass
        t._amorce = amorce
        t._empreintes = list(amorce)
        return t

    # --- état lisible par l'interface
    def instantane(self) -> dict:
        with _verrou:
            s = json.loads(json.dumps(self.session))
        s["niveau"], s["retard"] = round(self.niveau, 3), round(self.retard, 1)
        if s["etat"] == "en_cours":
            s["duree"] = round(self.position, 1)     # reprise : durée d'avant comprise
        return s

    def demarrer(self):
        self._continuer = True
        self._fil = threading.Thread(target=self._executer, daemon=True, name="transcription")
        self._fil.start()

    def arreter(self):
        self._continuer = False

    def attendre(self, delai=None):
        if self._fil:
            self._fil.join(delai)

    # --- pipeline
    def _preparer(self):
        import numpy as np
        if self._transcrire is None:
            modele = _whisper(self.session["modele"])

            import inspect
            try:
                acceptes = set(inspect.signature(modele.transcribe).parameters)
            except (TypeError, ValueError):
                acceptes = None

            def transcrire(audio, langue, consigne=""):
                crete = float(np.abs(audio).max()) if len(audio) else 0.0
                if 1e-4 < crete < 0.3:      # voix lointaine : volume remonté (jusqu'à x20) pour Whisper
                    audio = audio * min(20.0, 0.5 / crete)
                options = options_whisper(langue, consigne)
                if acceptes is not None:        # anciennes versions de faster-whisper : options inconnues retirées
                    options = {k: v for k, v in options.items() if k in acceptes}
                segs, _ = modele.transcribe(audio, **options)
                return decouper_phrases(segs)
            self._transcrire = transcrire
        if self._empreinte_fn is None:
            self._empreinte_fn = _empreinte()
        nom = getattr(self._empreinte_fn, "nom", "")
        seuil = float(CONFIG.get("transcription_seuil") or getattr(self._empreinte_fn, "seuil", 0.5))
        self.diariseur = Diariseur(seuil, self.session["nb_locuteurs"])
        if self._amorce:
            ancien = self.session.get("empreinte") or ""
            dims = {len(np.ravel(e)) for e, _, _ in self._amorce if e is not None}
            if ancien != nom or len(dims) > 1:
                # autre extracteur de voix qu'à l'époque : empreintes incomparables, les voix de la suite
                # deviennent de nouveaux locuteurs (les phrases d'avant gardent les leurs)
                self._amorce = [(None, False, d) for _, _, d in self._amorce]
                self._empreintes = list(self._amorce)
            self.diariseur.amorcer(self._amorce)
        self.session["empreinte"] = nom
        if self.session["source"] == "fichier":
            self._audio_fichier = lire_fichier_audio(self._fichier_audio)
            self._captures = []
        elif self._captures is None:
            self._captures = []
            if self.session["source"] == "systeme":
                t = Tampon("systeme")
                self._captures.append((capture_systeme(t), t))
                if self.session["avec_micro"]:
                    m = Tampon("micro")
                    c = CaptureMicro(m)
                    c.demarrer()
                    self._captures.append((c, m))
            else:
                t = Tampon("micro")
                c = CaptureMicro(t)
                c.demarrer()
                self._captures.append((c, t))
        else:
            for c, _ in self._captures:
                c.demarrer()

    def _executer(self):
        import numpy as np
        try:
            self._preparer()
        except Exception as e:
            traceback.print_exc()
            self._fin_erreur(str(e))
            return
        with _verrou:
            self.session["etat"] = "en_cours"
            if not self._anciens and not self.session.get("reprises"):
                self.session["debut"] = time.time()     # reprise : la date de début reste celle d'origine
        sauver(self.session)
        _signaler(self.session["id"])
        mixeur = Mixeur([t for _, t in self._captures])
        decoupeur = Decoupeur()
        decoupeur.debut = self.position         # reprise : l'horodatage continue après la fin
        travailleur = threading.Thread(target=self._travailler, daemon=True, name="transcription-whisper")
        travailleur.start()
        fichier = getattr(self, "_audio_fichier", None)
        lu = 0                                  # échantillons du fichier importé déjà lus

        def traiter(x):
            if len(x):
                self.niveau = 0.8 * self.niveau + 0.2 * float(np.sqrt(np.mean(x * x)))
                bloc = decoupeur.ajouter(x)
                if bloc is not None:
                    self._blocs.put(bloc)
        try:
            while self._continuer:
                if fichier is not None:     # fichier importé : lu d'un coup (sans attendre l'horloge)
                    x = fichier[lu: lu + SR // 10]
                    if not len(x):
                        break
                    lu += len(x)
                    self.position += len(x) / SR
                    while self._blocs.qsize() > 3 and self._continuer:   # pas plus vite que Whisper
                        time.sleep(0.05)
                else:
                    time.sleep(0.1)
                    x = mixeur.lire()
                    self.position += len(x) / SR
                traiter(x)
                for _, t in self._captures:
                    if t.erreur:
                        raise RuntimeError(t.erreur)
            if fichier is None:
                # arrêt demandé juste après un mot : le son encore en route (latence de la carte son, ~0,3 s)
                # est lu avant de couper, sinon la fin de la dernière phrase manquait
                time.sleep(0.3)
                x = mixeur.lire()
                self.position += len(x) / SR
                traiter(x)
        except Exception as e:
            traceback.print_exc()
            self.session["erreur"] = str(e)
        finally:
            for c, _ in self._captures:
                try:
                    c.arreter()
                except Exception:
                    traceback.print_exc()
        with _verrou:
            self.session["duree"] = round(self.position, 1)
            self.session["etat"] = "finalisation"
        _signaler(self.session["id"])
        dernier = decoupeur.vider()
        if dernier is not None:
            self._blocs.put(dernier)
        self._blocs.put(None)
        travailleur.join()
        self._finaliser()

    def _consigne(self) -> str:
        """Amorce de Whisper : titre + vocabulaire (donné, déjà entendu, du sujet). Jamais le texte précédent :
        une erreur ou une boucle s'y propagerait."""
        with _verrou:
            textes = [x["texte"] for x in self.session["segments"][-300:]]
        return consigne_whisper(self.session["titre"],
                                vocabulaire(self.session["titre"], textes, self.session.get("vocabulaire", "")))

    def _travailler(self):
        """Fil Whisper : transcrit les blocs dans l'ordre, sans bloquer la capture."""
        while True:
            bloc = self._blocs.get()
            if bloc is None:
                return
            debut, audio = bloc
            self.retard = sum(len(b[1]) for b in list(self._blocs.queue) if b) / SR
            consigne = self._consigne()
            try:
                phrases = self._transcrire(audio, self.session["langue"], consigne)
            except Exception:
                # une erreur passagère (mémoire, décodage) ne doit pas faire perdre tout le bloc : 2e essai sans amorce
                traceback.print_exc()
                try:
                    phrases = self._transcrire(audio, self.session["langue"], "")
                    consigne = ""
                except Exception as e:
                    traceback.print_exc()
                    self.session["erreur"] = f"Transcription : {e}"
                    continue
            nouveaux = []
            for d, f, texte in phrases:
                texte = (texte or "").strip()
                if not texte or _hallucination(texte) or recopie_consigne(texte, consigne):
                    continue
                d = min(max(0.0, float(d)), max(0.0, len(audio) / SR - 0.01))
                f = min(len(audio) / SR, float(f))
                if f <= d:
                    f = min(len(audio) / SR, d + 0.01)
                fiable = f - d >= DUREE_FIABLE
                # empreinte sur au moins 1,5 s (élargie dans le bloc, coupé aux pauses : même voix le plus souvent)
                manque = max(0.0, 1.5 - (f - d)) / 2
                i0, i1 = int(max(0.0, d - manque) * SR), int(min(len(audio) / SR, f + manque) * SR)
                try:
                    e = self._empreinte_fn(audio[i0: max(i1, i0 + 1)])
                except Exception:
                    traceback.print_exc()
                    e = None
                self.diariseur.attribuer(e, fiable, f - d)
                self._empreintes.append((e, fiable, f - d))
                nouveaux.append({"debut": round(debut + d, 2), "fin": round(debut + f, 2), "locuteur": 1,
                                 "texte": texte})
            if nouveaux:
                with _verrou:
                    segs = self.session["segments"]
                    segs.extend(nouveaux)
                    # locuteurs à jour de toutes les phrases (fusions et regroupements réguliers du direct) ;
                    # reprise : celles d'avant gardent le leur
                    n0 = len(self._anciens)
                    for x, l in zip(segs[n0:], self._suite(self.diariseur.etiquettes, self.diariseur.historique)):
                        x["locuteur"] = l
                    self.session["duree"] = round(max(self.session.get("duree") or 0, debut + len(audio) / SR), 1)
                sauver(self.session)
                _signaler(self.session["id"])
            self.retard = sum(len(b[1]) for b in list(self._blocs.queue) if b) / SR

    def _suite(self, etiquettes: list[int], historique: list) -> list[int]:
        """Locuteurs des phrases de cette session (après les len(self._anciens) d'une reprise), d'après le
        regroupement `etiquettes` (aligné sur `historique` : (empreinte, fiable, durée)), qui couvre aussi les
        phrases d'avant si le diariseur a été amorcé avec."""
        n0 = len(self._anciens)
        nouvelles = len(self.session["segments"]) - n0
        base = len(etiquettes) - nouvelles          # n0 (amorcé) ou 0 (pas d'empreintes d'avant)
        anciens = self._anciens if base == n0 else []
        res = rattacher(anciens, list(etiquettes), [e is not None for e, _, _ in historique],
                        [d for _, _, d in historique], depart=max(self._anciens, default=0))
        return res[base:]

    def _finaliser(self):
        """Regroupement final des voix sur toute la réunion (aucune phrase laissée de côté, numéros 1, 2, 3…
        sans trou), puis fichiers définitifs. Le texte du direct est gardé tel quel."""
        segs = self.session["segments"]
        self.session["seuil"] = self.diariseur.seuil
        if segs and len(self._empreintes) == len(segs):
            try:
                sauver_empreintes(self.session["id"], [e for e, _, _ in self._empreintes],
                                  [f for _, f, _ in self._empreintes], [d for _, _, d in self._empreintes])
            except Exception:
                traceback.print_exc()
            try:
                etiquettes = self._suite(
                    regrouper_complet([e for e, _, _ in self._empreintes], self.diariseur.seuil,
                                      self.session["nb_locuteurs"], [f for _, f, _ in self._empreintes],
                                      [d for _, _, d in self._empreintes]), self._empreintes)
            except Exception:
                traceback.print_exc()
                etiquettes = None
        else:
            etiquettes = None
        n0 = len(self._anciens)
        if etiquettes is None:      # pas de regroupement final possible : numéros du direct, sans trou
            etiquettes = [x["locuteur"] for x in segs[n0:]] if n0 else renumeroter([x["locuteur"] for x in segs])
        with _verrou:
            for x, l in zip(segs[n0:], etiquettes):
                x["locuteur"] = l
            self.session["etat"] = "terminee"
        sauver(self.session)
        _liberer(self)
        _signaler(self.session["id"])

    def _fin_erreur(self, message: str):
        with _verrou:
            self.session["etat"], self.session["erreur"] = "erreur", message
        for c, _ in self._captures or []:
            try:
                c.arreter()
            except Exception:
                pass
        sauver(self.session, fichier_lisible=False)
        _liberer(self)
        _signaler(self.session["id"])


# ====================================================================================================
# Fidélité du texte : réglages de Whisper, phrases douteuses écartées, découpage aux pauses, vocabulaire
# (le texte n'est jamais reformulé ni résumé : on écarte ce que Whisper invente, on ne réécrit rien)
# ====================================================================================================
# Phrases que Whisper invente sur du silence, du bruit ou de la musique (apprises de sous-titres de vidéos)
# Toujours écartées : génériques de sous-titres, musique seule, ponctuation seule. Précis exprès : avant, « sous-titr »
# n'importe où suffisait, et une vraie phrase (« ajoute un sous-titre à la page ») disparaissait.
_HALLUCINATIONS = re.compile(
    r"(sous[- ]?titr\w*\s+(r[ée]alis|fait|par\b|:|de la soci)|^\W*sous[- ]?titrage\b|subtitles by|"
    r"amara\.org|soci[ée]t[ée] radio-canada|^\W*\[?\(?musique\)?\]?\W*$|^\W*♪[\s♪.]*$|^[\s.…!?,-]*$)", re.I)
# Formules de fin de vidéo : écartées seulement dans une phrase courte (c'est là que Whisper les invente)
_HALLUCINATIONS_VIDEO = re.compile(
    r"(merci d'avoir regardé|merci de nous avoir regardé|abonnez-vous|n'oubliez pas de vous abonner|"
    r"thanks for watching|thank you for watching)", re.I)
# Courtes phrases plausibles que Whisper invente aussi sur du silence : écartées seulement si le son est douteux
_HALLUCINATIONS_COURTES = re.compile(r"^\W*(merci( beaucoup)?|au revoir|bonne journée|à bientôt|"
                                     r"thank you|bye|you)\W*$", re.I)
PAUSE_DECOUPE = 0.8         # s de silence entre deux mots : nouvelle phrase (nouvel horodatage, nouvelle empreinte)
DUREE_PHRASE_MAX = 30.0     # s : une phrase plus longue est coupée en fin de phrase (ou entre deux mots)


def _hallucination(texte: str) -> bool:
    texte = texte.strip()
    return bool(_HALLUCINATIONS.search(texte)) or (
        len(texte.split()) <= 12 and bool(_HALLUCINATIONS_VIDEO.search(texte)))


def modele_auto(source: str = "micro") -> str:
    """Le modèle Whisper le plus précis que la machine fait tourner assez vite. large-v3-turbo : précision
    proche de large-v3, bien plus rapide (pas de distil-large-v3 : il ne connaît que l'anglais)."""
    import os
    try:
        import psutil
        ram = psutil.virtual_memory().total / 2 ** 30
    except Exception:
        ram = 8.0
    coeurs = os.cpu_count() or 4
    if ram >= 8 and (coeurs >= 8 or source == "fichier"):     # un fichier importé n'a pas à suivre le direct
        return "large-v3-turbo"
    if ram >= 6 and coeurs >= 4:
        return "small"
    return "base"


def modele_par_defaut() -> str:
    """Modèle retenu : celui que l'utilisateur a choisi lui-même (marqué depuis 2.4.0), sinon « auto ».
    Avant 2.4.0, l'interface enregistrait le modèle affiché (souvent « small ») à chaque lancement, même sans
    choix : ces anciens réglages ne bloquent pas le mode auto."""
    m = str(CONFIG.get("transcription_modele") or "")
    return m if m in MODELES_WHISPER and CONFIG.get("transcription_modele_choisi") else "auto"


def options_whisper(langue: str, consigne: str = "") -> dict:
    """Réglages pour un texte fidèle : décodage déterministe (température 0, recherche en faisceau), sans
    reprise du texte précédent (évite les boucles), segments douteux signalés, voix détectée par le VAD."""
    return {"language": langue or None, "task": "transcribe", "beam_size": 5, "best_of": 5, "temperature": 0.0,
            "condition_on_previous_text": False, "initial_prompt": consigne or None,
            "compression_ratio_threshold": 2.4, "log_prob_threshold": -1.0, "no_speech_threshold": 0.6,
            # VAD un peu plus sensible que par défaut (0,5) : une voix faible ou lointaine n'est pas jetée
            "vad_filter": True, "vad_parameters": {"threshold": 0.35, "min_silence_duration_ms": 500,
                                                   "speech_pad_ms": 400},
            "word_timestamps": True, "hallucination_silence_threshold": 2.0}


def segment_douteux(s) -> bool:
    """Segment Whisper à écarter : texte qui boucle (taux de compression élevé), très incertain, ou
    probablement du silence (no_speech élevé et texte peu sûr)."""
    lp = getattr(s, "avg_logprob", 0.0) or 0.0
    ns = getattr(s, "no_speech_prob", 0.0) or 0.0
    if (getattr(s, "compression_ratio", 0.0) or 0.0) > 2.4 or lp < -1.4 or (ns > 0.6 and lp < -1.0):
        return True
    return bool(_HALLUCINATIONS_COURTES.match(getattr(s, "text", "") or "")) and (ns > 0.3 or lp < -0.7)


def sans_boucles(texte: str) -> str:
    """Retire les répétitions parasites de Whisper (même groupe de mots répété en boucle : 4 fois et plus
    pour 2 à 8 mots, 5 fois et plus pour un mot). Les répétitions naturelles (« non, non ») restent."""
    mots = texte.split()
    if len(mots) < 4:
        return texte
    norm = [re.sub(r"[^\w$']", "", m.lower()) for m in mots]
    for n in range(8, 0, -1):
        mini = 5 if n == 1 else 4
        i = 0
        while i + n * mini <= len(mots):
            motif = norm[i:i + n]
            k = 1
            while norm[i + k * n: i + (k + 1) * n] == motif:
                k += 1
            if k >= mini and any(motif):
                del mots[i + n: i + k * n], norm[i + n: i + k * n]
            i += 1
    return " ".join(mots)


def decouper_phrases(segments, pause: float = PAUSE_DECOUPE, duree_max: float = DUREE_PHRASE_MAX) -> list:
    """Segments Whisper -> [(début, fin, texte)] : segments douteux écartés, coupés à chaque pause entre deux
    mots (horodatage fidèle, et une empreinte vocale par prise de parole) et au plus ~30 s par phrase."""
    phrases = []
    for s in segments:
        if segment_douteux(s):
            continue
        mots = [m for m in (getattr(s, "words", None) or []) if (m.word or "").strip()]
        if not mots:
            morceaux = [(float(s.start), float(s.end), s.text)]
        else:
            morceaux, courant = [], [mots[0]]
            for m in mots[1:]:
                duree = float(m.end) - float(courant[0].start)
                fin_phrase = courant[-1].word.strip()[-1:] in ".?!…"
                if float(m.start) - float(courant[-1].end) >= pause or duree > duree_max or \
                        (duree > duree_max * 0.6 and fin_phrase):
                    morceaux.append(courant)
                    courant = [m]
                else:
                    courant.append(m)
            morceaux.append(courant)
            morceaux = [(float(c[0].start), float(c[-1].end), "".join(m.word for m in c)) for c in morceaux]
        for d, f, texte in morceaux:
            texte = sans_boucles(re.sub(r"\s+", " ", texte or "").strip())
            if not texte or _hallucination(texte):
                continue
            if phrases and len(texte) > 15 and texte == phrases[-1][2] and d - phrases[-1][1] < 1.0:
                continue        # même phrase rendue deux fois d'affilée par Whisper (redite plus tard : gardée)
            phrases.append((d, max(f, d + 0.01), texte))
    return phrases


# Vocabulaire de quelques sujets (repéré dans le titre) : aide Whisper à écrire le jargon correctement
VOCABULAIRE_THEMES = {
    r"\bphp\b": ["PHP", "$this", "getter", "setter", "constructeur", "__construct", "trigger_error", "ucfirst",
                 "PDO", "echo", "public", "private", "protected", "static", "extends", "namespace", "var_dump"],
    r"\b(objet|poo|oop)\b": ["classe", "objet", "méthode", "attribut", "instance", "héritage", "encapsulation",
                             "interface", "getter", "setter", "constructeur"],
    r"\bpython\b": ["Python", "self", "def", "__init__", "import", "pip", "liste", "dictionnaire", "None"],
    r"\b(javascript|js|react|node)\b": ["JavaScript", "const", "let", "async", "await", "fetch", "useState",
                                        "React", "npm", "JSON"],
    r"\b(sql|mysql|base de donn[ée]es|bdd)\b": ["SQL", "SELECT", "INSERT", "UPDATE", "JOIN", "WHERE", "MySQL",
                                               "clé primaire", "clé étrangère"],
    r"\bjava\b": ["Java", "public static void main", "extends", "implements", "new", "String"],
    r"\b(html|css|web)\b": ["HTML", "CSS", "div", "class", "id", "flexbox", "balise"],
}
_MOT_TECHNIQUE = re.compile(r"\$\w+|\b\w+_\w+\b|\b\w+\(\)|\b[a-z]+[A-Z]\w*\b|\b[A-Z]{2,}[a-z]?\b")


def vocabulaire(titre: str = "", textes: list[str] | None = None, mots: str | list = "") -> list[str]:
    """Mots à bien orthographier : ceux donnés par l'utilisateur, les mots techniques déjà entendus dans la
    réunion (au moins deux fois), puis ceux du sujet (d'après le titre)."""
    from collections import Counter
    if isinstance(mots, str):
        mots = [m.strip() for m in re.split(r"[,;\n]", mots)]
    vus = Counter(m for t in (textes or []) for m in _MOT_TECHNIQUE.findall(t))
    theme = [m for motif, liste in VOCABULAIRE_THEMES.items() if re.search(motif, titre or "", re.I) for m in liste]
    res: list[str] = []
    for m in list(mots) + [m for m, n in vus.most_common(15) if n >= 2] + theme:
        if m and m.lower() not in {x.lower() for x in res}:
            res.append(m)
    return res[:40]


def consigne_whisper(titre: str = "", vocab: list[str] | None = None) -> str:
    """Texte d'amorce de Whisper (initial_prompt) : le sujet et le vocabulaire, pour orthographier le jargon.
    Court (Whisper n'en garde qu'environ 220 jetons) ; ne change pas le sens de ce qui est transcrit."""
    morceaux = []
    if titre and not titre.startswith("Réunion du "):
        morceaux.append(titre.strip().rstrip(".") + ".")
    if vocab:
        morceaux.append("Vocabulaire : " + ", ".join(vocab) + ".")
    return " ".join(morceaux)[:600]


def recopie_consigne(texte: str, consigne: str) -> bool:
    """Whisper recopie parfois son amorce quand le son est inaudible : cette « phrase » est écartée."""
    norme = lambda x: re.sub(r"\W+", " ", x.lower()).strip()
    t = norme(texte)
    if not consigne or len(t) < 8:
        return False
    if t.startswith("vocabulaire"):
        return True
    # Recopie du titre entier, ou d'une liste de mots du vocabulaire (« getter, setter, constructeur »). Avant,
    # toute phrase contenue dans l'amorce était jetée : « le constructeur » dit en cours disparaissait.
    titre = consigne.split(" Vocabulaire :")[0]
    return t == norme(titre) or (f" {t} " in f" {norme(consigne)} " and texte.count(",") >= 2)


def _liberer(t: Transcription):
    global _en_cours
    with _verrou:
        if _en_cours is t:
            _en_cours = None


def demarrer(source="micro", avec_micro=False, langue=None, modele="", titre="", nb_locuteurs=0, fichier_audio="",
             vocabulaire="", **tests) -> dict:
    """Lance une transcription (une seule à la fois) ; renvoie son état. langue : None = celle de Wesley
    (français par défaut), « » = détection automatique."""
    global _en_cours
    with _verrou:
        if _en_cours is not None:
            raise ValueError("Une transcription est déjà en cours : arrête-la d'abord.")
        if modele and modele not in MODELES_WHISPER:
            raise ValueError("Modèle de transcription inconnu.")
        t = Transcription(source, avec_micro, langue if langue is not None else (CONFIG.get("langue") or "fr"),
                          modele, titre, nb_locuteurs, fichier_audio, vocabulaire=vocabulaire, **tests)
        _en_cours = t
    t.demarrer()
    return t.instantane()


def reprendre(tid: str, source: str = "", avec_micro=None, fichier_audio: str = "", **tests) -> dict:
    """Reprend une transcription déjà faite (terminée, interrompue ou en erreur) : la suite s'écrit à la fin de
    la même transcription, mêmes locuteurs, horodatage continu. source vide = celle d'origine (micro pour un
    fichier importé) ; « fichier » + fichier_audio : un enregistrement à ajouter à la suite."""
    global _en_cours
    with _verrou:
        if _en_cours is not None:
            raise ValueError("Une transcription est déjà en cours : arrête-la d'abord.")
        s = lire(tid)
        if s is None:
            raise ValueError("Transcription introuvable.")
        t = Transcription.reprise(s, source, avec_micro, fichier_audio, **tests)
        _en_cours = t
    t.demarrer()
    return t.instantane()


def arreter() -> dict | None:
    """Arrête la capture ; la fin de la transcription et le regroupement final continuent en fond."""
    t = _en_cours
    if t is None:
        return None
    t.arreter()
    return t.instantane()
