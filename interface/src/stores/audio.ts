import { create } from "zustand";

export type VoixDispo = { uri: string; nom: string; lang: string; locale: boolean };

type EtatAudio = {
  pret: boolean;            // AudioContext créé (après le premier clic)
  micActif: boolean;
  nomMicro: string;
  erreurMicro: string | null;
  peripheriques: { id: string; nom: string }[];
  enregistre: boolean;
  transcrit: boolean;
  parle: boolean;
  eveilJusqua: number;      // mode « Wesley » : fenêtre d'écoute après avoir entendu son nom
  derniereTranscription: string;
  ecouteFond: boolean;            // appli de bureau : « Hey Wesley » géré par le serveur
  vocalServeur: "eveil" | "transcription" | null;
  voix: VoixDispo[];
};

export const useAudio = create<EtatAudio>(() => ({
  pret: false,
  micActif: false,
  nomMicro: "",
  erreurMicro: null,
  peripheriques: [],
  enregistre: false,
  transcrit: false,
  parle: false,
  eveilJusqua: 0,
  derniereTranscription: "",
  ecouteFond: false,
  vocalServeur: null,
  voix: [],
}));

export const audio = () => useAudio.getState();
export const majAudio = (p: Partial<EtatAudio>) => useAudio.setState(p);
