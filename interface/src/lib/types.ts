export type BlocTexte = { type: "texte"; texte: string };
export type BlocPensee = { type: "pensee"; texte: string };
export type BlocOutil = {
  type: "outil";
  id?: number;
  nom: string;
  args: Record<string, string>;
  resultat: string | null;
  erreur?: boolean;
  debut?: number;
  fin?: number;
};
export type Bloc = BlocTexte | BlocPensee | BlocOutil;

export type MessageUtilisateur = { id: string; role: "user"; texte: string; date: number };
export type MessageJarvis = { id: string; role: "jarvis"; blocs: Bloc[]; date: number; enCours: boolean };
export type MessageSysteme = { id: string; role: "info" | "erreur"; texte: string; date: number };
export type Message = MessageUtilisateur | MessageJarvis | MessageSysteme;

export type Session = { jeton: string; nom: string; nb_outils: number; plateforme?: "windows" | "mac" | "linux" };

export type Gpu = { nom: string; util: number; vram_used: number; vram_total: number; temp: number };
export type Systeme = {
  cpu: number;
  ram: number;
  ram_used: number;
  ram_total: number;
  disque: number;
  disque_libre: number;
  gpu: Gpu | null;
  ollama: boolean;
  charges: { nom: string; vram: number; taille: number }[];
  modele: string;
  cerveau?: "ollama" | "claude" | "openai";
  cle_claude_manquante?: boolean;
  occupe: boolean;
  uptime: number;
};

export type ConfigServeur = {
  modele: string;
  modele_vision: string;
  temperature: number;
  reflexion: boolean;
  num_ctx: number;
  max_etapes_outils: number;
  whisper_modele: string;
  nom_utilisateur: string;
  cerveau: "ollama" | "claude" | "openai";
  openai_modele?: string;
  claude_modele: string;
  claude_effort: string;
  conseiller?: boolean;
  recherche_web_native?: boolean;
};

export type Fait = { fait: string; categorie: string; date?: string; fid?: string; modifie?: number };
export type JourHistorique = { jour: string; nb: number; apercu: string; pcs?: string[] };
export type EntreeHistorique = { heure: string; role: "user" | "jarvis"; texte: string; pc?: string };
export type Action = { date: string; outil: string; args: Record<string, unknown>; resultat: string | null };
export type Outil = {
  nom: string;
  description: string;
  module: string;
  params: { nom: string; type: string; description: string; requis: boolean }[];
  doc: string;
};
