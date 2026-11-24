"""Telegram : parle à Wesley depuis n'importe où, par écrit ou par message vocal, sans App Store.

- Tu crées ton bot une fois avec @BotFather (Telegram) et tu colles son jeton dans Connecteurs › Telegram.
- Sécurité : le bot ne répond qu'à TOI. Au premier lancement, Wesley affiche un code ; tu envoies
  « /start CODE » à ton bot, et ta conversation est reliée. Tout autre compte Telegram est ignoré.
- Un seul ordinateur répond (celui choisi, sinon le premier qui démarre le bot) : deux ordinateurs ne se
  disputent pas les messages. Il exécute la demande avec tous ses outils et répond par écrit.
- Messages vocaux : transcrits sur l'ordinateur (Whisper, local) puis traités comme un texte.
- Photos et fichiers : enregistrés sur l'ordinateur (Téléchargements/Telegram) ; Wesley peut les lire, les ranger…
- Wesley peut t'envoyer un message ou un fichier (outils telegram_envoyer, telegram_envoyer_fichier), et, si tu
  le veux, ses annonces (automatisations, rappels) arrivent aussi sur Telegram.
"""
import os
import random
import threading
import time
from pathlib import Path

import requests

from .config import MACHINE, RACINE
from .connecteurs import Connecteur, _ecrire, _lire

API = "https://api.telegram.org"
MAX_TEXTE = 4000
INACTIVITE = 3600       # s : au-delà, la conversation Telegram repart de zéro (la mémoire, elle, reste)
CONSIGNE = ("[Message reçu sur Telegram : l'utilisateur n'est peut-être pas devant l'ordinateur. Réponds par écrit, "
            "court et clair (pas de mise en page lourde). Pour lui envoyer un fichier, utilise telegram_envoyer_fichier.]\n")


class Telegram(Connecteur):
    type = "telegram"
    nom = "Telegram"
    description = "Parle à Wesley depuis ton téléphone (textes, vocaux, photos, fichiers), où que tu sois."
    icone = "send"
    champs = [
        {"nom": "jeton", "libelle": "Jeton du bot", "type": "secret", "aide": "donné par @BotFather (123456:ABC…)"},
        {"nom": "appareil", "libelle": "Ordinateur qui répond", "type": "text", "requis": False,
         "aide": "vide = le premier qui démarre le bot (il se l'attribue)"},
        {"nom": "annonces", "libelle": "Recevoir aussi les annonces de Wesley", "type": "choix", "choix": ["oui", "non"],
         "requis": False},
        {"nom": "chats", "libelle": "Conversation reliée", "type": "text", "requis": False,
         "aide": "rempli tout seul quand tu envoies « /start CODE » à ton bot"},
    ]
    aide = ("1. Sur Telegram, écris à @BotFather : /newbot, choisis un nom, puis un identifiant finissant par « bot ».\n"
            "2. Copie le jeton qu'il te donne (123456:ABC…) et colle-le ici.\n"
            "3. Enregistre : Wesley affiche un code. Envoie « /start CODE » à ton bot pour relier ta conversation.")

    def __init__(self, cid, conf):
        super().__init__(cid, conf)
        self._stop = threading.Event()
        self.code = ""
        self.agents: dict = {}   # chat -> (Wesley, dernière activité)

    # ---------- API ----------
    def _api(self, methode: str, delai=40, fichiers=None, **params):
        """Appel à l'API des bots ; delai = attente réseau maximale (« timeout » est un paramètre de Telegram)."""
        r = requests.post(f"{API}/bot{self.v('jeton')}/{methode}", data=params if fichiers else None,
                          json=None if fichiers else params, files=fichiers, timeout=delai)
        d = r.json()
        if not d.get("ok"):
            raise RuntimeError(d.get("description") or f"HTTP {r.status_code}")
        return d["result"]

    def chats(self) -> list[int]:
        return [int(x) for x in str(self.conf.get("chats", "")).replace(" ", "").split(",") if x.strip("-").isdigit()]

    def repond_ici(self) -> bool:
        return not self.conf.get("appareil") or self.conf["appareil"] == MACHINE

    def _relier(self, chat: int):
        """Enregistre la conversation reliée (et cet ordinateur comme celui qui répond) dans les connecteurs."""
        d = _lire()
        x = d.get(self.cid)
        if x:
            x.setdefault("conf", {})["chats"] = ",".join(str(c) for c in sorted(set(self.chats() + [chat])))
            x["conf"]["appareil"] = x["conf"].get("appareil") or MACHINE
            self.conf = x["conf"]
            _ecrire(d)

    def _s_attribuer(self):
        if self.conf.get("appareil"):
            return
        d = _lire()
        x = d.get(self.cid)
        if x and not x.get("conf", {}).get("appareil"):
            x.setdefault("conf", {})["appareil"] = MACHINE
            self.conf = x["conf"]
            _ecrire(d)

    # ---------- démarrage ----------
    def demarrer(self):
        super().demarrer()
        if not self.repond_ici():
            self.erreur = ""
            return
        moi = self._api("getMe", delai=15)
        self._s_attribuer()
        if not self.chats():
            self.code = f"{random.randint(0, 999999):06d}"
            self.erreur = f"À relier : envoie « /start {self.code} » à @{moi.get('username')} sur Telegram."
        threading.Thread(target=self._boucle, daemon=True, name=f"telegram-{self.cid}").start()

    def arreter(self):
        self._stop.set()
        super().arreter()

    def tester(self):
        moi = self._api("getMe", delai=15)
        relie = "conversation reliée" if self.chats() else f"envoie « /start {self.code or 'CODE'} » au bot pour le relier"
        return f"Bot @{moi.get('username')} prêt ({relie}). Répond depuis : {self.conf.get('appareil') or MACHINE}."

    def _boucle(self):
        decalage = 0
        while not self._stop.is_set():
            try:
                for u in self._api("getUpdates", delai=45, offset=decalage, timeout=30):   # attente longue chez Telegram
                    decalage = u["update_id"] + 1
                    m = u.get("message") or {}
                    if m:
                        threading.Thread(target=self._message, args=(m,), daemon=True).start()
            except Exception as e:
                if "Conflict" in str(e):
                    self.erreur = "Un autre ordinateur (ou programme) lit déjà les messages de ce bot."
                time.sleep(10)

    # ---------- messages reçus ----------
    def _message(self, m: dict):
        chat = int(m["chat"]["id"])
        texte = (m.get("text") or m.get("caption") or "").strip()
        if chat not in self.chats():
            if self.code and texte.replace("/start", "").strip() == self.code:
                self._relier(chat)
                self.code, self.erreur = "", ""
                self.envoyer("C'est relié 👋 Je suis Wesley : écris-moi ou envoie un vocal, je m'en occupe sur ton ordinateur.", chat)
            return   # inconnu : ignoré (jamais de réponse qui confirmerait que le bot existe)
        try:
            self._api("sendChatAction", delai=10, chat_id=chat, action="typing")
        except Exception:
            pass
        try:
            demande = self._demande(m, texte)
        except Exception as e:
            self.envoyer(f"Je n'ai pas pu lire ce message : {e}", chat)
            return
        if not demande:
            return
        reponse = self._repondre(chat, demande)
        self.envoyer(reponse or "C'est fait.", chat)

    def _dossier(self) -> Path:
        d = Path.home() / "Downloads" / "Telegram"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _telecharger(self, file_id: str, nom: str) -> Path:
        f = self._api("getFile", delai=20, file_id=file_id)
        r = requests.get(f"{API}/file/bot{self.v('jeton')}/{f['file_path']}", timeout=120)
        r.raise_for_status()
        chemin = self._dossier() / nom
        chemin.write_bytes(r.content)
        return chemin

    def _demande(self, m: dict, texte: str) -> str:
        if m.get("voice") or m.get("audio"):
            v = m.get("voice") or m.get("audio")
            chemin = self._telecharger(v["file_id"], f"vocal-{int(time.time())}.ogg")
            try:
                dit = transcrire(chemin)
            finally:
                chemin.unlink(missing_ok=True)
            if not dit:
                return ""
            self.envoyer(f"🎤 « {dit} »", int(m["chat"]["id"]))
            return dit
        if m.get("photo"):
            p = m["photo"][-1]
            chemin = self._telecharger(p["file_id"], f"photo-{int(time.time())}.jpg")
            return f"[Photo reçue, enregistrée ici : {chemin}]\n{texte or 'Regarde cette photo.'}"
        if m.get("document"):
            doc = m["document"]
            nom = os.path.basename(doc.get("file_name") or f"fichier-{int(time.time())}")
            chemin = self._telecharger(doc["file_id"], nom)
            return f"[Fichier reçu, enregistré ici : {chemin}]\n{texte or 'Voici un fichier.'}"
        if texte.startswith("/start"):
            return ""
        return texte

    def _repondre(self, chat: int, demande: str) -> str:
        from .agent import Wesley
        agent, vu = self.agents.get(chat, (None, 0))
        if agent is None or time.time() - vu > INACTIVITE:
            agent = Wesley()
        self.agents[chat] = (agent, time.time())
        try:
            return agent.demander(CONSIGNE + demande).strip()
        except Exception as e:
            return f"Erreur sur {MACHINE} : {e}"

    # ---------- envoyer ----------
    def envoyer(self, texte: str, chat: int | None = None):
        for c in ([chat] if chat else self.chats()):
            for i in range(0, max(1, len(texte)), MAX_TEXTE):
                self._api("sendMessage", delai=20, chat_id=c, text=texte[i:i + MAX_TEXTE])

    def envoyer_fichier(self, chemin: str, legende: str = ""):
        p = Path(os.path.expanduser(chemin))
        if not p.is_file():
            raise FileNotFoundError(f"Fichier introuvable : {p}")
        if p.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("Fichier trop gros pour Telegram (50 Mo au maximum).")
        for c in self.chats():
            with open(p, "rb") as f:
                self._api("sendDocument", delai=300, fichiers={"document": (p.name, f)}, chat_id=str(c), caption=legende[:1000])

    def fonctions(self):
        def telegram_envoyer(texte: str):
            """Envoie un message à l'utilisateur sur Telegram (quand il n'est pas devant l'ordinateur, ou qu'il le demande).
            texte: le message"""
            if not self.chats():
                return "Le bot Telegram n'est pas encore relié à la conversation de l'utilisateur."
            self.envoyer(texte)
            return "Message envoyé sur Telegram."

        def telegram_envoyer_fichier(chemin: str, legende: str = ""):
            """Envoie un fichier de cet ordinateur à l'utilisateur sur Telegram (PDF, photo, document… jusqu'à 50 Mo).
            chemin: chemin du fichier sur cet ordinateur
            legende: texte accompagnant le fichier (facultatif)"""
            if not self.chats():
                return "Le bot Telegram n'est pas encore relié à la conversation de l'utilisateur."
            self.envoyer_fichier(chemin, legende)
            return f"Fichier {os.path.basename(chemin)} envoyé sur Telegram."
        return [("telegram_envoyer", telegram_envoyer), ("telegram_envoyer_fichier", telegram_envoyer_fichier)]


# ---------- vocal → texte (Whisper local) ----------
_whisper = {}


def transcrire(chemin: Path) -> str:
    from .config import CONFIG
    from .modeles import charger_whisper
    if "m" not in _whisper:
        _whisper["m"] = charger_whisper(CONFIG.get("whisper_modele") or "small", cpu_threads=4)
    segs, _ = _whisper["m"].transcribe(str(chemin), language=(CONFIG.get("langue") or "fr")[:2], vad_filter=True)
    return " ".join(s.text.strip() for s in segs).strip()


def transmettre_annonce(texte: str, titre: str = ""):
    """Annonces de Wesley (automatisations, rappels) aussi envoyées sur Telegram, si l'utilisateur l'a choisi."""
    from . import connecteurs
    for c in list(connecteurs.INSTANCES.values()):
        if isinstance(c, Telegram) and c.conf.get("annonces") == "oui" and c.chats() and c.repond_ici() and not c.erreur:
            try:
                c.envoyer(f"🔔 {titre} : {texte}" if titre and titre != "Wesley" else f"🔔 {texte}")
            except Exception as e:
                print(f"  ! Annonce Telegram : {e}")
