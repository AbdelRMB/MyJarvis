import { create } from "zustand";
import { uid } from "../lib/format";

export type Toast = { id: string; texte: string; genre: "info" | "succes" | "erreur" };

export const useToasts = create<{ toasts: Toast[] }>(() => ({ toasts: [] }));

export function toast(texte: string, genre: Toast["genre"] = "info") {
  const id = uid();
  useToasts.setState((s) => ({ toasts: [...s.toasts.slice(-3), { id, texte, genre }] }));
  setTimeout(() => useToasts.setState((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), genre === "erreur" ? 6000 : 3500);
}
