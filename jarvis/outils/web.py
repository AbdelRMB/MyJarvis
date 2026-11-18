import requests
from bs4 import BeautifulSoup

from . import outil

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}


@outil
def recherche_web(requete: str, nombre: int = 6):
    """Recherche sur internet (DuckDuckGo) : actus, docs, infos récentes.
    requete: la recherche
    nombre: nombre de résultats"""
    from ddgs import DDGS
    res = DDGS().text(requete, max_results=nombre, region="fr-fr")
    return "\n\n".join(f"{r['title']}\n{r['href']}\n{r['body']}" for r in res) or "Aucun résultat."


@outil
def actualites(sujet: str = "France"):
    """Dernières actualités sur un sujet.
    sujet: sujet"""
    from ddgs import DDGS
    res = DDGS().news(sujet, max_results=8, region="fr-fr")
    return "\n\n".join(f"{r.get('date','')[:10]} - {r['title']} ({r.get('source','')})\n{r['url']}" for r in res)


@outil
def lire_page_web(url: str):
    """Télécharge une page web et renvoie son texte lisible.
    url: adresse de la page"""
    r = requests.get(url, headers=UA, timeout=20)
    s = BeautifulSoup(r.text, "html.parser")
    for t in s(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        t.decompose()
    txt = "\n".join(l.strip() for l in s.get_text("\n").splitlines() if l.strip())
    return f"{s.title.string if s.title else url}\n\n{txt[:10000]}"


@outil
def meteo(ville: str = ""):
    """Météo actuelle et prévisions (wttr.in).
    ville: ville (défaut : localisation auto)"""
    r = requests.get(f"https://wttr.in/{ville}?format=j1&lang=fr", headers=UA, timeout=15).json()
    c = r["current_condition"][0]
    desc = c.get("lang_fr", c["weatherDesc"])[0]["value"]
    out = [f"Maintenant : {c['temp_C']}°C (ressenti {c['FeelsLikeC']}°C), {desc}, vent {c['windspeedKmph']} km/h"]
    for j in r["weather"][:3]:
        out.append(f"{j['date']} : {j['mintempC']}–{j['maxtempC']}°C")
    return "\n".join(out)


@outil
def telecharger(url: str, destination: str):
    """Télécharge un fichier depuis une URL.
    url: URL du fichier
    destination: chemin de sauvegarde"""
    from pathlib import Path
    p = Path(destination).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=UA, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(p, "wb") as f:
            for ch in r.iter_content(65536):
                f.write(ch)
    return f"Téléchargé : {p} ({p.stat().st_size//1024} Ko)"
