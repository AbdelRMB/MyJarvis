import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type ModeMicro = "ptt" | "auto" | "eveil";
export type Vue = "assistant" | "historique" | "memoire" | "connecteurs" | "activite" | "arsenal" | "systeme" | "reglages" | "majs" | "automatisations" | "taches" | "appareils" | "afaire" | "tickets" | "stats" | "sites";

export type Reglages = {
  mode: ModeMicro;
  deviceId: string;
  gain: number;
  seuil: number;
  silence: number;
  bruit: boolean;
  echo: boolean;
  agc: boolean;
  sourdine: boolean;
  tts: boolean;
  ttsMoteur: "edge" | "piper" | "navigateur" | "kyutai";
  ttsVoixKyutai: string;
  ttsVoixEdge: string;
  ttsVoixPiper: string;
  voix: string;
  debit: number;
  hauteur: number;
  volume: number;
  bips: boolean;
  animations: "completes" | "legeres" | "aucunes";
  langue: string;
  menuReduit: boolean;
  groupesFermes: string[]; // sections de la barre latérale repliées
  vue: Vue;
};

export const DEFAUT: Reglages = {
  mode: "ptt",
  deviceId: "",
  gain: 1.5,
  seuil: 0.03,
  silence: 2500,
  bruit: true,
  echo: true,
  agc: false,
  sourdine: true,
  tts: true,
  ttsMoteur: "edge",
  ttsVoixEdge: "fr-FR-HenriNeural",
  ttsVoixPiper: "fr_FR-tom-medium",
  ttsVoixKyutai: "cml-tts/fr/10087_11650_000028-0002.wav",
  voix: "",
  debit: 1.05,
  hauteur: 0.92,
  volume: 1,
  bips: true,
  animations: "legeres",
  langue: "fr",
  menuReduit: false,
  groupesFermes: [],
  vue: "assistant",
};

// localStorage peut être indisponible (navigation privée stricte) : on retombe sur une mémoire volatile
const stockageSur = () => {
  try {
    localStorage.setItem("__t", "1");
    localStorage.removeItem("__t");
    return localStorage;
  } catch {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
  }
};

export const useReglages = create<Reglages & { maj: (p: Partial<Reglages>) => void }>()(
  persist((set) => ({ ...DEFAUT, maj: (p) => set(p) }), {
    name: "wesley.reglages.v2",
    storage: createJSONStorage(stockageSur),
    version: 3,
    // v0 -> v1 : nouvelle voix serveur, envoi plus réactif
    migrate: (ancien, version) => {
      const r = { ...DEFAUT, ...(ancien as Partial<Reglages>) };
      if (version < 1) r.debit = 1.05;
      if (version < 3) r.silence = 2500; // écoute continue : envoi après 2,5 s de silence
      return r as Reglages & { maj: (p: Partial<Reglages>) => void };
    },
  }),
);

export const reglages = () => useReglages.getState();
