/**
 * Langue de l'interface : français (textes d'origine) ou anglais.
 * Les textes sont écrits en français dans le code et passent par t("…") ; la traduction anglaise est dans
 * ./en.ts (clé = texte français). Changer de langue recharge l'interface (Réglages › Interface).
 */
import { EN } from "./en";

export type Langue = "fr" | "en";
const CLE = "jarvis-langue";

function lire(): Langue {
  try {
    return localStorage.getItem(CLE) === "en" ? "en" : "fr";
  } catch {
    return "fr";
  }
}

export const LANGUE: Langue = lire();

export function changerLangue(l: Langue) {
  try {
    localStorage.setItem(CLE, l);
  } catch {
    /* stockage indisponible */
  }
}

/** Traduit un texte français ; {nom} est remplacé par vars.nom. Les espaces de début/fin sont conservés. */
export function t(texte: string, vars?: Record<string, string | number>): string {
  let r = texte;
  if (LANGUE === "en") {
    const debut = texte.match(/^\s*/)![0];
    const fin = texte.match(/\s*$/)![0];
    const cle = texte.trim();
    const trad = EN[cle];
    if (trad !== undefined) r = debut + trad + fin;
  }
  if (vars) for (const [k, v] of Object.entries(vars)) r = r.replaceAll(`{${k}}`, String(v));
  return r;
}
