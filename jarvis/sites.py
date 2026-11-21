"""Sites appris : Jarvis connaît par cœur les sites (complexes, d'entreprise) que tu lui as fait apprendre.

Pour chaque site : la carte des pages (chemin pour y arriver, boutons, champs, titres), les procédures montrées en
démonstration, des astuces (notées par toi ou par Jarvis après une tâche réussie) et un guide rédigé à la fin de
l'exploration. Quand tu poses une question sur le site, Jarvis cherche d'abord là-dedans pour savoir où aller.

Rangé sur cet ordinateur seulement (dossier du compte, jamais envoyé au serveur) : les sites d'entreprise sont
confidentiels.
"""
import json
import re
import threading
import time
import unicodedata
import uuid
from urllib.parse import urldefrag, urlparse

from . import config

_verrou = threading.RLock()
EXPLO = {"en_cours": False, "site": "", "pages": 0, "max": 0, "etape": "", "erreur": "", "arreter": False}
# liens qu'une exploration ne suit JAMAIS (elle ne doit rien modifier ni déconnecter)
_DANGER = re.compile(r"log.?out|log.?off|sign.?out|d[ée]connex|deconnect|quitter|exit|delete|supprim|remove|destroy|"
                     r"annul|cancel|reset|purge|unsubscribe|d[ée]sinscri|payer|checkout|commander|"
                     r"\.(pdf|zip|xlsx?|docx?|csv|exe|dmg|png|jpe?g|gif|mp4)(\?|$)|/download|/export|mailto:|tel:|javascript:", re.I)


def _dossier():
    d = config.PARTAGE / "sites"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fichier(sid: str):
    return _dossier() / f"{sid}.json"


def lister() -> list:
    sites = []
    for f in sorted(_dossier().glob("*.json")):
        try:
            sites.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return sites


def lire(sid: str) -> dict | None:
    try:
        return json.loads(_fichier(sid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ecrire(site: dict):
    with _verrou:
        site["modifie"] = time.strftime("%Y-%m-%d %H:%M")
        _fichier(site["id"]).write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        from . import web
        web.diffuser(type="sites_maj")
    except Exception:
        pass


def resume(s: dict) -> dict:
    return {"id": s["id"], "nom": s["nom"], "url": s["url"], "pages": len(s.get("pages", [])),
            "procedures": len(s.get("procedures", [])), "astuces": len(s.get("astuces", [])),
            "guide": bool(s.get("guide")), "modifie": s.get("modifie", ""), "explore": s.get("explore", "")}


def ajouter(nom: str, url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    hote = urlparse(url).hostname or url
    existant = next((s for s in lister() if s["hote"] == hote), None)
    if existant:
        return existant
    s = {"id": uuid.uuid4().hex[:8], "nom": nom.strip() or hote, "url": url, "hote": hote, "pages": [], "procedures": [],
         "astuces": [], "guide": "", "cree": time.strftime("%Y-%m-%d %H:%M")}
    _ecrire(s)
    return s


def trouver(nom_ou_url: str) -> dict | None:
    cle = nom_ou_url.strip().lower()
    hote = urlparse(cle if "://" in cle else "https://" + cle).hostname or cle
    sites = lister()
    return (next((s for s in sites if s["id"] == cle or s["nom"].lower() == cle or s["hote"] == hote), None)
            or next((s for s in sites if cle and (cle in s["nom"].lower() or cle in s["hote"])), None))


def supprimer(sid: str):
    _fichier(sid).unlink(missing_ok=True)


# ---------- astuces et procédures ----------
def noter(sid: str, texte: str) -> dict:
    s = lire(sid)
    s.setdefault("astuces", []).append({"id": uuid.uuid4().hex[:6], "texte": texte.strip(), "date": time.strftime("%Y-%m-%d")})
    _ecrire(s)
    return s


def retirer(sid: str, quoi: str, iid: str):
    s = lire(sid)
    s[quoi] = [x for x in s.get(quoi, []) if x["id"] != iid]
    _ecrire(s)


def ajouter_procedure(sid: str, nom: str, etapes: list, description: str = "") -> dict:
    s = lire(sid)
    p = {"id": uuid.uuid4().hex[:6], "nom": nom.strip() or "Procédure", "etapes": etapes, "description": description,
         "date": time.strftime("%Y-%m-%d")}
    s.setdefault("procedures", []).append(p)
    _ecrire(s)
    return p


def decrire_etape(e: dict) -> str:
    ou = f" (page « {e.get('titre') or e.get('url', '')} »)" if e.get("titre") or e.get("url") else ""
    if e.get("action") == "saisie":
        return f"Remplir « {e.get('libelle') or e.get('element')} » avec « {e.get('valeur', '')} »{ou}"
    if e.get("action") == "ouvrir":
        return f"Aller sur {e.get('url')}"
    return f"Cliquer sur « {e.get('libelle') or e.get('element')} »{ou}"


# ---------- exploration (lecture seule) ----------
def explorer(sid: str, max_pages: int = 80):
    if EXPLO["en_cours"]:
        raise RuntimeError("Une exploration est déjà en cours.")
    EXPLO.update(en_cours=True, site=sid, pages=0, max=max_pages, etape="Ouverture du site…", erreur="", arreter=False)
    threading.Thread(target=_explorer, args=(sid, max_pages), daemon=True, name="exploration-site").start()


def _diffuser():
    try:
        from . import web
        web.diffuser(type="exploration", **{k: v for k, v in EXPLO.items() if k != "arreter"})
    except Exception:
        pass


def _explorer(sid: str, max_pages: int):
    from . import navigateur
    try:
        s = lire(sid)
        depart = s["url"]
        vues, file, pages = set(), [(depart, [])], []
        while file and len(pages) < max_pages and not EXPLO["arreter"]:
            url, chemin = file.pop(0)
            url = urldefrag(url)[0]
            if url in vues:
                continue
            vues.add(url)
            try:
                v = navigateur.ouvrir(url)
            except Exception as e:
                print(f"  ! Exploration {url} : {e}")
                continue
            reel = urldefrag(v.get("url") or url)[0]
            if (urlparse(reel).hostname or "") != s["hote"]:
                continue   # redirigé ailleurs (page de connexion d'un autre domaine…)
            vues.add(reel)
            elements = v.get("elements", [])
            page = {"url": reel, "titre": v.get("titre", ""), "chemin": chemin, "titres": v.get("titres", [])[:15],
                    "boutons": sorted({e["libelle"] for e in elements if e["type"] in ("button", "submit") or "button" in e["type"]
                                       if e["libelle"]})[:40],
                    "champs": [e["libelle"] for e in elements if e["type"].startswith("champ") or e["type"] in ("select", "textarea")
                               if e["libelle"]][:40],
                    "liens": sorted({e["libelle"] for e in elements if e["type"] == "lien" and e["libelle"]})[:60],
                    "texte": v.get("texte", "")[:700]}
            pages.append(page)
            EXPLO.update(pages=len(pages), etape=f"Page {len(pages)} : {page['titre'] or reel}")
            _diffuser()
            for e in elements:
                h = e.get("href") or ""
                if e["type"] != "lien" or not h.startswith("http") or _DANGER.search(h) or _DANGER.search(e["libelle"]):
                    continue
                h = urldefrag(h)[0]
                if (urlparse(h).hostname or "") == s["hote"] and h not in vues:
                    file.append((h, chemin + [e["libelle"] or h]))
        s = lire(sid)
        anciennes = {p["url"]: p for p in s.get("pages", [])}
        anciennes.update({p["url"]: p for p in pages})
        s["pages"] = list(anciennes.values())
        s["explore"] = time.strftime("%Y-%m-%d %H:%M")
        _ecrire(s)
        EXPLO["etape"] = "Rédaction du guide du site…"
        _diffuser()
        try:
            s["guide"] = rediger_guide(s)
            _ecrire(s)
        except Exception as e:
            print(f"  ! Guide du site : {e}")
        EXPLO["etape"] = f"Terminé : {len(pages)} pages apprises."
        try:
            from . import annonces
            annonces.annoncer(f"J'ai fini d'apprendre le site {s['nom']} : {len(pages)} pages.", titre="Sites", vue="sites")
        except Exception:
            pass
    except Exception as e:
        EXPLO["erreur"] = str(e)[:400]
        EXPLO["etape"] = "Échec de l'exploration."
    finally:
        EXPLO["en_cours"] = False
        _diffuser()


# ---------- guide rédigé par le cerveau choisi ----------
def _llm(consigne: str) -> str:
    from .config import CONFIG
    cerveau = CONFIG.get("cerveau")
    if cerveau == "claude":
        from . import claude
        r = claude.client().messages.create(model=CONFIG["claude_modele"], max_tokens=6000, output_config={"effort": "low"},
                                            messages=[{"role": "user", "content": consigne}])
        claude.enregistrer_cout(r.usage, CONFIG["claude_modele"])
        return "".join(b.text for b in r.content if b.type == "text")
    if cerveau == "openai":
        from . import openai_cerveau
        r = openai_cerveau.client().chat.completions.create(model=openai_cerveau.modele(),
                                                            messages=[{"role": "user", "content": consigne}])
        return r.choices[0].message.content or ""
    import ollama
    r = ollama.chat(model=CONFIG["modele"], think=False, messages=[{"role": "user", "content": consigne}],
                    options={"num_ctx": CONFIG.get("num_ctx", 16384)})
    return r.message.content or ""


def rediger_guide(s: dict) -> str:
    carte = "\n".join(f"- {p['titre'] or p['url']} | chemin : {' > '.join(p['chemin']) or 'accueil'} | url : {p['url']}"
                      f" | boutons : {', '.join(p['boutons'][:12])} | champs : {', '.join(p['champs'][:12])}"
                      for p in s.get("pages", [])[:150])
    return _llm(f"Voici la carte du site « {s['nom']} » ({s['url']}) explorée page par page. Rédige en français un guide "
                "pratique et compact pour un assistant qui devra s'en servir : les grandes sections, où se trouve chaque "
                "fonction importante (avec le chemin de menus pour y aller), et comment faire les actions courantes "
                "(créer, rechercher, modifier, exporter…). Pas d'introduction ni de conclusion, des listes courtes.\n\n" + carte)[:12000]


# ---------- recherche ----------
def _mots(t: str) -> list:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return [m for m in re.findall(r"[a-z0-9]{3,}", t) if m not in _VIDES]


_VIDES = {"les", "des", "une", "est", "pour", "dans", "sur", "avec", "que", "qui", "quoi", "comment", "ou", "faire", "mon",
          "mes", "ton", "tes", "son", "ses", "the", "and", "how", "page", "site", "veux", "dois", "peux", "fait", "aller",
          "trouve", "trouver", "est-ce"}


def chercher(question: str, site: str = "") -> str:
    mots = set(_mots(question))
    sites = [trouver(site)] if site else lister()
    sites = [s for s in sites if s]
    if not sites:
        return "Aucun site appris" + (f" ne correspond à « {site} »." if site else ".")
    sorties = []
    for s in sites:
        notes = []
        for p in s.get("pages", []):
            score = (3 * len(mots & set(_mots(p["titre"] + " " + " ".join(p["chemin"]))))
                     + 2 * len(mots & set(_mots(" ".join(p["titres"] + p["boutons"] + p["champs"]))))
                     + len(mots & set(_mots(" ".join(p["liens"]) + " " + p["texte"]))))
            if score:
                notes.append((score, "page", p))
        for pr in s.get("procedures", []):
            score = 4 * len(mots & set(_mots(pr["nom"] + " " + pr.get("description", "")))) + \
                len(mots & set(_mots(" ".join(decrire_etape(e) for e in pr["etapes"]))))
            if score:
                notes.append((score + 2, "procedure", pr))
        for a in s.get("astuces", []):
            score = 2 * len(mots & set(_mots(a["texte"])))
            if score:
                notes.append((score + 1, "astuce", a))
        notes.sort(key=lambda x: -x[0])
        if not notes and len(sites) > 1:
            continue
        lignes = [f"## {s['nom']} ({s['url']})"]
        for _, genre, x in notes[:8]:
            if genre == "page":
                lignes.append(f"- Page « {x['titre']} » — chemin : {' > '.join(x['chemin']) or 'accueil'} — {x['url']}"
                              + (f"\n  boutons : {', '.join(x['boutons'][:15])}" if x["boutons"] else "")
                              + (f"\n  champs : {', '.join(x['champs'][:15])}" if x["champs"] else ""))
            elif genre == "procedure":
                lignes.append(f"- Procédure « {x['nom'] } » (montrée par l'utilisateur) :\n" +
                              "\n".join(f"  {i + 1}. {decrire_etape(e)}" for i, e in enumerate(x["etapes"][:40])))
            else:
                lignes.append(f"- Astuce : {x['texte']}")
        if s.get("guide"):
            lignes.append("\nGuide du site :\n" + s["guide"][:4000])
        if not notes:
            lignes.append("(rien de précis trouvé pour cette question : sers-toi du guide, ou ouvre le site et regarde)")
        sorties.append("\n".join(lignes))
    return "\n\n".join(sorties) or "Rien trouvé sur les sites appris pour cette question."
