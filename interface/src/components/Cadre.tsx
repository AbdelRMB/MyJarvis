import { Cloche } from "./Notifications";
import { t } from "../lib/i18n";
import {
  Activity,
  Brain,
  ChevronsLeft,
  ChevronsRight,
  Cpu,
  Download,
  History,
  MessageSquare,
  Mic,
  MicOff,
  Plug,
  Settings,
  Volume2,
  VolumeX,
  Wrench,
  Zap,
  ListTodo,
} from "lucide-react";
import { useEffect, useState } from "react";
import { micro } from "../audio/micro";
import { sons } from "../audio/bips";
import { taire } from "../audio/tts";
import { cx } from "../lib/format";
import { useAudio } from "../stores/audio";
import { useJarvis } from "../stores/jarvis";
import { useReglages, type ModeMicro, type Vue } from "../stores/reglages";
import { useSysteme } from "../stores/systeme";
import { useToasts } from "../stores/toasts";
import { Pastille } from "./ui";

const NAV: { id: Vue; libelle: string; icone: typeof Activity }[] = [
  { id: "assistant", libelle: t("Assistant"), icone: MessageSquare },
  { id: "historique", libelle: t("Historique"), icone: History },
  { id: "memoire", libelle: t("Mémoire"), icone: Brain },
  { id: "connecteurs", libelle: t("Connecteurs"), icone: Plug },
  { id: "taches", libelle: t("Tâches"), icone: ListTodo },
  { id: "automatisations", libelle: t("Automatisations"), icone: Zap },
  { id: "activite", libelle: t("Activité"), icone: Activity },
  { id: "arsenal", libelle: t("Arsenal"), icone: Wrench },
  { id: "systeme", libelle: t("Système"), icone: Cpu },
  { id: "reglages", libelle: t("Réglages"), icone: Settings },
  { id: "majs", libelle: t("Mises à jour"), icone: Download },
];

function MiniReacteur({ actif }: { actif: boolean }) {
  return (
    <svg viewBox="0 0 40 40" className={cx("size-9 flex-none", actif && "animate-spin [animation-duration:3s]")} aria-hidden>
      <circle cx="20" cy="20" r="17" fill="none" stroke="var(--color-hud)" strokeWidth="1.5" strokeDasharray="20 6.7" opacity=".8" />
      <circle cx="20" cy="20" r="12" fill="none" stroke="var(--color-hud)" strokeWidth="3" strokeDasharray="4 2.3" opacity=".5" />
      <circle cx="20" cy="20" r="6" fill="var(--color-hud)" style={{ filter: "drop-shadow(0 0 5px var(--color-hud))" }} />
    </svg>
  );
}

export function BarreLaterale() {
  const { vue, menuReduit, maj } = useReglages();
  const connecte = useJarvis((s) => s.connecte);
  const occupe = useJarvis((s) => s.occupe);
  const nom = useJarvis((s) => s.session?.nom ?? "");
  const ollama = useSysteme((s) => s.dernier?.ollama ?? false);
  const micActif = useAudio((s) => s.micActif);

  return (
    <nav
      className={cx(
        "flex flex-none flex-col border-r border-ligne bg-surface/80 transition-[width] duration-200 max-md:hidden",
        menuReduit ? "w-[68px]" : "w-[232px]",
      )}
    >
      <div className={cx("flex h-16 items-center gap-3 border-b border-ligne", menuReduit ? "justify-center" : "px-4")}>
        <MiniReacteur actif={occupe} />
        {!menuReduit && (
          <div className="min-w-0">
            <div className="font-display text-[15px] font-black tracking-[0.3em] text-hud [text-shadow:0_0_14px_rgb(60_232_255/.5)]">{t("JARVIS")}</div>
            <div className="truncate text-[10px] tracking-wider text-tres-doux">{t("ASSISTANT PERSONNEL")}</div>
          </div>
        )}
      </div>

      <ul className="flex-1 space-y-1 p-2.5">
        {NAV.map(({ id, libelle, icone: I }) => (
          <li key={id}>
            <button
              onClick={() => maj({ vue: id })}
              title={libelle}
              className={cx(
                "group relative flex h-10 w-full items-center gap-3 rounded-md text-sm transition-colors",
                menuReduit ? "justify-center" : "px-3",
                vue === id ? "bg-hud/12 text-hud" : "text-doux hover:bg-white/[0.04] hover:text-texte",
              )}
            >
              {vue === id && <span className="absolute inset-y-2 left-0 w-0.5 rounded bg-hud shadow-glow" />}
              <I className="size-[18px] flex-none" />
              {!menuReduit && libelle}
            </button>
          </li>
        ))}
      </ul>

      <div className={cx("space-y-2 border-t border-ligne p-4", menuReduit && "flex flex-col items-center px-2")}>
        {menuReduit ? (
          <div className="flex flex-col gap-2" title={`Liaison ${connecte ? "OK" : "coupée"} · Ollama ${ollama ? "OK" : "arrêté"} · Micro ${micActif ? "actif" : "inactif"}`}>
            {[connecte, ollama, micActif].map((ok, i) => (
              <span key={i} className={cx("size-2 rounded-full", ok ? "bg-vert" : "bg-rouge")} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Pastille ok={connecte}>{t("Liaison serveur")}</Pastille>
            <Pastille ok={ollama}>{t("Ollama")}</Pastille>
            <Pastille ok={micActif}>{t("Micro")}</Pastille>
            {nom && <div className="pt-1 text-xs text-tres-doux">{t("Connecté en tant que ")}<span className="text-doux">{nom}</span></div>}
          </div>
        )}
        <button
          onClick={() => maj({ menuReduit: !menuReduit })}
          className="mt-1 flex items-center gap-2 text-xs text-tres-doux hover:text-doux"
          aria-label={menuReduit ? "Déplier le menu" : "Replier le menu"}
        >
          {menuReduit ? <ChevronsRight className="size-4" /> : <><ChevronsLeft className="size-4" />{t(" Replier")}</>}
        </button>
      </div>
    </nav>
  );
}

/** Navigation basse sur mobile. */
export function NavMobile() {
  const { vue, maj } = useReglages();
  return (
    <nav className="flex border-t border-ligne bg-surface md:hidden">
      {NAV.filter((n) => n.id !== "arsenal" && n.id !== "activite").map(({ id, libelle, icone: I }) => (
        <button
          key={id}
          onClick={() => maj({ vue: id })}
          className={cx("flex flex-1 flex-col items-center gap-1 py-2 text-[10px]", vue === id ? "text-hud" : "text-doux")}
        >
          <I className="size-5" />
          {libelle}
        </button>
      ))}
    </nav>
  );
}

const MODES: { id: ModeMicro; libelle: string; aide: string }[] = [
  { id: "ptt", libelle: t("Appui"), aide: t("Maintiens Espace ou le bouton micro pour parler") },
  { id: "auto", libelle: t("Auto"), aide: t("Mains libres : ta phrase part quand tu te tais") },
  { id: "eveil", libelle: t("« Jarvis »"), aide: t("Ne réagit qu'aux phrases qui commencent par « Jarvis »") },
];

export function BarreHaut() {
  const { mode, tts, maj } = useReglages();
  const micActif = useAudio((s) => s.micActif);
  const modele = useSysteme((s) => s.dernier?.modele);
  const [h, setH] = useState(new Date());
  useEffect(() => {
    const i = setInterval(() => setH(new Date()), 1000);
    return () => clearInterval(i);
  }, []);

  return (
    <header className="flex h-16 flex-none items-center gap-3 border-b border-ligne bg-surface/50 px-4 backdrop-blur md:px-6">
      <div className="flex items-center rounded-md border border-ligne bg-surface-2 p-0.5" role="radiogroup" aria-label={t("Mode du micro")}>
        {MODES.map((m) => (
          <button
            key={m.id}
            role="radio"
            aria-checked={mode === m.id}
            title={m.aide}
            onClick={() => {
              maj({ mode: m.id });
              sons.clic();
            }}
            className={cx(
              "h-8 rounded px-3 text-[13px] transition-colors",
              mode === m.id ? "bg-hud/15 text-hud" : "text-doux hover:text-texte",
            )}
          >
            {m.libelle}
          </button>
        ))}
      </div>
      <button
        onClick={() => (micActif ? micro.arreter() : micro.demarrer())}
        title={micActif ? "Couper le micro" : "Activer le micro"}
        className={cx("grid size-9 place-items-center rounded-md border", micActif ? "border-ligne text-hud" : "border-rouge/40 text-rouge")}
      >
        {micActif ? <Mic className="size-4" /> : <MicOff className="size-4" />}
      </button>
      <button
        onClick={() => {
          if (tts) taire();
          maj({ tts: !tts });
        }}
        title={tts ? "Couper la voix de Jarvis" : "Activer la voix de Jarvis"}
        className={cx("grid size-9 place-items-center rounded-md border border-ligne", tts ? "text-hud" : "text-tres-doux")}
      >
        {tts ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
      </button>

      <div className="ml-auto flex items-center gap-5">
        <Cloche />
        {modele && (
          <span className="hidden items-center gap-2 rounded-md border border-ligne px-2.5 py-1 font-mono text-xs text-doux lg:flex">
            <Brain className="size-3.5 text-hud" />
            {modele}
          </span>
        )}
        <div className="text-right max-sm:hidden">
          <div className="font-display text-lg leading-none tracking-wider text-hud-clair">
            {h.toLocaleTimeString("fr-FR")}
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-widest text-tres-doux">
            {h.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
          </div>
        </div>
      </div>
    </header>
  );
}

export function Toasts() {
  const toasts = useToasts((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[min(380px,calc(100vw-32px))] flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={cx(
            "animate-entree rounded-md border bg-surface-2/95 px-4 py-3 text-sm shadow-xl backdrop-blur",
            t.genre === "erreur" ? "border-rouge/50 text-rouge" : t.genre === "succes" ? "border-vert/40 text-vert" : "border-ligne-forte text-texte",
          )}
        >
          {t.texte}
        </div>
      ))}
    </div>
  );
}
