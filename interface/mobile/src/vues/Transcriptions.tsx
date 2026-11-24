import { Copy, Loader2, RefreshCw, RotateCcw, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { Bouton } from "../../../src/components/ui";
import { t } from "../../../src/lib/i18n";
import { agirPartage, chargerPartages, horodatage, lirePartage, toursDeParole, usePartages, type Partage, type Segment } from "../moteur/partages";
import { allerA, Entete, erreurToast, Feuille, Ligne, Section, toast } from "../ui";
import { Origine } from "./Taches";

const ETATS: Record<string, [string, string]> = {
  preparation: ["Préparation…", "text-ambre"],
  en_cours: ["En cours", "text-hud"],
  finalisation: ["Finalisation…", "text-ambre"],
  terminee: ["Terminée", "text-vert"],
  erreur: ["Erreur", "text-rouge"],
  interrompue: ["Interrompue", "text-doux"],
};
const COULEURS = ["#3ce8ff", "#ffb547", "#5ef38c", "#ff6b9d", "#b18cff", "#ff8a4c", "#4cc3ff", "#e8e35a", "#7cf0d0", "#ff5c5c"];
const actif = (e?: string) => e === "preparation" || e === "en_cours" || e === "finalisation";

type Contenu = { segments: Segment[]; noms: Record<string, string> };

function DetailTranscription({ p, onFermer }: { p: Partage; onFermer: () => void }) {
  const [c, setC] = useState<Contenu | null>(null);
  const [attente, setAttente] = useState("");
  const [etat, setEtat] = useState("");
  useEffect(() => {
    lirePartage<Contenu>("transcription", p.resume.id)
      .then(setC)
      .catch((e) => (erreurToast(e), setC({ segments: [], noms: {} })));
  }, [p.resume.id, p.modifie]);

  const nom = (l: number) => c?.noms?.[String(l)]?.trim() || t("Locuteur {n}", { n: l });
  const tours = c ? toursDeParole(c.segments ?? []) : [];
  const agir = async (action: string) => {
    setAttente(action);
    try {
      toast(await agirPartage(p, action, {}, setEtat));
    } catch (e) {
      erreurToast(e);
    } finally {
      setAttente("");
      setEtat("");
    }
  };
  const copier = async () => {
    try {
      await navigator.clipboard.writeText(`${p.resume.titre}\n\n` + tours.map((x) => `[${horodatage(x.debut)}] ${nom(x.locuteur)} : ${x.texte}`).join("\n\n"));
      toast(t("Transcription copiée."));
    } catch (e) {
      erreurToast(e);
    }
  };
  const r = p.resume;
  const [libelle, couleur] = ETATS[r.etat || ""] ?? [r.etat || "", "text-doux"];
  const sur = ` ${t("sur {appareil}", { appareil: r.appareil_nom || "?" })}`;
  return (
    <Feuille titre={r.titre} onFermer={onFermer}>
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className={couleur}>{t(libelle)}</span>
        <Origine p={p} />
      </div>
      <p className="mt-1 text-[12px] text-doux">
        {r.debut ? new Date(r.debut * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" }) : ""} · {horodatage(r.duree || 0)} ·{" "}
        {t("{n} locuteur(s)", { n: r.nb_locuteurs ?? 0 })}
      </p>
      {r.erreur && <p className="mt-1 text-[12px] text-rouge">{r.erreur}</p>}
      <div className="mt-3 grid grid-cols-2 gap-2">
        {actif(r.etat) ? (
          r.source !== "fichier" && (
            <Bouton variante="danger" icone={<Square className="size-4" />} chargement={attente === "arreter"} onClick={() => agir("arreter")}>
              {t("Arrêter") + sur}
            </Bouton>
          )
        ) : (
          <Bouton variante="primaire" icone={<RotateCcw className="size-4" />} chargement={attente === "reprendre"} onClick={() => agir("reprendre")}>
            {t("Reprendre") + sur}
          </Bouton>
        )}
        <Bouton icone={<Copy className="size-4" />} disabled={!tours.length} onClick={copier}>
          {t("Copier")}
        </Bouton>
      </div>
      {etat && <p className="mt-2 text-[12px] text-doux">{etat}</p>}
      <div className="mt-4 space-y-3">
        {c === null ? (
          <Loader2 className="size-4 animate-spin text-doux" />
        ) : tours.length === 0 ? (
          <p className="text-[13px] text-doux">{t("Rien n'a été transcrit.")}</p>
        ) : (
          tours.map((x, i) => (
            <div key={i}>
              <div className="flex items-center gap-2 text-[12px]">
                <span className="font-mono text-tres-doux">{horodatage(x.debut)}</span>
                <span className="font-medium" style={{ color: COULEURS[(x.locuteur - 1 + COULEURS.length) % COULEURS.length] }}>
                  {nom(x.locuteur)}
                </span>
              </div>
              <p className="text-[14px] leading-relaxed">{x.texte}</p>
            </div>
          ))
        )}
      </div>
    </Feuille>
  );
}

/** Transcriptions de réunions faites sur tes ordinateurs : lecture ici, reprise sur l'ordinateur d'origine. */
export function Transcriptions() {
  const { liste, charge } = usePartages();
  const transcriptions = liste.filter((x) => x.genre === "transcription").sort((a, b) => (b.resume.debut || 0) - (a.resume.debut || 0));
  const [choisie, setChoisie] = useState<string | null>(null);
  const detail = transcriptions.find((x) => x.resume.id === choisie);
  useEffect(() => void chargerPartages(), []);
  return (
    <div>
      <Entete
        titre={t("Transcription")}
        retour={() => allerA("plus")}
        actions={
          <button className="grid size-9 place-items-center text-doux" onClick={() => void chargerPartages()} aria-label={t("Actualiser")}>
            <RefreshCw className={charge ? "size-4.5 animate-spin" : "size-4.5"} />
          </button>
        }
      />
      <Section titre={t("Transcriptions")}>
        {transcriptions.length === 0 ? (
          <p className="p-3 text-[13px] text-doux">{t("Aucune transcription sur tes ordinateurs. Lance-en une depuis l'onglet Transcription de Wesley sur ton Mac ou ton PC.")}</p>
        ) : (
          transcriptions.map((p) => {
            const [libelle, couleur] = ETATS[p.resume.etat || ""] ?? [p.resume.etat || "", "text-doux"];
            return (
              <Ligne key={p.resume.id} onClick={() => setChoisie(p.resume.id)}>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[14px]">{p.resume.titre}</div>
                  <div className="flex items-center gap-2 text-[11px] text-tres-doux">
                    <Origine p={p} />
                    <span>· {p.resume.debut ? new Date(p.resume.debut * 1000).toLocaleDateString([], { day: "numeric", month: "short" }) : ""}</span>
                    <span>· {horodatage(p.resume.duree || 0)}</span>
                  </div>
                </div>
                <span className={`flex-none text-[12px] ${couleur}`}>
                  {actif(p.resume.etat) && <Loader2 className="mr-1 inline size-3 animate-spin" />}
                  {t(libelle)}
                </span>
              </Ligne>
            );
          })
        )}
      </Section>
      {detail && <DetailTranscription p={detail} onFermer={() => setChoisie(null)} />}
    </div>
  );
}
