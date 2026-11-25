"""Recherche unique : une question, toutes les sources de Wesley à la fois.

Souvenirs et conversations passées (par le sens), transcriptions (de tous les appareils du compte), documents
indexés (PDF, Word, textes) et liste « À faire ». Chaque source est cherchée indépendamment : si l'une échoue
(modèle de sens absent, index vide…), les autres répondent quand même.
"""
from datetime import datetime

SOURCES = ("souvenirs", "historique", "transcriptions", "documents", "afaire")


def _afaire(requete: str, n: int) -> list[dict]:
    from . import afaire, semantique
    taches = [t for t in afaire.lister() if t.get("titre")]
    textes = [f"{t['titre']} {t.get('note', '')}".strip() for t in taches]
    return [{"id": taches[i]["id"], "titre": taches[i]["titre"], "note": taches[i].get("note", ""),
             "statut": taches[i].get("statut", ""), "echeance": taches[i].get("echeance", ""), "score": round(s, 3)}
            for i, s in semantique.classer(requete, textes, k=n, seuil=0.80)]


def _transcriptions(requete: str, n: int) -> list[dict]:
    from . import recherche_transcriptions
    return [{"id": r["id"], "titre": r["titre"], "date": r.get("date"), "heure": r.get("heure", ""),
             "locuteur": r.get("locuteur", ""), "texte": r["texte"], "appareil": r.get("appareil", "")}
            for r in recherche_transcriptions.chercher(requete, n)]


def _documents(requete: str, n: int) -> list[dict]:
    from . import documents
    return [{"fichier": p["fichier"], "page": p["page"], "texte": p["texte"][:400], "score": p["score"]}
            for p in documents.chercher(requete, n)]


def chercher_partout(requete: str, n: int = 6) -> dict:
    """{source: [résultats]} pour chaque source, plus "erreurs" ({source: message}) pour celles qui ont échoué."""
    requete = (requete or "").strip()
    res: dict = {s: [] for s in SOURCES}
    res["erreurs"] = {}
    if not requete:
        return res
    try:
        from . import memoire
        d = memoire.chercher_detail(requete, k_faits=n, k_historique=n)
        res["souvenirs"], res["historique"] = d["souvenirs"], d["historique"]
    except Exception as e:
        res["erreurs"]["souvenirs"] = str(e)
    for nom, fn in (("transcriptions", _transcriptions), ("documents", _documents), ("afaire", _afaire)):
        try:
            res[nom] = fn(requete, n)
        except Exception as e:
            res["erreurs"][nom] = str(e)
    return res


def en_texte(res: dict, requete: str = "") -> str:
    """Résultats lisibles par un modèle (outil de Wesley, serveur MCP)."""
    blocs = []
    if res["souvenirs"]:
        blocs.append("Souvenirs :\n" + "\n".join(f"- {x['fait']}" for x in res["souvenirs"]))
    if res["historique"]:
        blocs.append("Conversations passées :\n" + "\n".join(f"- [{x['jour']}] {x['texte']}" for x in res["historique"]))
    if res["transcriptions"]:
        def date(x):
            return datetime.fromtimestamp(x["date"]).strftime("%d/%m/%Y") if x.get("date") else ""
        blocs.append("Transcriptions :\n" + "\n".join(
            f"- [{x['id']}] « {x['titre']} » {date(x)}" + (f" à {x['heure']}, {x['locuteur']}" if x["heure"] else "")
            + f" : {x['texte']}" for x in res["transcriptions"]))
    if res["documents"]:
        blocs.append("Documents :\n" + "\n".join(
            f"- {x['fichier']}" + (f" (page {x['page']})" if x["page"] else "") + f" : {x['texte']}"
            for x in res["documents"]))
    if res["afaire"]:
        blocs.append("À faire :\n" + "\n".join(
            f"- [{x['id']}] {x['titre']} ({x['statut']}" + (f", pour le {x['echeance']}" if x["echeance"] else "") + ")"
            for x in res["afaire"]))
    return "\n\n".join(blocs) or f"Rien trouvé sur « {requete} »."
