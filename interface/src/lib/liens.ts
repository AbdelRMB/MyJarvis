import { api } from "./api";

/** Ouvre une page (politique de confidentialité, mentions légales…) dans le navigateur de l'ordinateur. */
export async function ouvrirLien(url: string) {
  try {
    await api("/api/ouvrir-lien", { method: "POST", json: { url } });
  } catch {
    window.open(url, "_blank", "noopener"); // interface ouverte dans un navigateur
  }
}
