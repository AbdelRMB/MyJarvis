import { ShieldAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { parler } from "../audio/tts";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import { bus } from "../stores/jarvis";
import { Bouton } from "./ui";

type Demande = { id: string; titre: string; detail: string };

/** Jarvis demande l'accord avant une action sensible (ex : commande qui modifie un serveur). */
export function Confirmations() {
  const [liste, setListe] = useState<Demande[]>([]);
  const annoncees = useRef(new Set<string>());
  useEffect(() => {
    const sur = (e: Event) => {
      const d = (e as CustomEvent<Demande>).detail;
      setListe((l) => (l.some((x) => x.id === d.id) ? l : [...l, d]));
      if (!annoncees.current.has(d.id)) {
        annoncees.current.add(d.id);
        parler(t("J'ai besoin de ton accord."), true);
      }
    };
    const fin = (e: Event) => setListe((l) => l.filter((x) => x.id !== (e as CustomEvent<string>).detail));
    bus.addEventListener("confirmation", sur);
    bus.addEventListener("confirmation_fin", fin);
    return () => {
      bus.removeEventListener("confirmation", sur);
      bus.removeEventListener("confirmation_fin", fin);
    };
  }, []);
  const repondre = async (d: Demande, ok: boolean) => {
    setListe((l) => l.filter((x) => x.id !== d.id));
    await api("/api/confirmation", { method: "POST", json: { id: d.id, ok } }).catch(() => {});
  };
  if (!liste.length) return null;
  const d = liste[0];
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <div className="w-[min(560px,100%)] rounded-xl border border-ambre/60 bg-surface-2 p-5 shadow-glow">
        <div className="mb-2 flex items-center gap-2 font-semibold text-ambre">
          <ShieldAlert className="size-5" /> {t("Jarvis demande ton accord")}
        </div>
        <p className="text-sm">{d.titre}</p>
        {d.detail && <pre className="mt-3 max-h-[40vh] overflow-auto rounded-md border border-ligne bg-black/40 p-3 font-mono text-[12px] whitespace-pre-wrap">{d.detail}</pre>}
        <div className="mt-4 flex justify-end gap-2">
          <Bouton variante="fantome" onClick={() => repondre(d, false)}>
            {t("Refuser")}
          </Bouton>
          <Bouton variante="primaire" onClick={() => repondre(d, true)}>
            {t("Autoriser")}
          </Bouton>
        </div>
      </div>
    </div>
  );
}
