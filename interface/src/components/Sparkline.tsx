import { cx } from "../lib/format";

/** Mini-courbe SVG 0–100 %. */
export function Sparkline({ valeurs, className, couleur = "var(--color-hud)" }: { valeurs: number[]; className?: string; couleur?: string }) {
  const W = 100;
  const H = 30;
  const n = Math.max(2, valeurs.length);
  const pts = valeurs.map((v, i) => `${(i / (n - 1)) * W},${H - (Math.min(100, Math.max(0, v)) / 100) * (H - 2) - 1}`);
  const id = `sp-${couleur.replace(/\W/g, "")}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={cx("block h-10 w-full", className)} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={couleur} stopOpacity="0.3" />
          <stop offset="1" stopColor={couleur} stopOpacity="0" />
        </linearGradient>
      </defs>
      {pts.length > 1 && (
        <>
          <polygon points={`0,${H} ${pts.join(" ")} ${((pts.length - 1) / (n - 1)) * W},${H}`} fill={`url(#${id})`} />
          <polyline points={pts.join(" ")} fill="none" stroke={couleur} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
        </>
      )}
    </svg>
  );
}

/** Jauge circulaire. */
export function JaugeRonde({ valeur, libelle, detail, taille = 120 }: { valeur: number; libelle: string; detail?: string; taille?: number }) {
  const r = 42;
  const c = 2 * Math.PI * r;
  const v = Math.min(100, Math.max(0, valeur));
  const couleur = v > 90 ? "var(--color-rouge)" : v > 75 ? "var(--color-ambre)" : "var(--color-hud)";
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: taille, height: taille }}>
        <svg viewBox="0 0 100 100" className="size-full -rotate-90">
          <circle cx="50" cy="50" r={r} fill="none" stroke="rgb(60 232 255 / .1)" strokeWidth="6" />
          <circle cx="50" cy="50" r={r + 6} fill="none" stroke="rgb(60 232 255 / .15)" strokeWidth="0.6" strokeDasharray="1 3" />
          <circle
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke={couleur}
            strokeWidth="6"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - v / 100)}
            style={{ transition: "stroke-dashoffset .6s, stroke .3s", filter: `drop-shadow(0 0 4px ${couleur})` }}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="font-display text-xl font-bold">{Math.round(v)}<span className="text-xs text-doux">%</span></div>
          </div>
        </div>
      </div>
      <div className="text-center">
        <div className="titre-hud text-[10px] text-hud">{libelle}</div>
        {detail && <div className="mt-0.5 font-mono text-[11px] text-doux">{detail}</div>}
      </div>
    </div>
  );
}
