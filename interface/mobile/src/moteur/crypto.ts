/**
 * Cryptographie du compte, identique à l'appli de bureau (wesley/compte.py et wesley/appareils.py) :
 * - scrypt(mot de passe, "wesley-compte:" + e-mail, N=2^15, r=8, p=1, 64 octets)
 *   → 32 premiers octets = preuve d'identité (envoyée au serveur, en hexadécimal) ;
 *   → 32 derniers = clé du coffre (reste sur le téléphone).
 * - AES-GCM : nonce (12 octets) + chiffré, en base64 ; données associées "wesley-coffre" (coffre) ou
 *   "wesley-ordre" (ordres entre appareils) ou "wesley-partage" (tâches et transcriptions des ordinateurs,
 *   compressées zlib avant d'être chiffrées : wesley/partage.py).
 */
import scryptJs from "scrypt-js"; // module CommonJS : import par défaut (Vite comme Node)
const { scrypt } = scryptJs;

const enc = new TextEncoder();
const dec = new TextDecoder();

export const b64 = (u8: Uint8Array) => {
  let s = "";
  for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode(...u8.subarray(i, i + 0x8000));
  return btoa(s);
};
export const deb64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const hex = (u8: Uint8Array) => Array.from(u8, (x) => x.toString(16).padStart(2, "0")).join("");

export async function deriver(email: string, motDePasse: string): Promise<{ auth: string; cle: Uint8Array }> {
  const maitre = await scrypt(enc.encode(motDePasse), enc.encode("wesley-compte:" + email.trim().toLowerCase()), 2 ** 15, 8, 1, 64);
  return { auth: hex(maitre.slice(0, 32)), cle: maitre.slice(32) };
}

export type Contexte = "wesley-coffre" | "wesley-ordre" | "wesley-partage";

const cles = new Map<string, CryptoKey>();
async function cleAes(cleB64: string) {
  let k = cles.get(cleB64);
  if (!k) {
    k = await crypto.subtle.importKey("raw", deb64(cleB64), "AES-GCM", false, ["encrypt", "decrypt"]);
    cles.set(cleB64, k);
  }
  return k;
}

export async function chiffrer(obj: unknown, cleB64: string, contexte: Contexte): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const c = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: enc.encode(contexte) }, await cleAes(cleB64), enc.encode(JSON.stringify(obj))),
  );
  const tout = new Uint8Array(12 + c.length);
  tout.set(iv);
  tout.set(c, 12);
  return b64(tout);
}

/** Déchiffre puis décompresse (zlib) un élément partagé par un ordinateur (wesley/partage.py). */
export async function dechiffrerPartage<T = Record<string, unknown>>(blob: string, cleB64: string): Promise<T> {
  const brut = deb64(blob);
  const p = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: brut.slice(0, 12), additionalData: enc.encode("wesley-partage") },
    await cleAes(cleB64),
    brut.slice(12),
  );
  const flux = new Blob([p]).stream().pipeThrough(new DecompressionStream("deflate"));
  return JSON.parse(await new Response(flux).text()) as T;
}

export async function dechiffrer<T = Record<string, unknown>>(blob: string, cleB64: string, contexte: Contexte): Promise<T> {
  const brut = deb64(blob);
  const p = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: brut.slice(0, 12), additionalData: enc.encode(contexte) },
    await cleAes(cleB64),
    brut.slice(12),
  );
  return JSON.parse(dec.decode(p)) as T;
}
