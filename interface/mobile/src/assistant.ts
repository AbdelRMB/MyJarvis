/**
 * La conversation avec Wesley sur le téléphone (gardée quand on change d'écran) : fil des messages, étapes
 * (outils utilisés), voix, conversation suivie (réécoute après la réponse si on a parlé).
 */
import { create } from "zustand";
import { Conversation, type Evenement } from "./moteur/cerveau";
import { signalerOccupe } from "./moteur/synchro";
import { cache, definirCache, reglagesTel } from "./moteur/stockage";
import { ecouter, parler } from "./moteur/voix";

export type Etape = { nom: string; args: Record<string, unknown>; resultat?: string };
export type Message = { id: string; qui: "moi" | "wesley"; texte: string; ts: number; erreur?: boolean; etapes?: Etape[]; cerveau?: string };

type Etat = {
  messages: Message[];
  enCours: boolean;
  etat: string; // « Claude réfléchit… », « PC-Bureau travaille… »
  ecoute: boolean;
  partiel: string; // texte reconnu pendant que l'utilisateur parle
};

export const useAssistant = create<Etat>(() => ({ messages: cache("fil", []), enCours: false, etat: "", ecoute: false, partiel: "" }));

const conversation = new Conversation();
const id = () => Math.random().toString(36).slice(2, 10);

function ajouter(m: Omit<Message, "id" | "ts">) {
  const msg = { ...m, id: id(), ts: Date.now() };
  const messages = [...useAssistant.getState().messages, msg].slice(-100);
  useAssistant.setState({ messages });
  definirCache("fil", messages.map((x) => ({ ...x, etapes: x.etapes?.map((e) => ({ ...e, resultat: e.resultat?.slice(0, 500) })) })));
  return msg.id;
}
function maj(mid: string, p: Partial<Message>) {
  const messages = useAssistant.getState().messages.map((m) => (m.id === mid ? { ...m, ...p } : m));
  useAssistant.setState({ messages });
  definirCache("fil", messages);
}

export function effacerFil() {
  conversation.reset();
  useAssistant.setState({ messages: [] });
  definirCache("fil", []);
}

export const arreter = () => conversation.arreter();

export async function envoyer(texte: string, parVoix = false) {
  texte = texte.trim();
  if (!texte || useAssistant.getState().enCours) return;
  ajouter({ qui: "moi", texte });
  const etapes: Etape[] = [];
  const rid = ajouter({ qui: "wesley", texte: "", etapes });
  useAssistant.setState({ enCours: true, etat: "Wesley réfléchit…" });
  signalerOccupe(true);
  const surEv = (e: Evenement) => {
    if (e.type === "etat") useAssistant.setState({ etat: e.texte });
    else if (e.type === "outil") {
      etapes.push({ nom: e.nom, args: e.args });
      useAssistant.setState({ etat: `${e.nom.replace(/_/g, " ")}…` });
      maj(rid, { etapes: [...etapes] });
    } else if (e.type === "resultat") {
      const x = [...etapes].reverse().find((s) => s.nom === e.nom && s.resultat === undefined);
      if (x) x.resultat = e.resultat;
      maj(rid, { etapes: [...etapes] });
    }
  };
  let reponse = "";
  try {
    const r = await conversation.demander(texte, surEv);
    reponse = r.texte;
    maj(rid, { texte: r.texte, cerveau: r.cerveau.nom + (r.cerveau.raison ? ` (${r.cerveau.raison})` : "") });
  } catch (e) {
    maj(rid, { texte: (e as Error).message, erreur: true });
  } finally {
    useAssistant.setState({ enCours: false, etat: "" });
    signalerOccupe(false);
  }
  if (reponse) {
    await parler(reponse);
    // conversation suivie : après une demande à la voix, on réécoute la suite (sans retoucher le micro)
    if (parVoix && reglagesTel().suivie && !document.hidden) void ecouterEtEnvoyer();
  }
}

export async function ecouterEtEnvoyer() {
  if (useAssistant.getState().ecoute) return;
  useAssistant.setState({ ecoute: true, partiel: "" });
  try {
    const texte = await ecouter((p) => useAssistant.setState({ partiel: p }));
    useAssistant.setState({ ecoute: false, partiel: "" });
    // « Wesley, stop » / « stop » : on se tait
    if (/^(wesley[ ,]*)?(stop|tais-toi|silence|arr[êe]te)\W*$/i.test(texte)) return;
    if (texte) await envoyer(texte.replace(/^wesley[ ,]+/i, ""), true);
  } catch (e) {
    useAssistant.setState({ ecoute: false, partiel: "" });
    ajouter({ qui: "wesley", texte: (e as Error).message, erreur: true });
  }
}

/** Demande reçue d'un autre appareil : traitée par une conversation séparée (le fil en cours n'est pas dérangé). */
export async function demandeRecue(texte: string, de: string) {
  const c = new Conversation();
  const rid = ajouter({ qui: "wesley", texte: `Demande de ${de}…`, etapes: [] });
  try {
    const r = await c.demander(texte, () => {}, false);
    maj(rid, { texte: `**Demande de ${de}** — ${r.texte}` });
    return r.texte;
  } catch (e) {
    maj(rid, { texte: `Demande de ${de} : ${(e as Error).message}`, erreur: true });
    throw e;
  }
}

export function annonce(texte: string) {
  ajouter({ qui: "wesley", texte });
  void parler(texte);
}
