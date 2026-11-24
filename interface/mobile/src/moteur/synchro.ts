/**
 * Temps réel, comme sur le bureau (compte.demarrer_synchro) : le serveur répond dès qu'un appareil change quelque
 * chose dans le compte, ou qu'un ordre arrive pour ce téléphone. Présence toutes les 20 s (onglet Appareils).
 * Un navigateur de téléphone met l'appli en pause en arrière-plan : la boucle reprend dès qu'on revient.
 */
import { api, chargerCoffre, ErreurCompte, VERSION_MOBILE } from "./compte";
import { traiter } from "./appareils";
import { chargerAppareils, synchroniser, useDonnees, viderAttente, type Changements } from "./donnees";
import { chargerPartages } from "./partages";
import { nomTelephone, reglagesTel, session } from "./stockage";

let lancee = false;
let revision = 0;
let partages = 0; // dernière version vue des tâches / transcriptions des ordinateurs (moteur/partages.ts)
let occupe = false;
let controleur: AbortController | null = null;
const ecouteurs: ((c: Changements & { coffre?: boolean }) => void)[] = [];

export const quandChangement = (f: (c: Changements & { coffre?: boolean }) => void) => {
  ecouteurs.push(f);
  return () => void ecouteurs.splice(ecouteurs.indexOf(f), 1);
};
export const signalerOccupe = (v: boolean) => {
  occupe = v;
};

export async function presence() {
  if (!session()) return;
  const r = reglagesTel();
  try {
    await api("POST", "/appareils/presence", {
      nom: nomTelephone(),
      plateforme: "telephone",
      version: VERSION_MOBILE,
      occupe,
      accepte: r.accepte,
      mode: r.confirmation ? "confirmation" : "libre",
    });
  } catch {
    /* hors ligne */
  }
}

async function synchroComplete() {
  const ch: Changements & { coffre?: boolean } = await synchroniser();
  ch.coffre = await chargerCoffre().catch(() => false);
  if (Object.values(ch).some(Boolean)) for (const f of ecouteurs) f(ch);
}

const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function demarrerSynchro() {
  if (lancee) return;
  lancee = true;
  void (async () => {
    let dernierePresence = 0;
    let premiere = true;
    while (lancee) {
      if (!session()) {
        await pause(2000);
        continue;
      }
      if (document.hidden) {
        await pause(1000); // en arrière-plan : le navigateur coupe le réseau, on attend le retour
        continue;
      }
      try {
        if (premiere) {
          premiere = false;
          await synchroComplete();
          void chargerAppareils().catch(() => {});
        }
        if (Date.now() - dernierePresence > 20_000) {
          dernierePresence = Date.now();
          void presence().then(() => chargerAppareils().catch(() => {}));
        }
        await viderAttente();
        controleur = new AbortController();
        const r = await api<{ revision: number; change: boolean; ordres: { id: string; blob: string }[]; partages?: number }>(
          "GET",
          `/attendre?depuis=${revision}&partages=${partages}`,
          undefined,
          { signal: controleur.signal },
        );
        useDonnees.setState({ enLigne: true });
        if (r.ordres?.length) void traiter(r.ordres);
        if (r.partages !== undefined && r.partages >= 0 && r.partages !== partages) {
          partages = r.partages; // une tâche ou une transcription a changé sur un ordinateur
          void chargerPartages();
        }
        if (r.change && revision !== 0) await synchroComplete();
        revision = r.revision;
      } catch (e) {
        if ((e as Error).name === "AbortError") continue; // retour au premier plan : on relance tout de suite
        if (e instanceof ErreurCompte && e.statut === 401) {
          await pause(2000);
          continue;
        }
        useDonnees.setState({ enLigne: false });
        await pause(8000);
      }
    }
  })();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && session()) {
      controleur?.abort(); // l'attente en cours a pu être coupée pendant la pause : on repart sur une neuve
      void synchroComplete().catch(() => {});
      void chargerPartages();
      void presence();
    }
  });
  window.addEventListener("online", () => controleur?.abort());
}

export function arreterSynchro() {
  lancee = false;
  revision = 0;
  partages = 0;
  controleur?.abort();
}

/** Synchro immédiate (bouton « Actualiser », tirer pour rafraîchir). */
export const actualiser = () => synchroComplete();
