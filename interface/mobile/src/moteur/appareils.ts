/**
 * Mes appareils, depuis le téléphone (même protocole que wesley/appareils.py) :
 * - le téléphone pilote les ordinateurs : « sur mon PC, lance Discord », fichiers dans les deux sens ;
 * - il reçoit aussi leurs ordres (« sur mon téléphone, ajoute… ») et les exécute avec son propre Wesley.
 * Chaque ordre est chiffré ET authentifié (AES-GCM, clé du coffre dérivée du mot de passe) : le serveur relaie
 * sans pouvoir lire ni fabriquer un ordre. Un ordre trop vieux ou déjà vu est rejeté.
 */
import { api } from "./compte";
import { chiffrer, dechiffrer } from "./crypto";
import { chargerAppareils, garderFichier, noterOrdre, useDonnees } from "./donnees";
import { nomTelephone, reglagesTel, session } from "./stockage";
import type { Appareil } from "./types";

export const MAX_FICHIER = 10 * 1024 * 1024; // 10 Mo par fichier, comme sur le bureau
export const ORDINATEURS = ["mac", "windows", "linux"];

const cle = () => {
  const s = session();
  if (!s) throw new Error("Il faut être connecté à ton compte pour piloter tes autres appareils.");
  return s.cle;
};

/** Retrouve un appareil par son nom (même approximatif : « PC », « mac », « windows ») ou son identifiant. */
export async function trouver(nomOuId: string): Promise<Appareil> {
  const c = nomOuId.trim().toLowerCase();
  const autres = (await chargerAppareils()).filter((a) => !a.moi);
  const tests: ((a: Appareil) => boolean)[] = [
    (a) => a.id === c,
    (a) => a.nom.toLowerCase() === c,
    (a) => !!c && a.nom.toLowerCase().includes(c),
    (a) =>
      (!!c && a.plateforme.toLowerCase().includes(c)) ||
      (["pc", "windows", "ordinateur", "ordi"].includes(c) && a.plateforme === "windows") ||
      (["mac", "macbook", "ordinateur", "ordi"].includes(c) && a.plateforme === "mac"),
  ];
  for (const test of tests) {
    const trouves = autres.filter(test);
    if (trouves.length === 1) return trouves[0];
    if (trouves.length > 1) {
      const enLigne = trouves.filter((a) => a.en_ligne);
      if (enLigne.length === 1) return enLigne[0];
      throw new Error("Plusieurs appareils correspondent : " + trouves.map((a) => a.nom).join(", "));
    }
  }
  throw new Error(`Aucun autre appareil ne correspond à « ${nomOuId} ». Appareils : ${autres.map((a) => a.nom).join(", ") || "aucun"}`);
}

/** L'ordinateur qui traite les demandes que le téléphone ne peut pas faire lui-même. */
export async function ordinateurParDefaut(): Promise<Appareil> {
  const l = (await chargerAppareils()).filter((a) => !a.moi && ORDINATEURS.includes(a.plateforme));
  const choisi = reglagesTel().relais;
  const a = l.find((x) => x.id === choisi && x.en_ligne) || l.find((x) => x.en_ligne && x.accepte && !x.occupe) || l.find((x) => x.en_ligne && x.accepte);
  if (!a) {
    throw new Error(
      l.length
        ? `Aucun de tes ordinateurs n'est allumé avec Wesley ouvert (${l.map((x) => x.nom).join(", ")}).`
        : "Aucun ordinateur n'est connecté à ton compte : installe Wesley sur ton Mac ou ton PC.",
    );
  }
  return a;
}

export type ReponseOrdre = { ok: boolean; resultat: string; appareil: string; nom?: string; contenu?: string };

/** Envoie un ordre chiffré à un autre appareil et attend sa réponse (jusqu'à 10 min). */
export async function envoyer(cible: string | Appareil, contenu: Record<string, unknown>, surEtat?: (s: string) => void): Promise<ReponseOrdre> {
  const a = typeof cible === "string" ? await trouver(cible) : cible;
  if (!a.en_ligne) throw new Error(`${a.nom} est hors ligne (éteint, ou Wesley n'y tourne pas).`);
  if (!a.accepte) throw new Error(`${a.nom} refuse les ordres à distance (réglage dans son onglet Appareils).`);
  const ordre = { ...contenu, nonce: crypto.randomUUID().replace(/-/g, ""), ts: Date.now() / 1000, de: nomTelephone(), vers: a.id };
  const quoi = (contenu.texte as string) || `${contenu.type} ${contenu.chemin || ""}`.trim();
  const { id } = await api<{ id: string }>("POST", "/ordres", { vers: a.id, blob: await chiffrer(ordre, cle(), "wesley-ordre") });
  surEtat?.(`${a.nom} reçoit la demande…`);
  const debut = Date.now();
  let recu = false;
  while (Date.now() - debut < 600_000) {
    const r = await api<{ pret: boolean; blob?: string; recu: boolean }>("GET", `/ordres/${id}/attendre`);
    if (r.recu && !recu) surEtat?.(`${a.nom} travaille…`);
    recu = recu || r.recu;
    if (r.pret && r.blob) {
      const rep = await dechiffrer<Omit<ReponseOrdre, "appareil">>(r.blob, cle(), "wesley-ordre");
      noterOrdre({ sens: "envoye", appareil: a.nom, quoi, resultat: rep.resultat || "", statut: rep.ok ? "ok" : "erreur" });
      return { ...rep, appareil: a.nom };
    }
    if (!recu && Date.now() - debut > 60_000) break;
  }
  noterOrdre({ sens: "envoye", appareil: a.nom, quoi, resultat: "", statut: "sans réponse" });
  throw new Error(`${a.nom} n'a pas répondu` + (recu ? " (il travaille peut-être encore)." : " (hors ligne ?)."));
}

// ---------- recevoir un ordre ----------
const vus = new Set<string>();

/** Branchés par l'appli : exécuter une demande avec le Wesley du téléphone, demander confirmation à l'écran. */
export const recepteur: {
  demande: (texte: string, de: string) => Promise<string>;
  confirmer: (titre: string, detail: string) => Promise<boolean>;
  notifier: (titre: string, texte: string) => void;
} = {
  demande: async () => "Wesley n'est pas prêt sur ce téléphone.",
  confirmer: async () => false,
  notifier: () => {},
};

async function repondre(oid: string, rep: Record<string, unknown>) {
  try {
    await api("POST", `/ordres/${oid}/reponse`, { blob: await chiffrer(rep, cle(), "wesley-ordre") });
  } catch {
    /* l'appareil qui attend finira par abandonner */
  }
}

export async function traiter(ordres: { id: string; blob: string }[]) {
  for (const o of ordres) void executer(o);
}

async function executer(o: { id: string; blob: string }) {
  let d: Record<string, any>;
  try {
    d = await dechiffrer(o.blob, cle(), "wesley-ordre");
  } catch {
    return; // signature invalide : ne vient pas d'un de tes appareils
  }
  if (vus.has(d.nonce) || Math.abs(Date.now() / 1000 - Number(d.ts || 0)) > 600) return;
  vus.add(d.nonce);
  const de = String(d.de || "?");
  const quoi = d.texte || `${d.type} ${d.chemin || ""}`.trim();
  const r = reglagesTel();
  if (!r.accepte) {
    await repondre(o.id, { ok: false, resultat: `${nomTelephone()} refuse les ordres à distance.` });
    noterOrdre({ sens: "recu", appareil: de, quoi, resultat: "refusé (réglage)", statut: "refuse" });
    return;
  }
  if (r.confirmation && d.type !== "ping" && !(await recepteur.confirmer(`${de} demande d'exécuter sur ce téléphone`, quoi))) {
    await repondre(o.id, { ok: false, resultat: "L'utilisateur a refusé sur le téléphone." });
    noterOrdre({ sens: "recu", appareil: de, quoi, resultat: "refusé par l'utilisateur", statut: "refuse" });
    return;
  }
  try {
    const [resultat, extra] = await realiser(d);
    await repondre(o.id, { ok: true, resultat, ...extra });
    noterOrdre({ sens: "recu", appareil: de, quoi, resultat, statut: "ok" });
    recepteur.notifier(`Ordre de ${de}`, `${quoi}\n→ ${resultat.slice(0, 300)}`);
  } catch (e) {
    const m = (e as Error).message;
    await repondre(o.id, { ok: false, resultat: `Erreur sur ${nomTelephone()} : ${m}` });
    noterOrdre({ sens: "recu", appareil: de, quoi, resultat: m, statut: "erreur" });
  }
}

const nomFichier = (chemin: string) => chemin.split(/[\\/]/).pop() || "fichier";

async function realiser(d: Record<string, any>): Promise<[string, Record<string, unknown>]> {
  switch (d.type) {
    case "demande": {
      const rep = await recepteur.demande(
        `[Demande envoyée depuis ton autre appareil « ${d.de} » : exécute-la ici, sur le téléphone ${nomTelephone()}, puis réponds en une ou deux phrases]\n${d.texte || ""}`,
        String(d.de || "?"),
      );
      return [rep.trim() || "C'est fait.", {}];
    }
    case "ecrire_fichier": {
      // le téléphone n'a pas de dossiers comme un ordinateur : le fichier rejoint « Fichiers reçus » (onglet Appareils)
      const nom = nomFichier(String(d.chemin || "fichier"));
      const contenu = String(d.contenu || "");
      garderFichier({ nom, taille: Math.floor((contenu.length * 3) / 4), de: String(d.de || "?"), contenu });
      return [`Fichier reçu sur ${nomTelephone()} : ${nom} (onglet Appareils › Fichiers reçus).`, {}];
    }
    case "lire_fichier": {
      const nom = nomFichier(String(d.chemin || ""));
      const f = [...useDonnees.getState().fichiers].reverse().find((x) => x.nom === nom || x.id === d.chemin);
      if (!f) {
        const l = useDonnees.getState().fichiers.map((x) => x.nom);
        throw new Error(`Fichier introuvable sur le téléphone. Fichiers disponibles : ${l.join(", ") || "aucun"}`);
      }
      return [`Fichier ${f.nom} (${f.taille} octets).`, { nom: f.nom, contenu: f.contenu }];
    }
    case "ping":
      return [`${nomTelephone()} est là.`, {}];
    case "mettre_a_jour":
      return [`${nomTelephone()} est une appli web : elle est toujours à jour.`, {}];
    default:
      throw new Error(`Type d'ordre inconnu : ${d.type}`);
  }
}
