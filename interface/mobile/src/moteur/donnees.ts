/**
 * Données du compte sur le téléphone : mémoire, historique, À faire, automatisations, connecteurs, réglages
 * communs, appareils, tickets. Même serveur et mêmes formats que l'appli de bureau : tout ce qui change ici
 * arrive sur les ordinateurs en ~1 s (et inversement, voir synchro.ts).
 *
 * Hors ligne : chaque écriture part tout de suite ; si le réseau manque, elle attend dans une file (comme
 * attente.json sur le bureau) et repart dès qu'il revient. Les envois sont idempotents côté serveur.
 */
import { create } from "zustand";
import { api, ErreurCompte } from "./compte";
import { cache, definirCache, nomTelephone, session } from "./stockage";
import type { Appareil, Automatisation, Connecteurs, EntreeOrdre, Fait, FichierRecu, LigneHistorique, Profil, TacheAFaire, Ticket } from "./types";

type Donnees = {
  faits: Fait[];
  afaire: TacheAFaire[];
  automatisations: Automatisation[];
  connecteurs: Connecteurs;
  profil: Profil;
  appareils: Appareil[];
  tickets: Ticket[];
  ticketsAdmin: Ticket[];
  historique: LigneHistorique[];
  ordres: EntreeOrdre[];
  fichiers: FichierRecu[];
  enLigne: boolean; // le serveur répond
  synchro: number; // horodatage de la dernière synchro réussie
};

export const useDonnees = create<Donnees>(() => ({
  faits: cache("faits", []),
  afaire: cache("afaire", []),
  automatisations: cache("automatisations", []),
  connecteurs: cache("connecteurs", {}),
  profil: cache("profil", {}),
  appareils: cache("appareils", []),
  tickets: cache("tickets", []),
  ticketsAdmin: [],
  historique: cache("historique", []),
  ordres: cache("ordres", []),
  fichiers: cache("fichiers", []),
  enLigne: navigator.onLine,
  synchro: 0,
}));

function poser<K extends keyof Donnees>(cle: K, valeur: Donnees[K], garder = true) {
  useDonnees.setState({ [cle]: valeur } as Pick<Donnees, K>);
  if (garder) definirCache(cle, valeur);
}

export const prenom = () => session()?.prenom || (useDonnees.getState().profil.nom_utilisateur as string) || "Utilisateur";
const maintenantIso = () => {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};
export const jourIso = () => maintenantIso().slice(0, 10);
export const nouvelId = (n = 8) => crypto.randomUUID().replace(/-/g, "").slice(0, n);

// ---------- file d'attente (hors ligne) ----------
type Op =
  | { type: "fait"; fait: Record<string, unknown> }
  | { type: "suppression"; fid: string; texte: string; ts: number }
  | { type: "ligne"; ligne: { jour: string; machine: string; ligne: string } }
  | { type: "doc"; nom: string; contenu: unknown };

const attente = (): Op[] => cache("attente", []);
let envoiEnCours = false;

export async function viderAttente() {
  if (envoiEnCours || !session()) return;
  const ops = attente();
  if (!ops.length) return;
  envoiEnCours = true;
  try {
    const lignes = ops.filter((o): o is Extract<Op, { type: "ligne" }> => o.type === "ligne").map((o) => o.ligne);
    for (const o of ops) {
      if (o.type === "fait") await api("POST", "/faits", o.fait);
      else if (o.type === "suppression") await api("POST", "/faits/supprimer", { fid: o.fid, texte: o.texte, ts: o.ts, appareil: nomTelephone() });
      else if (o.type === "doc") await api("PUT", `/documents/${o.nom}`, { contenu: o.contenu });
    }
    if (lignes.length) await api("POST", "/historique", { lignes });
    // seules les opérations envoyées sont retirées (d'autres ont pu s'ajouter pendant l'envoi)
    definirCache("attente", attente().slice(ops.length));
    poser("enLigne", true, false);
  } catch (e) {
    if (e instanceof ErreurCompte && e.statut === 0) poser("enLigne", false, false);
  } finally {
    envoiEnCours = false;
  }
}

function enAttente(op: Op) {
  definirCache("attente", [...attente(), op]);
  void viderAttente();
}
export const ecrituresEnAttente = () => attente().length;

// ---------- mémoire ----------
/** Ajoute ou réutilise un souvenir (même règle que memoire.py : un texte déjà connu n'est pas dupliqué). */
export function memoriser(fait: string, categorie = "general"): string {
  fait = fait.trim();
  if (!fait) return "Rien à retenir.";
  const faits = useDonnees.getState().faits;
  const deja = faits.find((f) => f.fait.toLowerCase() === fait.toLowerCase());
  const ts = Date.now() / 1000;
  const f: Fait = deja ? { ...deja, categorie, modifie: ts } : { fait, categorie, date: jourIso(), fid: nouvelId(16), modifie: ts };
  poser("faits", deja ? faits.map((x) => (x.fid === f.fid ? f : x)) : [...faits, f]);
  enAttente({ type: "fait", fait: { ...f, ts, appareil: nomTelephone(), action: deja ? "utilisation" : "ajout" } });
  return deja ? `Je le savais déjà : ${fait}` : `Retenu : ${fait}`;
}

export function modifierSouvenir(fid: string, fait: string, categorie?: string) {
  const faits = useDonnees.getState().faits;
  const x = faits.find((f) => f.fid === fid);
  if (!x) return false;
  const ts = Date.now() / 1000;
  const f = { ...x, fait: fait.trim(), categorie: categorie || x.categorie, modifie: ts };
  poser("faits", faits.map((y) => (y.fid === fid ? f : y)));
  enAttente({ type: "fait", fait: { ...f, ts, appareil: nomTelephone(), action: "modification" } });
  return true;
}

export function oublierSouvenir(fid: string) {
  const faits = useDonnees.getState().faits;
  const x = faits.find((f) => f.fid === fid);
  if (!x) return false;
  poser("faits", faits.filter((f) => f.fid !== fid));
  enAttente({ type: "suppression", fid, texte: "", ts: Date.now() / 1000 });
  return true;
}

export function chercherSouvenirs(req: string): Fait[] {
  const mots = req.toLowerCase().split(/\s+/).filter((m) => m.length > 2);
  return useDonnees
    .getState()
    .faits.map((f) => ({ f, score: mots.filter((m) => (f.fait + " " + f.categorie).toLowerCase().includes(m)).length }))
    .filter((x) => x.score > 0 || !mots.length)
    .sort((a, b) => b.score - a.score)
    .map((x) => x.f);
}

export const journalMemoire = () =>
  api<{ fid: string; action: string; fait: string; categorie: string; appareil: string; ts: number; supprime_actuellement: number | null }[]>(
    "GET",
    "/memoire/journal",
  );

// ---------- historique des conversations ----------
export function journaliser(role: string, texte: string) {
  const d = new Date();
  const ligne = `[${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}] ${role}: ${texte.trim()}`;
  const l = { jour: jourIso(), machine: nomTelephone(), ligne };
  const h = useDonnees.getState().historique;
  poser("historique", [...h, { id: (h.at(-1)?.id || 0) + 0.001, ...l }].slice(-3000));
  enAttente({ type: "ligne", ligne: l });
}

async function chargerHistorique() {
  const tout = useDonnees.getState().historique;
  const h = tout.filter((x) => Number.isInteger(x.id)); // lignes confirmées par le serveur
  const depuis = h.length ? Math.max(...h.map((x) => x.id)) : 0;
  const nouvelles = await api<LigneHistorique[]>("GET", `/historique?depuis=${depuis}`);
  if (!nouvelles.length) return false;
  // lignes écrites ici, pas encore revenues du serveur : gardées à la fin
  const recues = new Set(nouvelles.map((x) => x.jour + x.ligne));
  const locales = tout.filter((x) => !Number.isInteger(x.id) && !recues.has(x.jour + x.ligne));
  // le téléphone garde les 30 derniers jours (il n'a pas besoin de tout)
  const limite = new Date(Date.now() - 30 * 86400e3).toISOString().slice(0, 10);
  poser("historique", [...h, ...nouvelles, ...locales].filter((x) => x.jour >= limite).slice(-3000));
  return nouvelles.length > 0;
}

/** Les dernières lignes de conversation (tous appareils), pour le contexte de l'IA. */
export function resumeRecent(n = 30) {
  return useDonnees
    .getState()
    .historique.slice(-n)
    .map((l) => `(${l.jour}, ${l.machine}) ${l.ligne.slice(0, 200)}`)
    .join("\n");
}

// ---------- documents partagés (À faire, automatisations, connecteurs, réglages communs) ----------
type NomDoc = "afaire" | "automatisations" | "connecteurs" | "profil";

async function lireDoc<T>(nom: NomDoc): Promise<T | null> {
  return (await api<{ contenu: T | null }>("GET", `/documents/${nom}`)).contenu;
}

/** Part de la dernière version du serveur (un ordinateur a pu la changer), applique, renvoie. */
async function modifierDoc<T>(nom: NomDoc, defaut: T, modif: (d: T) => T | void): Promise<T> {
  let d: T;
  try {
    d = (await lireDoc<T>(nom)) ?? defaut;
  } catch (e) {
    if (e instanceof ErreurCompte && e.statut !== 0) throw e;
    d = (useDonnees.getState()[nom] as T) ?? defaut; // hors ligne : on part du cache
  }
  d = structuredClone(d);
  d = (modif(d) as T) ?? d;
  poser(nom, d as Donnees[NomDoc]);
  enAttente({ type: "doc", nom, contenu: d });
  return d;
}

// À faire
export const ETAPES = ["a_faire", "en_cours", "fait"] as const;
export const LIBELLES_ETAPES: Record<string, string> = { a_faire: "à faire", en_cours: "en cours", fait: "fait" };

const dateAFaire = (s: string) => (s || "").trim().replace(" ", "T").slice(0, 16);

export async function ajouterAFaire(p: { titre: string; note?: string; echeance?: string; rappel?: string; priorite?: string; statut?: string }) {
  const t: TacheAFaire = {
    id: nouvelId(),
    titre: p.titre.trim(),
    note: (p.note || "").trim(),
    echeance: dateAFaire(p.echeance || ""),
    rappel: dateAFaire(p.rappel || ""),
    priorite: (["basse", "normale", "haute"].includes(p.priorite || "") ? p.priorite : "normale") as TacheAFaire["priorite"],
    statut: (ETAPES as readonly string[]).includes(p.statut || "") ? (p.statut as TacheAFaire["statut"]) : "a_faire",
    cree: maintenantIso(),
    modifie: maintenantIso(),
    fait_le: p.statut === "fait" ? maintenantIso() : "",
  };
  await modifierDoc<TacheAFaire[]>("afaire", [], (l) => void l.push(t));
  return t;
}

export function trouverAFaire(cle: string): TacheAFaire[] {
  cle = cle.replace(/[[\] ]/g, "").toLowerCase() || cle.toLowerCase();
  const l = useDonnees.getState().afaire;
  const parId = l.filter((t) => t.id.startsWith(cle));
  return parId.length ? parId : l.filter((t) => t.titre.toLowerCase().includes(cle.trim()));
}

export async function modifierAFaire(id: string, champs: Partial<TacheAFaire>) {
  await modifierDoc<TacheAFaire[]>("afaire", [], (l) => {
    const t = l.find((x) => x.id === id);
    if (!t) return;
    Object.assign(t, champs, { modifie: maintenantIso() });
    if (champs.echeance !== undefined) t.echeance = dateAFaire(champs.echeance);
    if (champs.rappel !== undefined) t.rappel = dateAFaire(champs.rappel);
    if (champs.statut) t.fait_le = champs.statut === "fait" ? maintenantIso() : "";
  });
}

export const supprimerAFaire = (id: string) => modifierDoc<TacheAFaire[]>("afaire", [], (l) => l.filter((x) => x.id !== id));

// Automatisations (exécutées par les ordinateurs ; le téléphone les crée, les modifie et lance les routines)
export const JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];

export function decrireAutomatisation(r: Automatisation) {
  const d = r.declencheur;
  const a = r.action;
  let quand: string;
  if (d.type === "horaire") {
    const j = d.jours || [];
    quand = (!j.length || j.length === 7 ? "Tous les jours" : "Le " + j.map((x) => JOURS[x]).join(", ")) + ` à ${d.heure || "?"}`;
  } else if (d.type === "intervalle") quand = `Toutes les ${d.minutes} min`;
  else if (d.type === "demarrage") quand = "Au démarrage de Wesley";
  else if (d.type === "commande") quand = `Quand tu dis « ${d.phrase || r.nom} »`;
  else if (d.type === "rendez_vous") quand = `${d.avant || 15} min avant un rendez-vous${d.contient ? ` « ${d.contient} »` : ""}`;
  else if (d.type === "fichier") quand = `Quand un fichier ${d.motif || "*"} arrive dans ${d.dossier || "Téléchargements"}`;
  else if (d.type === "tache_finie") quand = "Quand une tâche de code se termine";
  else if (d.type === "site") quand = `Quand ${d.url} ne répond plus`;
  else {
    const f = [d.expediteur && `de ${d.expediteur}`, d.sujet && `sujet « ${d.sujet} »`, d.contient && `contenant « ${d.contient} »`].filter(Boolean);
    quand = `Mail ${f.join(", ") || "(tous)"}`;
  }
  const quoi = a.type === "wesley" ? `Wesley : ${a.consigne || "…"}` : `Prévenir${a.message ? ` : « ${a.message} »` : ""}`;
  return `${quand}${d.condition ? `, si ${d.condition}` : ""} → ${quoi}${r.appareil ? ` (sur ${r.appareil})` : ""}`;
}

export async function creerAutomatisation(p: {
  nom: string;
  type: Automatisation["declencheur"]["type"];
  heure?: string;
  jours?: number[];
  minutes?: number;
  expediteur?: string;
  sujet?: string;
  contient?: string;
  connecteur?: string;
  action?: "prevenir" | "wesley";
  consigne?: string;
  message?: string;
  phrase?: string;
  appareil?: string;
}) {
  const r: Automatisation = {
    id: nouvelId(10),
    nom: p.nom.trim() || "Automatisation",
    actif: true,
    declencheur: {
      type: p.type,
      expediteur: (p.expediteur || "").trim(),
      sujet: (p.sujet || "").trim(),
      contient: (p.contient || "").trim(),
      connecteur: (p.connecteur || "").trim(),
      heure: (p.heure || "").trim(),
      jours: [...new Set((p.jours || []).filter((j) => j >= 0 && j <= 6))].sort(),
      minutes: p.type === "intervalle" ? Math.max(1, p.minutes || 0) : 0,
      phrase: p.type === "commande" ? (p.phrase || p.nom).trim() : "",
    },
    action: { type: p.action === "prevenir" ? "prevenir" : "wesley", consigne: (p.consigne || "").trim(), message: (p.message || "").trim() },
    // le téléphone n'exécute pas les règles à heure fixe : par défaut, tous les ordinateurs allumés (comme les règles mail)
    appareil: p.appareil || "",
    cree: maintenantIso().slice(0, 19),
  };
  await modifierDoc<Automatisation[]>("automatisations", [], (l) => void l.push(r));
  return r;
}

export const basculerAutomatisation = (id: string, actif: boolean) =>
  modifierDoc<Automatisation[]>("automatisations", [], (l) => {
    const r = l.find((x) => x.id === id);
    if (r) r.actif = actif;
  });
export const supprimerAutomatisation = (id: string) => modifierDoc<Automatisation[]>("automatisations", [], (l) => l.filter((x) => x.id !== id));

export function trouverRoutine(nom: string) {
  const cle = nom.trim().replace(/^[«»"' ]+|[«»"' ]+$/g, "").toLowerCase();
  const routines = useDonnees.getState().automatisations.filter((r) => r.actif && r.declencheur.type === "commande");
  return (
    routines.find((r) => [(r.declencheur.phrase || "").toLowerCase(), r.nom.toLowerCase(), r.id].includes(cle)) ||
    routines.find((r) => cle && ((r.declencheur.phrase || "").toLowerCase().includes(cle) || r.nom.toLowerCase().includes(cle)))
  );
}

// Réglages communs (profil) et connecteurs
export const modifierProfil = (p: Profil) => modifierDoc<Profil>("profil", {}, (d) => void Object.assign(d, p));
export const modifierConnecteurs = (modif: (c: Connecteurs) => Connecteurs | void) => modifierDoc<Connecteurs>("connecteurs", {}, modif);

// ---------- appareils ----------
export async function chargerAppareils() {
  const l = await api<Appareil[]>("GET", "/appareils");
  poser("appareils", l);
  return l;
}
export const deconnecterAppareil = (id: string) => api("POST", `/appareils/${id}/deconnecter`);

export function noterOrdre(e: Omit<EntreeOrdre, "ts">) {
  poser("ordres", [...useDonnees.getState().ordres, { ...e, ts: Date.now() / 1000, quoi: e.quoi.slice(0, 1000), resultat: e.resultat.slice(0, 3000) }].slice(-200));
}

export function garderFichier(f: Omit<FichierRecu, "id" | "ts">) {
  const n: FichierRecu = { ...f, id: nouvelId(), ts: Date.now() / 1000 };
  // le stockage du navigateur est limité : on garde les 10 derniers fichiers reçus
  poser("fichiers", [...useDonnees.getState().fichiers, n].slice(-10));
  return n;
}
export const supprimerFichier = (id: string) => poser("fichiers", useDonnees.getState().fichiers.filter((f) => f.id !== id));

// ---------- tickets ----------
export async function chargerTickets() {
  poser("tickets", await api<Ticket[]>("GET", "/tickets"));
  if (session()?.admin) poser("ticketsAdmin", await api<Ticket[]>("GET", "/admin/tickets"), false);
}
export async function envoyerTicket(genre: string, titre: string, description = "") {
  const r = await api<{ id: number }>("POST", "/tickets", {
    genre,
    titre,
    description,
    version: "mobile",
    plateforme: "telephone",
    appareil: nomTelephone(),
  });
  void chargerTickets().catch(() => {});
  return r.id;
}
export async function traiterTicket(id: number, statut: string, reponse?: string) {
  // POST et non PATCH : le proxy du serveur de comptes ne laisse passer que GET, POST et PUT
  await api("POST", `/admin/tickets/${id}`, { statut, ...(reponse !== undefined ? { reponse } : {}) });
  await chargerTickets();
}

// ---------- synchronisation descendante ----------
export type Changements = Partial<Record<"faits" | "historique" | "afaire" | "automatisations" | "connecteurs" | "profil" | "tickets", boolean>>;

const egal = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** Récupère l'état du compte (ce qu'un autre appareil a changé). Le serveur fait foi, sauf écritures en attente. */
export async function synchroniser(): Promise<Changements> {
  const ch: Changements = {};
  await viderAttente();
  if (attente().length) return ch; // hors ligne : on garde le cache tel quel
  const s = useDonnees.getState();
  const faits = (await api<Fait[]>("GET", "/faits")).map((x) => ({ fait: x.fait, categorie: x.categorie, date: x.date, fid: x.fid, modifie: x.modifie }));
  if (!attente().length && !egal(faits, s.faits)) {
    poser("faits", faits);
    ch.faits = true;
  }
  for (const nom of ["afaire", "automatisations", "connecteurs", "profil"] as const) {
    try {
      const d = await lireDoc<unknown>(nom);
      const local = useDonnees.getState()[nom];
      if (d !== null && !attente().length && !egal(d, local)) {
        poser(nom, d as never);
        ch[nom] = true;
      }
    } catch (e) {
      if (!(e instanceof ErreurCompte && e.statut === 404)) throw e;
    }
  }
  ch.historique = await chargerHistorique();
  const avant = useDonnees.getState().tickets;
  await chargerTickets().catch(() => {});
  ch.tickets = !egal(avant, useDonnees.getState().tickets);
  useDonnees.setState({ enLigne: true, synchro: Date.now() });
  return ch;
}
