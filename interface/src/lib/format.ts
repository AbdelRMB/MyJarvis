export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export const uid = () => Math.random().toString(36).slice(2, 10);

export function duree(secondes: number) {
  const j = Math.floor(secondes / 86400);
  const h = Math.floor((secondes % 86400) / 3600);
  const m = Math.floor((secondes % 3600) / 60);
  return [j && `${j} j`, (j || h) && `${h} h`, `${m} min`].filter(Boolean).join(" ");
}

export function jourLisible(iso: string) {
  const d = new Date(iso + "T12:00:00");
  const auj = new Date();
  const hier = new Date(Date.now() - 86400000);
  if (d.toDateString() === auj.toDateString()) return "Aujourd'hui";
  if (d.toDateString() === hier.toDateString()) return "Hier";
  return d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
}

export const heure = (t: number) => new Date(t).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

export const nomOutil = (n: string) => n.replace(/_/g, " ");

/** Texte lisible à voix haute : sans code, sans Markdown, sans URL. */
export function pourLaVoix(t: string) {
  return t
    .replace(/```[\s\S]*?```/g, " (le code est affiché à l'écran) ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "le lien")
    .replace(/[*_#>|]/g, "")
    .replace(/\((J'ai atteint|Tâche interrompue)[^)]*\)/g, "")
    .trim();
}
