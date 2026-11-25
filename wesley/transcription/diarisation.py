"""Diarisation : qui parle ? Regroupement des voix (numpy) et empreintes vocales (sherpa-onnx, sinon empreinte
spectrale simple)."""
from __future__ import annotations

from pathlib import Path

from .communs import DOSSIER_MODELES, MODELE_LOCUTEURS, SR, URL_MODELE_LOCUTEURS
from .document import renumeroter


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
