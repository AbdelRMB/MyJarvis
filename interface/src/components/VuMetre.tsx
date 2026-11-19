import { t } from "../lib/i18n";
import { useEffect, useRef } from "react";
import { micro } from "../audio/micro";
import { cx } from "../lib/format";
import { useAudio } from "../stores/audio";
import { useReglages } from "../stores/reglages";

const MAX = 0.3;
const echelle = (v: number) => Math.min(1, Math.sqrt(v / MAX)); // échelle perceptive

/** VU-mètre segmenté + ligne de seuil de détection (orange). */
export function VuMetre({ className, segments = 40 }: { className?: string; segments?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const seuil = useReglages((s) => s.seuil);

  useEffect(() => {
    const cv = ref.current!;
    const g = cv.getContext("2d")!;
    let raf = 0;
    let pic = 0;
    let derniere = 0;
    let vide = false;
    const image = (t: number) => {
      raf = requestAnimationFrame(image);
      if (t - derniere < 33) return;
      derniere = t;
      const actifMic = useAudio.getState().micActif;
      if (!actifMic && vide) return;
      vide = !actifMic;
      const r = cv.getBoundingClientRect();
      const dpr = devicePixelRatio || 1;
      if (cv.width !== Math.round(r.width * dpr)) {
        cv.width = Math.round(r.width * dpr);
        cv.height = Math.round(r.height * dpr);
      }
      const W = cv.width;
      const H = cv.height;
      g.clearRect(0, 0, W, H);
      const actif = useAudio.getState().micActif;
      const s = echelle(useReglages.getState().seuil);
      const v = actif ? echelle(micro.niveau) : 0;
      pic = Math.max(v, pic - 0.008);
      const l = W / segments;
      for (let i = 0; i < segments; i++) {
        const f = (i + 0.5) / segments;
        g.fillStyle =
          f < v ? (f > 0.88 ? "#ff5468" : f > s ? "#3ce8ff" : "rgba(60,232,255,.42)") : "rgba(60,232,255,.08)";
        g.fillRect(i * l + dpr, H * 0.2, l - 2 * dpr, H * 0.6);
      }
      if (pic > 0.02) {
        g.fillStyle = "rgba(168,245,255,.9)";
        g.fillRect(Math.min(W - 2 * dpr, pic * W), H * 0.12, 2 * dpr, H * 0.76);
      }
    };
    raf = requestAnimationFrame(image);
    return () => cancelAnimationFrame(raf);
  }, [segments]);

  return (
    <div className={cx("relative h-9 overflow-hidden rounded border border-ligne bg-hud/[0.03]", className)}>
      <canvas ref={ref} className="block size-full" />
      <div
        className="absolute inset-y-0 w-0.5 bg-ambre shadow-[0_0_8px] shadow-ambre"
        style={{ left: `${echelle(seuil) * 100}%` }}
        title={t("Seuil de détection")}
      />
    </div>
  );
}
