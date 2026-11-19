import { t } from "../lib/i18n";
/**
 * Chaîne vocale : phrase captée → Whisper (serveur) → filtrage mot d'activation → envoi à Jarvis.
 * Branche aussi la voix et les bips sur les événements de la conversation.
 */
import { api } from "../lib/api";
import { audio, majAudio, useAudio } from "../stores/audio";
import { arreter, bus, envoyer, signalerParole, useJarvis } from "../stores/jarvis";
import { reglages } from "../stores/reglages";
import { toast } from "../stores/toasts";
import { sons } from "./bips";
import { micro, versPcm16k } from "./micro";
import { finirFlux, recevoirFlux, taire } from "./tts";

// Même règles que l'écoute de fond (jarvis/ecoute.py) : « Jarvis », « Hé/Et/Ok/Dis Jarvis », transcriptions approximatives
const NOM = String.raw`(?:d[ie]\s?)?(?:j|dj)[ae]r?v[iy](?:s|ce|sse|ss)?`;
const MOTS_STOP = String.raw`(?:stop+|arr[êe]te[sz]?(?:[- ]toi)?|annule|tais[- ]toi|taisez[- ]vous|chut+|silence|ça suffit|ca suffit|attends|pause|ferme[- ]la|c'est bon)`;
const RX_EVEIL = new RegExp(String.raw`^\W*(?:(?:hey|hé|he|eh|et|é|ok|okay|dis|salut|bonjour)\W+)?` + NOM + String.raw`\b[\s,.!?:;-]*`, "i");
const RX_STOP = new RegExp(String.raw`^\W*(?:` + NOM + String.raw`\W+)?` + MOTS_STOP + String.raw`(?![a-zà-ÿ])`, "i");
const RX_STOP_PARTOUT = new RegExp(NOM + String.raw`\W{0,3}(?:\w+\W+)?` + MOTS_STOP + String.raw`(?![a-zà-ÿ])`, "i");

async function transcrireRapide(morceaux: Float32Array[]) {
  const pcm = versPcm16k(morceaux, micro.sr);
  const r = await api<{ texte: string }>("/api/transcrire_rapide", {
    method: "POST",
    body: pcm.buffer as ArrayBuffer,
    headers: { "content-type": "application/octet-stream" },
  });
  return r.texte.trim();
}

export async function transcrire(morceaux: Float32Array[]) {
  const pcm = versPcm16k(morceaux, micro.sr);
  const r = await api<{ texte: string; secondes: number }>(`/api/transcrire?langue=${encodeURIComponent(reglages().langue)}`, {
    method: "POST",
    body: pcm.buffer as ArrayBuffer,
    headers: { "content-type": "application/octet-stream" },
  });
  return r.texte.trim();
}

export function stopTout() {
  taire();
  if (useJarvis.getState().occupe) arreter();
  sons.stop();
}

function traiterParole(texte: string, auto: boolean) {
  if (!texte) return;
  majAudio({ derniereTranscription: texte });
  const { occupe } = useJarvis.getState();
  const a = audio();
  if (RX_STOP.test(texte) && (occupe || a.parle)) return stopTout();
  if (auto && occupe) return; // mains libres : on ignore ce qui est dit pendant une tâche
  if (reglages().mode === "eveil" && Date.now() > a.eveilJusqua) {
    if (!RX_EVEIL.test(texte)) return; // ce n'était pas pour Jarvis
    texte = texte.replace(RX_EVEIL, "").trim();
    if (texte.length < 3) {
      // « Jarvis ? » tout seul : il attend la suite
      majAudio({ eveilJusqua: Date.now() + 8000 });
      sons.eveil();
      return;
    }
  } else {
    texte = texte.replace(RX_EVEIL, "").trim() || texte;
  }
  majAudio({ eveilJusqua: 0 });
  envoyer(texte);
}

let branche = false;
export function brancherVoix() {
  if (branche) return;
  branche = true;

  // Tu parles par-dessus Jarvis : « stop » le coupe, « Jarvis, … » le coupe et lance la nouvelle demande
  let interruptionEnCours = false;
  micro.surInterruption = async (morceaux) => {
    if (interruptionEnCours) return;
    interruptionEnCours = true;
    try {
      const texte = await transcrireRapide(morceaux);
      if (!texte) return;
      if (RX_STOP.test(texte) || RX_STOP_PARTOUT.test(texte)) {
        majAudio({ derniereTranscription: texte });
        stopTout();
      } else if (RX_EVEIL.test(texte) && texte.replace(RX_EVEIL, "").trim().length >= 3) {
        majAudio({ derniereTranscription: texte });
        stopTout();
        const suite = await transcrire(morceaux); // transcription précise de la nouvelle demande
        traiterParole(suite || texte, false);
      }
    } catch {
      /* interruption non comprise : on laisse Jarvis continuer */
    } finally {
      interruptionEnCours = false;
    }
  };

  micro.surPhrase = async (morceaux, auto) => {
    majAudio({ transcrit: true });
    try {
      traiterParole(await transcrire(morceaux), auto);
    } catch (e) {
      toast(t("Transcription impossible : {msg}", { msg: (e as Error).message }), "erreur");
    } finally {
      majAudio({ transcrit: false });
    }
  };

  window.addEventListener("jarvis:debut-ecoute", (e) => {
    const { auto } = (e as CustomEvent<{ auto: boolean }>).detail;
    if (audio().parle) taire();
    const r = reglages();
    if (!auto || r.mode === "auto" || Date.now() < audio().eveilJusqua) sons.ecoute();
  });

  bus.addEventListener("envoi", () => {
    taire();
    sons.envoi();
  });
  bus.addEventListener("texte", (e) => recevoirFlux((e as CustomEvent<string>).detail));
  bus.addEventListener("outil", () => {
    finirFlux(); // dit ce qui a été écrit avant l'action (« Je regarde ça… »)
    sons.outil();
  });
  bus.addEventListener("erreur", () => sons.erreur());
  // « Hey Jarvis » entendu par l'écoute de fond de l'appli (même fenêtre cachée)
  bus.addEventListener("vocal", (e) => {
    const v = (e as CustomEvent<{ etat: string; texte?: string }>).detail;
    if (v.etat === "eveil") {
      taire();
      sons.eveil();
      majAudio({ vocalServeur: "eveil" });
    } else if (v.etat === "transcription") majAudio({ vocalServeur: "transcription" });
    else majAudio({ vocalServeur: null, ...(v.texte ? { derniereTranscription: v.texte } : {}) });
  });
  bus.addEventListener("stop_voix", () => stopTout());
  useAudio.subscribe((s, avant) => {
    if (s.parle !== avant.parle) signalerParole(s.parle);
  });
  bus.addEventListener("fin", () => {
    sons.fin();
    finirFlux();
  });
}
