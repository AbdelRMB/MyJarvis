import { reglages } from "../stores/reglages";
import { micro } from "./micro";

/** Petits sons d'interface synthétisés (aucun fichier audio). */
export function bip(freqs: number[] = [880], duree = 0.09, vol = 0.05) {
  const ctx = micro.ctx;
  if (!reglages().bips || !ctx) return;
  let t = ctx.currentTime;
  for (const f of freqs) {
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "sine";
    o.frequency.value = f;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(vol, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + duree);
    o.connect(g).connect(ctx.destination);
    o.start(t);
    o.stop(t + duree + 0.02);
    t += duree * 0.75;
  }
}

export const sons = {
  demarrage: () => bip([440, 660, 880, 1320], 0.1),
  ecoute: () => bip([660, 990], 0.07),
  eveil: () => bip([880, 1320], 0.08),
  envoi: () => bip([520], 0.06),
  outil: () => bip([1200], 0.04, 0.025),
  fin: () => bip([990, 660], 0.07),
  stop: () => bip([440, 330], 0.08),
  erreur: () => bip([300, 200], 0.12),
  clic: () => bip([740], 0.05, 0.03),
};
