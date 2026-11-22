/**
 * Stockage local du téléphone (localStorage) : session du compte, réglages propres à ce téléphone, cache
 * des données du compte (pour s'ouvrir instantanément et fonctionner hors ligne) et fil de la conversation.
 */
const CLE = "wesley-mobile-2";

export type Session = {
  jeton: string;
  id: number;
  email: string;
  prenom: string;
  cle: string; // clé du coffre (base64), dérivée du mot de passe sur ce téléphone : ne quitte jamais l'appareil
  admin: boolean;
  politique: string;
  politique_actuelle: string;
};

export type ReglagesTel = {
  nom: string; // nom de ce téléphone dans « Mes appareils »
  voix: boolean; // réponses lues à voix haute
  vitesse: number; // vitesse de la synthèse vocale
  suivie: boolean; // conversation suivie : réécoute après chaque réponse
  cerveau: string; // "" = celui du compte ; sinon claude | openai | … | relais
  relais: string; // identifiant de l'ordinateur qui traite les demandes en mode relais ("" = le premier en ligne)
  ollama_url: string; // Ollama joignable en HTTPS depuis le téléphone (sinon : relais par l'ordinateur)
  accepte: boolean; // accepte les ordres des autres appareils
  confirmation: boolean; // demande confirmation avant d'exécuter un ordre reçu
};

export const REGLAGES_DEFAUT: ReglagesTel = {
  nom: "",
  voix: true,
  vitesse: 1.05,
  suivie: false,
  cerveau: "",
  relais: "",
  ollama_url: "",
  accepte: true,
  confirmation: true,
};

type Tout = {
  session?: Session;
  email?: string;
  reglages?: Partial<ReglagesTel>;
  cache?: Record<string, unknown>;
};

function lire(): Tout {
  try {
    return JSON.parse(localStorage.getItem(CLE) || "{}") as Tout;
  } catch {
    return {};
  }
}

function ecrire(m: (t: Tout) => void) {
  const t = lire();
  m(t);
  try {
    localStorage.setItem(CLE, JSON.stringify(t));
  } catch {
    /* stockage plein : le cache n'est qu'une copie */
  }
}

export const session = () => lire().session;
export const dernierEmail = () => lire().email || "";
export function definirSession(s: Session | undefined) {
  ecrire((t) => {
    if (s) t.email = s.email;
    t.session = s;
    if (!s) t.cache = {}; // déconnexion : plus rien du compte sur ce téléphone
  });
}
export function majSession(p: Partial<Session>) {
  ecrire((t) => {
    if (t.session) t.session = { ...t.session, ...p };
  });
}

export const reglagesTel = (): ReglagesTel => ({ ...REGLAGES_DEFAUT, ...lire().reglages });
export function majReglagesTel(p: Partial<ReglagesTel>) {
  ecrire((t) => (t.reglages = { ...t.reglages, ...p }));
}

export function cache<T>(nom: string, defaut: T): T {
  const v = lire().cache?.[nom];
  return v === undefined ? defaut : (v as T);
}
export function definirCache(nom: string, valeur: unknown) {
  ecrire((t) => (t.cache = { ...t.cache, [nom]: valeur }));
}

export const nomParDefaut = () => {
  const ua = navigator.userAgent;
  return /iPhone/.test(ua) ? "iPhone" : /Android/.test(ua) ? "Android" : "Téléphone";
};
export const nomTelephone = () => reglagesTel().nom.trim() || nomParDefaut();
