/**
 * Compte Wesley depuis le téléphone : mêmes appels au serveur de comptes que l'appli de bureau (wesley/compte.py).
 * Le mot de passe ne quitte jamais le téléphone : on en dérive la preuve d'identité et la clé du coffre.
 */
import { chiffrer, dechiffrer, b64, deriver } from "./crypto";
import { definirSession, majSession, nomTelephone, session, type Session } from "./stockage";
import type { Coffre } from "./types";

declare global {
  interface Window {
    WESLEY_CLE_APPLI?: string;
  }
}

/** Version de la politique de confidentialité (même valeur que POLITIQUE dans serveur/app.py). */
export const POLITIQUE = "2026-11-21";
export const VERSION_MOBILE = "2.6.0";

export class ErreurCompte extends Error {
  constructor(message: string, public statut = 0) {
    super(message);
  }
}

let surSessionRevoquee: () => void = () => {};
export const quandSessionRevoquee = (f: () => void) => (surSessionRevoquee = f);

export async function api<T = any>(methode: string, chemin: string, corps?: unknown, opts: { jeton?: string; signal?: AbortSignal } = {}): Promise<T> {
  const jeton = opts.jeton ?? session()?.jeton;
  let r: Response;
  try {
    r = await fetch("/v1" + chemin, {
      method: methode,
      headers: {
        "Content-Type": "application/json",
        "X-Wesley-Appli": window.WESLEY_CLE_APPLI || "",
        ...(jeton ? { Authorization: `Bearer ${jeton}` } : {}),
      },
      body: corps === undefined ? undefined : JSON.stringify(corps),
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ErreurCompte("Serveur Wesley injoignable (pas de réseau ?).");
  }
  if (r.status === 401 && chemin !== "/connexion" && chemin !== "/inscription") {
    surSessionRevoquee();
    throw new ErreurCompte("Session expirée : reconnecte-toi.", 401);
  }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new ErreurCompte(typeof d.detail === "string" ? d.detail : `Erreur du serveur (${r.status}).`, r.status);
  return d as T;
}

// ---------- connexion ----------
type ReponseConnexion = { jeton: string; id: number; email: string; prenom: string; coffre: string; admin: boolean; politique: string; politique_actuelle: string };

function ouvrir(r: ReponseConnexion, cle: Uint8Array): Session {
  const s: Session = {
    jeton: r.jeton,
    id: r.id,
    email: r.email,
    prenom: r.prenom || "",
    cle: b64(cle),
    admin: !!r.admin,
    politique: r.politique || "",
    politique_actuelle: r.politique_actuelle || "",
  };
  definirSession(s);
  return s;
}

export async function connecter(email: string, motDePasse: string) {
  email = email.trim().toLowerCase();
  const { auth, cle } = await deriver(email, motDePasse);
  try {
    return ouvrir(await api<ReponseConnexion>("POST", "/connexion", { email, cle_auth: auth, appareil: nomTelephone() }), cle);
  } catch (e) {
    if (e instanceof ErreurCompte && e.statut === 401) throw new ErreurCompte("E-mail ou mot de passe incorrect.", 401);
    throw e;
  }
}

export async function inscrire(email: string, motDePasse: string, prenom: string, politiqueAcceptee: boolean) {
  if (!politiqueAcceptee) throw new ErreurCompte("Accepte la politique de confidentialité pour créer ton compte.");
  if (motDePasse.length < 8) throw new ErreurCompte("Mot de passe trop court (8 caractères minimum).");
  email = email.trim().toLowerCase();
  const { auth, cle } = await deriver(email, motDePasse);
  return ouvrir(
    await api<ReponseConnexion>("POST", "/inscription", { email, cle_auth: auth, prenom: prenom.trim(), appareil: nomTelephone(), politique: POLITIQUE }),
    cle,
  );
}

export async function deconnecter() {
  await api("POST", "/deconnexion").catch(() => {});
  definirSession(undefined);
}

export async function accepterPolitique() {
  const p = await api<{ politique: string; politique_actuelle: string }>("POST", "/moi/politique");
  majSession({ politique: p.politique, politique_actuelle: p.politique_actuelle });
}

export async function supprimerCompte(motDePasse: string) {
  const s = session();
  if (!s) throw new ErreurCompte("Aucun compte connecté.");
  const { auth } = await deriver(s.email, motDePasse);
  try {
    await api("POST", "/moi/supprimer", { cle_auth: auth });
  } catch (e) {
    if (e instanceof ErreurCompte && e.statut === 403) throw new ErreurCompte("Mot de passe incorrect.", 403);
    throw e;
  }
  definirSession(undefined);
}

// ---------- coffre (clés API, mots de passe des connecteurs : chiffrés, illisibles par le serveur) ----------
let coffre: Coffre = {};
let dernierBlob: string | null = null;

export const lireCoffre = () => coffre;

export async function chargerCoffre(blob?: string): Promise<boolean> {
  const s = session();
  if (!s) return false;
  if (blob === undefined) blob = (await api<{ coffre: string }>("GET", "/moi")).coffre;
  if (blob === dernierBlob) return false;
  dernierBlob = blob;
  try {
    coffre = blob ? await dechiffrer<Coffre>(blob, s.cle, "wesley-coffre") : {};
  } catch {
    coffre = {}; // clé du compte changée ailleurs : le coffre sera relu après reconnexion
  }
  return true;
}

/** Relit le coffre du serveur, applique la modification, renvoie le tout chiffré (fusion, comme sur le bureau). */
export async function modifierCoffre(modif: (c: Coffre) => void) {
  const s = session();
  if (!s) throw new ErreurCompte("Non connecté.");
  const blob = (await api<{ coffre: string }>("GET", "/moi")).coffre;
  let c: Coffre = {};
  try {
    c = blob ? await dechiffrer<Coffre>(blob, s.cle, "wesley-coffre") : {};
  } catch {
    throw new ErreurCompte("Coffre illisible : reconnecte-toi avec ton mot de passe actuel.");
  }
  c.trousseau ||= {};
  modif(c);
  const nouveau = await chiffrer(c, s.cle, "wesley-coffre");
  await api("PUT", "/coffre", { coffre: nouveau });
  coffre = c;
  dernierBlob = nouveau;
}

export const secret = (nom: string) => (coffre.trousseau || {})[nom] || "";
export const cleApi = (env: string) => (typeof coffre[env] === "string" ? (coffre[env] as string) : "");
