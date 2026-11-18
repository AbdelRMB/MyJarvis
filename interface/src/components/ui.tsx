import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/format";

type Variante = "primaire" | "contour" | "fantome" | "danger";

export function Bouton({
  variante = "contour",
  taille = "md",
  icone,
  chargement,
  className,
  children,
  ...p
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; taille?: "sm" | "md"; icone?: ReactNode; chargement?: boolean }) {
  return (
    <button
      {...p}
      disabled={p.disabled || chargement}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all select-none disabled:opacity-40 whitespace-nowrap",
        taille === "sm" ? "h-8 px-3 text-[13px]" : "h-10 px-4 text-sm",
        variante === "primaire" && "bg-hud text-fond hover:bg-hud-clair shadow-glow",
        variante === "contour" && "border border-ligne-forte text-hud bg-hud/5 hover:bg-hud/15 hover:border-hud",
        variante === "fantome" && "text-doux hover:text-texte hover:bg-white/5",
        variante === "danger" && "border border-rouge/50 text-rouge bg-rouge/5 hover:bg-rouge/15",
        className,
      )}
    >
      {chargement ? <Loader2 className="size-4 animate-spin" /> : icone}
      {children}
    </button>
  );
}

export function BoutonIcone({
  className,
  actif,
  label,
  children,
  ...p
}: ButtonHTMLAttributes<HTMLButtonElement> & { actif?: boolean; label: string }) {
  return (
    <button
      {...p}
      aria-label={label}
      title={label}
      className={cx(
        "grid size-9 place-items-center rounded-md transition-colors",
        actif ? "bg-hud/15 text-hud" : "text-doux hover:bg-white/5 hover:text-texte",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Panneau({
  titre,
  icone,
  actions,
  className,
  corpsClassName,
  children,
}: {
  titre?: ReactNode;
  icone?: ReactNode;
  actions?: ReactNode;
  className?: string;
  corpsClassName?: string;
  children: ReactNode;
}) {
  return (
    <section className={cx("coins flex min-h-0 flex-col border border-ligne bg-surface/70 backdrop-blur-sm", className)}>
      {titre && (
        <header className="flex items-center gap-2 border-b border-ligne px-4 py-3">
          {icone && <span className="text-hud [&>svg]:size-4">{icone}</span>}
          <h2 className="titre-hud text-[11px] text-hud">{titre}</h2>
          <div className="ml-auto flex items-center gap-1">{actions}</div>
        </header>
      )}
      <div className={cx("min-h-0 flex-1 p-4", corpsClassName)}>{children}</div>
    </section>
  );
}

export function Interrupteur({
  actif,
  onChange,
  label,
  aide,
}: {
  actif: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  aide?: ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 py-2.5">
      <span>
        <span className="block text-sm">{label}</span>
        {aide && <span className="mt-0.5 block text-[13px] text-doux">{aide}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={actif}
        onClick={() => onChange(!actif)}
        className={cx(
          "relative h-6 w-11 flex-none rounded-full border transition-colors",
          actif ? "border-hud bg-hud/25" : "border-ligne-forte bg-surface-3",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 size-4.5 rounded-full transition-all",
            actif ? "left-[22px] bg-hud shadow-glow" : "left-0.5 bg-doux",
          )}
        />
      </button>
    </label>
  );
}

export function Curseur({
  label,
  valeur,
  affichage,
  min,
  max,
  pas,
  onChange,
  aide,
}: {
  label: ReactNode;
  valeur: number;
  affichage: string;
  min: number;
  max: number;
  pas: number;
  onChange: (v: number) => void;
  aide?: ReactNode;
}) {
  return (
    <div className="py-2">
      <div className="mb-1.5 flex items-baseline justify-between text-sm">
        <span>{label}</span>
        <span className="font-mono text-xs text-hud">{affichage}</span>
      </div>
      <input
        type="range"
        className="w-full"
        min={min}
        max={max}
        step={pas}
        value={valeur}
        onChange={(e) => onChange(+e.target.value)}
      />
      {aide && <p className="mt-1 text-[13px] text-doux">{aide}</p>}
    </div>
  );
}

export function Selecteur({
  label,
  valeur,
  options,
  onChange,
  aide,
}: {
  label: ReactNode;
  valeur: string;
  options: { valeur: string; libelle: string }[];
  onChange: (v: string) => void;
  aide?: ReactNode;
}) {
  return (
    <label className="block py-2">
      <span className="mb-1.5 block text-sm">{label}</span>
      <select
        value={valeur}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm outline-none focus:border-hud"
      >
        {options.map((o) => (
          <option key={o.valeur} value={o.valeur} className="bg-surface-2">
            {o.libelle}
          </option>
        ))}
      </select>
      {aide && <span className="mt-1 block text-[13px] text-doux">{aide}</span>}
    </label>
  );
}

export function Champ({ className, ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...p}
      className={cx(
        "h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm outline-none placeholder:text-tres-doux focus:border-hud",
        className,
      )}
    />
  );
}

export function Pastille({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-doux">
      <span className={cx("size-2 rounded-full", ok ? "bg-vert shadow-[0_0_8px] shadow-vert" : "bg-rouge shadow-[0_0_8px] shadow-rouge")} />
      {children}
    </span>
  );
}

export function Badge({ children, ton = "hud" }: { children: ReactNode; ton?: "hud" | "ambre" | "rouge" | "vert" | "doux" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[11px]",
        ton === "hud" && "bg-hud/10 text-hud",
        ton === "ambre" && "bg-ambre/10 text-ambre",
        ton === "rouge" && "bg-rouge/10 text-rouge",
        ton === "vert" && "bg-vert/10 text-vert",
        ton === "doux" && "bg-white/5 text-doux",
      )}
    >
      {children}
    </span>
  );
}

export function Onglets<T extends string>({
  onglets,
  actif,
  onChange,
}: {
  onglets: { id: T; libelle: string; icone?: ReactNode }[];
  actif: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-ligne">
      {onglets.map((o) => (
        <button
          key={o.id}
          role="tab"
          aria-selected={o.id === actif}
          onClick={() => onChange(o.id)}
          className={cx(
            "-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm transition-colors [&>svg]:size-4",
            o.id === actif ? "border-hud text-hud" : "border-transparent text-doux hover:text-texte",
          )}
        >
          {o.icone}
          {o.libelle}
        </button>
      ))}
    </div>
  );
}

export function Vide({ icone, titre, texte }: { icone: ReactNode; titre: string; texte?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="grid size-12 place-items-center rounded-full border border-ligne-forte text-hud [&>svg]:size-5">{icone}</div>
      <p className="font-medium">{titre}</p>
      {texte && <p className="max-w-sm text-sm text-doux">{texte}</p>}
    </div>
  );
}

export function EnTetePage({ titre, sousTitre, actions }: { titre: string; sousTitre?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end gap-4">
      <div>
        <h1 className="titre-hud text-lg font-bold text-texte">{titre}</h1>
        {sousTitre && <p className="mt-1 text-sm text-doux">{sousTitre}</p>}
      </div>
      <div className="ml-auto flex flex-wrap gap-2">{actions}</div>
    </div>
  );
}
