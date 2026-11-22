/**
 * L'appli s'appelait Jarvis avant la 2.0.0 : ses préférences d'interface étaient rangées sous d'autres clés.
 * Importé EN PREMIER par main.tsx, avant les stores qui lisent ces clés.
 */
const CLES: [ancienne: string, nouvelle: string][] = [
  ["jarvis.reglages.v2", "wesley.reglages.v2"],
  ["jarvis-langue", "wesley-langue"],
];

try {
  for (const [ancienne, nouvelle] of CLES) {
    const valeur = localStorage.getItem(ancienne);
    if (valeur !== null && localStorage.getItem(nouvelle) === null) localStorage.setItem(nouvelle, valeur);
    if (valeur !== null) localStorage.removeItem(ancienne);
  }
} catch {
  // stockage indisponible (navigation privée stricte) : rien à reprendre
}

export {};
