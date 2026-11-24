/**
 * Outils du Wesley du téléphone. Mêmes noms et mêmes paramètres que sur le bureau (wesley/outils/*.py) quand
 * l'outil existe aussi là-bas, pour que l'IA se comporte pareil partout.
 *
 * Ce qui ne peut pas tourner dans un téléphone (souris, clavier, applis de l'ordinateur, terminal, mails IMAP,
 * SSH, navigateur piloté, sites appris, tâches de code) passe par un de tes ordinateurs : l'outil lui envoie la
 * demande (ordre chiffré, voir appareils.ts) et renvoie sa réponse.
 */
import { cleApi, secret } from "./compte";
import { envoyer, MAX_FICHIER, ordinateurParDefaut, trouver } from "./appareils";
import {
  ajouterAFaire,
  basculerAutomatisation,
  chargerAppareils,
  chargerTickets,
  chercherSouvenirs,
  creerAutomatisation,
  decrireAutomatisation,
  envoyerTicket,
  garderFichier,
  LIBELLES_ETAPES,
  memoriser,
  modifierAFaire,
  modifierSouvenir,
  oublierSouvenir,
  supprimerAFaire,
  supprimerAutomatisation,
  trouverAFaire,
  trouverRoutine,
  useDonnees,
  JOURS,
} from "./donnees";
import { nomTelephone } from "./stockage";
import type { Automatisation, Connecteurs } from "./types";
import { agirPartage, chargerPartages, horodatage, lirePartage, toursDeParole, usePartages, type Genre, type Partage, type Segment } from "./partages";

export type Contexte = { surEtat: (s: string) => void; signal?: AbortSignal };
type Params = Record<string, { type: "string" | "integer" | "boolean" | "number"; description: string; enum?: string[] }>;
export type Outil = {
  nom: string;
  description: string;
  params: Params;
  requis?: string[];
  disponible?: () => boolean;
  executer: (a: Record<string, any>, c: Contexte) => Promise<string> | string;
};

const s = (description: string, en?: string[]) => ({ type: "string" as const, description, ...(en ? { enum: en } : {}) });
const n = (description: string) => ({ type: "integer" as const, description });
const b = (description: string) => ({ type: "boolean" as const, description });

/** Fait faire quelque chose par un ordinateur du compte (celui demandé, sinon le premier disponible). */
async function parOrdinateur(demande: string, c: Contexte, appareil = "") {
  const a = appareil ? await trouver(appareil) : await ordinateurParDefaut();
  c.surEtat(`Envoi à ${a.nom}…`);
  const r = await envoyer(a, { type: "demande", texte: demande }, c.surEtat);
  return `[${r.appareil}] ${r.resultat || ""}`;
}

const pad = (x: number) => String(x).padStart(2, "0");

/** Tâche ou transcription d'un ordinateur, par son code (vide = la plus récente). */
async function partage(genre: Genre, identifiant: string): Promise<Partage> {
  await chargerPartages();
  const l = usePartages
    .getState()
    .liste.filter((x) => x.genre === genre)
    .sort((a, b) => (b.resume.debut || b.resume.cree || 0) - (a.resume.debut || a.resume.cree || 0));
  const id = identifiant.replace(/[[\]\s]/g, "");
  const p = id ? l.find((x) => x.resume.id === id) : l[0];
  if (!p) throw new Error(genre === "tache" ? "Tâche introuvable." : "Transcription introuvable.");
  return p;
}

// ---------- GitHub (directement depuis le téléphone, avec le jeton du coffre) ----------
function jetonGitHub() {
  const c = useDonnees.getState().connecteurs;
  for (const [cid, d] of Object.entries(c)) if (d.type === "github" && d.actif !== false && secret(`${cid}:jeton`)) return secret(`${cid}:jeton`);
  return secret("github:jeton");
}
async function github(methode: string, chemin: string, corps?: unknown) {
  const r = await fetch(`https://api.github.com${chemin}`, {
    method: methode,
    headers: { Authorization: `Bearer ${jetonGitHub()}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
    body: corps ? JSON.stringify(corps) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`GitHub ${r.status} : ${(d as { message?: string }).message || ""}`.slice(0, 200));
  return d as any;
}

export const OUTILS: Outil[] = [
  // ---------- base ----------
  {
    nom: "date_heure",
    description: "Donne la date et l'heure exactes du téléphone.",
    params: {},
    executer: () => {
      const d = new Date();
      return `${JOURS[(d.getDay() + 6) % 7]} ${d.toLocaleDateString("fr-FR")} ${pad(d.getHours())}:${pad(d.getMinutes())} (fuseau ${Intl.DateTimeFormat().resolvedOptions().timeZone})`;
    },
  },

  // ---------- mémoire ----------
  {
    nom: "memoriser",
    description:
      "Retient un fait durable sur l'utilisateur (goût, projet, personne, habitude) ou une consigne sur ta façon de te comporter (catégorie « consigne »). Synchronisé sur tous ses appareils.",
    params: { fait: s("le fait, en une phrase"), categorie: s("general, preference, personne, projet, consigne, lecon…") },
    requis: ["fait"],
    executer: (a) => memoriser(a.fait, a.categorie || "general"),
  },
  {
    nom: "retenir_lecon",
    description: "Retient une méthode qui a marché (ou une correction de l'utilisateur sur ta façon de faire), pour la réappliquer ensuite.",
    params: { lecon: s("la leçon, en une phrase") },
    requis: ["lecon"],
    executer: (a) => memoriser(a.lecon, "lecon"),
  },
  {
    nom: "chercher_memoire",
    description: "Cherche dans la mémoire (souvenirs) de l'utilisateur. Renvoie les souvenirs avec leur identifiant.",
    params: { requete: s("mots à chercher (vide = tout)") },
    executer: (a) =>
      chercherSouvenirs(a.requete || "")
        .slice(0, 40)
        .map((f) => `[${f.fid}] (${f.categorie}) ${f.fait}`)
        .join("\n") || "Rien trouvé.",
  },
  {
    nom: "modifier_souvenir",
    description: "Corrige un souvenir faux ou qui a changé (au lieu de le supprimer puis le recréer).",
    params: { identifiant: s("identifiant entre crochets (chercher_memoire)"), fait: s("nouveau texte"), categorie: s("nouvelle catégorie (facultatif)") },
    requis: ["identifiant", "fait"],
    executer: (a) => (modifierSouvenir(String(a.identifiant).replace(/[[\]]/g, ""), a.fait, a.categorie) ? "Souvenir corrigé." : "Souvenir introuvable."),
  },
  {
    nom: "oublier",
    description: "Oublie un souvenir qui n'est plus vrai du tout.",
    params: { identifiant: s("identifiant entre crochets (chercher_memoire), ou un morceau du texte") },
    requis: ["identifiant"],
    executer: (a) => {
      const cle = String(a.identifiant).replace(/[[\]]/g, "").trim();
      const faits = useDonnees.getState().faits;
      const cibles = faits.some((f) => f.fid === cle) ? [cle] : faits.filter((f) => f.fait.toLowerCase().includes(cle.toLowerCase())).map((f) => f.fid);
      if (cibles.length > 3) return `Trop de souvenirs correspondent (${cibles.length}) : précise avec l'identifiant.`;
      cibles.forEach(oublierSouvenir);
      return cibles.length ? `Oublié (${cibles.length}).` : "Rien à oublier.";
    },
  },
  {
    nom: "historique_jours",
    description: "Liste les jours où l'utilisateur a parlé avec Wesley (tous appareils, 30 derniers jours sur le téléphone).",
    params: {},
    executer: () => {
      const j: Record<string, number> = {};
      for (const l of useDonnees.getState().historique) j[l.jour] = (j[l.jour] || 0) + 1;
      return Object.entries(j)
        .map(([k, v]) => `${k} : ${v} lignes`)
        .join("\n") || "Aucun historique.";
    },
  },
  {
    nom: "historique_lire",
    description: "Lit les conversations d'un jour (tous appareils confondus).",
    params: { jour: s("AAAA-MM-JJ (vide = aujourd'hui)"), recherche: s("mot à chercher (facultatif)") },
    executer: (a) => {
      const jour = a.jour || new Date().toISOString().slice(0, 10);
      const r = (a.recherche || "").toLowerCase();
      return (
        useDonnees
          .getState()
          .historique.filter((l) => l.jour === jour && (!r || l.ligne.toLowerCase().includes(r)))
          .map((l) => `(${l.machine}) ${l.ligne}`)
          .slice(-200)
          .join("\n") || "Rien ce jour-là."
      );
    },
  },

  // ---------- À faire ----------
  {
    nom: "ajouter_a_faire",
    description:
      "Ajoute une tâche à la liste « À faire » de l'utilisateur (ce qu'il doit / veut faire). Avec rappel : il est prévenu à l'heure dite sur ses appareils.",
    params: {
      titre: s("la tâche, courte"),
      note: s("détails (facultatif)"),
      echeance: s("échéance AAAA-MM-JJ ou AAAA-MM-JJ HH:MM (facultatif)"),
      rappel: s("quand le prévenir, AAAA-MM-JJ HH:MM (facultatif)"),
      priorite: s("basse | normale | haute", ["basse", "normale", "haute"]),
    },
    requis: ["titre"],
    executer: async (a) => {
      const t = await ajouterAFaire(a as { titre: string });
      return `Ajouté [${t.id}] : ${t.titre}${t.rappel ? ` (rappel ${t.rappel.replace("T", " ")})` : ""}`;
    },
  },
  {
    nom: "lister_a_faire",
    description: "Liste la liste « À faire » (par défaut : ce qui n'est pas fini).",
    params: { tout: b("true pour inclure les tâches faites") },
    executer: (a) =>
      useDonnees
        .getState()
        .afaire.filter((t) => a.tout || t.statut !== "fait")
        .map(
          (t) =>
            `[${t.id}] ${LIBELLES_ETAPES[t.statut]} — ${t.titre}${t.echeance ? ` (pour ${t.echeance.replace("T", " ")})` : ""}${t.priorite === "haute" ? " ⚑" : ""}${t.note ? ` — ${t.note}` : ""}`,
        )
        .join("\n") || "Rien de prévu.",
  },
  {
    nom: "changer_etape_a_faire",
    description: "Passe une tâche à une autre étape (« c'est fait », « j'ai commencé »).",
    params: { tache: s("identifiant ou morceau du titre"), etape: s("a_faire | en_cours | fait", ["a_faire", "en_cours", "fait"]) },
    requis: ["tache", "etape"],
    executer: async (a) => {
      const l = trouverAFaire(a.tache);
      if (l.length !== 1) return l.length ? `Plusieurs tâches correspondent : ${l.map((t) => `[${t.id}] ${t.titre}`).join(", ")}` : "Tâche introuvable.";
      await modifierAFaire(l[0].id, { statut: a.etape });
      return `« ${l[0].titre} » : ${LIBELLES_ETAPES[a.etape] || a.etape}.`;
    },
  },
  {
    nom: "modifier_a_faire",
    description: "Modifie une tâche de la liste À faire (titre, note, échéance, rappel, priorité).",
    params: {
      tache: s("identifiant ou morceau du titre"),
      titre: s("nouveau titre"),
      note: s("nouvelle note"),
      echeance: s("AAAA-MM-JJ HH:MM"),
      rappel: s("AAAA-MM-JJ HH:MM"),
      priorite: s("basse | normale | haute"),
    },
    requis: ["tache"],
    executer: async (a) => {
      const l = trouverAFaire(a.tache);
      if (l.length !== 1) return l.length ? "Plusieurs tâches correspondent : précise." : "Tâche introuvable.";
      const { tache: _t, ...champs } = a;
      await modifierAFaire(l[0].id, champs);
      return "Tâche modifiée.";
    },
  },
  {
    nom: "supprimer_a_faire",
    description: "Supprime une tâche de la liste À faire.",
    params: { tache: s("identifiant ou morceau du titre") },
    requis: ["tache"],
    executer: async (a) => {
      const l = trouverAFaire(a.tache);
      if (l.length !== 1) return l.length ? "Plusieurs tâches correspondent : précise." : "Tâche introuvable.";
      await supprimerAFaire(l[0].id);
      return `Supprimée : ${l[0].titre}`;
    },
  },
  {
    nom: "briefing_du_jour",
    description: "Prépare le briefing du jour : date, tâches en retard et du jour, rappels, tickets mis à jour. Résume-le ensuite à l'oral.",
    params: {},
    executer: () => {
      const d = useDonnees.getState();
      const auj = new Date().toISOString().slice(0, 10);
      const ouvertes = d.afaire.filter((t) => t.statut !== "fait");
      const retard = ouvertes.filter((t) => t.echeance && t.echeance.slice(0, 10) < auj);
      const jour = ouvertes.filter((t) => t.echeance.slice(0, 10) === auj || t.rappel.slice(0, 10) === auj);
      const enLigne = d.appareils.filter((a) => !a.moi && a.en_ligne).map((a) => a.nom);
      return [
        `Date : ${new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}`,
        `En retard : ${retard.map((t) => t.titre).join(", ") || "rien"}`,
        `Aujourd'hui : ${jour.map((t) => t.titre + (t.rappel ? ` (rappel ${t.rappel.slice(11)})` : "")).join(", ") || "rien de daté"}`,
        `Autres tâches ouvertes : ${ouvertes.length - retard.length - jour.length}`,
        `Appareils allumés : ${enLigne.join(", ") || "aucun"}`,
        "(Agenda, mails, météo : demande-les à un ordinateur avec utiliser_service si l'utilisateur les veut.)",
      ].join("\n");
    },
  },

  // ---------- automatisations ----------
  {
    nom: "creer_automatisation",
    description:
      "Crée une automatisation (règle permanente), exécutée par ses ordinateurs : « tous les matins à 8 h lis-moi mon agenda », « quand je reçois un mail de papa préviens-moi », routine « mode travail »…",
    params: {
      description: s("nom court de la règle"),
      declencheur: s("horaire | intervalle | demarrage | mail | commande (routine dite à voix haute)", ["horaire", "intervalle", "demarrage", "mail", "commande"]),
      heure: s("pour horaire : HH:MM"),
      jours: s("pour horaire : 0=lundi … 6=dimanche, séparés par des virgules (vide = tous les jours)"),
      minutes: n("pour intervalle : toutes les combien de minutes"),
      expediteur: s("pour mail : adresse ou nom de l'expéditeur"),
      sujet: s("pour mail : mot du sujet"),
      contient: s("pour mail : mot du texte"),
      action: s("wesley (exécuter la consigne) ou prevenir (dire le message)", ["wesley", "prevenir"]),
      consigne: s("pour action wesley : ce qu'il faut faire"),
      message: s("pour action prevenir : la phrase à dire"),
      phrase: s("pour commande : la phrase qui lance la routine"),
      appareil: s("nom de l'ordinateur qui l'exécute (vide = tous)"),
    },
    requis: ["description"],
    executer: async (a) => {
      const type = (a.declencheur || "mail") as Automatisation["declencheur"]["type"];
      if (type === "mail" && !(a.expediteur || a.sujet || a.contient)) return "Pour un mail, précise au moins un expéditeur, un mot du sujet ou un mot du texte.";
      if (type === "horaire" && !a.heure) return "Précise l'heure (HH:MM).";
      if (type === "intervalle" && !a.minutes) return "Précise l'intervalle en minutes.";
      const r = await creerAutomatisation({
        ...a,
        nom: a.description,
        type,
        jours: a.jours ? String(a.jours).split(",").map(Number).filter((x) => !isNaN(x)) : [],
      });
      return `Automatisation créée : ${decrireAutomatisation(r)}`;
    },
  },
  {
    nom: "lister_automatisations",
    description: "Liste les automatisations de l'utilisateur (règles « quand… alors… » et routines).",
    params: {},
    executer: () =>
      useDonnees
        .getState()
        .automatisations.map((r) => `[${r.id}] ${r.actif ? "" : "(en pause) "}${r.nom} : ${decrireAutomatisation(r)}`)
        .join("\n") || "Aucune automatisation.",
  },
  {
    nom: "activer_automatisation",
    description: "Met en pause ou réactive une automatisation.",
    params: { identifiant: s("code entre crochets (lister_automatisations)"), actif: b("true = active, false = en pause") },
    requis: ["identifiant", "actif"],
    executer: async (a) => {
      await basculerAutomatisation(String(a.identifiant).replace(/[[\] ]/g, ""), !!a.actif);
      return a.actif ? "Réactivée." : "Mise en pause.";
    },
  },
  {
    nom: "supprimer_automatisation",
    description: "Supprime une automatisation.",
    params: { identifiant: s("code entre crochets (lister_automatisations)") },
    requis: ["identifiant"],
    executer: async (a) => {
      const id = String(a.identifiant).replace(/[[\] ]/g, "");
      if (!useDonnees.getState().automatisations.some((r) => r.id === id)) return "Introuvable.";
      await supprimerAutomatisation(id);
      return "Supprimée.";
    },
  },
  {
    nom: "lancer_routine",
    description: "Lance une routine de l'utilisateur (« mode travail », « fin de journée »…) : renvoie les étapes à exécuter tout de suite avec tes outils.",
    params: { nom: s("la phrase ou le nom de la routine") },
    requis: ["nom"],
    executer: (a) => {
      const r = trouverRoutine(a.nom);
      if (!r) {
        const noms = useDonnees
          .getState()
          .automatisations.filter((x) => x.declencheur.type === "commande")
          .map((x) => x.declencheur.phrase || x.nom);
        return "Routine introuvable." + (noms.length ? ` Routines existantes : ${noms.join(", ")}.` : " Aucune routine : propose d'en créer une.");
      }
      return (
        `[Routine « ${r.declencheur.phrase || r.nom} »] Fais maintenant, dans l'ordre et avec tes outils, ce qui suit, puis résume en une phrase. ` +
        `Les étapes qui demandent un ordinateur (applis, fichiers, mails…) : passe par demander_a_appareil.\n${r.action.consigne || r.action.message || r.nom}`
      );
    },
  },

  // ---------- appareils ----------
  {
    nom: "lister_appareils",
    description: "Liste les appareils où Wesley est connecté avec le même compte : en ligne ou non, occupé, accepte les ordres.",
    params: {},
    executer: async () =>
      (await chargerAppareils())
        .map((a) => {
          const etat = a.en_ligne ? "en ligne" + (a.occupe ? ", occupé" : "") : `hors ligne (vu il y a ${Math.floor((Date.now() / 1000 - (a.vu || 0)) / 60)} min)`;
          return `- ${a.nom} (${a.plateforme || "?"}) : ${etat}${a.moi ? " — CET APPAREIL (téléphone)" : ""}${a.accepte || a.moi ? "" : " — refuse les ordres"}`;
        })
        .join("\n") || "Aucun appareil.",
  },
  {
    nom: "demander_a_appareil",
    description:
      "Fait exécuter une demande par Wesley sur un de tes ORDINATEURS (ou un autre téléphone) : ouvrir une appli, souris/clavier, fichiers, terminal, écran, « éteins le PC »… Le Wesley de l'appareil cible l'exécute avec ses propres outils et renvoie le résultat.",
    params: { appareil: s("nom de l'appareil (ou « PC », « Mac »… voir lister_appareils ; vide = l'ordinateur allumé)"), demande: s("ce qu'il doit faire, en une phrase claire et complète") },
    requis: ["demande"],
    executer: (a, c) => parOrdinateur(a.demande, c, a.appareil || ""),
  },
  {
    nom: "recuperer_fichier_appareil",
    description: "Copie un fichier d'un de tes ordinateurs vers ce téléphone (10 Mo maximum) : il apparaît dans Appareils › Fichiers reçus, prêt à ouvrir ou partager.",
    params: { appareil: s("nom de l'appareil source"), chemin_distant: s("chemin du fichier là-bas (ex : ~/Desktop/rapport.pdf)") },
    requis: ["appareil", "chemin_distant"],
    executer: async (a, c) => {
      const r = await envoyer(a.appareil, { type: "lire_fichier", chemin: a.chemin_distant }, c.surEtat);
      if (!r.ok || !r.contenu) return r.resultat || "Échec.";
      const f = garderFichier({ nom: r.nom || "fichier", taille: Math.floor((r.contenu.length * 3) / 4), de: r.appareil, contenu: r.contenu });
      return `Fichier récupéré depuis ${r.appareil} : ${f.nom} (Appareils › Fichiers reçus).`;
    },
  },
  {
    nom: "envoyer_fichier_appareil",
    description: "Copie un fichier du téléphone (joint dans la conversation ou reçu, voir Fichiers reçus) vers un de tes ordinateurs (10 Mo maximum).",
    params: { appareil: s("nom de l'appareil de destination"), fichier: s("nom du fichier sur le téléphone (vide = le dernier)"), chemin_distant: s("où l'enregistrer là-bas (ex : ~/Downloads/photo.jpg)") },
    requis: ["appareil"],
    executer: async (a, c) => {
      const l = useDonnees.getState().fichiers;
      const f = a.fichier ? [...l].reverse().find((x) => x.nom === a.fichier || x.nom.includes(a.fichier)) : l.at(-1);
      if (!f) return `Fichier introuvable sur le téléphone. Fichiers : ${l.map((x) => x.nom).join(", ") || "aucun (joins-en un avec le trombone)"}`;
      if (f.taille > MAX_FICHIER) return "Fichier trop gros (maximum 10 Mo).";
      const r = await envoyer(a.appareil, { type: "ecrire_fichier", chemin: a.chemin_distant || `~/Downloads/${f.nom}`, contenu: f.contenu }, c.surEtat);
      return r.resultat || "";
    },
  },

  // ---------- services connectés (sur les ordinateurs) ----------
  {
    nom: "utiliser_service",
    description:
      "Utilise un service connecté de l'utilisateur, qui tourne sur ses ordinateurs : mails (lire, chercher, répondre, envoyer), agenda, serveur SSH, navigateur de Wesley et sites appris (site_chercher, connexion auto), WhatsApp, Notion, serveurs MCP, recherche web… Décris la demande complète : un ordinateur l'exécute avec ses outils.",
    params: { demande: s("la demande complète, ex : « lis mes 5 derniers mails non lus de Gmail travail »"), appareil: s("ordinateur à utiliser (vide = celui qui est allumé)") },
    requis: ["demande"],
    executer: (a, c) => parOrdinateur(a.demande, c, a.appareil || ""),
  },

  // ---------- tâches de fond (Claude Code sur un ordinateur) ----------
  {
    nom: "lancer_tache_code",
    description:
      "Lance une tâche de code EN ARRIÈRE-PLAN sur un ordinateur (Claude Code ou Codex crée une branche et code) : à utiliser dès qu'on te demande de coder / développer / corriger quelque chose dans un projet. Le WESLEY.md du projet est transmis à l'agent, qui le tient à jour.",
    params: {
      consigne: s("la demande complète et précise"),
      projet: s("chemin du dossier du projet sur l'ordinateur (vide = le demander à l'ordinateur)"),
      outil: s("claude_code (défaut), codex, ou wesley", ["claude_code", "codex", "wesley"]),
      titre: s("titre court"),
      appareil: s("ordinateur (vide = celui qui est allumé)"),
    },
    requis: ["consigne"],
    executer: (a, c) =>
      parOrdinateur(
        `Lance une tâche de fond avec l'outil lancer_tache_code : consigne = « ${a.consigne} »` +
          (a.projet ? `, projet = ${a.projet}` : ", projet = trouve le bon dossier dans tes projets détectés") +
          `, outil = ${a.outil || "claude_code"}${a.titre ? `, titre = « ${a.titre} »` : ""}. Réponds avec le code de la tâche.`,
        c,
        a.appareil || "",
      ),
  },
  // tâches et transcriptions des ordinateurs : lues ici (publiées chiffrées dans le compte), et les actions sont
  // demandées à l'ordinateur qui les a lancées (moteur/partages.ts) ; s'il ne peut pas, on dit pourquoi
  {
    nom: "lister_taches",
    description: "Liste les tâches de fond (code) de tous tes ordinateurs, avec leur état, leur bilan et l'ordinateur où elles tournent.",
    params: {},
    executer: async () => {
      await chargerPartages();
      const l = usePartages.getState().liste.filter((x) => x.genre === "tache");
      return (
        l
          .map((p) => `[${p.resume.id}] ${p.resume.statut} — ${p.resume.titre} (sur ${p.resume.appareil_nom}, ${p.resume.projet || ""})` + (p.resume.bilan ? `\n   bilan : ${p.resume.bilan}` : ""))
          .join("\n") || "Aucune tâche."
      );
    },
  },
  {
    nom: "suivre_tache",
    description: "Donne l'état d'une tâche de fond et ses dernières étapes.",
    params: { identifiant: s("code de la tâche"), dernieres: { type: "number", description: "nombre d'étapes à afficher (15 par défaut)" } },
    requis: ["identifiant"],
    executer: async (a) => {
      const p = await partage("tache", a.identifiant);
      const t = await lirePartage<{ journal: { genre: string; texte: string }[] }>("tache", p.resume.id);
      const j = (t.journal ?? []).slice(-Math.max(1, Number(a.dernieres) || 15)).map((e) => `- (${e.genre}) ${String(e.texte).slice(0, 300)}`);
      return `[${p.resume.id}] ${p.resume.statut} — ${p.resume.titre} (sur ${p.resume.appareil_nom})\nBranche : ${p.resume.branche || "—"}\nBilan : ${p.resume.bilan || "—"}\n${j.join("\n")}`;
    },
  },
  {
    nom: "mettre_a_jour_tache",
    description: "Ajoute ou change une consigne d'une tâche de fond en cours (ou la relance) : demandé à l'ordinateur où elle tourne.",
    params: { identifiant: s("code de la tâche"), consigne: s("la nouvelle consigne") },
    requis: ["identifiant", "consigne"],
    executer: async (a, c) => agirPartage(await partage("tache", a.identifiant), "consigne", { texte: a.consigne }, c.surEtat),
  },
  {
    nom: "arreter_tache",
    description: "Arrête une tâche de fond (sur l'ordinateur où elle tourne).",
    params: { identifiant: s("code de la tâche") },
    requis: ["identifiant"],
    executer: async (a, c) => agirPartage(await partage("tache", a.identifiant), "arreter", {}, c.surEtat),
  },
  {
    nom: "reprendre_tache",
    description:
      "Relance une tâche de fond arrêtée, interrompue, terminée ou en échec, sur l'ordinateur où elle a été lancée. S'il est éteint ou ne peut pas, la réponse dit pourquoi : répète-le simplement à l'utilisateur.",
    params: { identifiant: s("code de la tâche") },
    requis: ["identifiant"],
    executer: async (a, c) => agirPartage(await partage("tache", a.identifiant), "reprendre", {}, c.surEtat),
  },

  // ---------- transcriptions de réunions (faites sur les ordinateurs) ----------
  {
    nom: "lister_transcriptions",
    description: "Liste les transcriptions de réunions faites sur tes ordinateurs (titre, date, durée, personnes, état, ordinateur, identifiant).",
    params: {},
    executer: async () => {
      await chargerPartages();
      const l = usePartages.getState().liste.filter((x) => x.genre === "transcription").sort((a, b) => (b.resume.debut || 0) - (a.resume.debut || 0));
      return (
        l
          .map(
            (p) =>
              `[${p.resume.id}] ${p.resume.titre} — ${new Date((p.resume.debut || 0) * 1000).toLocaleString("fr-FR")}, ${horodatage(p.resume.duree || 0)}, ` +
              `${p.resume.nb_locuteurs ?? 0} locuteur(s), ${p.resume.etat}, sur ${p.resume.appareil_nom}`,
          )
          .join("\n") || "Aucune transcription."
      );
    },
  },
  {
    nom: "lire_transcription",
    description:
      "Renvoie le texte exact d'une transcription de réunion (heure et locuteur de chaque prise de parole), pour la résumer ou retrouver qui a dit quoi. Longue réunion : par parties (partie=2, 3… quand la réponse l'indique).",
    params: { identifiant: s("code de la transcription (vide = la plus récente)"), partie: { type: "number", description: "partie à lire (1 par défaut)" } },
    executer: async (a) => {
      const p = await partage("transcription", a.identifiant || "");
      const c = await lirePartage<{ segments: Segment[]; noms: Record<string, string> }>("transcription", p.resume.id);
      const nom = (l: number) => c.noms?.[String(l)]?.trim() || `Locuteur ${l}`;
      const texte = toursDeParole(c.segments ?? []).map((x) => `[${horodatage(x.debut)}] ${nom(x.locuteur)} : ${x.texte}`).join("\n");
      const n = Math.max(1, Number(a.partie) || 1);
      const morceau = texte.slice((n - 1) * 9000, n * 9000);
      const suite = texte.length > n * 9000 ? `\n\n(Suite : partie=${n + 1})` : "";
      return `${p.resume.titre} (sur ${p.resume.appareil_nom})\n${morceau || "Rien n'a été transcrit."}${suite}`;
    },
  },
  {
    nom: "reprendre_transcription",
    description:
      "Reprend une transcription de réunion (terminée ou interrompue) sur l'ordinateur où elle a été faite : la suite s'ajoute, mêmes personnes, horodatage qui continue. S'il ne peut pas (éteint, autre transcription en cours…), la réponse dit pourquoi : répète-le à l'utilisateur.",
    params: { identifiant: s("code de la transcription (vide = la plus récente)") },
    executer: async (a, c) => agirPartage(await partage("transcription", a.identifiant || ""), "reprendre", {}, c.surEtat),
  },
  {
    nom: "arreter_transcription",
    description: "Arrête la transcription de réunion en cours sur un de tes ordinateurs.",
    params: { identifiant: s("code de la transcription (vide = celle en cours)") },
    executer: async (a, c) => {
      await chargerPartages();
      const enCours = usePartages.getState().liste.filter((x) => x.genre === "transcription" && ["preparation", "en_cours"].includes(x.resume.etat || ""));
      const p = a.identifiant ? await partage("transcription", a.identifiant) : enCours[0];
      if (!p) return "Aucune transcription en cours sur tes ordinateurs.";
      return agirPartage(p, "arreter", {}, c.surEtat);
    },
  },

  // ---------- GitHub (direct) ----------
  {
    nom: "github_depots",
    description: "Liste tes dépôts GitHub (les plus récemment modifiés d'abord).",
    params: {},
    disponible: () => !!jetonGitHub(),
    executer: async () =>
      (await github("GET", "/user/repos?sort=pushed&per_page=30"))
        .map((d: any) => `${d.full_name}${d.private ? " (privé)" : ""} — ★${d.stargazers_count} — maj ${String(d.pushed_at).slice(0, 10)} — ${d.description || ""}`)
        .join("\n"),
  },
  {
    nom: "github_issues",
    description: "Liste les issues et pull requests d'un dépôt GitHub.",
    params: { depot: s("propriétaire/nom"), etat: s("open | closed | all", ["open", "closed", "all"]) },
    requis: ["depot"],
    disponible: () => !!jetonGitHub(),
    executer: async (a) =>
      (await github("GET", `/repos/${a.depot}/issues?state=${a.etat || "open"}&per_page=30`))
        .map((i: any) => `#${i.number} ${i.pull_request ? "[PR] " : ""}${i.title} — ${i.user?.login}`)
        .join("\n") || "Aucune.",
  },
  {
    nom: "github_creer_issue",
    description: "Crée une issue dans un dépôt GitHub.",
    params: { depot: s("propriétaire/nom"), titre: s("titre"), description: s("texte") },
    requis: ["depot", "titre"],
    disponible: () => !!jetonGitHub(),
    executer: async (a) => {
      const i = await github("POST", `/repos/${a.depot}/issues`, { title: a.titre, body: a.description || "" });
      return `Issue #${i.number} créée : ${i.html_url}`;
    },
  },
  {
    nom: "github_notifications",
    description: "Tes notifications GitHub non lues.",
    params: {},
    disponible: () => !!jetonGitHub(),
    executer: async () =>
      (await github("GET", "/notifications?per_page=30")).map((x: any) => `${x.repository.full_name} — ${x.subject.type} — ${x.subject.title}`).join("\n") ||
      "Aucune notification.",
  },

  // ---------- tickets ----------
  {
    nom: "envoyer_ticket",
    description: "Envoie un ticket au développeur de Wesley : bug, idée, amélioration, question.",
    params: { genre: s("bug | amelioration | idee | question", ["bug", "amelioration", "idee", "question"]), titre: s("titre court"), description: s("détails") },
    requis: ["titre"],
    executer: async (a) => `Ticket n°${await envoyerTicket(a.genre || "bug", a.titre, (a.description || "") + `\n\n(envoyé depuis Wesley mobile, ${navigator.userAgent})`)} envoyé.`,
  },
  {
    nom: "mes_tickets",
    description: "Liste les tickets de l'utilisateur et les réponses du développeur.",
    params: {},
    executer: async () => {
      await chargerTickets();
      return (
        useDonnees
          .getState()
          .tickets.map((t) => `n°${t.id} [${t.statut}] ${t.titre}${t.reponse ? ` — réponse : ${t.reponse}` : ""}`)
          .join("\n") || "Aucun ticket."
      );
    },
  },

  // ---------- le téléphone lui-même ----------
  {
    nom: "ouvrir_sur_telephone",
    description:
      "Ouvre quelque chose sur le téléphone : un site (https://…), un appel (tel:+33…), un SMS (sms:+33…?body=…), un mail (mailto:…), un itinéraire (https://maps.google.com/?q=…). L'utilisateur confirme à l'écran.",
    params: { lien: s("le lien à ouvrir") },
    requis: ["lien"],
    executer: (a) => {
      const lien = String(a.lien);
      if (!/^(https?:|tel:|sms:|mailto:|geo:)/i.test(lien)) return "Lien refusé (seulement https, tel, sms, mailto, geo).";
      window.open(lien, "_blank", "noopener");
      return `Ouvert sur le téléphone : ${lien}`;
    },
  },
  {
    nom: "partager",
    description: "Ouvre le menu de partage du téléphone avec un texte (ou un lien) : WhatsApp, SMS, mail, notes…",
    params: { texte: s("le texte à partager"), titre: s("titre (facultatif)") },
    requis: ["texte"],
    executer: async (a) => {
      if (!navigator.share) {
        await navigator.clipboard?.writeText(a.texte);
        return "Partage indisponible ici : texte copié dans le presse-papiers.";
      }
      await navigator.share({ text: a.texte, title: a.titre || undefined });
      return "Menu de partage ouvert.";
    },
  },
  {
    nom: "copier",
    description: "Copie un texte dans le presse-papiers du téléphone.",
    params: { texte: s("le texte") },
    requis: ["texte"],
    executer: async (a) => {
      await navigator.clipboard.writeText(a.texte);
      return "Copié.";
    },
  },
  {
    nom: "position_actuelle",
    description: "Donne la position GPS du téléphone (l'utilisateur doit l'autoriser), pour la météo, un itinéraire, « où suis-je ».",
    params: {},
    executer: () =>
      new Promise<string>((ok) =>
        navigator.geolocation
          ? navigator.geolocation.getCurrentPosition(
              (p) => ok(`Latitude ${p.coords.latitude.toFixed(5)}, longitude ${p.coords.longitude.toFixed(5)} (précision ${Math.round(p.coords.accuracy)} m)`),
              (e) => ok(`Position indisponible : ${e.message}`),
              { timeout: 15000, maximumAge: 60000 },
            )
          : ok("Position indisponible sur ce téléphone."),
      ),
  },
];

export const outilsDisponibles = () => OUTILS.filter((o) => !o.disponible || o.disponible());

export function schemaJson(o: Outil) {
  return { type: "object", properties: o.params, required: o.requis || [] };
}

export async function executerOutil(nom: string, args: Record<string, unknown>, c: Contexte): Promise<string> {
  const o = OUTILS.find((x) => x.nom === nom);
  if (!o) return `Outil inconnu : ${nom}`;
  try {
    const r = await o.executer(args || {}, c);
    return (r || "OK").slice(0, 30000);
  } catch (e) {
    return `Erreur : ${(e as Error).message}`;
  }
}

const NOMS_TYPES: Record<string, string> = {
  mail: "Messagerie (IMAP)",
  gmail: "Gmail",
  agenda: "Agenda",
  github: "GitHub",
  notion: "Notion",
  mcp: "Serveur MCP",
  ssh: "Serveur SSH",
  whatsapp: "WhatsApp",
};
/** Nom lisible d'un connecteur : « Gmail · moi@gmail.com », « Serveur SSH · vps.exemple.fr ». */
export function etiquetteConnecteur(c: Connecteurs[string]) {
  const conf = c.conf || {};
  const detail = ["nom", "email", "adresse", "utilisateur", "hote", "url"].map((k) => conf[k]).find((v) => typeof v === "string" && v);
  return `${NOMS_TYPES[c.type] || c.type}${detail ? ` · ${detail}` : ""}`;
}

/** Les services connectés (connecteurs des ordinateurs), pour le prompt. */
export function servicesTexte() {
  const d = useDonnees.getState();
  const lignes = Object.entries(d.connecteurs)
    .filter(([, c]) => c.actif !== false)
    .map(([cid, c]) => `- ${etiquetteConnecteur(c)} (${cid})${c.type === "github" && jetonGitHub() ? " — direct depuis le téléphone (github_*)" : " — via utiliser_service"}`);
  const routines = d.automatisations.filter((r) => r.actif && r.declencheur.type === "commande");
  if (routines.length) lignes.push(`- Routines (lancer_routine) : ${routines.map((r) => `« ${r.declencheur.phrase || r.nom} »`).join(", ")}`);
  const autres = d.automatisations.filter((r) => r.actif && r.declencheur.type !== "commande").length;
  if (autres) lignes.push(`- ${autres} automatisation(s) active(s) (lister_automatisations)`);
  const ordis = d.appareils.filter((a) => !a.moi);
  lignes.push(`- Appareils : ${ordis.map((a) => `${a.nom} (${a.plateforme || "?"}, ${a.en_ligne ? "en ligne" : "hors ligne"})`).join(", ") || "aucun autre"} ; ce téléphone : ${nomTelephone()}`);
  return lignes.join("\n");
}

/** Clé API présente dans le coffre pour un nom de variable (ANTHROPIC_API_KEY, OPENAI_API_KEY…). */
export const aCle = (env: string) => !!cleApi(env);
