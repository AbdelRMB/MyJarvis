/** Formats des données du compte : les mêmes que l'appli de bureau (wesley/*.py). */

export type Fait = { fait: string; categorie: string; date: string; fid: string; modifie?: number };

export type TacheAFaire = {
  id: string;
  titre: string;
  note: string;
  echeance: string;
  rappel: string;
  priorite: "basse" | "normale" | "haute";
  statut: "a_faire" | "en_cours" | "fait";
  cree: string;
  modifie: string;
  fait_le: string;
};

export type Automatisation = {
  id: string;
  nom: string;
  actif: boolean;
  declencheur: {
    type: "mail" | "horaire" | "intervalle" | "demarrage" | "commande";
    expediteur?: string;
    sujet?: string;
    contient?: string;
    connecteur?: string;
    heure?: string;
    jours?: number[];
    minutes?: number;
    phrase?: string;
  };
  action: { type: "prevenir" | "wesley"; consigne?: string; message?: string };
  appareil: string;
  cree: string;
};

/** connecteurs.json : { cid: { type, nom?, ...champs non secrets } } ; les secrets sont dans le coffre (« cid:champ »). */
export type Connecteurs = Record<string, { type: string; actif?: boolean; conf?: Record<string, unknown>; [k: string]: unknown }>;

export type Profil = Record<string, string | number | boolean | undefined> & {
  nom_utilisateur?: string;
  cerveau?: string;
  claude_modele?: string;
  langue?: string;
};

export type Appareil = {
  id: string;
  nom: string;
  plateforme: string;
  version: string;
  vu: number;
  en_ligne: boolean;
  occupe: boolean;
  accepte: boolean;
  mode: string;
  connecte_depuis: number;
  moi: boolean;
};

export type Ticket = {
  id: number;
  genre: string;
  titre: string;
  description: string;
  statut: string;
  reponse: string;
  version: string;
  plateforme: string;
  appareil: string;
  cree: number;
  modifie: number;
  email?: string;
  prenom?: string;
};

export type Coffre = { trousseau?: Record<string, string>; [cle: string]: unknown };

export type LigneHistorique = { id: number; jour: string; machine: string; ligne: string };

/** Un ordre reçu ou envoyé (journal affiché dans l'onglet Appareils). */
export type EntreeOrdre = { ts: number; sens: "envoye" | "recu"; appareil: string; quoi: string; resultat: string; statut: string };

/** Fichier reçu d'un autre appareil (gardé sur le téléphone, téléchargeable). */
export type FichierRecu = { id: string; nom: string; taille: number; de: string; ts: number; contenu: string };
