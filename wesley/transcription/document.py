"""Mise en forme d'une transcription : horodatage, tours de parole, export, renommage et tri des locuteurs (pur
Python : testable sans dépendance)."""
from __future__ import annotations

import re
import time
from datetime import datetime

from .communs import DUREE_TOUR_MAX, PAUSE_TOUR


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
    from ..resume_transcription import en_markdown
    bloc_resume = en_markdown(session.get("resume") or {})
    if format == "txt":
        lignes = [titre, debut.strftime("%d/%m/%Y %H:%M") + f" · durée {duree} · source : {source}",
                  f"Participants : {noms}", ""]
        if bloc_resume:
            lignes += [bloc_resume.replace("## ", "").replace("### ", "").strip(), "", "Transcription :", ""]
        for i, t in enumerate(tours):
            lignes += [f"— {r} —" for r in reprise_avant(i)]
            lignes.append(f"[{horodatage(t['debut'])}] {nom_locuteur(session, t['locuteur'])} : {t['texte']}")
        return "\n".join(lignes).rstrip() + "\n"
    lignes = [f"# {titre}", "",
              f"- **Date** : {debut.strftime('%d/%m/%Y %H:%M')}",
              f"- **Durée** : {duree}",
              f"- **Source** : {source}",
              f"- **Participants** : {noms}", "", "---", ""]
    if bloc_resume:
        lignes += [bloc_resume, "---", "", "## Transcription", ""]
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
