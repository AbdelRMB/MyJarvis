"""Test de bout en bout de l'interface de bureau (Chromium) : la vraie interface compilée (wesley/static) face à
un faux serveur Wesley (réponses de /api simulées dans le navigateur, WebSocket simulé). Rien n'est installé,
aucune donnée de l'utilisateur n'est lue.

Parcours vérifiés :
  1. premier lancement : écran de choix, création d'un compte (prénom, e-mail, mot de passe, politique) ;
  2. Réglages › Cerveau : passer à Claude, enregistrer la clé API ;
  3. Transcription : lancer une transcription (source, titre) puis l'arrêter ;
  4. chaque vue s'ouvre sans erreur JavaScript.

Lancer (après `cd interface && npm run build`) :
    pip install playwright && playwright install chromium
    python tests/e2e_bureau.py            (WESLEY_CAPTURES=dossier pour garder des captures d'écran)
"""
import functools
import http.server
import json
import os
import re
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

STATIC = Path(__file__).resolve().parent.parent / "wesley" / "static"
CAPTURES = os.environ.get("WESLEY_CAPTURES", "")


# ---------- faux serveur Wesley ----------
class FauxWesley:
    """État minimal du serveur local et journal des appels reçus (méthode, chemin, corps JSON)."""

    def __init__(self):
        self.appels: list[tuple[str, str, dict]] = []
        self.inconnus: set[str] = set()
        self.compte = {"connecte": False, "mode": "", "email": "", "prenom": "", "serveur": "https://exemple.invalid",
                       "machine": "PC-Test", "admin": False, "politique_a_accepter": False,
                       "url_confidentialite": "https://exemple.invalid/c", "url_mentions": "https://exemple.invalid/m"}
        self.config = {"modele": "qwen3.5:9b", "modele_vision": "qwen3.5:9b", "temperature": 0.6, "reflexion": False,
                       "num_ctx": 16384, "max_etapes_outils": 25, "whisper_modele": "small",
                       "nom_utilisateur": "Test", "cerveau": "ollama", "claude_modele": "claude-sonnet-5-5",
                       "claude_effort": "moyen", "langue": "fr", "briefing_matin": False, "conversation_suivie": True,
                       "maj_auto": False, "conseiller": False, "recherche_web_native": True,
                       "transcription_resume_auto": True, "transcription_actions_afaire": True,
                       "transcription_gpu": False, "memoire_semantique": True, "apprentissage_auto": True,
                       "budget_mensuel": 0, "modele_rapide_fond": True, "bilan_soir": False, "bilan_soir_heure": "19:00"}
        self.cle_claude = False
        self.transcription = None
        self.mcp_actif = False

    def _session_transcription(self, titre: str, source: str) -> dict:
        return {"id": "t1", "titre": titre or "Réunion", "source": source, "avec_micro": True, "etat": "en_cours",
                "duree": 12.0, "debut": 1764064800.0, "langue": "fr", "modele": "small", "fichier": "", "erreur": "",
                "segments": [{"debut": 1.0, "fin": 4.0, "locuteur": 1, "texte": "Bonjour à tous."}], "noms": {},
                "empreinte": "", "locuteurs": [{"id": 1, "nom": "", "duree": 3.0, "phrases": 1}],
                "nb_locuteurs": 1, "nb_phrases": 1, "genre": "", "a_resume": False, "niveau": 0.1}

    def repondre(self, methode: str, chemin: str, q: dict, corps: dict):
        self.appels.append((methode, chemin, corps))
        c, cfg = self.compte, self.config
        if chemin == "/api/session":
            return {"jeton": "jeton-test", "nom": "Test", "nb_outils": 120, "plateforme": "windows"}
        if chemin == "/api/compte" and methode == "GET":
            return c
        if chemin in ("/api/compte/inscription", "/api/compte/connexion"):
            c.update(connecte=True, mode="en_ligne", email=corps.get("email", ""), prenom=corps.get("prenom", ""))
            return {**c, "import": None}
        if chemin == "/api/compte/local":
            c.update(mode="local")
            return c
        if chemin == "/api/config":
            if methode == "POST":
                cfg.update({k: v for k, v in corps.items() if k in cfg})
                return {"ok": True}
            return {"config": cfg, "modeles": ["qwen3.5:9b"]}
        if chemin == "/api/systeme":
            return {"cpu": 5.0, "ram": 40.0, "ram_used": 6.4, "ram_total": 16.0, "disque": 50.0, "disque_libre": 200.0,
                    "gpu": None, "ollama": True, "charges": [], "cerveau": cfg["cerveau"], "modele": cfg["modele"],
                    "cle_claude_manquante": cfg["cerveau"] == "claude" and not self.cle_claude, "occupe": False,
                    "uptime": 3600}
        if chemin == "/api/appli":
            return {"appli": False, "plateforme": "windows", "demarrage_auto": False, "machine": "PC-Test",
                    "ecoute_fond": False, "ecoute_active": False, "seuil_eveil": 0.5, "raccourci": "ctrl+alt+w",
                    "silence_fin": 1.2}
        if chemin == "/api/autorisations":
            return {"plateforme": "windows", "autorisations": [], "a_proposer": []}
        if chemin == "/api/ia":
            return {"fournisseurs": [{"id": "openai", "nom": "OpenAI", "detail": "GPT", "cle_ou": "https://exemple.invalid",
                                      "cle": False, "local": False, "perso": False}]}
        if chemin == "/api/claude":
            return {"cle": self.cle_claude, "cle_masquee": "sk-ant-…test" if self.cle_claude else "",
                    "couts": {"total": 0.0, "appels": 0, "aujourdhui": 0, "mois": 0, "budget": 0.0, "economie": False},
                    "modeles": [{"id": "claude-sonnet-5-5", "nom": "Claude Sonnet 5.5"}]}
        if chemin == "/api/claude/cle":
            self.cle_claude = bool(corps.get("cle"))
            return {"ok": True}
        if chemin == "/api/transcriptions" and methode == "GET":
            t = self.transcription
            return {"liste": [t] if t else [], "en_cours": t if t and t["etat"] == "en_cours" else None,
                    "appareil": "PC-Test", "modeles": ["auto", "small"], "modele": "auto", "modele_auto": "small",
                    "dossier": "C:/Transcriptions", "plateforme": "windows"}
        if chemin == "/api/transcriptions/demarrer":
            self.transcription = self._session_transcription(corps.get("titre", ""), corps.get("source", "micro"))
            return self.transcription
        if chemin == "/api/transcriptions/arreter":
            if self.transcription:
                self.transcription["etat"] = "terminee"
            return self.transcription or {}
        if chemin == "/api/transcriptions/t1":
            return self.transcription or {}
        if chemin == "/api/appareils/ordinateurs":
            return {"ordinateurs": [], "moi": "PC-Test"}
        if chemin == "/api/recherche":
            return {"souvenirs": [{"fid": "f1", "fait": "La Clio est au garage", "categorie": "general"}],
                    "historique": [], "documents": [], "afaire": [], "erreurs": {},
                    "transcriptions": [{"id": "t1", "titre": "Réunion budget", "date": 1764064800.0, "heure": "00:12",
                                        "locuteur": "Paul", "texte": "le garage coûte 400 euros", "appareil": ""}]}
        if chemin == "/api/mcp":
            if methode == "POST" and "actif" in corps:
                self.mcp_actif = bool(corps["actif"])
            return {"actif": self.mcp_actif, "en_marche": self.mcp_actif, "url": "http://127.0.0.1:7778/mcp",
                    "cle": "wesley-cle", "erreur": "", "outils": ["chercher_partout", "memoriser"],
                    "claude_code": 'claude mcp add --transport http wesley http://127.0.0.1:7778/mcp --header "Authorization: Bearer wesley-cle"',
                    "claude_desktop": "{}"}
        if chemin == "/api/sauvegarde":
            return {"fichier": "C:/Users/test/Downloads/wesley-sauvegarde.wesley",
                    "contenu": {"souvenirs": 1, "jours": 2, "transcriptions": 1}}
        # réponses neutres des autres vues (mêmes formes que le vrai serveur, sans contenu)
        listes = {"/api/notifications", "/api/agents_code", "/api/afaire", "/api/afaire/faits", "/api/historique",
                  "/api/actions", "/api/memoire", "/api/memoire/journal", "/api/taches", "/api/outils"}
        if chemin in listes:
            return []
        neutres = {
            "/api/memoire/intelligence": {"semantique": {"active": True, "disponible": True, "telechargement": False,
                                                         "erreur": ""},
                                          "propositions": [], "rangement": None, "couts": {}, "nb_lecons": 0},
            "/api/documents": {"dossiers": [], "fichiers": 0, "passages": 0, "illisibles": [], "indexation": False,
                               "erreur": ""},
            "/api/automatisations": {"regles": [], "boites": [], "machine": "PC-Test"},
            "/api/connecteurs": {"catalogue": [], "installes": {}},
            "/api/appareils": {"appareils": [], "reglages": {"accepte": True, "mode": "confirmation"}, "journal": [],
                               "connecte": True, "mode": "en_ligne", "erreur": "", "derniere_version": "2.9.0"},
            "/api/sites": {"sites": [], "navigateur": {"executable": "", "ouvert": False,
                                          "installation": {"en_cours": False, "pct": 0, "erreur": ""},
                                          "enregistrement": {"actif": False, "site": "", "etapes": 0}},
                           "exploration": {"en_cours": False, "site": "", "pages": 0, "max": 0, "etape": "", "erreur": ""}},
            "/api/tickets": {"connecte": True, "admin": False, "miens": [], "tous": []},
            "/api/rapport": {"rapport": None},
            "/api/majs": {"version": "2.9.0", "jeton": False, "installee": True, "majs": [], "journal": [], "erreur": ""},
            "/api/sante": {"jours": 7, "appels": 0, "echecs": 0, "outils": [], "cerveaux": []},
            "/api/tts/voix": {"kyutai": [], "edge": [], "piper": []},
            "/api/contexte": {},
        }
        if chemin in neutres:
            return neutres[chemin]
        if methode == "GET":
            self.inconnus.add(chemin)
        return {}


def servir_static() -> tuple[http.server.ThreadingHTTPServer, str]:
    """Sert wesley/static (index.html pour toute page inconnue, comme le serveur de Wesley)."""
    class Gestion(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send_head(self):
            if not (STATIC / urlparse(self.path).path.lstrip("/")).is_file():
                self.path = "/index.html"
            return super().send_head()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Gestion, directory=str(STATIC)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def brancher(page, faux: FauxWesley):
    def sur_api(route):
        req = route.request
        u = urlparse(req.url)
        try:
            corps = json.loads(req.post_data or "{}") if "json" in (req.headers.get("content-type") or "") else {}
        except ValueError:
            corps = {}
        rep = faux.repondre(req.method, u.path, parse_qs(u.query), corps if isinstance(corps, dict) else {})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(rep))

    page.route(re.compile(r".*/api/.*"), sur_api)

    def sur_ws(ws):   # WebSocket simulé : conversation vide, rien en cours
        ws.send(json.dumps({"type": "init", "conversation": [], "occupe": False}))
    page.route_web_socket(re.compile(r".*/ws.*"), sur_ws)


def capture(page, nom: str):
    if CAPTURES:
        page.screenshot(path=str(Path(CAPTURES) / f"bureau-{nom}.png"))


def appel(faux: FauxWesley, methode: str, chemin: str) -> dict:
    trouves = [c for m, p, c in faux.appels if m == methode and p == chemin]
    assert trouves, f"aucun appel {methode} {chemin} ; reçus : {[(m, p) for m, p, _ in faux.appels][-15:]}"
    return trouves[-1]


def ouvrir_vue(page, libelle: str):
    page.get_by_title(libelle, exact=True).first.click()


def main() -> int:
    assert (STATIC / "index.html").exists(), "Interface non compilée : cd interface && npm run build"
    srv, url = servir_static()
    faux = FauxWesley()
    erreurs: list[str] = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 1400, "height": 900}, locale="fr-FR")
        ctx.add_init_script("try { localStorage.setItem('wesley-langue', 'fr') } catch {}")
        page = ctx.new_page()
        page.on("pageerror", lambda e: erreurs.append(f"pageerror: {e}"))
        page.on("console", lambda m: m.type == "error" and erreurs.append(f"console: {m.text}"))
        brancher(page, faux)
        page.goto(url + "/?appli")

        # 1. premier lancement : choix en ligne / local, puis création du compte
        page.get_by_text("En ligne, avec un compte").click()
        page.get_by_role("button", name="Créer un compte").click()
        page.get_by_placeholder("Ton prénom").fill("Alice")
        page.get_by_placeholder("Adresse e-mail").fill("alice@exemple.invalid")
        page.get_by_placeholder("Mot de passe", exact=True).fill("motdepasse-solide")
        page.get_by_placeholder("Confirme le mot de passe").fill("motdepasse-solide")
        page.get_by_role("checkbox").check()
        capture(page, "1-inscription")
        page.get_by_role("button", name="Créer mon compte").click()
        expect(page.get_by_placeholder("Adresse e-mail")).to_have_count(0)
        corps = appel(faux, "POST", "/api/compte/inscription")
        assert corps["email"] == "alice@exemple.invalid" and corps["prenom"] == "Alice" and corps["politique"] is True, corps
        print("✓ création du compte")

        # 2. Réglages › Cerveau : Claude + clé API
        ouvrir_vue(page, "Réglages")
        page.get_by_role("tab", name="Cerveau", exact=True).click()
        page.get_by_role("radio", name=re.compile("Claude \\(API\\)")).click()
        expect(page.get_by_role("radio", name=re.compile("Claude \\(API\\)"))).to_have_attribute("aria-checked", "true")
        assert appel(faux, "POST", "/api/config").get("cerveau") == "claude"
        page.get_by_placeholder("sk-ant-…").fill("sk-ant-test-123")
        page.get_by_placeholder("sk-ant-…").press("Enter")
        expect(page.get_by_text("Configurée")).to_be_visible()
        assert appel(faux, "POST", "/api/claude/cle") == {"cle": "sk-ant-test-123"}
        capture(page, "2-cerveau")
        print("✓ choix du cerveau et clé API")

        # 3. Transcription : lancer puis arrêter
        ouvrir_vue(page, "Transcription")
        page.get_by_role("button", name="Lancer la transcription").click()
        corps = appel(faux, "POST", "/api/transcriptions/demarrer")
        assert corps["source"] in ("systeme", "micro") and "titre" in corps, corps
        expect(page.get_by_text("Transcription en cours")).to_be_visible()
        capture(page, "3-transcription")
        page.get_by_role("button", name=re.compile("^Arrêter")).first.click()
        appel(faux, "POST", "/api/transcriptions/arreter")
        print("✓ lancement et arrêt d'une transcription")

        # 4. recherche unique : un résultat de transcription ouvre la bonne transcription
        ouvrir_vue(page, "Assistant")
        page.get_by_role("button", name="Rechercher partout").click()
        page.get_by_placeholder(re.compile("^Chercher dans tes souvenirs")).fill("garage")
        expect(page.get_by_text("La Clio est au garage")).to_be_visible()
        appel(faux, "GET", "/api/recherche")
        capture(page, "4-recherche")
        page.get_by_text("le garage coûte 400 euros").click()
        expect(page.get_by_role("dialog")).to_have_count(0)
        expect(page.get_by_role("button", name="Lancer la transcription")).to_be_visible()
        appel(faux, "GET", "/api/transcriptions/t1")
        print("✓ recherche unique")

        # 5. Réglages › Application : serveur MCP et sauvegarde complète
        ouvrir_vue(page, "Réglages")
        page.get_by_role("tab", name="Application", exact=True).click()
        page.get_by_text("Partager Wesley avec mes autres assistants").click()
        assert appel(faux, "POST", "/api/mcp") == {"actif": True}
        expect(page.get_by_text(re.compile("claude mcp add --transport http wesley"))).to_be_visible()
        page.get_by_placeholder(re.compile("^Mot de passe de la sauvegarde")).fill("motdepasse-solide")
        page.get_by_role("button", name="Créer une sauvegarde").click()
        expect(page.get_by_text(re.compile("Sauvegarde enregistrée"))).to_be_visible()
        assert appel(faux, "POST", "/api/sauvegarde") == {"mot_de_passe": "motdepasse-solide"}
        capture(page, "5-application")
        print("✓ serveur MCP et sauvegarde")

        # 6. chaque vue s'ouvre sans planter
        for libelle in ["Assistant", "À faire", "Historique", "Mémoire", "Connecteurs", "Activité", "Arsenal", "Tâches",
                        "Automatisations", "Mes appareils", "Système", "Mises à jour", "Tickets", "Sites appris", "Réglages"]:
            ouvrir_vue(page, libelle)
            page.wait_for_timeout(300)
            assert not page.get_by_text("Cette page a rencontré un problème").count(), f"la vue {libelle} a planté"
        print("✓ toutes les vues s'ouvrent")
        nav.close()
    srv.shutdown()
    # les erreurs réseau des réponses neutres ne comptent pas, seules les erreurs JavaScript
    vraies = [e for e in erreurs if "Failed to load resource" not in e]
    if faux.inconnus:
        print("  (routes non simulées :", ", ".join(sorted(faux.inconnus)) + ")")
    if vraies:
        print("✗ erreurs JavaScript :\n  " + "\n  ".join(vraies[:20]))
        return 1
    print("Interface de bureau : OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
