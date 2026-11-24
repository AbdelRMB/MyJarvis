/**
 * Tâches de fond et transcriptions de tes ordinateurs, visibles sur le téléphone (même protocole que
 * wesley/partage.py). Chaque ordinateur les publie dans le compte, chiffrées avec la clé du coffre : le serveur
 * ne voit ni les titres ni le texte.
 *
 * Un élément reste à l'ordinateur qui l'a créé (micro, projet, empreintes vocales) : « Reprendre », « Arrêter »…
 * lui sont demandés par un ordre chiffré. S'il ne peut pas (éteint, Wesley fermé, ordres refusés, autre
 * transcription en cours…), la raison est renvoyée telle quelle.
 */
import { create } from "zustand";
import { api } from "./compte";
import { b64, dechiffrerPartage } from "./crypto";
import { envoyer } from "./appareils";
import { chargerAppareils, useDonnees } from "./donnees";
import { session } from "./stockage";

export type Genre = "tache" | "transcription";

/** Résumé publié (taches.resume / transcription.resume côté bureau) + l'ordinateur d'origine. */
export type ElementPartage = {
  id: string;
  titre: string;
  appareil_nom: string;
  plateforme?: string;
  // tâche
  statut?: "en_cours" | "terminee" | "echec" | "arretee" | "interrompue";
  outil?: string;
  projet?: string;
  branche?: string;
  bilan?: string;
  cree?: number;
  maj?: number;
  etape?: number;
  // transcription
  etat?: "preparation" | "en_cours" | "finalisation" | "terminee" | "erreur" | "interrompue";
  debut?: number;
  duree?: number;
  source?: string;
  avec_micro?: boolean;
  nb_locuteurs?: number;
  nb_phrases?: number;
  erreur?: string;
  genre?: string;
  a_resume?: boolean;
};
export type Partage = { genre: Genre; appareilId: string; modifie: number; resume: ElementPartage };

type Etat = { liste: Partage[]; charge: boolean; erreur: string };
export const usePartages = create<Etat>(() => ({ liste: [], charge: false, erreur: "" }));

/** Branché par l'appli : notification quand une tâche, une transcription ou un résumé se termine sur un ordinateur. */
export const surFin: { notifier: (titre: string, texte: string) => void } = { notifier: () => {} };

const ACTIFS = ["en_cours", "preparation", "finalisation"];
const FINS_TACHE: Record<string, string> = { terminee: "terminée", echec: "en échec", arretee: "arrêtée", interrompue: "interrompue" };
const FINS_TRANSCRIPTION: Record<string, string> = { terminee: "terminée", erreur: "en erreur", interrompue: "interrompue" };

/** Ce qui vient de se finir (même règle que wesley/partage.fins). */
export function fins(avant: Partage[], apres: Partage[]): [string, string][] {
  const anciens = new Map(avant.map((p) => [`${p.genre}/${p.resume.id}`, p.resume]));
  const res: [string, string][] = [];
  for (const p of apres) {
    const a = anciens.get(`${p.genre}/${p.resume.id}`);
    const r = p.resume;
    if (!a) continue;
    const nom = r.appareil_nom || "un ordinateur";
    if (p.genre === "tache" && a.statut === "en_cours" && r.statut && FINS_TACHE[r.statut])
      res.push([`Tâche ${FINS_TACHE[r.statut]} sur ${nom}`, `« ${r.titre} »${r.bilan ? "\n" + r.bilan : ""}`]);
    else if (p.genre === "transcription") {
      if (ACTIFS.includes(a.etat || "") && r.etat && FINS_TRANSCRIPTION[r.etat])
        res.push([`Transcription ${FINS_TRANSCRIPTION[r.etat]} sur ${nom}`, `« ${r.titre} »${r.erreur ? "\n" + r.erreur : ""}`]);
      else if (r.a_resume && !a.a_resume) res.push([`Résumé prêt : ${r.titre}`, `Transcription faite sur ${nom}.`]);
    }
  }
  return res;
}

/** Raison d'un refus, sans le « Erreur sur X : » ajouté par l'ordinateur (son nom est déjà dans la phrase). */
const raison = (r?: string) => (r || "").replace(/^Erreur sur [^:]+ : /, "") || "raison inconnue";

const cle = () => {
  const s = session();
  if (!s) throw new Error("Il faut être connecté à ton compte.");
  return s.cle;
};

let dejaCharge = false; // pas de notification pour ce qui était déjà fini avant l'ouverture de l'appli

/** Relit la liste du compte (au démarrage, puis quand le serveur signale un changement). */
export async function chargerPartages() {
  if (!session()) return;
  usePartages.setState({ charge: true });
  try {
    const brut = await api<{ genre: Genre; id: string; appareil: string; resume: string; modifie: number; moi: boolean }[]>("GET", "/partages");
    const liste: Partage[] = [];
    for (const x of brut) {
      try {
        liste.push({ genre: x.genre, appareilId: x.appareil, modifie: x.modifie, resume: { ...(await dechiffrerPartage<ElementPartage>(x.resume, cle())), id: x.id } });
      } catch {
        /* chiffré avec une autre clé (ancien mot de passe) : illisible */
      }
    }
    const avant = usePartages.getState().liste;
    if (dejaCharge) for (const [titre, texte] of fins(avant, liste)) surFin.notifier(titre, texte);
    dejaCharge = true;
    usePartages.setState({ liste, erreur: "" });
  } catch (e) {
    usePartages.setState({ erreur: (e as Error).message });
  } finally {
    usePartages.setState({ charge: false });
  }
}

const contenus = new Map<string, { modifie: number; contenu: Record<string, any> }>();

/** Contenu complet (journal d'une tâche, phrases d'une transcription), dernière version publiée. */
export async function lirePartage<T = Record<string, any>>(genre: Genre, id: string): Promise<T> {
  const el = usePartages.getState().liste.find((x) => x.genre === genre && x.resume.id === id);
  const deja = contenus.get(`${genre}/${id}`);
  if (deja && el && deja.modifie === el.modifie) return deja.contenu as T;
  const d = await api<{ contenu: string; modifie: number }>("GET", `/partages/${genre}/${id}`);
  const contenu = await dechiffrerPartage<Record<string, any>>(d.contenu, cle());
  contenus.set(`${genre}/${id}`, { modifie: d.modifie, contenu });
  return contenu as T;
}

/** L'ordinateur d'origine d'un élément, tel que l'onglet Appareils le voit (en ligne, accepte les ordres…). */
export function origine(p: Partage) {
  return useDonnees.getState().appareils.find((a) => a.id === p.appareilId);
}

const VERBES: Record<string, string> = {
  reprendre: "reprendre",
  arreter: "arrêter",
  consigne: "envoyer la consigne",
  supprimer: "supprimer",
  resumer: "résumer",
  demarrer: "lancer",
};
const NOMS: Record<Genre, string> = { tache: "la tâche", transcription: "la transcription" };

/** Demande à l'ordinateur d'origine de faire l'action ; renvoie son message, ou une erreur qui dit pourquoi. */
export async function agirPartage(p: Partage, action: string, params: Record<string, unknown> = {}, surEtat?: (s: string) => void): Promise<string> {
  const verbe = VERBES[action] ?? action;
  const nom = p.resume.appareil_nom || "l'ordinateur";
  const appareils = await chargerAppareils().catch(() => useDonnees.getState().appareils);
  const a = appareils.find((x) => x.id === p.appareilId);
  if (!a) throw new Error(`Impossible de ${verbe} sur ${nom} : cet appareil n'est plus connecté à ton compte (déconnecté, ou Wesley n'y a pas été rouvert depuis).`);
  if (!a.en_ligne) throw new Error(`Impossible de ${verbe} sur ${nom} : il est hors ligne (éteint, en veille, ou Wesley n'y est pas ouvert). Rallume-le ou ouvre Wesley dessus, puis réessaie.`);
  if (!a.accepte) throw new Error(`Impossible de ${verbe} sur ${nom} : il refuse les ordres à distance (réglage dans son onglet Appareils).`);
  let rep;
  try {
    rep = await envoyer(
      a,
      { type: "partage", genre: p.genre, id: p.resume.id, action, params, texte: `${verbe[0].toUpperCase() + verbe.slice(1)} ${NOMS[p.genre]} « ${p.resume.titre} »` },
      surEtat,
    );
  } catch (e) {
    throw new Error(`Impossible de ${verbe} sur ${nom} : ${(e as Error).message}`);
  }
  if (!rep.ok) throw new Error(`${nom} n'a pas pu ${verbe} ${NOMS[p.genre]} : ${raison(rep.resultat)}`);
  contenus.delete(`${p.genre}/${p.resume.id}`);
  return rep.resultat || "C'est fait.";
}

/** Lance une NOUVELLE transcription sur un ordinateur (son micro ou son son) ; erreur avec la raison sinon. */
export async function lancerTranscription(appareilId: string, params: Record<string, unknown>, surEtat?: (s: string) => void): Promise<string> {
  const appareils = await chargerAppareils().catch(() => useDonnees.getState().appareils);
  const a = appareils.find((x) => x.id === appareilId);
  if (!a) throw new Error("Impossible de lancer la transcription : cet ordinateur n'est plus connecté à ton compte.");
  if (!a.en_ligne) throw new Error(`Impossible de lancer la transcription sur ${a.nom} : il est hors ligne (éteint, en veille, ou Wesley n'y est pas ouvert).`);
  if (!a.accepte) throw new Error(`Impossible de lancer la transcription sur ${a.nom} : il refuse les ordres à distance (réglage dans son onglet Appareils).`);
  let rep;
  try {
    rep = await envoyer(a, { type: "partage", genre: "transcription", id: "", action: "demarrer", params, texte: `Lancer la transcription « ${params.titre || ""} »` }, surEtat);
  } catch (e) {
    throw new Error(`Impossible de lancer la transcription sur ${a.nom} : ${(e as Error).message}`);
  }
  if (!rep.ok) throw new Error(`${a.nom} n'a pas pu lancer la transcription : ${raison(rep.resultat)}`);
  return rep.resultat || "C'est lancé.";
}

// ---------- le téléphone comme micro : l'enregistrement est envoyé à un ordinateur, qui le transcrit ----------
export const TAILLE_MORCEAU_AUDIO = 4 * 1024 * 1024; // 4 Mo par ordre chiffré (le serveur accepte ~15 Mo)

/** Envoie un enregistrement à l'ordinateur, morceau par morceau (chiffrés), puis il le transcrit. */
export async function envoyerAudio(
  appareilId: string,
  audio: Blob,
  options: { titre: string; nb_locuteurs?: number },
  progression: (fait: number, total: number) => void,
): Promise<string> {
  const appareils = await chargerAppareils().catch(() => useDonnees.getState().appareils);
  const a = appareils.find((x) => x.id === appareilId);
  if (!a) throw new Error("Impossible d'envoyer l'enregistrement : cet ordinateur n'est plus connecté à ton compte.");
  if (!a.en_ligne) throw new Error(`Impossible d'envoyer l'enregistrement à ${a.nom} : il est hors ligne (éteint, en veille, ou Wesley n'y est pas ouvert).`);
  if (!a.accepte) throw new Error(`Impossible d'envoyer l'enregistrement à ${a.nom} : il refuse les ordres à distance (réglage dans son onglet Appareils).`);
  const ext = audio.type.includes("mp4") || audio.type.includes("aac") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
  const envoi = crypto.randomUUID().replace(/-/g, "");
  const total = Math.max(1, Math.ceil(audio.size / TAILLE_MORCEAU_AUDIO));
  let dernier = "";
  for (let partie = 1; partie <= total; partie++) {
    const morceau = new Uint8Array(await audio.slice((partie - 1) * TAILLE_MORCEAU_AUDIO, partie * TAILLE_MORCEAU_AUDIO).arrayBuffer());
    progression(partie - 1, total);
    let rep;
    try {
      rep = await envoyer(a, {
        type: "partage",
        genre: "transcription",
        id: "",
        action: "audio",
        params: { envoi, partie, total, ext, titre: options.titre, nb_locuteurs: options.nb_locuteurs ?? 0, contenu: b64(morceau) },
        texte: `Transcrire l'enregistrement du téléphone « ${options.titre} »`,
      });
    } catch (e) {
      throw new Error(`Envoi à ${a.nom} interrompu (morceau ${partie}/${total}) : ${(e as Error).message}`);
    }
    if (!rep.ok) throw new Error(`${a.nom} n'a pas pu recevoir l'enregistrement : ${raison(rep.resultat)}`);
    dernier = rep.resultat;
  }
  progression(total, total);
  return dernier;
}

// ---------- recherche dans toutes les transcriptions (même règle que wesley/recherche_transcriptions.py) ----------
const MOTS_VIDES = new Set(
  "le la les un une des du de d l au aux et ou mais donc or ni car que qui quoi dont est sont a ai as avons avez ont ce cet cette ces se sa son ses mon ma mes ton ta tes leur leurs nous vous ils elles il elle on je tu en y ne pas plus pour par sur dans avec sans sous chez comme quand si tout tous toute toutes tres bien fait dit dire qu ca cela ceci the of and to in is it that this was for on with as be at by an are or from".split(
    " ",
  ),
);
export const normaliser = (s: string) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
const echapper = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const racine = (m: string) => (m.length > 4 && /[sx]$/.test(m) ? m.slice(0, -1) : m);

export type Trouve = { id: string; titre: string; appareil: string; debut: number; locuteur: string; texte: string; score: number; date: number };

export async function chercher(requete: string, limite = 15): Promise<Trouve[]> {
  const cles = (normaliser(requete).match(/[\w$]+/g) ?? []).filter((m) => m.length >= 2 && !MOTS_VIDES.has(m));
  if (!cles.length) return [];
  const score = (t: string) =>
    cles.filter((c) => new RegExp("(^|[^\\w$])" + echapper(racine(c))).test(t)).length + (cles.length > 1 && t.includes(cles.join(" ")) ? cles.length : 0);
  const mini = Math.max(1, Math.ceil(cles.length / 2));
  await chargerPartages();
  const res: Trouve[] = [];
  for (const p of usePartages.getState().liste.filter((x) => x.genre === "transcription")) {
    let c: { segments: Segment[]; noms: Record<string, string>; resume?: { texte?: string } };
    try {
      c = await lirePartage("transcription", p.resume.id);
    } catch {
      continue;
    }
    const bonus = score(normaliser(`${p.resume.titre} ${c.resume?.texte ?? ""}`)) > 0 ? 1 : 0;
    let trouve = false;
    for (const x of toursDeParole(c.segments ?? [])) {
      const s = score(normaliser(x.texte));
      if (s >= mini) {
        trouve = true;
        res.push({
          id: p.resume.id,
          titre: p.resume.titre,
          appareil: p.resume.appareil_nom,
          debut: x.debut,
          locuteur: c.noms?.[String(x.locuteur)]?.trim() || `Locuteur ${x.locuteur}`,
          texte: x.texte.slice(0, 600),
          score: s + bonus,
          date: p.resume.debut || 0,
        });
      }
    }
    if (!trouve && bonus)
      res.push({ id: p.resume.id, titre: p.resume.titre, appareil: p.resume.appareil_nom, debut: -1, locuteur: "", texte: (c.resume?.texte ?? "").split("\n\n")[0].slice(0, 600), score: 1, date: p.resume.debut || 0 });
  }
  return res.sort((a, b) => b.score - a.score || b.date - a.date || a.debut - b.debut).slice(0, limite);
}

// ---------- affichage d'une transcription (comme wesley/transcription.py : tours de parole) ----------
export type Segment = { debut: number; fin: number; locuteur: number; texte: string };

export function horodatage(s: number) {
  const x = Math.max(0, Math.floor(s));
  const h = Math.floor(x / 3600);
  const m = Math.floor((x % 3600) / 60);
  const p = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(x % 60)}` : `${p(m)}:${p(x % 60)}`;
}

/** Phrases consécutives d'une même personne réunies (coupées à 2 s de pause et 30 s), comme sur le bureau. */
export function toursDeParole(segments: Segment[]) {
  const tours: { locuteur: number; debut: number; fin: number; texte: string }[] = [];
  for (const s of segments) {
    const d = tours[tours.length - 1];
    if (d && d.locuteur === s.locuteur && s.debut - d.fin <= 2 && s.fin - d.debut <= 30) {
      d.texte += " " + s.texte;
      d.fin = s.fin;
    } else tours.push({ locuteur: s.locuteur, debut: s.debut, fin: s.fin, texte: s.texte });
  }
  return tours;
}
