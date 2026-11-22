import { t } from "../lib/i18n";
import { Power } from "lucide-react";
import { useEffect, useState } from "react";
import { cx } from "../lib/format";

const ETAPES = [
  "Liaison avec le noyau local",
  "Chargement des modules d'action",
  "Mémoire à long terme",
  "Capteurs audio",
  "Synthèse vocale",
  "Interface holographique",
];

/**
 * Écran d'allumage. Le clic est nécessaire : le navigateur n'autorise l'audio
 * (micro, sons, voix) qu'après une action de l'utilisateur.
 */
export function Demarrage({ pret, erreur, nbOutils, onDemarrer }: { pret: boolean; erreur: string | null; nbOutils: number; onDemarrer: () => void }) {
  const [n, setN] = useState(0);
  const [sortie, setSortie] = useState(false);
  useEffect(() => {
    if (n < ETAPES.length) {
      const t = setTimeout(() => setN(n + 1), 170);
      return () => clearTimeout(t);
    }
  }, [n]);

  const lancer = () => {
    setSortie(true);
    setTimeout(onDemarrer, 380);
  };

  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Enter" && pret && n >= ETAPES.length && lancer();
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  });

  return (
    <div className={cx("grille-hud fixed inset-0 z-40 grid place-items-center bg-fond transition-opacity duration-400", sortie && "opacity-0")}>
      <div className="w-[min(520px,calc(100vw-32px))]">
        <h1 className="mb-10 text-center font-display text-[clamp(28px,7vw,48px)] font-black tracking-[0.45em] text-hud [text-shadow:0_0_26px_rgb(60_232_255/.6)]">
          {t("Wesley")}
        </h1>
        <ul className="space-y-1.5 font-mono text-[13px]">
          {ETAPES.slice(0, n).map((e, i) => (
            <li key={e} className="flex animate-entree justify-between border-b border-ligne pb-1.5 text-doux">
              <span>
                <span className="mr-2 text-hud">›</span>
                {i === 1 && nbOutils ? `${e} — ${nbOutils} outils` : e}
              </span>
              <span className={erreur && i === 0 ? "text-rouge" : "text-vert"}>{erreur && i === 0 ? "ÉCHEC" : "OK"}</span>
            </li>
          ))}
        </ul>
        {erreur ? (
          <p className="mt-8 rounded-md border border-rouge/40 bg-rouge/5 p-4 text-center text-sm text-rouge">
            {erreur}
            <br />
            <span className="text-doux">{t("Vérifie que wesley-web.bat tourne, puis recharge la page.")}</span>
          </p>
        ) : (
          <button
            onClick={lancer}
            disabled={!pret || n < ETAPES.length}
            className="group mx-auto mt-10 flex items-center gap-3 rounded-full border border-hud bg-hud/10 px-8 py-3.5 font-display text-sm tracking-[0.3em] text-hud shadow-glow transition-all hover:bg-hud/20 hover:shadow-glow-fort disabled:opacity-0"
          >
            <Power className="size-4" />
            {t("INITIALISER")}
          </button>
        )}
      </div>
    </div>
  );
}
