import { useEffect, useRef } from "react";
import { micro } from "../audio/micro";
import { impulsionVoix } from "../audio/tts";
import { useAudio } from "../stores/audio";
import { useJarvis } from "../stores/jarvis";
import { useReglages } from "../stores/reglages";

/**
 * Réacteur arc animé au canvas. Lit l'état directement dans les stores à chaque image
 * (pas de re-rendu React) : réagit au micro, à la voix de Jarvis et à l'exécution d'outils.
 */
export function Reacteur({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current!;
    const g = cv.getContext("2d")!;
    let energie = 0.1;
    let rot = 0;
    let tPrec = performance.now();
    let raf = 0;

    let derniere = 0;
    let statiqueDessine = false;
    const image = (t: number) => {
      raf = requestAnimationFrame(image);
      // La carte graphique sert aussi au modèle d'IA : chaque image dessinée lui vole du temps.
      // On limite donc la cadence, surtout pendant que Jarvis réfléchit (là où le GPU compte le plus).
      const anim = useReglages.getState().animations;
      const j0 = useJarvis.getState();
      const a0 = useAudio.getState();
      const travail = j0.occupe || !!j0.outilEnCours;
      const fps = anim === "aucunes" ? 2 : travail ? (anim === "completes" ? 20 : 8) : a0.enregistre || a0.parle ? 30 : anim === "completes" ? 60 : 24;
      if (t - derniere < 1000 / fps - 2) return;
      if (anim === "aucunes" && statiqueDessine && !a0.enregistre) return;
      statiqueDessine = anim === "aucunes";
      derniere = t;
      const lueur = anim === "completes" && !travail;
      const dt = Math.min(120, t - tPrec) / 1000;
      tPrec = t;
      const r = cv.getBoundingClientRect();
      if (!r.width) return;
      const dpr = Math.min(anim === "completes" ? 2 : 1.25, devicePixelRatio || 1);
      if (cv.width !== Math.round(r.width * dpr) || cv.height !== Math.round(r.height * dpr)) {
        cv.width = Math.round(r.width * dpr);
        cv.height = Math.round(r.height * dpr);
      }
      const a = useAudio.getState();
      const j = useJarvis.getState();
      const mode = useReglages.getState().mode;
      const W = cv.width;
      const H = cv.height;
      const cx = W / 2;
      const cy = H / 2;
      const R0 = Math.min(W, H) * 0.47;
      const niveau = micro.niveau;
      const ecouteLibre = a.micActif && mode !== "ptt";

      let cible = 0.08;
      if (a.enregistre) cible = 0.2 + Math.min(1, niveau * 9);
      else if (a.parle) cible = 0.35 + 0.3 * Math.abs(Math.sin(t / 110)) + impulsionVoix();
      else if (j.outilEnCours) cible = 0.6;
      else if (j.occupe || a.transcrit) cible = 0.4 + 0.1 * Math.sin(t / 200);
      else if (ecouteLibre) cible = 0.1 + Math.min(0.4, niveau * 5);
      energie += (cible - energie) * Math.min(1, dt * 9);

      const vitesse = j.outilEnCours ? 2.6 : j.occupe || a.transcrit ? 1.6 : a.enregistre ? 0.9 : 0.25;
      rot += dt * vitesse;
      const coul = j.outilEnCours ? "255,181,71" : a.enregistre ? "110,255,215" : "60,232,255";
      const c = (al: number) => `rgba(${coul},${al})`;

      g.clearRect(0, 0, W, H);

      // graduations
      g.save();
      g.translate(cx, cy);
      g.rotate(-rot * 0.15);
      for (let i = 0; i < 144; i++) {
        const an = (i / 144) * Math.PI * 2;
        const maj = i % 12 === 0;
        const long = maj ? 0.07 : i % 4 === 0 ? 0.04 : 0.02;
        g.strokeStyle = c(maj ? 0.75 : 0.25);
        g.lineWidth = (maj ? 2 : 1) * dpr;
        g.beginPath();
        g.moveTo(Math.cos(an) * R0, Math.sin(an) * R0);
        g.lineTo(Math.cos(an) * R0 * (1 - long), Math.sin(an) * R0 * (1 - long));
        g.stroke();
      }
      g.restore();

      // anneaux segmentés
      g.shadowColor = c(0.9);
      g.shadowBlur = lueur ? 10 * dpr : 0;
      const anneaux: [number, number, number, number, number][] = [
        [0.88, 3, 3, 0.5, 0.7],
        [0.8, 7, 8, -0.8, 0.45],
        [0.7, 4, 2, 1.3, 0.9],
        [0.62, 24, 5, -0.3, 0.35],
      ];
      for (const [rr, n, w, sp, al] of anneaux) {
        const trou = n > 10 ? 0.35 : 0.5;
        g.strokeStyle = c(al * (0.6 + energie * 0.5));
        g.lineWidth = w * dpr;
        for (let k = 0; k < n; k++) {
          const a0 = rot * sp + (k / n) * Math.PI * 2;
          g.beginPath();
          g.arc(cx, cy, R0 * rr, a0, a0 + ((Math.PI * 2) / n) * (1 - trou));
          g.stroke();
        }
      }

      // spectre
      const spectre = micro.analyseur && (a.enregistre || ecouteLibre) ? micro.frequences : null;
      if (spectre) micro.analyseur!.getByteFrequencyData(spectre);
      const nb = 64;
      const rb = R0 * 0.5;
      g.lineWidth = 2.2 * dpr;
      for (let i = 0; i < nb; i++) {
        const an = (i / nb) * Math.PI * 2 - Math.PI / 2;
        let v = spectre ? spectre[Math.floor(2 + (i < nb / 2 ? i : nb - i) * 1.6)] / 255 : 0;
        v = Math.max(v * (a.enregistre ? 1 : 0.6), energie * (0.25 + 0.25 * Math.sin(t / 160 + i * 0.7)));
        const l = R0 * (0.02 + v * 0.13);
        g.strokeStyle = c(0.35 + v * 0.6);
        g.beginPath();
        g.moveTo(cx + Math.cos(an) * rb, cy + Math.sin(an) * rb);
        g.lineTo(cx + Math.cos(an) * (rb + l), cy + Math.sin(an) * (rb + l));
        g.stroke();
      }

      // segments du réacteur
      const rIn = R0 * 0.3;
      const rOut = R0 * 0.44;
      g.save();
      g.translate(cx, cy);
      g.rotate(rot * 0.2);
      for (let k = 0; k < 10; k++) {
        const a0 = (k / 10) * Math.PI * 2 + 0.06;
        const a1 = ((k + 1) / 10) * Math.PI * 2 - 0.06;
        g.beginPath();
        g.arc(0, 0, rOut, a0, a1);
        g.arc(0, 0, rIn, a1, a0, true);
        g.closePath();
        g.fillStyle = c(0.08 + energie * 0.22);
        g.fill();
        g.strokeStyle = c(0.75);
        g.lineWidth = 1.2 * dpr;
        g.stroke();
      }
      g.restore();

      // cœur
      const rc = R0 * (0.2 + energie * 0.07);
      const grd = g.createRadialGradient(cx, cy, 0, cx, cy, rc * 1.9);
      grd.addColorStop(0, "rgba(255,255,255,.95)");
      grd.addColorStop(0.25, c(0.95));
      grd.addColorStop(0.55, c(0.35));
      grd.addColorStop(1, c(0));
      g.shadowBlur = lueur ? 40 * dpr : 0;
      g.fillStyle = grd;
      g.beginPath();
      g.arc(cx, cy, rc * 1.9, 0, Math.PI * 2);
      g.fill();
      g.shadowBlur = 0;
      g.strokeStyle = c(0.9);
      g.lineWidth = 2 * dpr;
      g.beginPath();
      g.arc(cx, cy, rc * 0.75, 0, Math.PI * 2);
      g.stroke();
    };
    raf = requestAnimationFrame(image);
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}
