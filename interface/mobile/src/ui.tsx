/** Petits éléments propres au téléphone (le reste vient de l'interface de bureau : src/components/ui.tsx). */
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { create } from "zustand";
import { cx } from "../../src/lib/format";

export type Vue = "assistant" | "afaire" | "memoire" | "appareils" | "plus" | "automatisations" | "services" | "taches" | "transcriptions" | "tickets" | "reglages";

type Ui = {
  vue: Vue;
  toast: { texte: string; erreur?: boolean; id: number } | null;
  confirmation: { titre: string; detail: string; repondre: (ok: boolean) => void } | null;
};
export const useUi = create<Ui>(() => ({ vue: "assistant", toast: null, confirmation: null }));
export const allerA = (vue: Vue) => useUi.setState({ vue });

let minuterie = 0;
export function toast(texte: string, erreur = false) {
  clearTimeout(minuterie);
  useUi.setState({ toast: { texte, erreur, id: Date.now() } });
  minuterie = window.setTimeout(() => useUi.setState({ toast: null }), erreur ? 5000 : 2500);
}
export const erreurToast = (e: unknown) => toast((e as Error).message || String(e), true);

export function demanderConfirmation(titre: string, detail: string): Promise<boolean> {
  return new Promise((ok) => useUi.setState({ confirmation: { titre, detail, repondre: (v) => (useUi.setState({ confirmation: null }), ok(v)) } }));
}

/** En-tête d'un écran : titre + actions, collé en haut pendant le défilement. */
export function Entete({ titre, sous, actions, retour }: { titre: string; sous?: ReactNode; actions?: ReactNode; retour?: () => void }) {
  return (
    <header className="sticky top-0 z-10 flex items-center gap-2 border-b border-ligne bg-fond/90 px-3 py-2.5 backdrop-blur">
      {retour && (
        <button onClick={retour} className="-ml-1 grid size-9 place-items-center rounded-md text-doux active:bg-white/5" aria-label="Retour">
          ‹
        </button>
      )}
      <div className="min-w-0 flex-1">
        <h1 className="titre-hud truncate text-[13px] font-bold text-hud">{titre}</h1>
        {sous && <div className="truncate text-[12px] text-doux">{sous}</div>}
      </div>
      <div className="flex items-center gap-1">{actions}</div>
    </header>
  );
}

/** Ligne de liste tactile (hauteur ≥ 44 px), dense. */
export function Ligne({ children, onClick, className }: { children: ReactNode; onClick?: () => void; className?: string }) {
  const C = onClick ? "button" : "div";
  return (
    <C onClick={onClick} className={cx("flex min-h-11 w-full items-center gap-3 border-b border-ligne px-3 py-2 text-left", onClick && "active:bg-white/5", className)}>
      {children}
    </C>
  );
}

export function Section({ titre, children, actions }: { titre: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="mt-3">
      <div className="flex items-center px-3 pb-1">
        <h2 className="titre-hud text-[10px] text-tres-doux">{titre}</h2>
        <div className="ml-auto">{actions}</div>
      </div>
      <div className="border-t border-ligne bg-surface/50">{children}</div>
    </section>
  );
}

/** Feuille qui monte du bas de l'écran (formulaires, détails). */
export function Feuille({ titre, onFermer, children }: { titre: string; onFermer: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex flex-col justify-end bg-black/60" onClick={(e) => e.target === e.currentTarget && onFermer()}>
      <div className="animate-entree max-h-[88dvh] overflow-y-auto rounded-t-xl border-t border-ligne-forte bg-surface pb-[max(16px,env(safe-area-inset-bottom))]">
        <div className="sticky top-0 flex items-center border-b border-ligne bg-surface px-4 py-3">
          <h2 className="titre-hud text-[12px] text-hud">{titre}</h2>
          <button onClick={onFermer} className="-mr-2 ml-auto grid size-9 place-items-center text-doux" aria-label="Fermer">
            <X className="size-5" />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Zone({ className, ...p }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...p}
      className={cx("w-full rounded-md border border-ligne-forte bg-surface-2 px-3 py-2 text-sm outline-none placeholder:text-tres-doux focus:border-hud", className)}
    />
  );
}

export const tempsRelatif = (ts: number) => {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return new Date(ts * 1000).toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
};
