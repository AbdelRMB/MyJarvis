"""Recherche par le sens, 100 % locale : « ma voiture » retrouve « la Clio est au garage », « mes dents » retrouve
« rendez-vous chez le dentiste ».

- Modèle multilingual-e5-base (ONNX quantifié, ~270 Mo, licence MIT), téléchargé une fois dans RACINE/modeles au
  premier usage, comme le modèle des voix de la transcription. Tourne avec onnxruntime + tokenizers, déjà livrés
  avec Wesley (rien à installer). ~15 ms pour une phrase, déchargé après 10 min sans usage.
- Chaque texte est transformé en vecteur une seule fois : les vecteurs sont gardés sur cet appareil
  (RACINE/memoire/index_<nom>.npz), indexés par l'empreinte du texte (un souvenir modifié est simplement recalculé).
- classer() combine le sens et les mots exacts (noms propres, sigles) : sans le modèle (pas encore téléchargé,
  hors ligne), seule la recherche par mots fonctionne, comme avant.
"""
import hashlib
import threading
import time
import urllib.request

from .config import CONFIG, RACINE

NOM_MODELE = "multilingual-e5-base"
DEPOT = "https://huggingface.co/Xenova/multilingual-e5-base/resolve/main/"
FICHIERS = {"model_quantized.onnx": "onnx/model_quantized.onnx", "tokenizer.json": "tokenizer.json"}
DOSSIER = RACINE / "modeles" / NOM_MODELE
DOSSIER_INDEX = RACINE / "memoire"
INACTIVITE = 600            # s sans usage : le modèle est déchargé (rend ~300 Mo de mémoire)
_verrou = threading.RLock()
_etat = {"session": None, "tok": None, "dernier": 0.0, "telechargement": None, "erreur": ""}


# ---------- modèle ----------
def disponible() -> bool:
    return all((DOSSIER / f).exists() for f in FICHIERS)


def utilisable() -> bool:
    """Modèle téléchargé ET bibliothèques présentes (onnxruntime, tokenizers : livrées avec Wesley)."""
    if not disponible():
        return False
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
        return True
    except ImportError:
        return False


def active() -> bool:
    return CONFIG.get("memoire_semantique", True)


def telecharger():
    """Télécharge le modèle (une fois). Appelé en fond au démarrage ; sans réseau, on réessaiera plus tard."""
    with _verrou:
        if disponible() or _etat["telechargement"]:
            return
        _etat["telechargement"] = True
    try:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        for nom, chemin in FICHIERS.items():
            cible = DOSSIER / nom
            if cible.exists():
                continue
            tmp = cible.with_suffix(cible.suffix + ".part")
            with urllib.request.urlopen(DEPOT + chemin, timeout=60) as r, open(tmp, "wb") as f:
                while True:
                    bloc = r.read(1 << 20)
                    if not bloc:
                        break
                    f.write(bloc)
            tmp.replace(cible)
        print(f"  Mémoire par le sens : modèle {NOM_MODELE} prêt.")
    except Exception as e:
        _etat["erreur"] = str(e)
        print(f"  (mémoire par le sens : modèle non téléchargé pour l'instant : {e})")
    finally:
        _etat["telechargement"] = None


def telecharger_en_fond():
    if active() and not disponible():
        threading.Thread(target=telecharger, daemon=True, name="modele-sens").start()


def _charger():
    import onnxruntime as ort
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(DOSSIER / "tokenizer.json"))
    tok.enable_truncation(256)
    tok.enable_padding()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2      # ne pas monopoliser l'ordinateur pendant une transcription ou un jeu
    session = ort.InferenceSession(str(DOSSIER / "model_quantized.onnx"), options, providers=["CPUExecutionProvider"])
    _etat["session"], _etat["tok"] = session, tok
    threading.Thread(target=_surveiller_inactivite, daemon=True).start()


def _surveiller_inactivite():
    while True:
        time.sleep(60)
        with _verrou:
            if _etat["session"] is None:
                return
            if time.time() - _etat["dernier"] > INACTIVITE:
                _etat["session"] = _etat["tok"] = None
                return


def encoder(textes: list[str], requete: bool = False):
    """Vecteurs normalisés (numpy float32, une ligne par texte). None si le modèle n'est pas disponible."""
    import numpy as np
    if not textes or not active() or not disponible():
        return None
    with _verrou:
        try:
            if _etat["session"] is None:
                _charger()
        except Exception as e:
            _etat["erreur"] = str(e)
            return None
        _etat["dernier"] = time.time()
        session, tok = _etat["session"], _etat["tok"]
        noms = [i.name for i in session.get_inputs()]
        prefixe = "query: " if requete else "passage: "      # convention du modèle e5
        res = []
        for i in range(0, len(textes), 32):
            lot = tok.encode_batch([prefixe + t for t in textes[i:i + 32]])
            ids = np.array([x.ids for x in lot], dtype=np.int64)
            masque = np.array([x.attention_mask for x in lot], dtype=np.int64)
            entree = {"input_ids": ids, "attention_mask": masque}
            if "token_type_ids" in noms:
                entree["token_type_ids"] = np.zeros_like(ids)
            h = session.run(None, entree)[0]
            v = (h * masque[..., None]).sum(1) / np.maximum(masque.sum(1, keepdims=True), 1)
            res.append(v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9))
        return np.vstack(res).astype(np.float32)


# ---------- index : un vecteur par texte, calculé une seule fois ----------
def _empreinte(texte: str) -> str:
    return hashlib.sha1(texte.strip().lower().encode("utf-8")).hexdigest()[:20]


class Index:
    """Vecteurs déjà calculés (nom : « faits », « historique »…), sur cet appareil seulement."""

    def __init__(self, nom: str):
        self.fichier = DOSSIER_INDEX / f"index_{nom}.npz"
        self.vecteurs: dict = {}
        self._lu = False
        self._verrou = threading.Lock()

    def _lire(self):
        if self._lu:
            return
        self._lu = True
        try:
            import numpy as np
            with np.load(self.fichier) as z:
                self.vecteurs = dict(zip(z["cles"].tolist(), z["vecteurs"].astype(np.float32)))
        except Exception:
            self.vecteurs = {}

    def _ecrire(self):
        import numpy as np
        if not self.vecteurs:
            return
        DOSSIER_INDEX.mkdir(parents=True, exist_ok=True)
        tmp = self.fichier.with_suffix(".tmp.npz")
        cles = list(self.vecteurs)
        np.savez_compressed(tmp, cles=np.array(cles), vecteurs=np.stack([self.vecteurs[c] for c in cles]).astype(np.float16))
        tmp.replace(self.fichier)

    def matrice(self, textes: list[str], garder: bool = True):
        """Vecteurs des textes (calcule ceux qui manquent). garder : oublie ceux des textes disparus."""
        import numpy as np
        with self._verrou:
            self._lire()
            cles = [_empreinte(t) for t in textes]
            manquants = [(c, t) for c, t in dict(zip(cles, textes)).items() if c not in self.vecteurs]
            change = False
            if manquants:
                v = encoder([t for _, t in manquants])
                if v is None:
                    return None
                for (c, _), x in zip(manquants, v):
                    self.vecteurs[c] = x
                change = True
            if garder and len(self.vecteurs) > len(set(cles)) * 1.5 + 50:
                vivants = set(cles)
                self.vecteurs = {c: v for c, v in self.vecteurs.items() if c in vivants}
                change = True
            if change:
                try:
                    self._ecrire()
                except OSError:
                    pass
            return np.stack([self.vecteurs[c] for c in cles]).astype(np.float32) if cles else None


_index: dict = {}


def index(nom: str) -> Index:
    if nom not in _index:
        _index[nom] = Index(nom)
    return _index[nom]


# ---------- classement : sens + mots exacts ----------
def classer(requete: str, textes: list[str], k: int = 10, nom_index: str = "", seuil: float = 0.0) -> list[tuple[int, float]]:
    """Les k textes les plus proches de la requête : [(position, score)], meilleur d'abord.
    Score = similarité de sens (si le modèle est là) + bonus par mot exact retrouvé (noms propres, sigles)."""
    from .recherche_transcriptions import mots, normaliser, score as score_mots
    if not textes or not requete.strip():
        return []
    cles = mots(requete)
    lexical = [score_mots(normaliser(t), cles) / max(1, len(cles)) if cles else 0.0 for t in textes]
    sens = None
    try:
        q = encoder([requete], requete=True)
        if q is not None:
            m = index(nom_index).matrice(textes) if nom_index else encoder(textes)
            if m is not None:
                sens = (m @ q[0]).tolist()
    except Exception as e:
        _etat["erreur"] = str(e)
    if sens is None:   # pas de modèle : les mots seuls, comme avant
        res = [(i, s) for i, s in enumerate(lexical) if s > 0]
    else:
        # e5 donne des similarités serrées (~0,75 sans rapport, ~0,80+ lié) : un mot exact retrouvé pèse autant
        # qu'un net écart de sens (un nom propre ou un sigle ne doit jamais être raté)
        res = [(i, s + 0.08 * lexical[i]) for i, s in enumerate(sens) if s >= seuil or lexical[i] > 0]
    res.sort(key=lambda x: -x[1])
    return res[:k]


def etat() -> dict:
    return {"active": active(), "disponible": disponible(), "telechargement": bool(_etat["telechargement"]),
            "charge": _etat["session"] is not None, "erreur": _etat["erreur"], "modele": NOM_MODELE}
