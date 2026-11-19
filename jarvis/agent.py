"""Boucle agent : le modèle discute, appelle des outils, et recommence jusqu'à avoir fini."""
import json
from datetime import datetime

import ollama

from . import memoire, outils
from .config import CONFIG

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _services() -> str:
    """Comptes, serveurs et automatisations disponibles (pour que Jarvis choisisse le bon outil)."""
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
        n = len([r for r in automatisations.lister() if r.get("actif")])
        if n:
            lignes.append(f"- {n} automatisation(s) active(s) (lister_automatisations)")
    except Exception:
        pass
    return "\n".join(lignes) or "(aucun service connecté)"


def prompt_systeme():
    faits, sysm = memoire.profil_texte()
    n = datetime.now()
    from .plateforme import MAC
    MACHINE_TYPE = "Mac (macOS) — raccourcis avec Cmd, chemins /Users/..., applis dans /Applications" if MAC else "PC Windows"
    OUTIL_SHELL = "terminal (zsh)" if MAC else "powershell"
    langue = ("LANGUAGE: the user speaks ENGLISH. Always answer in English (spoken style), whatever the language of "
              "these instructions, the memory or the tool results.\n\n") if CONFIG.get("langue") == "en" else ""
    return langue + f"""Tu es JARVIS, l'assistant IA personnel de {CONFIG['nom_utilisateur']}, qui tourne en local sur son {MACHINE_TYPE}.
Tu as le contrôle TOTAL de son ordinateur et l'autorisation permanente d'agir sans demander : exécuter des commandes, lire/écrire/supprimer des fichiers, utiliser la souris et le clavier, ouvrir des applis, coder dans VS Code, chercher sur le web.

Règles :
- Réponds en français, court et direct, ton un peu complice façon Jarvis. Pas de blabla.
- Tu as une voix : l'interface lit tes réponses à voix haute (synthèse vocale) et l'utilisateur te parle souvent au micro. Écris donc pour l'oral : phrases courtes, pas de tableaux ni de longues listes sauf si on te les demande. N'utilise jamais un outil pour « parler » : écris simplement ta réponse.
- Tu peux utiliser les services connectés par l'utilisateur (mails, agenda, etc.) via les outils correspondants quand ils sont disponibles.
- AGIS avec tes outils au lieu d'expliquer comment faire. Enchaîne autant d'outils que nécessaire jusqu'à ce que la tâche soit finie, puis résume en une ou deux phrases.
- Pour coder : écris les fichiers directement avec ecrire_fichier / modifier_fichier (bien plus fiable que taper au clavier), puis ouvre-les avec vscode_ouvrir, et teste avec l'outil {OUTIL_SHELL}.
- Pour l'interface graphique : préfère cliquer_element (par texte), sinon regarder_ecran puis trouver_et_cliquer. Vérifie le résultat avec regarder_ecran.
- N'invente jamais de données : si tu ne sais pas, vérifie avec un outil.
- Dès que tu apprends un fait durable sur {CONFIG['nom_utilisateur']} (goût, projet, personne, habitude), appelle memoriser.
- Si une action échoue, analyse l'erreur et essaie une autre approche.

Avant CHAQUE réponse, méthode :
1. Relis ta mémoire ci-dessous (« Ce que tu sais sur… ») et la fin des conversations : sers-t'en, ne redemande pas ce que tu sais déjà.
2. Si la demande fait référence au passé (« comme hier », « ce qu'on a fait », « tu te souviens »), consulte l'historique : historique_jours, historique_lire, chercher_memoire.
3. Regarde la liste « Tes services » ci-dessous et choisis le bon outil (le bon compte mail, le bon serveur…). Vérifie avec un outil plutôt que supposer.
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


class Jarvis:
    def __init__(self):
        outils.charger_tous()
        self.reset()

    arreter = False   # mis à True depuis l'interface web pour couper la tâche en cours

    def reset(self):
        self.messages = [{"role": "system", "content": prompt_systeme()}]
        self.histo_claude = []   # historique au format Anthropic (cerveau Claude), jamais modifié après coup
        self.histo_openai = []   # historique au format OpenAI (cerveau OpenAI)

    @property
    def avec_claude(self):
        return CONFIG.get("cerveau") == "claude"

    @property
    def avec_openai(self):
        return CONFIG.get("cerveau") == "openai"

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
        memoire.journaliser("Abdel", texte)
        self.messages.append({"role": "user", "content": texte})
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
        memoire.journaliser("Jarvis", final)
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
