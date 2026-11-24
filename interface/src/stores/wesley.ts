import { create } from "zustand";
import { getJeton, ouvrirSession } from "../lib/api";
import { uid } from "../lib/format";
import type { Bloc, Message, MessageWesley, Session } from "../lib/types";
import { useReglages, type Vue } from "./reglages";

type EtatWesley = {
  session: Session | null;
  connecte: boolean;
  occupe: boolean;
  outilEnCours: string | null;
  messages: Message[];
};

export const useWesley = create<EtatWesley>(() => ({
  session: null,
  connecte: false,
  occupe: false,
  outilEnCours: null,
  messages: [],
}));

/** Événements pour les effets de bord (voix, bips) sans dépendance circulaire. */
export const bus = new EventTarget();
export const emettre = (nom: string, detail?: unknown) => bus.dispatchEvent(new CustomEvent(nom, { detail }));

let sock: WebSocket | null = null;
let tentative = 0;

export function connecter() {
  if (sock && sock.readyState <= WebSocket.OPEN) return; // déjà connecté ou en cours
  const proto = location.protocol === "https:" ? "wss" : "ws";
  sock = new WebSocket(`${proto}://${location.host}/ws?jeton=${encodeURIComponent(getJeton())}`);
  sock.onopen = () => {
    tentative = 0;
    useWesley.setState({ connecte: true });
  };
  sock.onclose = () => {
    useWesley.setState({ connecte: false });
    // le serveur a peut-être redémarré avec un nouveau jeton : on le redemande avant de se reconnecter
    setTimeout(() => {
      ouvrirSession()
        .then((s) => useWesley.setState({ session: s }))
        .catch(() => {})
        .finally(connecter);
    }, Math.min(8000, 500 * 2 ** tentative++));
  };
  sock.onmessage = (e) => recevoir(JSON.parse(e.data));
}

const envoyerBrut = (m: object) => {
  if (sock?.readyState === WebSocket.OPEN) {
    sock.send(JSON.stringify(m));
    return true;
  }
  return false;
};

export function envoyer(texte: string) {
  texte = texte.trim();
  if (!texte) return false;
  const { occupe } = useWesley.getState();
  if (occupe) {
    ajouterSysteme("info", "Je termine la tâche en cours — STOP pour l'interrompre.");
    return false;
  }
  if (!envoyerBrut({ type: "message", texte })) {
    ajouterSysteme("erreur", "Pas de liaison avec le serveur Wesley.");
    return false;
  }
  emettre("envoi", texte);
  return true;
}

export const arreter = () => envoyerBrut({ type: "stop" });
/** Prévient le serveur quand Wesley parle : l'écoute de fond guette alors « Wesley, stop » même mêlé à sa voix. */
export const signalerParole = (actif: boolean) => envoyerBrut({ type: "parle", actif });
export const nouvelleConversation = () => envoyerBrut({ type: "reset" });
export const rescanner = () => envoyerBrut({ type: "scan" });

export function ajouterSysteme(role: "info" | "erreur", texte: string) {
  useWesley.setState((s) => ({ messages: [...s.messages, { id: uid(), role, texte, date: Date.now() }] }));
}

/* ---------- réception ---------- */
type Evt =
  | { type: "maj"; etape: string; pct: number; texte: string }
  | { type: "naviguer"; vue: Vue }
  | { type: "contexte"; selection: string; fenetre: string }
  | { type: "memoire_maj"; faits: boolean; historique: number }
  | { type: "annonce"; texte: string }
  | { type: "confirmation"; id: string; titre: string; detail: string; saisie?: boolean }
  | { type: "confirmation_fin"; id: string }
  | { type: "tache_maj"; id: string }
  | { type: "transcription_maj"; id: string }
  | { type: "notifications"; non_lues: number }
  | { type: "appareils_maj" }
  | { type: "afaire_maj" }
  | { type: "tickets_maj" }
  | { type: "sites_maj" }
  | { type: "exploration" }
  | { type: "kyutai"; en_cours: boolean; etape: string; pct: number; erreur: string }
  | { type: "compte_deconnecte" }
  | { type: "init"; conversation: ({ role: "user"; texte: string } | { role: "wesley"; blocs: Bloc[] })[]; occupe: boolean }
  | { type: "utilisateur"; texte: string }
  | { type: "etat"; occupe: boolean }
  | { type: "texte"; t: string }
  | { type: "pensee"; t: string }
  | { type: "outil"; id: number; nom: string; args: Record<string, string> }
  | { type: "resultat"; id: number; nom: string; res: string; erreur: boolean }
  | { type: "fin"; texte: string }
  | { type: "erreur"; texte: string }
  | { type: "info"; texte: string }
  | { type: "reset" }
  | { type: "vocal"; etat: "eveil" | "transcription" | "fin"; texte?: string }
  | { type: "stop_voix" };

/** Modifie le message Wesley en cours (le crée si besoin). */
function majReponse(fn: (m: MessageWesley) => MessageWesley) {
  useWesley.setState((s) => {
    const msgs = [...s.messages];
    let i = msgs.length - 1;
    const dernier = msgs[i];
    if (!dernier || dernier.role !== "wesley" || !dernier.enCours) {
      msgs.push({ id: uid(), role: "wesley", blocs: [], date: Date.now(), enCours: true });
      i = msgs.length - 1;
    }
    msgs[i] = fn(msgs[i] as MessageWesley);
    return { messages: msgs };
  });
}

function ajouterFlux(type: "texte" | "pensee", t: string) {
  majReponse((m) => {
    const blocs = [...m.blocs];
    const d = blocs[blocs.length - 1];
    if (d && d.type === type) blocs[blocs.length - 1] = { ...d, texte: d.texte + t };
    else blocs.push({ type, texte: t });
    return { ...m, blocs };
  });
}

function recevoir(e: Evt) {
  switch (e.type) {
    case "init":
      useWesley.setState({
        occupe: e.occupe,
        messages: e.conversation.map((m) =>
          m.role === "user"
            ? { id: uid(), role: "user" as const, texte: m.texte, date: Date.now() }
            : { id: uid(), role: "wesley" as const, blocs: m.blocs, date: Date.now(), enCours: false },
        ),
      });
      break;
    case "utilisateur":
      useWesley.setState((s) => ({
        messages: [
          ...s.messages,
          { id: uid(), role: "user", texte: e.texte, date: Date.now() },
          { id: uid(), role: "wesley", blocs: [], date: Date.now(), enCours: true },
        ],
      }));
      break;
    case "etat":
      useWesley.setState({ occupe: e.occupe, ...(e.occupe ? {} : { outilEnCours: null }) });
      if (!e.occupe)
        useWesley.setState((s) => ({
          messages: s.messages
            .filter((m) => !(m.role === "wesley" && m.enCours && m.blocs.length === 0))
            .map((m) => (m.role === "wesley" && m.enCours ? { ...m, enCours: false } : m)),
        }));
      break;
    case "texte":
      ajouterFlux("texte", e.t);
      emettre("texte", e.t);
      break;
    case "pensee":
      ajouterFlux("pensee", e.t);
      break;
    case "outil":
      useWesley.setState({ outilEnCours: e.nom });
      majReponse((m) => ({
        ...m,
        blocs: [...m.blocs, { type: "outil", id: e.id, nom: e.nom, args: e.args, resultat: null, debut: Date.now() }],
      }));
      emettre("outil", e.nom);
      break;
    case "resultat":
      useWesley.setState({ outilEnCours: null });
      majReponse((m) => ({
        ...m,
        blocs: m.blocs.map((b) =>
          b.type === "outil" && b.id === e.id ? { ...b, resultat: e.res, erreur: e.erreur, fin: Date.now() } : b,
        ),
      }));
      break;
    case "fin":
      emettre("fin", e.texte);
      break;
    case "erreur":
      ajouterSysteme("erreur", e.texte);
      emettre("erreur", e.texte);
      break;
    case "info":
      ajouterSysteme("info", e.texte);
      break;
    case "reset":
      useWesley.setState({ messages: [], outilEnCours: null });
      break;
    case "vocal":
      emettre("vocal", e);
      break;
    case "stop_voix":
      emettre("stop_voix");
      break;
    case "maj":
      emettre("maj", e);
      break;
    case "memoire_maj":
      emettre("memoire_maj", e);
      break;
    case "annonce":
      emettre("annonce", e.texte);
      break;
    case "confirmation":
      emettre("confirmation", { id: e.id, titre: e.titre, detail: e.detail, saisie: e.saisie });
      break;
    case "confirmation_fin":
      emettre("confirmation_fin", e.id);
      break;
    case "tache_maj":
      emettre("tache_maj", e.id);
      break;
    case "transcription_maj":
      emettre("transcription_maj", e.id);
      break;
    case "notifications":
      emettre("notifications", e.non_lues);
      break;
    case "afaire_maj":
      emettre("afaire_maj");
      break;
    case "tickets_maj":
      emettre("tickets_maj");
      break;
    case "sites_maj":
      emettre("sites_maj");
      break;
    case "exploration":
      emettre("exploration");
      break;
    case "kyutai":
      emettre("kyutai", e);
      break;
    case "appareils_maj":
      emettre("appareils_maj");
      break;
    case "compte_deconnecte":
      emettre("compte_deconnecte");
      break;
    case "naviguer":
      useReglages.getState().maj({ vue: e.vue });
      break;
    case "contexte":   // Ctrl+Alt+E : ce que l'utilisateur regardait (sélection, fenêtre)
      useReglages.getState().maj({ vue: "assistant" });
      emettre("contexte", { selection: e.selection, fenetre: e.fenetre });
      break;
  }
}
