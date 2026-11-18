"""Connecteurs : services externes qui ajoutent des outils à Jarvis (mails, agenda, GitHub, Notion, serveurs MCP…).

- La liste des connecteurs et leurs réglages non secrets sont dans le dossier partagé (connecteurs.json) :
  ils apparaissent sur tous tes PC.
- Les mots de passe / jetons sont dans le Gestionnaire d'identifiants Windows (keyring) de CHAQUE PC :
  ils ne partent jamais sur OneDrive. Sur un nouveau PC, il suffit de les ressaisir une fois.
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
def secret(cid, champ):
    try:
        import keyring
        return keyring.get_password(SERVICE, f"{cid}:{champ}") or ""
    except Exception:
        return ""


def definir_secret(cid, champ, valeur):
    import keyring
    if valeur:
        keyring.set_password(SERVICE, f"{cid}:{champ}", valeur)
    else:
        try:
            keyring.delete_password(SERVICE, f"{cid}:{champ}")
        except Exception:
            pass


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

    def demarrer(self):
        for nom, fn in self.fonctions():
            outils.ajouter_fonction(fn, nom, source=self.cid)

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


TYPES = {c.type: c for c in (Gmail, Mail, Agenda, GitHub, Notion, MCP)}


# ---------- gestion ----------
def _lire():
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ecrire(d):
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, FICHIER)


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
             "aide": c.aide, "multiple": t in ("mcp", "mail")} for t, c in TYPES.items()]
