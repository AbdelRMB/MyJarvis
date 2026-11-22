/**
 * Le cerveau du Wesley du téléphone : la même boucle que sur le bureau (claude.py, openai_cerveau.py) — l'IA
 * discute, appelle des outils, et recommence jusqu'à avoir fini — mais exécutée dans le téléphone, qui appelle
 * directement l'API de l'IA avec la clé du coffre du compte.
 *
 * - Claude : API Messages d'Anthropic (recherche web et lecture de pages par Anthropic) ;
 * - OpenAI, Gemini, Mistral… : API compatible OpenAI ;
 * - Ollama / LM Studio (locaux) ou pas de clé : relais — un de tes ordinateurs traite la demande.
 */
import { cleApi, lireCoffre } from "./compte";
import { envoyer, ordinateurParDefaut } from "./appareils";
import { journaliser, prenom, resumeRecent, useDonnees } from "./donnees";
import { CLAUDE_DEFAUT, LOCAUX, PAR_ID } from "./fournisseurs";
import { executerOutil, outilsDisponibles, schemaJson, servicesTexte, type Contexte } from "./outils";
import { nomTelephone, reglagesTel } from "./stockage";
import { JOURS } from "./donnees";

export type Evenement =
  | { type: "outil"; nom: string; args: Record<string, unknown> }
  | { type: "resultat"; nom: string; resultat: string }
  | { type: "etat"; texte: string };

const MAX_TOURS = 30;

// ---------- quel cerveau ? ----------
export type Choix = { id: string; nom: string; raison?: string };

export function cerveauActif(): Choix {
  const r = reglagesTel();
  const profil = useDonnees.getState().profil;
  const id = r.cerveau || String(profil.cerveau || "claude");
  if (id === "relais") return { id: "relais", nom: "relais par ton ordinateur" };
  if (id === "claude") return cleApi("ANTHROPIC_API_KEY") ? { id, nom: "Claude" } : { id: "relais", nom: "relais", raison: "pas de clé API Claude dans ton compte" };
  if (id === "ollama" && /^https:\/\//.test(r.ollama_url)) return { id: "ollama", nom: "Ollama" };
  if (LOCAUX.includes(id)) return { id: "relais", nom: "relais", raison: `${id === "ollama" ? "Ollama" : "LM Studio"} tourne sur ton ordinateur` };
  const f = PAR_ID[id];
  if (!f) return { id: "relais", nom: "relais", raison: `IA inconnue : ${id}` };
  if (!cleApi(f.env) && id !== "perso") return { id: "relais", nom: "relais", raison: `pas de clé ${f.nom} dans ton compte` };
  return { id, nom: f.nom };
}

// ---------- instructions ----------
function consignes() {
  return useDonnees
    .getState()
    .faits.filter((f) => f.categorie === "consigne")
    .map((f) => f.fait);
}

export function promptSysteme() {
  const nom = prenom();
  const d = new Date();
  const c = consignes();
  const parCat: Record<string, string[]> = {};
  for (const f of useDonnees.getState().faits) if (f.categorie !== "consigne") (parCat[f.categorie] ||= []).push(f.fait);
  const faits = Object.entries(parCat)
    .map(([k, l]) => `## ${k}\n` + l.map((x) => `- ${x}`).join("\n"))
    .join("\n");
  const anglais = useDonnees.getState().profil.langue === "en" || localStorage.getItem("wesley-langue") === "en";
  return (
    (anglais ? "LANGUAGE: the user speaks ENGLISH. Always answer in English (spoken style).\n\n" : "") +
    `Tu es WESLEY, l'assistant IA personnel de ${nom}. Tu tournes ici sur son TÉLÉPHONE (${nomTelephone()}), dans l'appli Wesley mobile, connectée à son compte : même mémoire, même liste À faire, mêmes automatisations et mêmes services que sur ses ordinateurs.

${c.length ? `# Consignes de ${nom} — PRIORITÉ ABSOLUE\nIl te les a données lui-même : elles passent avant toutes les règles par défaut ci-dessous.\n${c.map((x) => `- ${x}`).join("\n")}\n\n` : ""}Règles par défaut :
- Réponds en français, court et direct, ton un peu complice. Pas de blabla.
- Tu as une voix : le téléphone lit tes réponses à voix haute et ${nom} te parle souvent au micro. Écris pour l'oral : phrases courtes, pas de tableaux ni de longues listes sauf si on te les demande.
- AGIS avec tes outils au lieu d'expliquer comment faire. Enchaîne autant d'outils que nécessaire, puis résume en une ou deux phrases.
- N'invente jamais de données : vérifie avec un outil.
- Dès que tu apprends un fait durable sur ${nom}, appelle memoriser. Quand il te dit comment te comporter, memoriser avec la catégorie « consigne », et applique-le toujours ensuite. Un souvenir faux : modifier_souvenir.
- Ce que tu crois savoir sur l'actualité, les prix ou les horaires peut être périmé : cherche sur le web (web_search / web_fetch si tu les as, sinon utiliser_service) et cite la source.

Ce que le téléphone fait lui-même : mémoire, historique, À faire (avec rappels), automatisations et routines, tickets, GitHub, liens (appel, SMS, mail, carte), partage, presse-papiers, position.
Ce qu'il NE peut PAS faire lui-même : souris, clavier, écran et applis d'un ordinateur, fichiers de l'ordinateur, terminal, mails, agenda, SSH, navigateur piloté, sites appris, WhatsApp, tâches de code. Pour tout ça, passe par un ordinateur : demander_a_appareil (applis, fichiers, système), utiliser_service (mails, agenda, SSH, sites, navigateur…), lancer_tache_code (coder), recuperer_fichier_appareil / envoyer_fichier_appareil (fichiers). Si aucun ordinateur n'est allumé, dis-le simplement et propose d'ajouter la demande à la liste À faire.

Méthode :
1. Relis ta mémoire ci-dessous et la fin des conversations (tous appareils) : ne redemande pas ce que tu sais.
2. Passé (« comme hier ») → historique_lire / chercher_memoire.
3. « Je dois… », « rappelle-moi de … à 18 h » → ajouter_a_faire (avec rappel). « Qu'est-ce que j'ai prévu ? » → lister_a_faire. « Le briefing » → briefing_du_jour.
4. « Sur mon PC / Mac… » → demander_a_appareil.
5. Bug ou idée pour Wesley → envoyer_ticket.

Nous sommes le ${JOURS[(d.getDay() + 6) % 7]} ${d.toLocaleDateString("fr-FR")} (heure exacte : date_heure).

# Tes services
${servicesTexte()}

# Ce que tu sais sur ${nom}
${faits || "(rien encore)"}

# Fin des dernières conversations (tous appareils)
${resumeRecent(30) || "(aucune)"}`
  );
}

// ---------- erreurs lisibles ----------
async function erreurApi(r: Response, ia: string): Promise<Error> {
  const d = await r.json().catch(() => ({}) as any);
  const m: string = d?.error?.message || d?.message || d?.detail || "";
  if (r.status === 401 || r.status === 403) return new Error(`Clé API ${ia} refusée : vérifie-la dans Réglages › Cerveau.${m ? ` (${m})` : ""}`);
  if (r.status === 429) return new Error(`${ia} : trop de demandes ou crédit épuisé, réessaie dans un instant.${m ? ` (${m})` : ""}`);
  return new Error(`${ia} : erreur ${r.status}${m ? ` — ${m}` : ""}`);
}

async function requete(url: string, init: RequestInit, ia: string) {
  try {
    return await fetch(url, init);
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new Error(`${ia} injoignable depuis le téléphone (réseau, ou ce service refuse les appareils mobiles). Choisis « relais » dans Réglages › Cerveau.`);
  }
}

// ---------- Claude ----------
type BlocClaude = { type: string; id?: string; name?: string; input?: any; text?: string; [k: string]: unknown };

async function tourClaude(histo: any[], ctx: Contexte, ev: (e: Evenement) => void): Promise<string> {
  const profil = useDonnees.getState().profil;
  const modele = String(profil.claude_modele || CLAUDE_DEFAUT);
  let web = true;
  for (let tour = 0; tour < MAX_TOURS; tour++) {
    const outils: any[] = outilsDisponibles()
      .filter((o) => !(web && o.nom === "recherche_web"))
      .map((o) => ({ name: o.nom, description: o.description, input_schema: schemaJson(o) }));
    if (web) outils.push({ type: "web_search_20260209", name: "web_search", max_uses: 6 }, { type: "web_fetch_20260209", name: "web_fetch", max_uses: 6 });
    outils[outils.length - 1].cache_control = { type: "ephemeral" };
    const r = await requete(
      "https://api.anthropic.com/v1/messages",
      {
        method: "POST",
        signal: ctx.signal,
        headers: {
          "content-type": "application/json",
          "x-api-key": cleApi("ANTHROPIC_API_KEY"),
          "anthropic-version": "2023-06-01",
          "anthropic-dangerous-direct-browser-access": "true",
        },
        body: JSON.stringify({
          model: modele,
          max_tokens: 16000,
          system: [{ type: "text", text: promptSysteme(), cache_control: { type: "ephemeral" } }],
          messages: histo,
          tools: outils,
        }),
      },
      "Claude",
    );
    if (!r.ok) {
      const e = await erreurApi(r, "Claude");
      // outils web indisponibles pour cette clé / ce modèle : on continue sans eux
      if (r.status === 400 && web && /web_(search|fetch)|tool/i.test(e.message)) {
        web = false;
        tour--;
        continue;
      }
      throw e;
    }
    const d = (await r.json()) as { content: BlocClaude[]; stop_reason: string };
    histo.push({ role: "assistant", content: d.content });
    for (const b of d.content) if (b.type === "server_tool_use") ev({ type: "outil", nom: String(b.name), args: (b.input as Record<string, unknown>) || {} });
    if (d.stop_reason === "pause_turn") continue; // recherche web longue : on relance pour qu'il finisse
    const appels = d.content.filter((b) => b.type === "tool_use");
    if (d.stop_reason !== "tool_use" || !appels.length) {
      return d.content
        .filter((b) => b.type === "text")
        .map((b) => b.text)
        .join("")
        .trim();
    }
    const resultats = [];
    for (const a of appels) {
      ev({ type: "outil", nom: a.name!, args: a.input || {} });
      const res = await executerOutil(a.name!, a.input || {}, ctx);
      ev({ type: "resultat", nom: a.name!, resultat: res });
      resultats.push({ type: "tool_result", tool_use_id: a.id, content: res });
    }
    histo.push({ role: "user", content: resultats });
  }
  return "(J'ai atteint le nombre maximum d'étapes pour cette demande.)";
}

// ---------- compatible OpenAI ----------
async function tourOpenAI(id: string, histo: any[], ctx: Contexte, ev: (e: Evenement) => void): Promise<string> {
  const profil = useDonnees.getState().profil;
  let base: string, cle: string, modele: string, nom: string;
  if (id === "ollama") {
    base = reglagesTel().ollama_url.replace(/\/+$/, "") + "/v1";
    cle = "ollama";
    modele = String(profil.ollama_modele || "qwen3.5:9b");
    nom = "Ollama";
  } else {
    const f = PAR_ID[id];
    base = f.url === "perso" ? String(profil.perso_url || "") : f.url;
    cle = cleApi(f.env);
    modele = String(profil[`${id}_modele`] || f.defaut);
    nom = f.nom;
    if (!base.startsWith("https://")) throw new Error(`${nom} : il faut une adresse HTTPS pour l'utiliser depuis le téléphone.`);
  }
  const outils = outilsDisponibles().map((o) => ({ type: "function", function: { name: o.nom, description: o.description, parameters: schemaJson(o) } }));
  for (let tour = 0; tour < MAX_TOURS; tour++) {
    const r = await requete(
      base.replace(/\/+$/, "") + "/chat/completions",
      {
        method: "POST",
        signal: ctx.signal,
        headers: { "Content-Type": "application/json", ...(cle ? { Authorization: `Bearer ${cle}` } : {}) },
        body: JSON.stringify({ model: modele, messages: [{ role: "system", content: promptSysteme() }, ...histo], tools: outils }),
      },
      nom,
    );
    if (!r.ok) throw await erreurApi(r, nom);
    const d = await r.json();
    const m = d.choices?.[0]?.message || {};
    const appels: { id: string; function: { name: string; arguments: string } }[] = m.tool_calls || [];
    histo.push({ role: "assistant", content: m.content || "", ...(appels.length ? { tool_calls: appels } : {}) });
    if (!appels.length) return String(m.content || "").trim();
    for (const a of appels) {
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(a.function.arguments || "{}");
      } catch {
        /* arguments mal formés : l'outil répondra qu'il manque des informations */
      }
      ev({ type: "outil", nom: a.function.name, args });
      const res = await executerOutil(a.function.name, args, ctx);
      ev({ type: "resultat", nom: a.function.name, resultat: res });
      histo.push({ role: "tool", tool_call_id: a.id, content: res });
    }
  }
  return "(J'ai atteint le nombre maximum d'étapes pour cette demande.)";
}

// ---------- relais : un ordinateur traite toute la demande ----------
async function tourRelais(texte: string, ctx: Contexte): Promise<string> {
  const a = await ordinateurParDefaut();
  ctx.surEtat(`Envoi à ${a.nom}…`);
  const r = await envoyer(a, { type: "demande", texte }, ctx.surEtat);
  return r.ok ? r.resultat : `${a.nom} : ${r.resultat}`;
}

// ---------- conversation ----------
export class Conversation {
  private claude: any[] = [];
  private openai: any[] = [];
  private controleur: AbortController | null = null;

  reset() {
    this.claude = [];
    this.openai = [];
  }

  arreter() {
    this.controleur?.abort();
  }

  /** Envoie une demande ; journal = écrit dans l'historique du compte (false pour les ordres reçus d'un autre appareil). */
  async demander(texte: string, ev: (e: Evenement) => void, journal = true): Promise<{ texte: string; cerveau: Choix }> {
    const choix = cerveauActif();
    this.controleur = new AbortController();
    const ctx: Contexte = { surEtat: (s) => ev({ type: "etat", texte: s }), signal: this.controleur.signal };
    if (journal) journaliser(prenom(), texte);
    // l'historique est raccourci pour rester rapide et bon marché (les 40 derniers messages, coupés proprement)
    const couper = (h: any[]) => {
      while (h.length > 40) {
        h.shift();
        while (h.length && (h[0].role !== "user" || typeof h[0].content !== "string")) h.shift();
      }
    };
    let rep: string;
    try {
      if (choix.id === "relais") rep = await tourRelais(texte, ctx);
      else if (choix.id === "claude") {
        this.claude.push({ role: "user", content: texte });
        couper(this.claude);
        rep = await tourClaude(this.claude, ctx, ev);
      } else {
        this.openai.push({ role: "user", content: texte });
        couper(this.openai);
        rep = await tourOpenAI(choix.id, this.openai, ctx, ev);
      }
    } catch (e) {
      // conversation remise à zéro après une erreur : l'historique au format de l'IA pourrait être incomplet
      this.reset();
      if ((e as Error).name === "AbortError") throw new Error("Interrompu.");
      throw e;
    } finally {
      this.controleur = null;
    }
    rep = rep || "C'est fait.";
    if (journal) journaliser("Wesley", rep);
    return { texte: rep, cerveau: choix };
  }
}

/** Indique si une clé IA est présente dans le coffre (pour l'écran Réglages). */
export const clesPresentes = () => Object.keys(lireCoffre()).filter((k) => k !== "trousseau" && !!lireCoffre()[k]);
