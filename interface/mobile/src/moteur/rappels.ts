/**
 * Rappels de la liste À faire sur le téléphone : à l'heure dite, notification + Wesley le dit à voix haute.
 * Une appli web n'est réveillée que lorsqu'elle est ouverte (ou en fond récent) : les ordinateurs allumés
 * préviennent aussi, comme avant. Chaque rappel n'est annoncé qu'une fois sur ce téléphone.
 */
import { useDonnees } from "./donnees";
import { cache, definirCache } from "./stockage";

let minuterie = 0;

export async function autoriserNotifications() {
  if (!("Notification" in window)) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  return (await Notification.requestPermission()) === "granted";
}

export async function notifier(titre: string, texte: string) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try {
    const sw = await navigator.serviceWorker?.getRegistration();
    if (sw) await sw.showNotification(titre, { body: texte, icon: "/mobile/icone-192.png", badge: "/mobile/icone-192.png", tag: titre });
    else new Notification(titre, { body: texte, icon: "/mobile/icone-192.png" });
  } catch {
    /* notifications bloquées */
  }
}

export function surveillerRappels(annoncer: (titre: string) => void) {
  clearInterval(minuterie);
  const verifier = () => {
    const faits: string[] = cache("rappels_faits", []);
    const maintenant = new Date();
    const p = (n: number) => String(n).padStart(2, "0");
    const iso = `${maintenant.getFullYear()}-${p(maintenant.getMonth() + 1)}-${p(maintenant.getDate())}T${p(maintenant.getHours())}:${p(maintenant.getMinutes())}`;
    const dus = useDonnees
      .getState()
      .afaire.filter((t) => t.statut !== "fait" && t.rappel && t.rappel.length >= 16 && t.rappel <= iso && !faits.includes(t.id + t.rappel));
    // un rappel vieux de plus de 2 h (téléphone éteint) est marqué sans être annoncé
    const recents = dus.filter((t) => Date.now() - new Date(t.rappel).getTime() < 2 * 3600e3);
    for (const t of recents) {
      void notifier("Rappel — Wesley", t.titre);
      annoncer(t.titre);
    }
    if (dus.length) definirCache("rappels_faits", [...faits, ...dus.map((t) => t.id + t.rappel)].slice(-300));
  };
  verifier();
  minuterie = window.setInterval(verifier, 20_000);
}
