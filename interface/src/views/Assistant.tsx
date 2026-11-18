import {
  AlertTriangle,
  ArrowUp,
  Check,
  ChevronRight,
  Info,
  Loader2,
  Mic,
  RotateCcw,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { micro } from "../audio/micro";
import { stopTout } from "../audio/voix";
import { Markdown } from "../components/Markdown";
import { Reacteur } from "../components/Reacteur";
import { Badge, BoutonIcone, Panneau } from "../components/ui";
import { VuMetre } from "../components/VuMetre";
import { cx, heure, nomOutil } from "../lib/format";
import type { BlocOutil, Message, MessageJarvis } from "../lib/types";
import { useAudio } from "../stores/audio";
import { envoyer, nouvelleConversation, useJarvis } from "../stores/jarvis";
import { useReglages } from "../stores/reglages";
import { useSysteme } from "../stores/systeme";

/* ---------------- statut global ---------------- */
export function useStatut(): { libelle: string; detail: string; ton: "hud" | "ambre" | "vert" } {
  const a = useAudio();
  const { occupe, outilEnCours } = useJarvis();
  const mode = useReglages((s) => s.mode);
  const [, force] = useState(0);
  useEffect(() => {
    if (a.eveilJusqua > Date.now()) {
      const t = setTimeout(() => force((x) => x + 1), a.eveilJusqua - Date.now() + 50);
      return () => clearTimeout(t);
    }
  }, [a.eveilJusqua]);

  if (a.vocalServeur === "eveil") return { libelle: "Écoute", detail: "Je t'écoute…", ton: "vert" };
  if (a.vocalServeur === "transcription") return { libelle: "Transcription", detail: "J'analyse ta voix…", ton: "hud" };
  if (a.enregistre) return { libelle: "Écoute", detail: mode === "ptt" ? "Relâche pour envoyer" : "J'envoie dès que tu te tais", ton: "vert" };
  if (a.transcrit) return { libelle: "Transcription", detail: "Whisper analyse ta voix…", ton: "hud" };
  if (outilEnCours) return { libelle: "Exécution", detail: nomOutil(outilEnCours), ton: "ambre" };
  if (occupe) return { libelle: "Analyse", detail: "Je réfléchis…", ton: "hud" };
  if (a.parle) return { libelle: "Transmission", detail: "Dis « Jarvis, stop » ou Échap pour couper", ton: "hud" };
  if (a.eveilJusqua > Date.now()) return { libelle: "À vos ordres", detail: "Je t'écoute…", ton: "vert" };
  if (!a.micActif) return { libelle: "En veille", detail: "Micro coupé — tape ta demande", ton: "hud" };
  if (mode === "eveil") return { libelle: "En attente", detail: a.ecouteFond ? "Dis « Jarvis, … »" : "Dis « Jarvis, … »", ton: "hud" };
  if (mode === "auto") return { libelle: "À l'écoute", detail: "Parle quand tu veux", ton: "hud" };
  return { libelle: "En veille", detail: "Maintiens Espace pour parler", ton: "hud" };
}

function Statut({ grand, gauche }: { grand?: boolean; gauche?: boolean }) {
  const s = useStatut();
  return (
    <div className={cx(gauche ? "text-left" : "text-center", grand ? "space-y-2" : "space-y-0.5")}>
      <div
        className={cx(
          "titre-hud font-bold",
          grand ? "text-sm tracking-[0.45em]" : "text-[11px]",
          s.ton === "ambre" ? "text-ambre" : s.ton === "vert" ? "text-vert" : "text-hud",
        )}
        style={{ textShadow: "0 0 14px currentColor" }}
      >
        {s.libelle}
      </div>
      <div className={cx("text-doux", grand ? "text-sm" : "truncate text-xs")}>{s.detail}</div>
    </div>
  );
}

/* ---------------- messages ---------------- */
function CarteOutil({ b }: { b: BlocOutil }) {
  const [ouvert, setOuvert] = useState(false);
  const enCours = b.resultat === null;
  const args = Object.entries(b.args);
  const apercu = args.map(([k, v]) => `${k}: ${v}`).join(" · ");
  const ms = b.fin && b.debut ? b.fin - b.debut : null;
  return (
    <div className={cx("overflow-hidden rounded-md border text-sm", b.erreur ? "border-rouge/30 bg-rouge/[0.04]" : enCours ? "border-ambre/40 bg-ambre/[0.05]" : "border-ligne bg-white/[0.015]")}>
      <button onClick={() => setOuvert(!ouvert)} className="flex w-full items-center gap-2.5 px-3 py-2 text-left" aria-expanded={ouvert}>
        <span className="grid size-5 flex-none place-items-center">
          {enCours ? (
            <Loader2 className="size-4 animate-spin text-ambre" />
          ) : b.erreur ? (
            <X className="size-4 text-rouge" />
          ) : (
            <Check className="size-4 text-vert" />
          )}
        </span>
        <span className="font-mono text-[13px] font-medium text-ambre">{b.nom}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-tres-doux">{apercu}</span>
        {ms !== null && <span className="font-mono text-[11px] text-tres-doux">{ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`}</span>}
        <ChevronRight className={cx("size-4 flex-none text-tres-doux transition-transform", ouvert && "rotate-90")} />
      </button>
      {enCours && <div className="relative h-px overflow-hidden bg-ambre/10"><div className="absolute inset-y-0 w-1/3 animate-balayage bg-ambre" /></div>}
      {ouvert && (
        <div className="space-y-3 border-t border-ligne px-3 py-3">
          {args.length > 0 && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-xs">
              {args.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-doux">{k}</dt>
                  <dd className="break-all whitespace-pre-wrap text-texte">{v}</dd>
                </div>
              ))}
            </dl>
          )}
          {b.resultat !== null && (
            <pre className="max-h-64 overflow-auto rounded bg-black/40 p-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap text-doux">{b.resultat || "(vide)"}</pre>
          )}
        </div>
      )}
    </div>
  );
}

function Pensee({ texte }: { texte: string }) {
  const [ouvert, setOuvert] = useState(false);
  return (
    <div className="text-sm">
      <button onClick={() => setOuvert(!ouvert)} className="flex items-center gap-1.5 text-doux hover:text-texte">
        <Sparkles className="size-3.5" /> Réflexion
        <ChevronRight className={cx("size-3.5 transition-transform", ouvert && "rotate-90")} />
      </button>
      {ouvert && <p className="mt-2 border-l border-ligne-forte pl-3 text-[13px] whitespace-pre-wrap text-doux italic">{texte}</p>}
    </div>
  );
}

function Points() {
  return (
    <span className="inline-flex gap-1 py-2" aria-label="Jarvis écrit">
      {[0, 1, 2].map((i) => (
        <span key={i} className="size-1.5 animate-pulse rounded-full bg-hud" style={{ animationDelay: `${i * 0.2}s` }} />
      ))}
    </span>
  );
}

function ReponseJarvis({ m }: { m: MessageJarvis }) {
  const dernier = m.blocs[m.blocs.length - 1];
  return (
    <div className="flex animate-entree gap-3">
      <div className="mt-0.5 grid size-8 flex-none place-items-center rounded-full border border-hud/50 bg-hud/10 shadow-glow">
        <span className="size-2.5 rounded-full bg-hud shadow-[0_0_8px] shadow-hud" />
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex items-baseline gap-2">
          <span className="titre-hud text-[11px] font-bold text-hud">Jarvis</span>
          <span className="text-[11px] text-tres-doux">{heure(m.date)}</span>
        </div>
        {m.blocs.map((b, i) =>
          b.type === "texte" ? (
            <Markdown key={i} texte={b.texte} />
          ) : b.type === "pensee" ? (
            <Pensee key={i} texte={b.texte} />
          ) : (
            <CarteOutil key={b.id ?? i} b={b} />
          ),
        )}
        {m.enCours && (!dernier || dernier.type !== "texte") && <Points />}
      </div>
    </div>
  );
}

function LigneMessage({ m }: { m: Message }) {
  if (m.role === "user")
    return (
      <div className="flex animate-entree justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm border border-hud/25 bg-hud/10 px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-hud-clair">
          {m.texte}
        </div>
      </div>
    );
  if (m.role === "jarvis") return <ReponseJarvis m={m} />;
  return (
    <div className={cx("flex animate-entree items-center justify-center gap-2 text-center text-[13px]", m.role === "erreur" ? "text-rouge" : "text-doux")}>
      {m.role === "erreur" ? <AlertTriangle className="size-4" /> : <Info className="size-4" />}
      {m.texte}
    </div>
  );
}

/* ---------------- saisie ---------------- */
function BoutonMicro() {
  const { micActif, enregistre, transcrit } = useAudio();
  const mode = useReglages((s) => s.mode);
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <button
      ref={ref}
      aria-label={enregistre ? "Arrêter l'écoute" : "Parler"}
      title={mode === "ptt" ? "Maintiens pour parler (ou Espace)" : "Clique pour parler"}
      disabled={!micActif}
      onPointerDown={(e) => {
        e.preventDefault();
        ref.current?.setPointerCapture(e.pointerId);
        if (mode === "ptt") micro.debutEnregistrement();
        else if (enregistre) micro.finEnregistrement();
        else micro.debutEnregistrement();
      }}
      onPointerUp={() => mode === "ptt" && micro.finEnregistrement()}
      onPointerCancel={() => mode === "ptt" && micro.finEnregistrement()}
      className={cx(
        "grid size-11 flex-none touch-none place-items-center rounded-full border-2 transition-all disabled:opacity-30",
        enregistre
          ? "animate-pulse-rouge border-rouge bg-rouge/30 text-white"
          : "border-hud/70 bg-hud/10 text-hud hover:bg-hud/20 hover:shadow-glow",
      )}
    >
      {transcrit ? <Loader2 className="size-5 animate-spin" /> : <Mic className="size-5" />}
    </button>
  );
}

function Saisie() {
  const [texte, setTexte] = useState("");
  const occupe = useJarvis((s) => s.occupe);
  const parle = useAudio((s) => s.parle);
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const t = ref.current!;
    t.style.height = "0";
    t.style.height = Math.min(200, t.scrollHeight) + "px";
  }, [texte]);

  useEffect(() => {
    const f = (e: Event) => {
      setTexte((e as CustomEvent<string>).detail);
      ref.current?.focus();
    };
    window.addEventListener("jarvis:pre-remplir", f);
    return () => window.removeEventListener("jarvis:pre-remplir", f);
  }, []);

  const valider = () => {
    if (envoyer(texte)) setTexte("");
  };

  return (
    <div className="coins flex items-end gap-2 rounded-lg border border-ligne-forte bg-surface-2/90 p-2 shadow-[0_8px_40px_rgb(0_0_0/.4)] backdrop-blur focus-within:border-hud/70">
      <BoutonMicro />
      <textarea
        id="saisie"
        ref={ref}
        rows={1}
        value={texte}
        onChange={(e) => setTexte(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            valider();
          }
        }}
        placeholder="Demande-moi n'importe quoi…"
        className="max-h-[200px] min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-relaxed outline-none placeholder:text-tres-doux"
      />
      {occupe || parle ? (
        <button onClick={stopTout} aria-label="Stop" title="Stop (Échap)" className="grid size-11 flex-none place-items-center rounded-full border border-rouge/60 bg-rouge/10 text-rouge hover:bg-rouge/20">
          <Square className="size-4 fill-current" />
        </button>
      ) : (
        <button
          onClick={valider}
          disabled={!texte.trim()}
          aria-label="Envoyer"
          className="grid size-11 flex-none place-items-center rounded-full bg-hud text-fond shadow-glow transition-all hover:bg-hud-clair disabled:bg-surface-3 disabled:text-tres-doux disabled:shadow-none"
        >
          <ArrowUp className="size-5" />
        </button>
      )}
    </div>
  );
}

/* ---------------- panneau latéral ---------------- */
function Rail() {
  const messages = useJarvis((s) => s.messages);
  const { nomMicro, micActif, derniereTranscription } = useAudio();
  const outils = useMemo(
    () => messages.flatMap((m) => (m.role === "jarvis" ? m.blocs.filter((b): b is BlocOutil => b.type === "outil") : [])).reverse(),
    [messages],
  );
  return (
    <aside className="flex w-[330px] flex-none flex-col gap-4 overflow-y-auto border-l border-ligne bg-surface/40 p-4 max-xl:hidden">
      <div className="relative">
        <Reacteur className="aspect-square w-full" />
      </div>
      <Statut grand />
      <Panneau titre="Audio" corpsClassName="space-y-2.5">
        <div className="truncate text-xs text-doux">{micActif ? nomMicro : "Micro inactif"}</div>
        <VuMetre />
        {derniereTranscription && (
          <p className="text-[13px] text-doux">
            <span className="text-tres-doux">Entendu : </span>« {derniereTranscription} »
          </p>
        )}
      </Panneau>
      <Panneau titre="Actions de la session" actions={<Badge ton="doux">{outils.length}</Badge>} className="min-h-[200px] flex-1" corpsClassName="overflow-y-auto p-0">
        {outils.length === 0 ? (
          <p className="p-4 text-center text-sm text-tres-doux">Aucune action pour l'instant.</p>
        ) : (
          <ul className="divide-y divide-ligne">
            {outils.map((o, i) => (
              <li key={o.id ?? i} className="flex items-center gap-2.5 px-4 py-2">
                {o.resultat === null ? <Loader2 className="size-3.5 animate-spin text-ambre" /> : o.erreur ? <X className="size-3.5 text-rouge" /> : <Check className="size-3.5 text-vert" />}
                <span className="truncate font-mono text-xs">{o.nom}</span>
                {o.debut && <span className="ml-auto font-mono text-[11px] text-tres-doux">{heure(o.debut)}</span>}
              </li>
            ))}
          </ul>
        )}
      </Panneau>
    </aside>
  );
}

/* ---------------- vue ---------------- */
const SUGGESTIONS = [
  "Ouvre mon dernier projet dans VS Code",
  "Quelle météo aujourd'hui ?",
  "Qu'est-ce qui consomme le plus de mémoire ?",
  "Fais une capture et dis-moi ce que tu vois",
  "Résume les actus tech du jour",
  "Crée un projet Vite React dans Documents",
];

function BandeauCle() {
  const manque = useSysteme((s) => s.dernier?.cle_claude_manquante);
  const maj = useReglages((s) => s.maj);
  if (!manque) return null;
  return (
    <button
      onClick={() => maj({ vue: "reglages" })}
      className="mb-6 w-full max-w-2xl rounded-md border border-ambre/50 bg-ambre/10 px-4 py-3 text-left text-sm text-ambre hover:bg-ambre/15"
    >
      <strong>Bienvenue sur ce PC !</strong> Ajoute ta clé API Claude pour que Jarvis puisse réfléchir : Réglages › Cerveau.
      <span className="mt-1 block text-[13px] text-doux">Ta mémoire et tes connecteurs sont déjà là grâce à OneDrive. Les mots de passe des connecteurs sont à ressaisir une fois sur ce PC.</span>
    </button>
  );
}

function Accueil() {
  const nom = useJarvis((s) => s.session?.nom ?? "");
  const h = new Date().getHours();
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-4 py-8">
      <div className="xl:hidden">
        <Reacteur className="aspect-square w-[min(340px,70vw)]" />
        <Statut grand />
      </div>
      <BandeauCle />
      <h2 className="mt-8 text-center text-2xl font-semibold xl:mt-0 xl:text-3xl">
        {h < 5 || h >= 18 ? "Bonsoir" : "Bonjour"} {nom}.
      </h2>
      <p className="mt-2 text-center text-doux">Tous les systèmes sont opérationnels. Que puis-je faire pour vous ?</p>
      <div className="mt-8 grid w-full max-w-2xl gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => envoyer(s)}
            className="rounded-md border border-ligne bg-surface-2/60 px-4 py-3 text-left text-sm text-doux transition-colors hover:border-hud/50 hover:bg-hud/5 hover:text-texte"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function EnTeteConversation({ children }: { children?: ReactNode }) {
  return (
    <div className="flex h-14 flex-none items-center gap-3 border-b border-ligne px-4 md:px-6">
      <div className="xl:hidden">
        <Reacteur className="size-11" />
      </div>
      <div className="min-w-0 xl:hidden">
        <Statut gauche />
      </div>
      <span className="titre-hud text-[11px] text-doux max-xl:hidden">Conversation en cours</span>
      <div className="ml-auto flex items-center gap-1">{children}</div>
    </div>
  );
}

export function VueAssistant() {
  const messages = useJarvis((s) => s.messages);
  const fil = useRef<HTMLDivElement>(null);
  const colle = useRef(true);

  useLayoutEffect(() => {
    const f = fil.current;
    if (f && colle.current) f.scrollTop = f.scrollHeight;
  }, [messages]);

  const vide = messages.length === 0;
  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        {!vide && (
          <EnTeteConversation>
            <BoutonIcone label="Nouvelle conversation" onClick={nouvelleConversation}>
              <RotateCcw className="size-4" />
            </BoutonIcone>
          </EnTeteConversation>
        )}
        <div
          ref={fil}
          onScroll={(e) => {
            const f = e.currentTarget;
            colle.current = f.scrollHeight - f.scrollTop - f.clientHeight < 80;
          }}
          className="min-h-0 flex-1 overflow-y-auto"
        >
          {vide ? (
            <Accueil />
          ) : (
            <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 md:px-6">
              {messages.map((m) => (
                <LigneMessage key={m.id} m={m} />
              ))}
            </div>
          )}
        </div>
        <div className="mx-auto w-full max-w-3xl px-4 pt-2 pb-4 md:px-6">
          <Saisie />
          <p className="mt-2 text-center text-[11px] text-tres-doux max-sm:hidden">
            Entrée pour envoyer · Maj+Entrée nouvelle ligne · Espace maintenu pour parler · Échap pour stopper
          </p>
        </div>
      </div>
      <Rail />
    </div>
  );
}
