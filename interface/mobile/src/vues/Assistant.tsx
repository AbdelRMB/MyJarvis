import { ChevronDown, Loader2, Mic, Paperclip, SendHorizontal, Square, Trash2, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Markdown } from "../../../src/components/Markdown";
import { cx, heure } from "../../../src/lib/format";
import { t } from "../../../src/lib/i18n";
import { arreter, ecouterEtEnvoyer, effacerFil, envoyer, useAssistant, type Message } from "../assistant";
import { cerveauActif } from "../moteur/cerveau";
import { garderFichier, prenom, useDonnees } from "../moteur/donnees";
import { b64 } from "../moteur/crypto";
import { MAX_FICHIER } from "../moteur/appareils";
import { arreterEcoute, arreterParole, recoDisponible } from "../moteur/voix";
import { Entete, toast } from "../ui";

const SUGGESTIONS = [
  "Qu'est-ce que j'ai prévu aujourd'hui ?",
  "Rappelle-moi d'appeler le garage demain à 10 h",
  "Sur mon PC, ouvre Spotify",
  "Fais-moi le briefing",
];

export function Assistant() {
  const { messages, enCours, etat, ecoute, partiel } = useAssistant();
  useDonnees((d) => d.profil); // le cerveau affiché suit les réglages du compte
  const [texte, setTexte] = useState("");
  const fil = useRef<HTMLDivElement>(null);
  const fichier = useRef<HTMLInputElement>(null);
  const cerveau = cerveauActif();

  useEffect(() => {
    fil.current?.scrollTo({ top: fil.current.scrollHeight, behavior: "smooth" });
  }, [messages, etat, partiel]);

  const valider = (e?: React.FormEvent) => {
    e?.preventDefault();
    const v = texte.trim();
    if (!v) return;
    setTexte("");
    void envoyer(v);
  };

  async function joindre(f: File | undefined) {
    if (!f) return;
    if (f.size > MAX_FICHIER) return toast(t("Fichier trop gros (maximum 10 Mo)."), true);
    const contenu = b64(new Uint8Array(await f.arrayBuffer()));
    garderFichier({ nom: f.name, taille: f.size, de: t("ce téléphone"), contenu });
    setTexte((x) => x || t("Envoie {nom} sur mon ordinateur", { nom: f.name }));
    toast(t("Fichier joint : {nom}", { nom: f.name }));
  }

  return (
    <div className="flex h-full flex-col">
      <Entete
        titre="Wesley"
        sous={`${cerveau.nom}${cerveau.raison ? ` · ${cerveau.raison}` : ""}`}
        actions={
          messages.length > 0 && (
            <button onClick={() => confirm(t("Effacer la conversation de ce téléphone ?")) && effacerFil()} className="grid size-9 place-items-center text-doux" aria-label={t("Effacer")}>
              <Trash2 className="size-4.5" />
            </button>
          )
        }
      />
      <div ref={fil} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {!messages.length && (
          <div className="pt-10 text-center">
            <p className="titre-hud text-[13px] text-hud">{t("Bonjour {nom}", { nom: prenom() })}</p>
            <p className="mt-2 text-sm text-doux">{t("Parle ou écris : je m'occupe du reste, ici ou sur tes ordinateurs.")}</p>
            <div className="mt-6 flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => void envoyer(t(s))} className="rounded-md border border-ligne px-3 py-2.5 text-left text-sm text-doux active:bg-white/5">
                  {t(s)}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <Bulle key={m.id} m={m} />
        ))}
        {ecoute && (
          <div className="ml-auto max-w-[85%] rounded-lg border border-hud/40 bg-hud/10 px-3 py-2 text-sm text-hud-clair italic">{partiel || t("Je t'écoute…")}</div>
        )}
        {enCours && (
          <div className="flex items-center gap-2 text-[13px] text-doux">
            <Loader2 className="size-3.5 animate-spin text-hud" /> {etat}
          </div>
        )}
      </div>
      <form onSubmit={valider} className="flex items-end gap-1.5 border-t border-ligne bg-surface/80 px-2 py-2">
        <input ref={fichier} type="file" hidden onChange={(e) => void joindre(e.target.files?.[0]).finally(() => (e.target.value = ""))} />
        <button type="button" onClick={() => fichier.current?.click()} className="grid size-11 flex-none place-items-center text-doux" aria-label={t("Joindre un fichier")}>
          <Paperclip className="size-5" />
        </button>
        <textarea
          value={texte}
          onChange={(e) => setTexte(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), valider())}
          rows={1}
          placeholder={t("Demande quelque chose…")}
          className="max-h-32 min-h-11 flex-1 resize-none rounded-lg border border-ligne-forte bg-surface-2 px-3 py-2.5 outline-none placeholder:text-tres-doux focus:border-hud"
        />
        {enCours ? (
          <button type="button" onClick={arreter} className="grid size-11 flex-none place-items-center rounded-full border border-rouge/50 text-rouge" aria-label={t("Arrêter")}>
            <Square className="size-4.5" />
          </button>
        ) : texte.trim() ? (
          <button type="submit" className="grid size-11 flex-none place-items-center rounded-full bg-hud text-fond" aria-label={t("Envoyer")}>
            <SendHorizontal className="size-5" />
          </button>
        ) : (
          <button
            type="button"
            disabled={!recoDisponible()}
            onClick={() => {
              arreterParole();
              if (ecoute) arreterEcoute();
              else void ecouterEtEnvoyer();
            }}
            className={cx("grid size-11 flex-none place-items-center rounded-full", ecoute ? "animate-pulse-rouge bg-rouge text-fond" : "bg-hud text-fond shadow-glow")}
            aria-label={t("Parler")}
          >
            <Mic className="size-5" />
          </button>
        )}
      </form>
    </div>
  );
}

function Bulle({ m }: { m: Message }) {
  const [ouvert, setOuvert] = useState(false);
  if (m.qui === "moi") {
    return (
      <div className="ml-auto max-w-[85%] rounded-lg rounded-br-sm bg-hud/15 px-3 py-2 text-[15px] whitespace-pre-wrap">
        {m.texte}
        <div className="mt-0.5 text-right text-[10px] text-tres-doux">{heure(m.ts)}</div>
      </div>
    );
  }
  const etapes = m.etapes || [];
  return (
    <div className={cx("max-w-[92%] rounded-lg rounded-bl-sm border px-3 py-2", m.erreur ? "border-rouge/40 bg-rouge/5 text-rouge" : "border-ligne bg-surface")}>
      {etapes.length > 0 && (
        <button onClick={() => setOuvert(!ouvert)} className="mb-1 flex items-center gap-1 text-[11px] text-tres-doux">
          <Wrench className="size-3" /> {etapes.map((e) => e.nom.replace(/_/g, " ")).join(" · ").slice(0, 70)}
          <ChevronDown className={cx("size-3 transition-transform", ouvert && "rotate-180")} />
        </button>
      )}
      {ouvert && (
        <div className="mb-2 space-y-1 border-l border-ligne-forte pl-2 font-mono text-[11px] text-doux">
          {etapes.map((e, i) => (
            <div key={i}>
              <span className="text-hud">{e.nom}</span> {JSON.stringify(e.args).slice(0, 140)}
              {e.resultat !== undefined && <div className="whitespace-pre-wrap text-tres-doux">→ {e.resultat.slice(0, 400)}</div>}
            </div>
          ))}
        </div>
      )}
      {m.texte ? <div className="prose-wesley text-[15px]">{m.erreur ? m.texte : <Markdown texte={m.texte} />}</div> : <Loader2 className="size-4 animate-spin text-hud" />}
      <div className="mt-1 text-[10px] text-tres-doux">
        {heure(m.ts)}
        {m.cerveau && ` · ${m.cerveau}`}
      </div>
    </div>
  );
}
