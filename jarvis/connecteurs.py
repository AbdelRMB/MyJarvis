"""Connecteurs : services externes qui ajoutent des outils à Jarvis (mails, agenda, GitHub, Notion, serveurs MCP…).

- La liste des connecteurs et leurs réglages non secrets sont dans le dossier partagé (connecteurs.json) :
  ils apparaissent sur tous tes PC.
- Les mots de passe / jetons / clés sont dans le trousseau de chaque appareil (keyring) ET dans le coffre du compte
  (chiffré avec le mot de passe du compte, illisible par le serveur) : ils suivent l'utilisateur sur ses appareils.
"""
import asyncio
import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import smtplib
import ssl
import threading
import traceback
from datetime import datetime, timedelta
from email.message import EmailMessage

import requests

from . import outils
from .config import PARTAGE

FICHIER = PARTAGE / "connecteurs.json"
SERVICE = "Jarvis"
_verrou = threading.RLock()
INSTANCES: dict = {}   # cid -> instance démarrée


# ---------- identifiants (coffre-fort Windows) ----------
_secrets_lus: dict = {}   # lus une seule fois par lancement (chaque lecture du trousseau peut afficher une demande)


def secret(cid, champ):
    nom = f"{cid}:{champ}"
    if nom not in _secrets_lus:
        try:
            import keyring
            _secrets_lus[nom] = keyring.get_password(SERVICE, nom) or ""
        except Exception:
            _secrets_lus[nom] = ""
    return _secrets_lus[nom]


def definir_secret(cid, champ, valeur):
    _secrets_lus[f"{cid}:{champ}"] = valeur or ""
    import keyring
    if valeur:
        keyring.set_password(SERVICE, f"{cid}:{champ}", valeur)
    else:
        try:
            keyring.delete_password(SERVICE, f"{cid}:{champ}")
        except Exception:
            pass
    from . import compte
    compte.secret_modifie(f"{cid}:{champ}", valeur)


# ---------- base ----------
class Connecteur:
    type = ""
    nom = ""
    description = ""
    icone = "plug"
    champs: list = []      # {nom, libelle, type: text|secret|url|choix|zone, aide, requis, choix}
    aide = ""              # étapes pour obtenir les identifiants
    prefixe = ""

    def __init__(self, cid, conf):
        self.cid, self.conf = cid, conf or {}
        self.erreur = ""

    def v(self, champ):
        d = next((c for c in self.champs if c["nom"] == champ), {})
        return secret(self.cid, champ) if d.get("type") == "secret" else str(self.conf.get(champ, "")).strip()

    def manquants(self):
        return [c["libelle"] for c in self.champs if c.get("requis", True) and not self.v(c["nom"])]

    def fonctions(self):
        """Liste de (nom_outil, fonction) — la docstring sert de description."""
        return []

    def etiquette(self) -> str:
        """Nom lisible de ce compte (plusieurs comptes du même type sont possibles)."""
        return (self.conf.get("compte") or self.conf.get("email") or self.conf.get("nom") or self.cid.split(":")[-1]).strip()

    def suffixe(self) -> str:
        """Le 1er compte d'un type garde les noms d'outils d'origine ; les suivants ont un suffixe (gmail_lire__travail)."""
        if self.cid == self.type:
            return ""
        return re.sub(r"[^a-z0-9]+", "_", self.etiquette().lower()).strip("_")[:20] or self.cid.split(":")[-1][:20]

    def demarrer(self):
        suffixe = self.suffixe()
        for nom, fn in self.fonctions():
            nom_outil = f"{nom}__{suffixe}"[:64] if suffixe else nom
            outils.ajouter_fonction(fn, nom_outil, source=self.cid,
                                    prefixe_desc=f"[{self.nom} — {self.etiquette()}] " if suffixe else f"[{self.etiquette()}] ")

    def arreter(self):
        outils.retirer_source(self.cid)

    def tester(self) -> str:
        return "OK"


# ---------- e-mail (IMAP / SMTP) ----------
def _dec(v):
    if not v:
        return ""
    return str(email.header.make_header(email.header.decode_header(v)))


def _texte(msg, limite=6000):
    """Texte lisible d'un e-mail (partie texte, sinon HTML nettoyé)."""
    texte, html = "", ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        try:
            contenu = part.get_payload(decode=True)
            if contenu is None:
                continue
            contenu = contenu.decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if part.get_content_type() == "text/plain" and not texte:
            texte = contenu
        elif part.get_content_type() == "text/html" and not html:
            html = contenu
    if not texte and html:
        from bs4 import BeautifulSoup
        texte = BeautifulSoup(html, "html.parser").get_text("\n")
    texte = re.sub(r"\n\s*\n+", "\n\n", texte).strip()
    return texte[:limite]


class Mail(Connecteur):
    type = "mail"
    nom = "Autre messagerie (IMAP)"
    description = "Lire, chercher et envoyer des e-mails avec n'importe quelle messagerie compatible IMAP (Free, Orange, iCloud, Yahoo…)."
    icone = "mail"
    prefixe = "mail"
    champs = [
        {"nom": "email", "libelle": "Adresse e-mail", "type": "text"},
        {"nom": "mot_de_passe", "libelle": "Mot de passe (ou mot de passe d'application)", "type": "secret"},
        {"nom": "imap", "libelle": "Serveur IMAP", "type": "text", "aide": "ex : imap.free.fr"},
        {"nom": "smtp", "libelle": "Serveur SMTP", "type": "text", "aide": "ex : smtp.free.fr (port 465)"},
    ]
    aide = "Les paramètres IMAP/SMTP sont dans l'aide de ta messagerie. Outlook/Hotmail n'accepte plus ce mode de connexion."

    def hote_imap(self):
        return self.v("imap")

    def hote_smtp(self):
        return self.v("smtp")

    def _imap(self):
        m = imaplib.IMAP4_SSL(self.hote_imap(), timeout=20)
        m.login(self.v("email"), self.v("mot_de_passe"))
        return m

    def _resume(self, m, uids):
        lignes = []
        for uid in uids:
            t, d = m.uid("FETCH", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if t != "OK" or not d or not isinstance(d[0], tuple):
                continue
            h = email.message_from_bytes(d[0][1])
            lu = "\\Seen" in d[0][0].decode(errors="ignore")
            lignes.append(f"[{uid.decode() if isinstance(uid, bytes) else uid}] {'' if lu else '(NON LU) '}"
                          f"{_dec(h['Date'])[:25]} — {_dec(h['From'])} — {_dec(h['Subject'])}")
        return "\n".join(lignes) or "Aucun e-mail."

    def _chercher(self, m, critere):
        t, d = m.uid("SEARCH", None, critere)
        return d[0].split() if t == "OK" and d and d[0] else []

    def fonctions(self):
        p = self.prefixe

        def recents(nombre: int = 10, non_lus_seulement: bool = False):
            """Liste les derniers e-mails reçus (expéditeur, sujet, date, identifiant).
            nombre: combien d'e-mails (défaut 10)
            non_lus_seulement: true pour ne voir que les non lus"""
            m = self._imap()
            try:
                m.select("INBOX", readonly=True)
                uids = self._chercher(m, "UNSEEN" if non_lus_seulement else "ALL")
                return self._resume(m, list(reversed(uids[-max(1, min(int(nombre), 50)):])))
            finally:
                m.logout()

        def chercher(recherche: str, nombre: int = 10):
            """Cherche des e-mails (dans l'expéditeur, le sujet et le texte).
            recherche: mots à chercher (ex : un nom, « facture », une adresse)
            nombre: nombre maximum de résultats"""
            m = self._imap()
            try:
                m.select("INBOX", readonly=True)
                q = recherche.replace('"', "")
                if q.isascii():
                    uids = self._chercher(m, f'(OR OR FROM "{q}" SUBJECT "{q}" TEXT "{q}")')
                else:
                    m.literal = q.encode("utf-8")
                    t, d = m.uid("SEARCH", "CHARSET", "UTF-8", "TEXT")
                    uids = d[0].split() if t == "OK" and d and d[0] else []
                return self._resume(m, list(reversed(uids[-max(1, min(int(nombre), 50)):])))
            finally:
                m.logout()

        def lire(identifiant: str):
            """Lit le contenu complet d'un e-mail.
            identifiant: le numéro entre crochets donné par la liste des e-mails"""
            m = self._imap()
            try:
                m.select("INBOX", readonly=True)
                t, d = m.uid("FETCH", identifiant.strip("[] "), "(BODY.PEEK[])")
                if t != "OK" or not d or not isinstance(d[0], tuple):
                    return "E-mail introuvable."
                msg = email.message_from_bytes(d[0][1])
                pj = [_dec(x.get_filename()) for x in msg.walk() if x.get_filename()]
                return (f"De : {_dec(msg['From'])}\nÀ : {_dec(msg['To'])}\nDate : {_dec(msg['Date'])}\n"
                        f"Sujet : {_dec(msg['Subject'])}\n" + (f"Pièces jointes : {', '.join(pj)}\n" if pj else "")
                        + "\n" + _texte(msg))
            finally:
                m.logout()

        def envoyer(destinataire: str, sujet: str, message: str):
            """Envoie un e-mail depuis l'adresse de l'utilisateur.
            destinataire: adresse(s) e-mail, séparées par des virgules
            sujet: objet du mail
            message: texte du mail"""
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = self.v("email"), destinataire, sujet
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg.set_content(message)
            with smtplib.SMTP_SSL(self.hote_smtp(), 465, context=ssl.create_default_context(), timeout=30) as s:
                s.login(self.v("email"), self.v("mot_de_passe"))
                s.send_message(msg)
            return f"E-mail envoyé à {destinataire}."

        return [(f"{p}_recents", recents), (f"{p}_chercher", chercher), (f"{p}_lire", lire), (f"{p}_envoyer", envoyer)]

    def tester(self):
        m = self._imap()
        try:
            m.select("INBOX", readonly=True)
            n = len(self._chercher(m, "UNSEEN"))
            return f"Connecté à {self.v('email')} — {n} e-mail(s) non lu(s)."
        finally:
            m.logout()


class Gmail(Mail):
    type = "gmail"
    nom = "Gmail"
    description = "Lire, chercher (avec la recherche Gmail) et envoyer des e-mails depuis ton compte Gmail."
    prefixe = "gmail"
    champs = [
        {"nom": "email", "libelle": "Adresse Gmail", "type": "text"},
        {"nom": "mot_de_passe", "libelle": "Mot de passe d'application (16 lettres)", "type": "secret"},
    ]
    aide = ("1. Active la validation en 2 étapes sur ton compte Google.\n"
            "2. Va sur myaccount.google.com/apppasswords, crée un mot de passe d'application nommé « Jarvis ».\n"
            "3. Colle les 16 lettres ici (pas ton vrai mot de passe Google).")

    def hote_imap(self):
        return "imap.gmail.com"

    def hote_smtp(self):
        return "smtp.gmail.com"

    def fonctions(self):
        fs = dict(super().fonctions())

        def chercher(recherche: str, nombre: int = 10):
            """Cherche des e-mails avec la syntaxe de recherche Gmail.
            recherche: comme dans Gmail (ex : « from:amazon facture », « is:unread », « newer_than:7d »)
            nombre: nombre maximum de résultats"""
            m = self._imap()
            try:
                m.select("INBOX", readonly=True)
                m.literal = recherche.encode("utf-8")
                t, d = m.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW")
                uids = d[0].split() if t == "OK" and d and d[0] else []
                return self._resume(m, list(reversed(uids[-max(1, min(int(nombre), 50)):])))
            finally:
                m.logout()

        fs["gmail_chercher"] = chercher
        return list(fs.items())


# ---------- agenda (lien iCal) ----------
class Agenda(Connecteur):
    type = "agenda"
    nom = "Agenda (Google, Outlook, iCloud)"
    description = "Consulter tes prochains événements via le lien secret iCal de ton agenda (lecture seule)."
    icone = "calendar"
    champs = [{"nom": "url", "libelle": "Adresse secrète au format iCal", "type": "secret",
               "aide": "Lien qui se termine par .ics"}]
    aide = ("Google Agenda : Paramètres > ton agenda > « Adresse secrète au format iCal ».\n"
            "Outlook.com : Paramètres > Calendrier > Calendriers partagés > Publier > lien ICS.\n"
            "Ce lien donne accès à ton agenda : il reste sur ce PC.")

    def _evenements(self, debut, fin):
        import icalendar
        import recurring_ical_events
        r = requests.get(self.v("url").replace("webcal://", "https://"), timeout=20)
        r.raise_for_status()
        cal = icalendar.Calendar.from_ical(r.content)
        evs = []
        for e in recurring_ical_events.of(cal).between(debut, fin):
            d = e.get("DTSTART").dt
            evs.append((d if isinstance(d, datetime) else datetime(d.year, d.month, d.day), isinstance(d, datetime),
                        str(e.get("SUMMARY", "(sans titre)")), str(e.get("LOCATION", "") or "")))
        evs.sort(key=lambda x: x[0].replace(tzinfo=None))
        return evs

    def fonctions(self):
        def evenements(jours: int = 7):
            """Liste les événements de l'agenda à venir.
            jours: sur combien de jours à partir d'aujourd'hui (défaut 7)"""
            debut = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            evs = self._evenements(debut, debut + timedelta(days=max(1, min(int(jours), 90))))
            if not evs:
                return "Aucun événement sur cette période."
            jours_fr = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
            lignes = []
            for d, h, t, lieu in evs:
                d = d.astimezone() if d.tzinfo else d
                lignes.append(f"{jours_fr[d.weekday()]} {d:%d/%m}" + (f" {d:%H:%M}" if h else " (journée)")
                              + f" — {t}" + (f" @ {lieu}" if lieu else ""))
            return "\n".join(lignes)
        return [("agenda_evenements", evenements)]

    def tester(self):
        debut = datetime.now()
        return f"Agenda lu : {len(self._evenements(debut, debut + timedelta(days=30)))} événement(s) dans les 30 jours."


# ---------- GitHub ----------
class GitHub(Connecteur):
    type = "github"
    nom = "GitHub"
    description = "Tes dépôts, issues, pull requests et notifications GitHub."
    icone = "github"
    champs = [{"nom": "jeton", "libelle": "Jeton d'accès personnel", "type": "secret"}]
    aide = "github.com > Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token."

    def _api(self, methode, chemin, **kw):
        r = requests.request(methode, f"https://api.github.com{chemin}", timeout=20, headers={
            "Authorization": f"Bearer {self.v('jeton')}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub {r.status_code} : {r.json().get('message', r.text)[:200]}")
        return r.json()

    def fonctions(self):
        def depots():
            """Liste tes dépôts GitHub (les plus récemment modifiés d'abord)."""
            return "\n".join(f"{d['full_name']}{' (privé)' if d['private'] else ''} — ★{d['stargazers_count']} — "
                             f"maj {d['pushed_at'][:10]} — {d.get('description') or ''}"
                             for d in self._api("GET", "/user/repos?sort=pushed&per_page=30"))

        def issues(depot: str, etat: str = "open"):
            """Liste les issues et pull requests d'un dépôt.
            depot: propriétaire/nom (ex : AbdelRMB/jarvis)
            etat: open | closed | all"""
            items = self._api("GET", f"/repos/{depot}/issues?state={etat}&per_page=30")
            return "\n".join(f"#{i['number']} {'[PR] ' if 'pull_request' in i else ''}{i['title']} — {i['user']['login']}"
                             for i in items) or "Aucune."

        def creer_issue(depot: str, titre: str, description: str = ""):
            """Crée une issue dans un dépôt.
            depot: propriétaire/nom
            titre: titre de l'issue
            description: texte de l'issue"""
            i = self._api("POST", f"/repos/{depot}/issues", json={"title": titre, "body": description})
            return f"Issue #{i['number']} créée : {i['html_url']}"

        def notifications():
            """Tes notifications GitHub non lues."""
            ns = self._api("GET", "/notifications?per_page=30")
            return "\n".join(f"{n['repository']['full_name']} — {n['subject']['type']} — {n['subject']['title']}"
                             for n in ns) or "Aucune notification."

        return [("github_depots", depots), ("github_issues", issues), ("github_creer_issue", creer_issue),
                ("github_notifications", notifications)]

    def tester(self):
        return f"Connecté en tant que {self._api('GET', '/user')['login']}."


# ---------- Notion ----------
class Notion(Connecteur):
    type = "notion"
    nom = "Notion"
    description = "Chercher, lire et compléter tes pages Notion."
    icone = "notebook"
    champs = [{"nom": "jeton", "libelle": "Jeton d'intégration interne", "type": "secret"}]
    aide = ("1. notion.so/profile/integrations > Nouvelle intégration (type interne) > copie le jeton.\n"
            "2. Dans Notion, sur chaque page à partager : ••• > Connexions > ajoute ton intégration.")

    def _api(self, methode, chemin, **kw):
        r = requests.request(methode, f"https://api.notion.com/v1{chemin}", timeout=20, headers={
            "Authorization": f"Bearer {self.v('jeton')}", "Notion-Version": "2022-06-28"}, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"Notion {r.status_code} : {r.json().get('message', r.text)[:200]}")
        return r.json()

    @staticmethod
    def _titre(o):
        for p in (o.get("properties") or {}).values():
            if p.get("type") == "title":
                return "".join(t["plain_text"] for t in p["title"]) or "(sans titre)"
        return "".join(t["plain_text"] for t in o.get("title", [])) or "(sans titre)"

    def fonctions(self):
        def chercher(texte: str):
            """Cherche des pages et bases de données dans Notion.
            texte: mots à chercher dans les titres"""
            r = self._api("POST", "/search", json={"query": texte, "page_size": 15})
            return "\n".join(f"[{o['id']}] {o['object']} — {self._titre(o)} — {o.get('url', '')}"
                             for o in r["results"]) or "Rien trouvé (la page est-elle partagée avec l'intégration ?)."

        def lire(page_id: str):
            """Lit le contenu texte d'une page Notion.
            page_id: identifiant de la page (donné par notion_chercher)"""
            r = self._api("GET", f"/blocks/{page_id}/children?page_size=100")
            lignes = []
            for b in r["results"]:
                contenu = b.get(b["type"], {})
                texte = "".join(t["plain_text"] for t in contenu.get("rich_text", []))
                if texte:
                    puce = "- " if "list_item" in b["type"] else ("# " if b["type"].startswith("heading") else "")
                    coche = ("[x] " if contenu.get("checked") else "[ ] ") if b["type"] == "to_do" else ""
                    lignes.append(puce + coche + texte)
            return "\n".join(lignes) or "(page vide)"

        def ajouter(page_id: str, texte: str):
            """Ajoute un paragraphe à la fin d'une page Notion.
            page_id: identifiant de la page
            texte: texte à ajouter"""
            self._api("PATCH", f"/blocks/{page_id}/children", json={"children": [
                {"object": "block", "type": "paragraph",
                 "paragraph": {"rich_text": [{"type": "text", "text": {"content": texte[:1900]}}]}}]})
            return "Ajouté."

        return [("notion_chercher", chercher), ("notion_lire", lire), ("notion_ajouter", ajouter)]

    def tester(self):
        n = len(self._api("POST", "/search", json={"page_size": 100})["results"])
        return f"Connecté — {n} page(s) partagée(s) avec l'intégration."


# ---------- serveurs MCP (n'importe quel outil compatible) ----------
_boucle = None


def _boucle_mcp():
    global _boucle
    if _boucle is None:
        _boucle = asyncio.new_event_loop()
        threading.Thread(target=_boucle.run_forever, daemon=True, name="mcp").start()
    return _boucle


class MCP(Connecteur):
    type = "mcp"
    nom = "Serveur MCP"
    description = ("Branche n'importe quel outil compatible MCP (Model Context Protocol) : Notion, Slack, Spotify, "
                   "Home Assistant, bases de données… Ses outils deviennent ceux de Jarvis.")
    icone = "blocks"
    champs = [
        {"nom": "nom", "libelle": "Nom", "type": "text", "aide": "court, sans espace (ex : spotify)"},
        {"nom": "mode", "libelle": "Connexion", "type": "choix", "choix": ["commande", "url"]},
        {"nom": "commande", "libelle": "Commande", "type": "text", "requis": False,
         "aide": "Mode commande : ex « npx -y @nom/serveur-mcp » ou « uvx serveur-mcp »"},
        {"nom": "env", "libelle": "Variables d'environnement (CLE=valeur, une par ligne)", "type": "secret", "requis": False},
        {"nom": "url", "libelle": "Adresse (mode url)", "type": "text", "requis": False, "aide": "ex : https://…/mcp"},
        {"nom": "entete", "libelle": "En-tête Authorization (mode url)", "type": "secret", "requis": False,
         "aide": "ex : Bearer xxxxx"},
    ]
    aide = ("La page de chaque serveur MCP indique la commande à lancer (souvent avec npx, qui nécessite Node.js) "
            "ou l'adresse à utiliser, et les clés à mettre en variables d'environnement.")

    def __init__(self, cid, conf):
        super().__init__(cid, conf)
        self.session = None
        self.arret = None
        self.outils_mcp = []

    @property
    def court(self):
        return re.sub(r"\W+", "_", self.v("nom") or self.cid.split(":", 1)[-1]).strip("_").lower()[:20] or "mcp"

    def manquants(self):
        m = [] if self.v("nom") else ["Nom"]
        if self.v("mode") == "url":
            return m + ([] if self.v("url") else ["Adresse"])
        return m + ([] if self.v("commande") else ["Commande"])

    async def _vivre(self, pret):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
        self.arret = asyncio.Event()
        try:
            if self.v("mode") == "url":
                h = {"Authorization": self.v("entete")} if self.v("entete") else None
                transport = streamable_http_client(self.v("url"), http_client=create_mcp_http_client(headers=h))
            else:
                import shlex
                morceaux = [m.strip('"') for m in shlex.split(self.v("commande"), posix=False)]
                env = dict(os.environ)
                for l in self.v("env").splitlines():
                    if "=" in l:
                        k, val = l.split("=", 1)
                        env[k.strip()] = val.strip()
                commande = morceaux[0]
                if os.name == "nt" and commande in ("npx", "npm", "uvx", "pnpm", "yarn"):
                    commande += ".cmd" if commande != "uvx" else ".exe"
                transport = stdio_client(StdioServerParameters(command=commande, args=morceaux[1:], env=env),
                                         errlog=open(os.devnull, "w"))
            async with transport as flux:
                async with ClientSession(flux[0], flux[1]) as s:
                    await s.initialize()
                    self.session = s
                    r = await s.list_tools()
                    self.outils_mcp = [(t.name, t.description or "", t.input_schema) for t in r.tools]
                    pret.set_result(None)
                    await self.arret.wait()
        except BaseException as e:   # noqa: BLE001 — on remonte l'erreur au démarrage
            if not pret.done():
                pret.set_exception(e if isinstance(e, Exception) else RuntimeError(str(e)))
            self.erreur = str(e)[:300]
        finally:
            self.session = None

    def _appel(self, nom_mcp):
        def appel(args):
            if not self.session:
                return f"Erreur : le serveur MCP « {self.court} » n'est pas connecté."
            fut = asyncio.run_coroutine_threadsafe(self.session.call_tool(nom_mcp, args or {}), _boucle_mcp())
            r = fut.result(timeout=180)
            morceaux = []
            for c in getattr(r, "content", []) or []:
                morceaux.append(getattr(c, "text", None) or f"[{getattr(c, 'type', 'contenu')}]")
            texte = "\n".join(morceaux) or json.dumps(getattr(r, "structured_content", None) or {}, ensure_ascii=False)
            return ("Erreur : " if getattr(r, "is_error", False) else "") + texte
        return appel

    def demarrer(self):
        boucle = _boucle_mcp()
        pret = boucle.create_future()
        boucle.call_soon_threadsafe(lambda: asyncio.ensure_future(self._vivre(pret)))
        asyncio.run_coroutine_threadsafe(asyncio.wait_for(asyncio.shield(pret), 60), boucle).result(65)
        for nom, desc, schema in self.outils_mcp:
            nom_outil = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{self.court}__{nom}")[:64]
            outils.ajouter_brut(nom_outil, f"[{self.court}] {desc}", schema, self._appel(nom), source=self.cid)

    def arreter(self):
        super().arreter()
        if self.arret is not None:
            _boucle_mcp().call_soon_threadsafe(self.arret.set)

    def tester(self):
        return f"{len(self.outils_mcp)} outil(s) : " + ", ".join(n for n, _, _ in self.outils_mcp[:15])


# ---------- serveurs SSH (VPS) ----------
# Commandes sans risque (lecture) : jamais de confirmation, autorisées même en mode « lecture seule ».
_LECTURE = re.compile(r"^\s*(ls|ll|cat|head|tail|less|more|df|du|free|uptime|whoami|id|hostname|uname|ps|pgrep|who|w|date|"
                      r"stat|file|wc|grep|egrep|zgrep|find|which|ss|netstat|ip\s+(a|addr|route)|ping\s+-c|lsblk|nproc|lscpu|"
                      r"top\s+-bn1|systemctl\s+(status|is-active|is-enabled|list-units|list-timers)|journalctl|"
                      r"docker\s+(ps|logs|stats\s+--no-stream|images|inspect|volume\s+ls|network\s+ls)|"
                      r"docker\s+compose\s+(ps|logs|config)|apache2ctl\s+(-S|-t|configtest)|nginx\s+-t|"
                      r"certbot\s+certificates|git\s+(status|log|diff|branch|remote)|crontab\s+-l|echo|pwd)\b")


# « sudo » employé comme commande (début, après ; & | ( ou un espace), avec son éventuel -n déjà présent
_SUDO = re.compile(r"(^|[;&|(\s])sudo(?:\s+-n)?(?=\s|$)")


def commande_en_lecture(commande: str) -> bool:
    """Vraie si la commande ne fait que lire (chaque morceau d'une chaîne ; | && ||), sans redirection d'écriture."""
    if re.search(r"(^|[^>2&])>{1,2}(?!&)|\btee\b|\bsudo\b|`|\$\(", commande):
        return False
    morceaux = [m for m in re.split(r"\|\||&&|;|\|", commande) if m.strip()]
    return bool(morceaux) and all(_LECTURE.match(m) for m in morceaux)


def generer_cle_ssh(commentaire: str = "jarvis") -> dict:
    """Nouvelle paire de clés Ed25519 : la privée va dans le connecteur (puis le coffre du compte),
    la publique est à ajouter dans ~/.ssh/authorized_keys du serveur."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    privee = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                             serialization.NoEncryption()).decode()
    return {"privee": privee, "publique": _publique(k, commentaire)}


def _publique(k, commentaire="jarvis") -> str:
    from cryptography.hazmat.primitives import serialization
    return k.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                       serialization.PublicFormat.OpenSSH).decode() + f" {commentaire}"


def cle_publique_ssh(cid: str) -> str:
    """Clé publique correspondant à la clé privée enregistrée dans un connecteur SSH (vide s'il n'y en a pas)."""
    from cryptography.hazmat.primitives import serialization
    privee = secret(cid, "cle_privee").strip()
    if not privee:
        return ""
    phrase = (secret(cid, "phrase_cle") or "").encode() or None
    donnees = (privee + "\n").encode()
    erreur = None
    for charger in (serialization.load_ssh_private_key, serialization.load_pem_private_key):
        for mdp in dict.fromkeys((phrase, None)):   # une phrase restée d'une ancienne clé ne doit pas bloquer
            try:
                return _publique(charger(donnees, password=mdp))
            except Exception as e:
                erreur = e
    raise RuntimeError(str(erreur))


class SSH(Connecteur):
    type = "ssh"
    nom = "Serveur SSH (VPS)"
    description = "Piloter un serveur à distance : commandes, fichiers, état (disque, mémoire, Docker, services)."
    icone = "server"
    prefixe = "ssh"
    champs = [
        {"nom": "hote", "libelle": "Adresse du serveur", "type": "text", "aide": "IP ou nom de domaine (ex : 51.38.38.18)"},
        {"nom": "port", "libelle": "Port SSH", "type": "text", "requis": False, "aide": "22 par défaut"},
        {"nom": "utilisateur", "libelle": "Utilisateur", "type": "text", "aide": "ex : debian, ubuntu, abdel"},
        {"nom": "mode", "libelle": "Ce que Jarvis a le droit de faire", "type": "choix",
         "choix": ["confirmation", "lecture", "libre"]},
        {"nom": "sudo", "libelle": "Droits administrateur (sudo)", "type": "choix", "choix": ["non", "oui"],
         "aide": "Oui : sudo doit marcher SANS mot de passe pour cet utilisateur sur le serveur (/etc/sudoers.d). "
                 "Chaque commande sudo te demande toujours « Autoriser / Refuser », même en mode libre."},
        {"nom": "cle_privee", "libelle": "Clé privée SSH", "type": "secret", "requis": False, "multiligne": True,
         "aide": "Bouton « Générer une clé » ci-dessus, ou colle une clé existante (-----BEGIN OPENSSH PRIVATE KEY----- …). "
                 "Collée ici, elle suit ton compte sur tous tes appareils. Vide : clés de cet ordinateur (~/.ssh)."},
        {"nom": "phrase_cle", "libelle": "Phrase de passe de la clé", "type": "secret", "requis": False},
        {"nom": "mot_de_passe", "libelle": "Mot de passe", "type": "secret", "requis": False,
         "aide": "Seulement si le serveur se connecte par mot de passe (une clé est plus sûre)."},
    ]
    aide = ("Modes :\n- confirmation (conseillé) : Jarvis regarde librement, mais te demande « Autoriser / Refuser » "
            "avant toute commande qui modifie le serveur ;\n- lecture : il ne peut que regarder (logs, état, fichiers) ;\n"
            "- libre : il agit sans demander.\nsudo : désactivé par défaut. Activé, il ne demande jamais ton mot de passe "
            "(sudo sans mot de passe à configurer sur le serveur) et chaque commande sudo attend ton accord.")

    def mode(self):
        return self.conf.get("mode") or "confirmation"

    def sudo_permis(self):
        return self.conf.get("sudo") == "oui"

    def _client(self):
        import io
        import paramiko
        from .config import RACINE
        c = paramiko.SSHClient()
        connus = RACINE / "ssh_known_hosts"
        if connus.exists():
            c.load_host_keys(str(connus))
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())   # 1re connexion : empreinte retenue ensuite
        cle, phrase = self.v("cle_privee"), self.v("phrase_cle") or None
        pkey = None
        if cle:
            for classe in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
                try:
                    pkey = classe.from_private_key(io.StringIO(cle.strip() + "\n"), password=phrase)
                    break
                except Exception:
                    continue
            if pkey is None:
                raise RuntimeError("Clé privée illisible (format ou phrase de passe).")
        c.connect(self.v("hote"), port=int(self.v("port") or 22), username=self.v("utilisateur"), pkey=pkey,
                  password=self.v("mot_de_passe") or None, allow_agent=not (cle or self.v("mot_de_passe")),
                  look_for_keys=not (cle or self.v("mot_de_passe")), timeout=15, banner_timeout=15, auth_timeout=15)
        try:
            c.save_host_keys(str(connus))
        except Exception:
            pass
        return c

    def _executer(self, commande: str, delai=120) -> str:
        c = self._client()
        try:
            _, sortie, erreur = c.exec_command(commande, timeout=delai)
            code = sortie.channel.recv_exit_status()
            out, err = sortie.read().decode(errors="replace"), erreur.read().decode(errors="replace")
        finally:
            c.close()
        res = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip() or "(aucune sortie)"
        return (f"[code {code}]\n" if code else "") + res[-12000:]

    def _autorise(self, action: str, detail: str, toujours_demander=False) -> str:
        """« » si autorisé, sinon le message à renvoyer à Jarvis (toujours_demander : même en mode libre)."""
        if self.mode() == "libre" and not toujours_demander:
            return ""
        if self.mode() == "lecture":
            return f"Refusé : {self.etiquette()} est en lecture seule (Connecteurs › {self.nom}). Explique à l'utilisateur ce qu'il faudrait faire."
        from . import web
        if web.demander_confirmation(f"{self.etiquette()} : {action}", detail):
            return ""
        return "L'utilisateur a refusé cette action. Ne la relance pas sans son accord."

    def fonctions(self):
        def commande(commande: str):
            """(description fixée plus bas, selon que sudo est permis ou non)"""
            if _SUDO.search(commande):
                if not self.sudo_permis():
                    return (f"Refusé : sudo n'est pas activé pour {self.etiquette()}. Fais sans sudo, ou explique à "
                            f"l'utilisateur qu'il peut l'activer dans Connecteurs › {self.nom} › Droits administrateur.")
                commande = _SUDO.sub(r"\1sudo -n", commande)   # -n : jamais de demande de mot de passe
                refus = self._autorise("commande administrateur (sudo)", commande, toujours_demander=True)
                if refus:
                    return refus
            elif not commande_en_lecture(commande):
                refus = self._autorise("exécuter une commande", commande)
                if refus:
                    return refus
            res = self._executer(commande)
            if "sudo" in commande and "password is required" in res:
                res += ("\n[Jarvis] sudo demande un mot de passe : sur le serveur, l'utilisateur doit autoriser sudo "
                        "sans mot de passe (sudo visudo -f /etc/sudoers.d/<utilisateur>).")
            return res
        commande.__doc__ = (
            "Exécute une commande shell sur ce serveur et renvoie sa sortie. Les commandes qui modifient le serveur "
            "peuvent demander l'accord de l'utilisateur. "
            + ("sudo est permis (sans mot de passe) ; chaque commande sudo demande l'accord de l'utilisateur, donc "
               "regroupe les actions administrateur en une commande. Fichier protégé : printf '...' | sudo tee chemin."
               if self.sudo_permis() else "Pas de sudo.")
            + "\ncommande: la commande à lancer (ex : df -h, docker ps, tail -n 50 /var/log/syslog)")

        def etat():
            """État rapide du serveur : système, charge, mémoire, disque, conteneurs Docker, services en échec."""
            return self._executer("uname -sr; uptime; echo; free -h; echo; df -h -x tmpfs -x devtmpfs; echo; "
                                  "(docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true); echo; "
                                  "(systemctl --failed --no-legend 2>/dev/null | head -20 || true)")

        def lire_fichier(chemin: str, lignes: int = 300):
            """Lit un fichier texte du serveur (les dernières lignes s'il est long).
            chemin: chemin du fichier sur le serveur
            lignes: nombre maximum de lignes (fin du fichier)"""
            return self._executer(f"tail -n {max(1, min(int(lignes), 3000))} -- {_quote(chemin)}")

        def ecrire_fichier(chemin: str, contenu: str):
            """Écrit (remplace) un fichier texte sur le serveur. Peut demander l'accord de l'utilisateur.
            chemin: chemin du fichier sur le serveur
            contenu: nouveau contenu complet"""
            refus = self._autorise(f"écrire le fichier {chemin}", contenu[:1500])
            if refus:
                return refus
            c = self._client()
            try:
                with c.open_sftp() as sftp, sftp.open(chemin, "w") as f:
                    f.write(contenu)
            finally:
                c.close()
            return f"Fichier écrit : {chemin} ({len(contenu)} caractères)."

        def envoyer_fichier(local: str, distant: str):
            """Copie un fichier de cet ordinateur vers le serveur. Peut demander l'accord de l'utilisateur.
            local: chemin du fichier sur cet ordinateur
            distant: chemin de destination sur le serveur"""
            refus = self._autorise(f"envoyer {local} vers {distant}", "")
            if refus:
                return refus
            c = self._client()
            try:
                with c.open_sftp() as sftp:
                    sftp.put(os.path.expanduser(local), distant)
            finally:
                c.close()
            return f"Envoyé : {local} → {distant}"

        def recuperer_fichier(distant: str, local: str):
            """Copie un fichier du serveur vers cet ordinateur.
            distant: chemin du fichier sur le serveur
            local: chemin de destination sur cet ordinateur"""
            c = self._client()
            try:
                with c.open_sftp() as sftp:
                    sftp.get(distant, os.path.expanduser(local))
            finally:
                c.close()
            return f"Récupéré : {distant} → {local}"

        p = self.prefixe
        return [(f"{p}_commande", commande), (f"{p}_etat", etat), (f"{p}_lire_fichier", lire_fichier),
                (f"{p}_ecrire_fichier", ecrire_fichier), (f"{p}_envoyer_fichier", envoyer_fichier),
                (f"{p}_recuperer_fichier", recuperer_fichier)]

    def tester(self):
        return "Connecté — " + self._executer("uname -sr && uptime -p", delai=20).replace("\n", " — ")


def _quote(chemin: str) -> str:
    import shlex
    return shlex.quote(chemin)


# Chaque type accepte plusieurs comptes : un nom court pour les distinguer (et pour le dire à Jarvis)
CHAMP_COMPTE = {"nom": "compte", "libelle": "Nom de ce compte", "type": "text", "requis": False,
                "aide": "ex : perso, travail, papa. Tu pourras dire à Jarvis « regarde mes mails travail »."}
for _t in (Mail, Gmail, Agenda, GitHub, Notion, SSH):
    if not any(c["nom"] == "compte" for c in _t.__dict__.get("champs", [])):
        _t.champs = [CHAMP_COMPTE] + list(_t.champs)

TYPES = {c.type: c for c in (Gmail, Mail, Agenda, GitHub, Notion, SSH, MCP)}


# ---------- gestion ----------
def _lire():
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ecrire(d, synchro=True):
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, FICHIER)
    if synchro:
        from . import compte
        compte.document_modifie("connecteurs", d)


def _instancier(cid, d):
    return TYPES[d["type"]](cid, d.get("conf", {}))


def demarrer(cid):
    """(Re)démarre un connecteur actif ; renvoie son état."""
    with _verrou:
        arreter(cid)
        d = _lire().get(cid)
        if not d or not d.get("actif") or d.get("type") not in TYPES:
            return
        c = _instancier(cid, d)
        if c.manquants():
            c.erreur = "Identifiants à saisir sur ce PC : " + ", ".join(c.manquants())
            INSTANCES[cid] = c
            return
        try:
            c.demarrer()
        except Exception as e:
            c.arreter()
            c.erreur = f"{type(e).__name__} : {e}"[:300]
        INSTANCES[cid] = c


def arreter(cid):
    c = INSTANCES.pop(cid, None)
    if c:
        try:
            c.arreter()
        except Exception:
            traceback.print_exc()


def demarrer_tous():
    for cid in list(_lire()):
        try:
            demarrer(cid)
        except Exception:
            traceback.print_exc()


def enregistrer(cid, type_, conf, secrets, actif):
    if type_ not in TYPES:
        raise ValueError("Type de connecteur inconnu")
    with _verrou:
        d = _lire()
        champs = {c["nom"]: c for c in TYPES[type_].champs}
        d[cid] = {"type": type_, "actif": bool(actif),
                  "conf": {k: v for k, v in (conf or {}).items() if k in champs and champs[k]["type"] != "secret"}}
        _ecrire(d)
    for k, v in (secrets or {}).items():
        if k in champs and champs[k]["type"] == "secret" and v is not None:
            definir_secret(cid, k, v)
    demarrer(cid)


def supprimer(cid):
    with _verrou:
        arreter(cid)
        d = _lire()
        d2 = d.pop(cid, None)
        _ecrire(d)
    if d2 and d2.get("type") in TYPES:
        for c in TYPES[d2["type"]].champs:
            if c["type"] == "secret":
                definir_secret(cid, c["nom"], "")


def tester(cid):
    d = _lire().get(cid)
    if not d:
        raise ValueError("Connecteur inconnu")
    c = INSTANCES.get(cid) or _instancier(cid, d)
    if c.manquants():
        raise ValueError("Il manque : " + ", ".join(c.manquants()))
    if isinstance(c, MCP) and not c.session:
        raise ValueError(c.erreur or "Serveur MCP non connecté")
    return c.tester()


def etat():
    d = _lire()
    # un connecteur ajouté depuis un autre PC : on le démarre ici aussi
    for cid in d:
        if cid not in INSTANCES and d[cid].get("actif"):
            try:
                demarrer(cid)
            except Exception:
                pass
    out = {}
    for cid, x in d.items():
        cls = TYPES.get(x.get("type"))
        if not cls:
            continue
        c = INSTANCES.get(cid)
        out[cid] = {
            "type": x["type"], "actif": x.get("actif", False), "conf": x.get("conf", {}),
            "secrets": {ch["nom"]: bool(secret(cid, ch["nom"])) for ch in cls.champs if ch["type"] == "secret"},
            "erreur": c.erreur if c else "",
            "outils": sorted(n for n, o in outils.OUTILS.items() if o.get("source") == cid),
        }
    return out


def catalogue():
    return [{"type": t, "nom": c.nom, "description": c.description, "icone": c.icone, "champs": c.champs,
             "aide": c.aide, "multiple": True} for t, c in TYPES.items()]   # autant de comptes que tu veux par type
