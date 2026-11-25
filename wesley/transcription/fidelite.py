"""Fidélité du texte : réglages de Whisper, phrases inventées écartées, découpage aux pauses, vocabulaire
technique. Le texte n'est jamais reformulé."""
from __future__ import annotations

import re

from ..config import CONFIG
from .communs import MODELES_WHISPER


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
