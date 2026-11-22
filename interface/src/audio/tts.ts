/**
 * Voix de Wesley.
 * La réponse est lue phrase par phrase PENDANT qu'elle s'écrit : dès qu'une phrase est complète,
 * elle part en synthèse (serveur : Microsoft neuronal ou Piper local) et joue dès qu'elle arrive,
 * pendant que les suivantes se préparent. Le navigateur sert de secours.
 */
import { api, getJeton } from "../lib/api";
import { pourLaVoix } from "../lib/format";
import { majAudio } from "../stores/audio";
import { reglages } from "../stores/reglages";
import { micro } from "./micro";

type Morceau = { texte: string; audio: Promise<Blob | null> };

let file: Morceau[] = [];
let tampon = "";
let generation = 0;
let enLecture = false;
let enCours = "";
/** Ce que Wesley est en train de dire (et va dire) : sert à reconnaître l'écho de sa propre voix dans le micro. */
export const texteEnCours = () => [enCours, ...file.map((m) => m.texte)].join(" ");
let lecteur: HTMLAudioElement | null = null;
let analyseur: AnalyserNode | null = null;
const donnees = new Uint8Array(256);

/* ---------- impulsion lue par le réacteur ---------- */
let impulsionNav = 0;
export function impulsionVoix() {
  if (analyseur && lecteur && !lecteur.paused) {
    analyseur.getByteTimeDomainData(donnees);
    let s = 0;
    for (let i = 0; i < donnees.length; i++) s += ((donnees[i] - 128) / 128) ** 2;
    return Math.min(0.6, Math.sqrt(s / donnees.length) * 3);
  }
  impulsionNav *= 0.9;
  return impulsionNav;
}

function getLecteur() {
  if (!lecteur) {
    lecteur = new Audio();
    lecteur.preload = "auto";
  }
  // branche le lecteur sur un analyseur pour animer le réacteur (une seule fois par élément)
  if (!analyseur && micro.ctx) {
    try {
      const src = micro.ctx.createMediaElementSource(lecteur);
      analyseur = micro.ctx.createAnalyser();
      analyseur.fftSize = 512;
      src.connect(analyseur);
      analyseur.connect(micro.ctx.destination);
    } catch {
      /* pas d'analyse, la lecture fonctionne quand même */
    }
  }
  return lecteur;
}

/* ---------- voix du navigateur (secours) ---------- */
export function chargerVoix() {
  if (!("speechSynthesis" in window)) return;
  const langue = reglages().langue || "fr";
  const voix = speechSynthesis
    .getVoices()
    .map((v) => ({ uri: v.voiceURI, nom: v.name, lang: v.lang, locale: v.localService }))
    .sort((a, b) => Number(b.lang.startsWith(langue)) - Number(a.lang.startsWith(langue)) || a.nom.localeCompare(b.nom));
  majAudio({ voix });
  if (!reglages().voix && voix.length) {
    const fr = voix.find((v) => /^fr/i.test(v.lang) && /natural|henri|paul|claude/i.test(v.nom)) ?? voix.find((v) => /^fr/i.test(v.lang));
    if (fr) reglages().maj({ voix: fr.uri });
  }
}
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = chargerVoix;

function direNavigateur(texte: string) {
  return new Promise<void>((fin) => {
    if (!("speechSynthesis" in window)) return fin();
    const r = reglages();
    const u = new SpeechSynthesisUtterance(texte);
    const v = speechSynthesis.getVoices().find((x) => x.voiceURI === r.voix);
    if (v) {
      u.voice = v;
      u.lang = v.lang;
    } else u.lang = "fr-FR";
    u.rate = r.debit;
    u.pitch = r.hauteur;
    u.volume = r.volume;
    u.onboundary = () => {
      impulsionNav = 0.35;
    };
    u.onend = u.onerror = () => fin();
    speechSynthesis.speak(u);
  });
}

/* ---------- synthèse serveur ---------- */
async function synthetiser(texte: string): Promise<Blob | null> {
  const r = reglages();
  if (r.ttsMoteur === "navigateur") return null;
  try {
    const rep = await fetch("/api/tts", {
      method: "POST",
      headers: { "content-type": "application/json", "x-jeton": getJeton() },
      body: JSON.stringify({
        texte,
        moteur: r.ttsMoteur,
        voix: r.ttsMoteur === "edge" ? r.ttsVoixEdge : r.ttsMoteur === "kyutai" ? r.ttsVoixKyutai : r.ttsVoixPiper,
        debit: r.debit,
      }),
    });
    if (!rep.ok) throw new Error(String(rep.status));
    return await rep.blob();
  } catch {
    return null; // secours : voix du navigateur
  }
}

async function jouerSuivant(gen: number) {
  if (gen !== generation) return;
  const m = file.shift();
  if (!m) {
    enLecture = false;
    majAudio({ parle: false });
    return;
  }
  enLecture = true;
  enCours = m.texte;
  majAudio({ parle: true });
  const blob = await m.audio;
  if (gen !== generation) return;
  if (!blob) {
    await direNavigateur(m.texte);
    return jouerSuivant(gen);
  }
  const l = getLecteur();
  const url = URL.createObjectURL(blob);
  l.src = url;
  l.volume = reglages().volume;
  l.onended = l.onerror = () => {
    URL.revokeObjectURL(url);
    jouerSuivant(gen);
  };
  try {
    await l.play();
  } catch {
    URL.revokeObjectURL(url);
    jouerSuivant(gen);
  }
}

function ajouterPhrase(brut: string) {
  const texte = pourLaVoix(brut).replace(/\s+/g, " ").trim();
  if (!/[\p{L}\d]/u.test(texte)) return;
  file.push({ texte, audio: synthetiser(texte) }); // la synthèse démarre tout de suite, en parallèle
  if (!enLecture) jouerSuivant(generation);
}

/** Coupe le tampon en phrases complètes, sans jamais couper à l'intérieur d'un bloc de code. */
function decouper(final: boolean) {
  const fin = /[.!?…]+["»)]?(?=\s)|\n\s*\n|:\s*\n|\n(?=\s*(?:[-*•]|\d+[.)])\s)/g;
  let debut = 0;
  for (const m of tampon.matchAll(fin)) {
    const pos = m.index! + m[0].length;
    const blocs = (tampon.slice(0, pos).match(/```/g) ?? []).length;
    if (blocs % 2 === 1) continue; // on est dans un bloc de code : on attend sa fermeture
    if (pos - debut < 12 && !/\n/.test(m[0])) continue; // trop court (« M. », « 1. ») : on regroupe
    ajouterPhrase(tampon.slice(debut, pos));
    debut = pos;
  }
  tampon = tampon.slice(debut);
  if (final) {
    if ((tampon.match(/```/g) ?? []).length % 2 === 1) tampon += "\n```";
    ajouterPhrase(tampon);
    tampon = "";
  }
}

/* ---------- API publique ---------- */
export function recevoirFlux(t: string) {
  if (!reglages().tts) return;
  tampon += t;
  decouper(false);
}

export function finirFlux() {
  if (!reglages().tts) {
    tampon = "";
    return;
  }
  decouper(true);
}

export function taire() {
  generation++;
  file = [];
  tampon = "";
  enLecture = false;
  if (lecteur) {
    lecteur.onended = lecteur.onerror = null;
    lecteur.pause();
  }
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  majAudio({ parle: false });
}

export function parler(texte: string, force = false) {
  if (!texte || (!reglages().tts && !force)) return;
  taire();
  tampon = texte;
  decouper(true);
}

export type VoixServeur = { edge: { id: string; nom: string }[]; piper: { id: string; nom: string }[]; kyutai?: { id: string; nom: string }[] };
export const listerVoixServeur = () => api<VoixServeur>("/api/tts/voix");
