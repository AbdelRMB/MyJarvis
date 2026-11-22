/**
 * Capture micro : WebAudio (gain → analyseur + AudioWorklet), détection d'activité vocale,
 * push-to-talk, et préparation du PCM 16 kHz pour Whisper côté serveur.
 */
import { audio, majAudio } from "../stores/audio";
import { reglages } from "../stores/reglages";

const CODE_WORKLET = `
class Capture extends AudioWorkletProcessor {
  constructor() { super(); this.b = new Float32Array(2048); this.i = 0; }
  process(entrees) {
    const c = entrees[0][0];
    if (c) for (let k = 0; k < c.length; k++) {
      this.b[this.i++] = c[k];
      if (this.i === 2048) { this.port.postMessage(this.b.slice(0)); this.i = 0; }
    }
    return true;
  }
}
registerProcessor("capture", Capture);`;

class Micro {
  ctx: AudioContext | null = null;
  analyseur: AnalyserNode | null = null;
  frequences = new Uint8Array(256);
  niveau = 0;
  sr = 48000;
  /** Niveau du silence de la pièce (moyenne glissante quand personne ne parle). */
  bruit = 0.004;

  private flux: MediaStream | null = null;
  private src: MediaStreamAudioSourceNode | null = null;
  private gain: GainNode | null = null;
  private noeud: AudioWorkletNode | null = null;
  private moduleCharge = false;
  private morceaux: Float32Array[] = [];
  private preRoll: Float32Array[] = [];
  private debut = 0;
  private dernierSon = 0;
  private capteurTest: Float32Array[] | null = null;

  /** Appelé quand une phrase est terminée (PCM brut au taux natif). */
  surPhrase: ((morceaux: Float32Array[], auto: boolean) => void) | null = null;

  async initialiser() {
    if (!this.ctx) this.ctx = new AudioContext();
    if (this.ctx.state !== "running") await this.ctx.resume();
    majAudio({ pret: true });
  }

  async demarrer(): Promise<void> {
    await this.initialiser();
    this.arreter();
    const r = reglages();
    try {
      this.flux = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: r.deviceId ? { exact: r.deviceId } : undefined,
          channelCount: 1,
          echoCancellation: r.echo,
          noiseSuppression: r.bruit,
          autoGainControl: r.agc,
        },
      });
    } catch (e) {
      if (r.deviceId) {
        // le périphérique mémorisé a disparu : on reprend celui par défaut
        reglages().maj({ deviceId: "" });
        return this.demarrer();
      }
      majAudio({ micActif: false, erreurMicro: (e as Error).message || "Accès au micro refusé" });
      return;
    }
    const ctx = this.ctx!;
    this.sr = ctx.sampleRate;
    if (!this.moduleCharge) {
      await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([CODE_WORKLET], { type: "application/javascript" })));
      this.moduleCharge = true;
    }
    this.src = ctx.createMediaStreamSource(this.flux);
    this.gain = ctx.createGain();
    this.gain.gain.value = r.gain;
    this.analyseur = ctx.createAnalyser();
    this.analyseur.fftSize = 512;
    this.analyseur.smoothingTimeConstant = 0.6;
    this.frequences = new Uint8Array(this.analyseur.frequencyBinCount);
    this.noeud = new AudioWorkletNode(ctx, "capture");
    this.noeud.port.onmessage = (e) => this.surMorceau(e.data as Float32Array);
    this.src.connect(this.gain);
    this.gain.connect(this.analyseur);
    this.gain.connect(this.noeud);
    const piste = this.flux.getAudioTracks()[0];
    piste.onended = () => majAudio({ micActif: false, erreurMicro: "Micro déconnecté" });
    majAudio({ micActif: true, erreurMicro: null, nomMicro: piste.label || "Micro par défaut" });
    await this.listerPeripheriques();
  }

  arreter() {
    this.flux?.getTracks().forEach((t) => t.stop());
    try {
      this.src?.disconnect();
      this.noeud?.disconnect();
    } catch {
      /* déjà déconnecté */
    }
    this.flux = null;
    this.niveau = 0;
    majAudio({ micActif: false, enregistre: false });
  }

  async listerPeripheriques() {
    const devs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
    majAudio({ peripheriques: devs.map((d, i) => ({ id: d.deviceId, nom: d.label || `Micro ${i + 1}` })) });
  }

  idPeripheriqueActif() {
    return this.flux?.getAudioTracks()[0]?.getSettings().deviceId ?? "";
  }

  setGain(v: number) {
    if (this.gain) this.gain.gain.value = v;
  }

  private surMorceau(d: Float32Array) {
    let s = 0;
    for (let i = 0; i < d.length; i++) s += d[i] * d[i];
    const rms = Math.sqrt(s / d.length);
    this.niveau = rms;
    if (this.capteurTest) {
      this.capteurTest.push(d);
      return;
    }
    const r = reglages();
    const a = audio();
    if (a.enregistre) {
      this.morceaux.push(d);
      if (r.mode !== "ptt") {
        const t = performance.now();
        // silence = sous le seuil réglé ET proche du bruit de la pièce (une voix faible compte comme de la parole)
        if (rms > Math.max(r.seuil * 0.7, this.bruit * 1.8)) this.dernierSon = t;
        else if (t - this.dernierSon > r.silence) this.finEnregistrement();
        if (t - this.debut > 180000) this.finEnregistrement();
      }
      return;
    }
    if (!a.parle) this.bruit = 0.97 * this.bruit + 0.03 * Math.min(rms, 0.1);
    // ~350 ms gardés en mémoire pour ne pas couper le début de la phrase
    this.preRoll.push(d);
    if (this.preRoll.length > 8) this.preRoll.shift();
    // Wesley parle : l'annulation d'écho du navigateur retire sa voix du micro,
    // donc ce qui dépasse le seuil, c'est toi qui l'interromps (« stop », « Wesley, … »).
    if (a.parle) {
      this.surveillerInterruption(d, rms, r.seuil);
      return;
    }
    this.interruption = null;
    const sourdine = r.sourdine && a.parle;
    const serveurEcoute = r.mode === "eveil" && a.ecouteFond; // l'appli de bureau s'en charge déjà
    const seuilDebut = r.seuil > 0 ? r.seuil : this.bruit * 2.5; // seuil 0 = automatique (s'adapte à la pièce)
    if (r.mode !== "ptt" && !serveurEcoute && !sourdine && !a.transcrit && rms > Math.max(seuilDebut, 0.002)) this.debutEnregistrement(true);
  }

  private interruption: Float32Array[] | null = null;
  private intDebut = 0;
  private intDernierSon = 0;
  /** Phrase dite par-dessus la voix de Wesley (max 2,5 s), transmise à surInterruption. */
  surInterruption: ((morceaux: Float32Array[]) => void) | null = null;

  private surveillerInterruption(d: Float32Array, rms: number, seuil: number) {
    const t = performance.now();
    const s = Math.max(seuil * 1.5, 0.02);
    if (!this.interruption) {
      if (rms > s) {
        this.interruption = [...this.preRoll.slice(-3)];
        this.intDebut = this.intDernierSon = t;
      }
      return;
    }
    this.interruption.push(d);
    if (rms > s * 0.7) this.intDernierSon = t;
    if (t - this.intDernierSon > 500 || t - this.intDebut > 2500) {
      const m = this.interruption;
      this.interruption = null;
      if (t - this.intDebut > 300) this.surInterruption?.(m);
    }
  }

  debutEnregistrement(auto = false) {
    const a = audio();
    if (!a.micActif || a.enregistre) return;
    this.morceaux = auto ? [...this.preRoll] : [];
    this.debut = this.dernierSon = performance.now();
    majAudio({ enregistre: true });
    window.dispatchEvent(new CustomEvent("wesley:debut-ecoute", { detail: { auto } }));
  }

  finEnregistrement() {
    if (!audio().enregistre) return;
    majAudio({ enregistre: false });
    const duree = performance.now() - this.debut;
    const morceaux = this.morceaux;
    this.morceaux = [];
    if (duree < 350 || morceaux.length === 0) return;
    this.surPhrase?.(morceaux, reglages().mode !== "ptt");
  }

  async enregistrerTest(ms: number) {
    this.capteurTest = [];
    await new Promise((r) => setTimeout(r, ms));
    const m = this.capteurTest;
    this.capteurTest = null;
    return m;
  }

  rejouer(morceaux: Float32Array[]) {
    if (!this.ctx || !morceaux.length) return;
    const n = morceaux.reduce((a, m) => a + m.length, 0);
    const buf = this.ctx.createBuffer(1, n, this.sr);
    const d = buf.getChannelData(0);
    let o = 0;
    for (const m of morceaux) {
      d.set(m, o);
      o += m.length;
    }
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);
    src.start();
  }
}

export const micro = new Micro();

/** Rééchantillonne vers 16 kHz mono (moyenne par fenêtre) pour Whisper. */
export function versPcm16k(morceaux: Float32Array[], sr: number) {
  const n = morceaux.reduce((a, m) => a + m.length, 0);
  const entree = new Float32Array(n);
  let o = 0;
  for (const m of morceaux) {
    entree.set(m, o);
    o += m.length;
  }
  const ratio = sr / 16000;
  const sortie = new Float32Array(Math.floor(n / ratio));
  for (let i = 0; i < sortie.length; i++) {
    const a = Math.floor(i * ratio);
    const b = Math.min(n, Math.floor((i + 1) * ratio));
    let s = 0;
    for (let k = a; k < b; k++) s += entree[k];
    sortie[i] = s / Math.max(1, b - a);
  }
  return sortie;
}

export function crete(morceaux: Float32Array[]) {
  let c = 0;
  for (const m of morceaux) for (let i = 0; i < m.length; i++) c = Math.max(c, Math.abs(m[i]));
  return c;
}
