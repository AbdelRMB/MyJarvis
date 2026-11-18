import { useJarvis } from "../stores/jarvis";

/** Système de l'ordinateur où tourne Jarvis (pour adapter les textes). */
export function useOS() {
  const p = useJarvis((s) => s.session?.plateforme ?? "windows");
  const mac = p === "mac";
  return {
    mac,
    ordi: mac ? "Mac" : "PC",
    coffre: mac ? "Trousseau d'accès du Mac" : "Gestionnaire d'identifiants Windows",
    zoneIcone: mac ? "dans la barre des menus (en haut à droite)" : "près de l'horloge",
    demarrage: mac ? "à l'ouverture de session sur le Mac" : "au démarrage de Windows",
    touches: (combo: string) =>
      combo
        .replace(/[<>]/g, "")
        .split("+")
        .map((k) => (mac ? ({ ctrl: "⌃ Ctrl", alt: "⌥ Option", cmd: "⌘ Cmd", shift: "⇧ Maj" } as Record<string, string>)[k] : undefined) ?? k.charAt(0).toUpperCase() + k.slice(1))
        .join(" + "),
  };
}
