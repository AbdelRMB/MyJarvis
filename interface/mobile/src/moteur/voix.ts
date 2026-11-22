/**
 * Voix du téléphone : reconnaissance vocale et synthèse vocale du système (Android : Google ; iPhone : Siri),
 * en français ou en anglais selon la langue de l'interface. Rien à installer.
 */
import { LANGUE } from "../../../src/lib/i18n";
import { pourLaVoix } from "../../../src/lib/format";
import { reglagesTel } from "./stockage";

type Reco = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: any) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: any) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

const Classe = (): (new () => Reco) | undefined => (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
export const recoDisponible = () => !!Classe();
export const syntheseDisponible = () => "speechSynthesis" in window;

let reco: Reco | null = null;

/** Écoute une phrase. surTexte reçoit le texte au fil de l'eau ; la promesse donne le texte final ("" si rien). */
export function ecouter(surTexte: (t: string) => void): Promise<string> {
  const C = Classe();
  if (!C) return Promise.reject(new Error("La reconnaissance vocale n'est pas disponible dans ce navigateur (essaie Chrome sur Android ou Safari sur iPhone)."));
  arreterParole();
  reco?.abort();
  return new Promise((ok, ko) => {
    const r = new C();
    reco = r;
    r.lang = LANGUE === "en" ? "en-US" : "fr-FR";
    r.interimResults = true;
    r.continuous = false;
    let final = "";
    r.onresult = (e) => {
      final = Array.from(e.results as ArrayLike<any>)
        .map((x) => x[0].transcript)
        .join("");
      surTexte(final);
    };
    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") ko(new Error("Micro refusé : autorise-le dans les réglages du navigateur pour ce site."));
    };
    r.onend = () => {
      if (reco === r) reco = null;
      ok(final.trim());
    };
    r.start();
  });
}

export function arreterEcoute() {
  reco?.stop();
}
export const ecouteEnCours = () => !!reco;

// ---------- synthèse vocale ----------
let fin: (() => void) | null = null;

function voixChoisie() {
  const lang = LANGUE === "en" ? "en" : "fr";
  const v = speechSynthesis.getVoices().filter((x) => x.lang.toLowerCase().startsWith(lang));
  return v.find((x) => /premium|enhanced|neural|google/i.test(x.name)) || v.find((x) => x.localService) || v[0];
}

/** Lit un texte à voix haute (si la voix est activée). La promesse se termine quand il a fini de parler. */
export function parler(texte: string): Promise<void> {
  const t = pourLaVoix(texte);
  if (!t || !syntheseDisponible() || !reglagesTel().voix) return Promise.resolve();
  arreterParole();
  return new Promise((ok) => {
    // les longs textes sont coupés en phrases : certains téléphones arrêtent de parler au-delà de ~15 s
    const morceaux = t.match(/[^.!?\n]+[.!?]*\s*/g) || [t];
    let i = 0;
    fin = () => {
      fin = null;
      ok();
    };
    const suivant = () => {
      if (!fin) return;
      if (i >= morceaux.length) return fin();
      const u = new SpeechSynthesisUtterance(morceaux[i++].trim());
      u.lang = LANGUE === "en" ? "en-GB" : "fr-FR";
      const v = voixChoisie();
      if (v) u.voice = v;
      u.rate = reglagesTel().vitesse;
      u.onend = suivant;
      u.onerror = () => fin?.();
      speechSynthesis.speak(u);
    };
    suivant();
  });
}

export function arreterParole() {
  if (syntheseDisponible()) speechSynthesis.cancel();
  fin?.();
}
export const parleEnCours = () => syntheseDisponible() && speechSynthesis.speaking;

/** iOS n'autorise la voix qu'après un premier geste de l'utilisateur : on la « réveille » au premier toucher. */
export function debloquerVoix() {
  if (!syntheseDisponible()) return;
  const u = new SpeechSynthesisUtterance(" ");
  u.volume = 0;
  speechSynthesis.speak(u);
  speechSynthesis.getVoices();
}
