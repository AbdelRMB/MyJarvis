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
import { dechiffrerPartage } from "./crypto";
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
};
export type Partage = { genre: Genre; appareilId: string; modifie: number; resume: ElementPartage };

type Etat = { liste: Partage[]; charge: boolean; erreur: string };
export const usePartages = create<Etat>(() => ({ liste: [], charge: false, erreur: "" }));

const cle = () => {
  const s = session();
  if (!s) throw new Error("Il faut être connecté à ton compte.");
  return s.cle;
};

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
  if (!rep.ok) throw new Error(`${nom} n'a pas pu ${verbe} ${NOMS[p.genre]} : ${rep.resultat || "raison inconnue"}`);
  contenus.delete(`${p.genre}/${p.resume.id}`);
  return rep.resultat || "C'est fait.";
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
