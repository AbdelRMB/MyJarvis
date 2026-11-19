import { useJarvis } from "../stores/jarvis";
import { t } from "./i18n";

/** Système de l'ordinateur où tourne Jarvis (pour adapter les textes). */
export function useOS() {
  const p = useJarvis((s) => s.session?.plateforme ?? "windows");
  const mac = p === "mac";
  return {
    mac,
    ordi: mac ? "Mac" : "PC",
    coffre: mac ? t("Trousseau d'accès du Mac") : t("Gestionnaire d'identifiants Windows"),
    zoneIcone: mac ? t("dans la barre des menus (en haut à droite)") : t("près de l'horloge"),
    demarrage: mac ? t("à l'ouverture de session sur le Mac") : t("au démarrage de Windows"),
    touches: (combo: string) =>
      combo
        .replace(/[<>]/g, "")
        .split("+")
        .map((k) => (mac ? ({ ctrl: "⌃ Ctrl", alt: "⌥ Option", cmd: "⌘ Cmd", shift: t("⇧ Maj") } as Record<string, string>)[k] : undefined) ?? k.charAt(0).toUpperCase() + k.slice(1))
        .join(" + "),
  };
}
