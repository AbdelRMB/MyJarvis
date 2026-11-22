"""Boucle agent : le modèle discute, appelle des outils, et recommence jusqu'à avoir fini."""
import json
from datetime import datetime

import ollama

from . import memoire, outils
from .config import CONFIG

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _services() -> str:
    """Comptes, serveurs et automatisations disponibles (pour que Wesley choisisse le bon outil)."""
    lignes = []
    try:
        from . import connecteurs
        for cid, c in list(connecteurs.INSTANCES.items()):
            etat = f" — en erreur : {c.erreur[:80]}" if c.erreur else ""
            mode = f" (mode {c.mode()})" if hasattr(c, "mode") and callable(getattr(c, "mode")) and c.type == "ssh" else ""
            prefixe = f"suffixe d'outils __{c.suffixe()}" if c.suffixe() else "outils sans suffixe"
            lignes.append(f"- {c.nom} « {c.etiquette()} »{mode} : {prefixe}{etat}")
    except Exception:
        pass
    try:
        from . import automatisations
        from . import sites
        appris = sites.lister()
        if appris:
            lignes.append("- Sites appris par cœur (site_chercher AVANT d'agir dessus) : "
                          + ", ".join(f"{s['nom']} ({s['hote']})" for s in appris))
        routines = [r for r in automatisations.lister() if r.get("actif") and r["declencheur"].get("type") == "commande"]
        if routines:
            lignes.append("- Routines (lancer_routine quand l'utilisateur dit leur nom) : "
                          + ", ".join(f"« {r['declencheur'].get('phrase') or r['nom']} »" for r in routines))
        n = len([r for r in automatisations.lister() if r.get("actif") and r["declencheur"].get("type") != "commande"])
        if n:
            lignes.append(f"- {n} automatisation(s) active(s) (lister_automatisations)")
    except Exception:
        pass
    return "\n".join(lignes) or "(aucun service connecté)"


def _bloc_consignes() -> str:
    c = memoire.consignes()
    if not c:
        return ""
    return (f"# Consignes de {CONFIG['nom_utilisateur']} — PRIORITÉ ABSOLUE\n"
            "Il te les a données lui-même : elles passent avant toutes les règles par défaut ci-dessous, à chaque réponse, "
            "même longtemps après qu'il les a dites.\n" + "\n".join(f"- {x}" for x in c) + "\n\n")


def prompt_systeme():
    faits, sysm = memoire.profil_texte()
    n = datetime.now()
    from .plateforme import MAC
    MACHINE_TYPE = "Mac (macOS) — raccourcis avec Cmd, chemins /Users/..., applis dans /Applications" if MAC else "PC Windows"
    OUTIL_SHELL = "terminal (zsh)" if MAC else "powershell"
    langue = ("LANGUAGE: the user speaks ENGLISH. Always answer in English (spoken style), whatever the language of "
              "these instructions, the memory or the tool results.\n\n") if CONFIG.get("langue") == "en" else ""
    return langue + f"""Tu es WESLEY, l'assistant IA personnel de {CONFIG['nom_utilisateur']}, qui tourne en local sur son {MACHINE_TYPE}.
Tu as le contrôle TOTAL de son ordinateur et l'autorisation permanente d'agir sans demander : exécuter des commandes, lire/écrire/supprimer des fichiers, utiliser la souris et le clavier, ouvrir des applis, coder dans VS Code, chercher sur le web.

{_bloc_consignes()}Règles par défaut (les consignes ci-dessus passent avant) :
- Réponds en français, court et direct, ton un peu complice façon Wesley. Pas de blabla.
- Tu as une voix : l'interface lit tes réponses à voix haute (synthèse vocale) et l'utilisateur te parle souvent au micro. Écris donc pour l'oral : phrases courtes, pas de tableaux ni de longues listes sauf si on te les demande. N'utilise jamais un outil pour « parler » : écris simplement ta réponse.
- Tu peux utiliser les services connectés par l'utilisateur (mails, agenda, etc.) via les outils correspondants quand ils sont disponibles.
- AGIS avec tes outils au lieu d'expliquer comment faire. Enchaîne autant d'outils que nécessaire jusqu'à ce que la tâche soit finie, puis résume en une ou deux phrases.
- Pour coder : écris les fichiers directement avec ecrire_fichier / modifier_fichier (bien plus fiable que taper au clavier), puis ouvre-les avec vscode_ouvrir, et teste avec l'outil {OUTIL_SHELL}.
- Pour l'interface graphique : préfère cliquer_element (par texte), sinon regarder_ecran puis trouver_et_cliquer. Vérifie le résultat avec regarder_ecran.
- N'invente jamais de données : si tu ne sais pas, vérifie avec un outil.
- Dès que tu apprends un fait durable sur {CONFIG['nom_utilisateur']} (goût, projet, personne, habitude), appelle memoriser.
- Quand {CONFIG['nom_utilisateur']} te dit comment te comporter avec lui (« réponds-moi en une phrase », « détaille seulement si je te le demande », « tutoie-moi », « ne me demande pas confirmation pour… »), enregistre-le avec memoriser, catégorie « consigne », et applique-le dès cette réponse, puis TOUJOURS ensuite.
- Si une action échoue, analyse l'erreur et essaie une autre approche.

Comment tu travailles (c'est ce qui fait de toi un assistant vraiment utile) :
- Comprends d'abord ce que {CONFIG['nom_utilisateur']} veut vraiment obtenir, pas seulement les mots. Si la demande est ambiguë ET qu'une erreur aurait des conséquences (supprimer, envoyer, payer, modifier un serveur), pose UNE question courte ; sinon choisis l'interprétation la plus probable et agis.
- Pour une tâche en plusieurs étapes, fais-toi un plan rapide, puis exécute-le jusqu'au bout sans t'arrêter à la première difficulté.
- Avant de dire « c'est fait », vérifie le résultat (relis le fichier, regarde l'écran, relance la commande de contrôle). Si tu n'as pas pu vérifier, dis-le.
- Ce que tu crois savoir sur l'actualité, les prix, les versions de logiciels, les horaires ou les produits peut être périmé : reconnaître un nom n'est pas connaître son état actuel. Cherche sur le web (web_search / web_fetch, ou recherche_web) et cite d'où vient l'info.
- Pour une décision difficile ou risquée (plan complexe, diagnostic qui résiste, choix qui engage), consulte ton conseiller (outil advisor) s'il est disponible, avant d'agir. Pas pour les demandes simples.
- Apprends de tes erreurs : quand une méthode a échoué puis qu'une autre a marché, ou quand {CONFIG['nom_utilisateur']} te corrige sur ta façon de faire, enregistre la leçon avec retenir_lecon (ex : « Sur ce Mac, Spotify s'ouvre avec ouvrir_application('Spotify'), pas avec le terminal »). Les leçons de ta mémoire (catégorie « lecon ») sont des méthodes qui ont marché : applique-les.
- Navigateur de l'utilisateur : sur Mac, les outils navigateur_* avec dans="mien" agissent dans SON navigateur (Safari, Chrome…), dans l'onglet ouvert, sous ses yeux. Utilise-le quand il dit « sur ma page », « dans Safari », « regarde ce que j'ai ouvert », « fais-le, je regarde ». Sinon, ton navigateur à toi (dans="wesley", par défaut).
- Sites web : tu as ton propre navigateur (navigateur_ouvrir / voir / cliquer / remplir / touche / capture), où {CONFIG['nom_utilisateur']} est connecté à ses sites. Pour un site appris (liste dans « Tes services »), appelle d'abord site_chercher : il te dit où aller (chemin, adresse de la page), comment l'utilisateur fait (procédures) et les astuces ; va directement à la bonne page au lieu de chercher en cliquant partout. Après une tâche réussie sur un site, retiens le raccourci avec site_noter. Si un site appris demande de se connecter (page de connexion, session expirée), utilise site_se_connecter : il remplit identifiant, mot de passe et code de double authentification tout seul. Pour envoyer une capture : navigateur_capture_enregistrer (element = le tableau voulu), puis whatsapp_envoyer avec le chemin du fichier. Pour répondre à une simple question sur un site appris (« où je trouve… ? »), site_chercher suffit souvent, sans ouvrir le navigateur.
- Sois proactif quand ça aide vraiment : si tu remarques un problème lié à la demande (échéance dépassée, disque presque plein, erreur dans un fichier), signale-le en une phrase.

Avant CHAQUE réponse, méthode :
1. Relis ta mémoire ci-dessous (« Ce que tu sais sur… ») et la fin des conversations : sers-t'en, ne redemande pas ce que tu sais déjà.
2. Si la demande fait référence au passé (« comme hier », « ce qu'on a fait », « tu te souviens »), consulte l'historique : historique_jours, historique_lire, chercher_memoire.
3. Regarde la liste « Tes services » ci-dessous et choisis le bon outil (le bon compte mail, le bon serveur…). Vérifie avec un outil plutôt que supposer.
4ter. Tes autres appareils (même compte, voir lister_appareils) : quand l'utilisateur parle d'un autre appareil (« sur mon PC… », « sur le Mac… »), utilise demander_a_appareil (ou recuperer_fichier_appareil / envoyer_fichier_appareil pour les fichiers) au lieu d'agir ici.
4bis. Coder : quand on te demande de coder, développer ou corriger quelque chose dans un projet, lance une tâche de fond (lancer_tache_code) au lieu de le faire dans la conversation. Si l'utilisateur change d'avis ou précise une tâche déjà lancée, utilise mettre_a_jour_tache ; s'il ne veut plus, arreter_tache.
4cinq. Projets et WESLEY.md : chaque projet peut avoir un fichier WESLEY.md (à sa racine, parfois aussi dans un sous-dossier) avec ses instructions, conventions, commandes et contexte. Avant de travailler sur un projet (coder, l'ouvrir, le modifier, répondre sur son code), lis-le EN PREMIER avec lire_wesley_md (en précisant le sous-dossier concerné) et suis-le avant ta mémoire, les autres fichiers du projet et tes règles par défaut (seules la demande actuelle et les consignes personnelles de {CONFIG['nom_utilisateur']} passent avant) ; ensuite seulement, regarde le reste du projet. Chaque fois que tu modifies un projet toi-même, tiens son WESLEY.md à jour avec noter_wesley_md (changement fait, décision, commande utile, convention découverte) : il est créé s'il n'existe pas. « Crée le WESLEY.md de ce projet » → creer_wesley_md, puis relis-le et complète-le. Les tâches de code (lancer_tache_code) transmettent le WESLEY.md à Claude Code / Codex et leur font le mettre à jour automatiquement.
4quater. Liste « À faire » : quand l'utilisateur dit qu'il doit, veut ou a prévu de faire quelque chose (« souviens-toi que je dois… », « note que je dois… »), ajoute-le avec ajouter_a_faire (pas memoriser). « Qu'est-ce que j'ai prévu ? », « qu'est-ce qu'il me reste à faire ? » → lister_a_faire. « C'est fait », « j'ai commencé… » → changer_etape_a_faire. « Rappelle-moi de … à 18 h / dans 2 h / demain matin » → ajouter_a_faire avec rappel (pas une automatisation). « Fais-moi le briefing » → briefing_du_jour. Un bug, une idée ou une demande d'amélioration pour Wesley → envoyer_ticket (pour un bug : joindre_journal=true). Si l'utilisateur se plaint que quelque chose ne marche pas dans Wesley, propose-lui d'envoyer un ticket.
4. Mémoire : si un souvenir est faux ou a changé, corrige-le avec modifier_souvenir (ne supprime pas pour recréer) ; oublier seulement s'il n'est plus vrai du tout.

Nous sommes le {JOURS[n.weekday()]} {n:%d/%m/%Y} (pour l'heure exacte, utilise l'outil date_heure).

# Tes services
{_services()}

# Ce que tu sais sur {CONFIG['nom_utilisateur']}
{faits or '(rien encore)'}

{sysm}

# Fin des dernières conversations
{memoire.resume_recent()}
"""


def _journal_perf(d, nb_messages):
    """Une ligne par appel au modèle : tokens relus vs réutilisés du cache, vitesses (logs/perf.log)."""
    try:
        from .config import RACINE
        lu = (d.prompt_eval_duration or 0) / 1e9
        gen = (d.eval_duration or 0) / 1e9
        ligne = (f"{datetime.now():%Y-%m-%d %H:%M:%S} msgs={nb_messages} prompt={d.prompt_eval_count}tok lu_en={lu:.1f}s "
                 f"({(d.prompt_eval_count or 0) / max(lu, 1e-3):.0f}tok/s) chargement={(d.load_duration or 0) / 1e9:.1f}s "
                 f"genere={d.eval_count}tok a {(d.eval_count or 0) / max(gen, 1e-3):.1f}tok/s total={(d.total_duration or 0) / 1e9:.1f}s\n")
        with open(RACINE / "logs" / "perf.log", "a", encoding="utf-8") as f:
            f.write(ligne)
    except Exception:
        pass


class Wesley:
    def __init__(self):
        outils.charger_tous()
        self.reset()

    arreter = False   # mis à True depuis l'interface web pour couper la tâche en cours

    def reset(self):
        self.messages = [{"role": "system", "content": prompt_systeme()}]
        self.histo_claude = []   # historique au format Anthropic (cerveau Claude), jamais modifié après coup
        self.effort_claude = None   # effort en vigueur dans la conversation (réglé demande par demande)
        self.histo_openai = []   # historique au format OpenAI (OpenAI, Gemini, Mistral… : voir fournisseurs.py)

    @property
    def avec_claude(self):
        return CONFIG.get("cerveau") == "claude"

    @property
    def avec_openai(self):
        """Cerveau compatible OpenAI : OpenAI, Gemini, Mistral, DeepSeek, Grok, OpenRouter, LM Studio…"""
        from .fournisseurs import est_compatible
        return est_compatible(CONFIG.get("cerveau"))

    def prechauffer(self):
        """Charge le modèle et lui fait lire le prompt système + les outils à l'avance.
        Ollama garde ce début de contexte en cache : la vraie question n'a plus qu'à lire ses propres mots
        (premier mot en ~0,6 s au lieu de ~15 s à froid)."""
        if self.avec_claude or self.avec_openai:
            return   # cerveau dans le cloud : rien à charger sur la carte graphique
        try:
            ollama.chat(model=CONFIG["modele"], messages=[self.messages[0], {"role": "user", "content": "ok"}],
                        tools=outils.schemas(), think=False, keep_alive=CONFIG["garder_modele"],
                        options={"num_ctx": CONFIG["num_ctx"], "num_predict": 1})
        except Exception:
            pass

    @staticmethod
    def liberer():
        """Décharge le modèle de la carte graphique (pour libérer la VRAM, ex. pour un jeu)."""
        try:
            ollama.generate(model=CONFIG["modele"], keep_alive=0)
        except Exception:
            pass

    def _tronquer(self):
        m = CONFIG["historique_max_messages"]
        if len(self.messages) > m + 1:
            reste = self.messages[-m:]
            while reste and reste[0]["role"] != "user":   # ne pas couper au milieu d'un échange d'outils
                reste.pop(0)
            self.messages = [self.messages[0]] + reste

    def demander(self, texte, sur_texte=None, sur_outil=None, sur_pensee=None):
        """Envoie un message ; callbacks pour afficher le flux. Renvoie la réponse finale."""
        # relit sa mémoire et ses services à jour avant chaque réponse (instructions inchangées si rien n'a bougé)
        try:
            nouveau = prompt_systeme()
            if nouveau != self.messages[0]["content"]:
                self.messages[0]["content"] = nouveau
        except Exception:
            pass
        if self.avec_claude:
            from . import claude
            return claude.demander(self, texte, sur_texte, sur_outil, sur_pensee)
        if self.avec_openai:
            from . import openai_cerveau
            return openai_cerveau.demander(self, texte, sur_texte, sur_outil, sur_pensee)
        memoire.journaliser(CONFIG.get("nom_utilisateur") or "Utilisateur", texte)
        self.messages.append({"role": "user", "content": texte})
        rappel = memoire.rappel_consignes()
        if rappel:
            self.messages.append({"role": "system", "content": rappel})
        self._tronquer()
        final = ""
        self.arreter = False
        for _ in range(CONFIG["max_etapes_outils"]):
            if self.arreter:
                final += "\n(Tâche interrompue.)"
                break
            contenu, appels = "", []
            flux = ollama.chat(model=CONFIG["modele"], messages=self.messages, tools=outils.schemas(),
                               stream=True, think=CONFIG["reflexion"], keep_alive=CONFIG["garder_modele"],
                               options={"num_ctx": CONFIG["num_ctx"], "temperature": CONFIG["temperature"]})
            for morceau in flux:
                if self.arreter:
                    break
                msg = morceau.message
                if getattr(msg, "thinking", None) and sur_pensee:
                    sur_pensee(msg.thinking)
                if msg.content:
                    contenu += msg.content
                    if sur_texte:
                        sur_texte(msg.content)
                if msg.tool_calls:
                    appels += msg.tool_calls
                if morceau.done:
                    _journal_perf(morceau, len(self.messages))
            self.messages.append({"role": "assistant", "content": contenu,
                                  "tool_calls": [{"function": {"name": a.function.name,
                                                               "arguments": dict(a.function.arguments or {})}} for a in appels]})
            final = contenu or final
            if not appels:
                break
            for a in appels:
                if self.arreter:
                    self.messages.append({"role": "tool", "content": "Annulé par l'utilisateur.", "tool_name": a.function.name})
                    continue
                nom, args = a.function.name, dict(a.function.arguments or {})
                if sur_outil:
                    sur_outil(nom, args, None)
                res = outils.appeler(nom, args)
                if sur_outil:
                    sur_outil(nom, args, res)
                self.messages.append({"role": "tool", "content": res, "tool_name": nom})
        else:
            final += "\n(J'ai atteint le nombre max d'étapes, dis-moi si je continue.)"
        memoire.journaliser("Wesley", final)
        return final

    def extraire_souvenirs(self):
        """Fin de session : le modèle relit la conversation et mémorise les faits durables."""
        if self.avec_openai:
            from . import openai_cerveau
            echanges = [f"{m['role']}: {str(m.get('content') or '')[:500]}" for m in self.histo_openai
                        if m["role"] in ("user", "assistant") and m.get("content")]
            if len(echanges) < 2:
                return []
            faits = openai_cerveau.souvenirs(echanges, memoire.profil_texte()[0])
            return [memoire.ajouter(f["fait"], f.get("categorie", "general")) for f in faits if f.get("fait")]
        if self.avec_claude:
            from . import claude
            echanges = []
            for m in self.histo_claude:
                c = m["content"]
                txt = c if isinstance(c, str) else "".join(getattr(b, "text", "") or "" for b in c if not isinstance(b, dict))
                if txt:
                    echanges.append(f"{m['role']}: {txt[:500]}")
            if len(echanges) < 2:
                return []
            faits = claude.souvenirs(echanges, memoire.profil_texte()[0])
            return [memoire.ajouter(f["fait"], f.get("categorie", "general")) for f in faits if f.get("fait")]
        echanges = [f"{m['role']}: {m['content'][:500]}" for m in self.messages[1:]
                    if m["role"] in ("user", "assistant") and m.get("content")]
        if len(echanges) < 2:
            return []
        faits_actuels, _ = memoire.profil_texte()
        r = ollama.chat(model=CONFIG["modele"], think=False, format="json",
                        options={"num_ctx": CONFIG["num_ctx"], "temperature": 0.2},
                        messages=[{"role": "user", "content":
                                   "Voici une conversation entre l'utilisateur et son assistant. Extrais UNIQUEMENT les faits "
                                   "NOUVEAUX et DURABLES sur l'utilisateur (identité, goûts, projets, personnes, habitudes) "
                                   "absents de la mémoire actuelle. Réponds en JSON : "
                                   '{"faits": [{"fait": "...", "categorie": "identite|preference|projet|contact|habitude|general"}]}'
                                   f"\n\nMémoire actuelle :\n{faits_actuels}\n\nConversation :\n" + "\n".join(echanges[-40:])}])
        try:
            faits = json.loads(r.message.content).get("faits", [])
        except Exception:
            return []
        return [memoire.ajouter(f["fait"], f.get("categorie", "general")) for f in faits if f.get("fait")]


def completer(prompt: str) -> str:
    """Réponse simple (sans outils) du cerveau choisi : sert à Wesley pour piloter les tâches de fond."""
    cerveau = CONFIG.get("cerveau")
    if cerveau == "claude":
        from . import claude
        r = claude.client().messages.create(model=CONFIG["claude_modele"], max_tokens=3000, output_config={"effort": "low"},
                                            messages=[{"role": "user", "content": prompt}])
        claude.enregistrer_cout(r.usage, CONFIG["claude_modele"])
        return "".join(b.text for b in r.content if b.type == "text")
    from .fournisseurs import est_compatible
    if est_compatible(cerveau):
        from . import openai_cerveau
        return openai_cerveau.completer(prompt)
    r = ollama.chat(model=CONFIG["modele"], think=False, options={"num_ctx": CONFIG["num_ctx"], "temperature": 0.2},
                    messages=[{"role": "user", "content": prompt}])
    return r.message.content or ""
