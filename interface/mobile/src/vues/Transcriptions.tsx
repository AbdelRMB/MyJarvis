import { Copy, Loader2, Mic, Monitor, Play, RefreshCw, RotateCcw, Sparkles, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { Markdown } from "../../../src/components/Markdown";
import { Bouton, Champ } from "../../../src/components/ui";
import { ORDINATEURS } from "../moteur/appareils";
import { useDonnees } from "../moteur/donnees";
import { t } from "../../../src/lib/i18n";
import { agirPartage, chargerPartages, chercher, lancerTranscription, type Trouve, horodatage, lirePartage, toursDeParole, usePartages, type Partage, type Segment } from "../moteur/partages";
import { allerA, Entete, erreurToast, Feuille, Ligne, Section, toast } from "../ui";
import { Enregistreur } from "./Enregistreur";
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

type Resume = { texte?: string; genre?: string; actions?: { titre: string; qui: string; echeance: string }[]; en_cours?: boolean; erreur?: string };
type Contenu = { segments: Segment[]; noms: Record<string, string>; resume?: Resume };
const GENRES: Record<string, string> = {
  cours: "Cours",
  reunion: "Réunion",
  discussion: "Discussion",
  appel: "Appel",
  entretien: "Entretien",
  conference: "Conférence",
  note: "Note vocale",
  autre: "Transcription",
};

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
      {!actif(r.etat) && c && (
        <div className="mt-4 rounded-md border border-ligne bg-surface-2/40 p-3">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-hud" />
            <span className="titre-hud text-[10px] text-tres-doux">{t("Résumé")}</span>
            {c.resume?.texte && c.resume.genre && <span className="text-[11px] text-hud">{t(GENRES[c.resume.genre] ?? c.resume.genre)}</span>}
            <span className="ml-auto">
              <Bouton taille="sm" variante="fantome" chargement={attente === "resumer" || !!c.resume?.en_cours} onClick={() => agir("resumer")}>
                {c.resume?.texte ? t("Refaire") : t("Résumer")}
              </Bouton>
            </span>
          </div>
          {c.resume?.erreur && <p className="mt-1 text-[12px] text-rouge">{c.resume.erreur}</p>}
          {c.resume?.texte ? (
            <>
              <div className="prose-wesley mt-2 text-[14px]">
                <Markdown texte={c.resume.texte} />
              </div>
              {!!c.resume.actions?.length && (
                <ul className="mt-2 list-none pl-0 text-[13px]">
                  {c.resume.actions.map((a, i) => (
                    <li key={i}>
                      ☐ {a.titre}
                      {a.qui ? ` · ${a.qui}` : ""}
                      {a.echeance ? ` · ${new Date(a.echeance).toLocaleDateString()}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="mt-1 text-[12px] text-doux">
              {c.resume?.en_cours ? t("Wesley lit la transcription et écrit le résumé…") : t("Pas encore de résumé : touche Résumer, l'ordinateur le prépare.")}
            </p>
          )}
        </div>
      )}
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

/** Lancer une transcription sur un de tes ordinateurs (réunion en ligne : son son ; réunion physique : son micro). */
function Lancement() {
  const ordis = useDonnees((d) => d.appareils).filter((a) => !a.moi && ORDINATEURS.includes(a.plateforme));
  const [sur, setSur] = useState("");
  const [source, setSource] = useState<"systeme" | "micro">("systeme");
  const [titre, setTitre] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [etat, setEtat] = useState("");
  const choisi = ordis.find((a) => a.id === sur) ?? ordis.find((a) => a.en_ligne) ?? ordis[0];
  if (!ordis.length) return null;
  const lancer = async () => {
    if (!choisi) return;
    setEnvoi(true);
    try {
      toast(await lancerTranscription(choisi.id, { source, avec_micro: true, titre: titre.trim() }, setEtat));
      setTitre("");
      void chargerPartages();
    } catch (e) {
      erreurToast(e);
    } finally {
      setEnvoi(false);
      setEtat("");
    }
  };
  return (
    <Section titre={t("Nouvelle transcription")}>
      <div className="space-y-2 p-3">
        <select value={choisi?.id ?? ""} onChange={(e) => setSur(e.target.value)} className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3">
          {ordis.map((a) => (
            <option key={a.id} value={a.id}>
              {t("Sur {appareil}", { appareil: a.nom })} {a.en_ligne ? "" : `(${t("hors ligne")})`}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              ["systeme", t("Réunion en ligne"), Monitor],
              ["micro", t("Réunion physique"), Mic],
            ] as const
          ).map(([id, libelle, I]) => (
            <button
              key={id}
              onClick={() => setSource(id)}
              className={`flex items-center gap-2 rounded-md border px-3 py-2 text-[13px] ${source === id ? "border-hud bg-hud/10" : "border-ligne"}`}
            >
              <I className="size-4" /> {libelle}
            </button>
          ))}
        </div>
        <Champ value={titre} onChange={(e) => setTitre(e.target.value)} placeholder={t("Titre (facultatif)")} />
        <Bouton variante="primaire" className="w-full" icone={<Play className="size-4" />} chargement={envoi} disabled={!choisi} onClick={lancer}>
          {t("Lancer sur {appareil}", { appareil: choisi?.nom ?? "?" })}
        </Bouton>
        {etat && <p className="text-[12px] text-doux">{etat}</p>}
      </div>
    </Section>
  );
}

/** Transcriptions de réunions faites sur tes ordinateurs : lecture ici, reprise sur l'ordinateur d'origine. */
export function Transcriptions() {
  const { liste, charge } = usePartages();
  const transcriptions = liste.filter((x) => x.genre === "transcription").sort((a, b) => (b.resume.debut || 0) - (a.resume.debut || 0));
  const [choisie, setChoisie] = useState<string | null>(null);
  const detail = transcriptions.find((x) => x.resume.id === choisie);
  useEffect(() => void chargerPartages(), []);
  const [q, setQ] = useState("");
  const [trouves, setTrouves] = useState<Trouve[] | null>(null);
  useEffect(() => {
    if (q.trim().length < 2) return setTrouves(null);
    const m = setTimeout(() => void chercher(q, 30).then(setTrouves).catch(() => setTrouves([])), 400);
    return () => clearTimeout(m);
  }, [q]);
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
      <div className="px-3 pt-3">
        <Champ value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Chercher dans toutes les transcriptions…")} />
      </div>
      {trouves && (
        <Section titre={t("Résultats")}>
          {trouves.length === 0 ? (
            <p className="p-3 text-[13px] text-doux">{t("Rien trouvé.")}</p>
          ) : (
            trouves.map((r, i) => (
              <Ligne key={i} onClick={() => setChoisie(r.id)}>
                <div className="min-w-0 flex-1">
                  <div className="flex gap-2 text-[12px]">
                    <span className="truncate font-medium">{r.titre}</span>
                    {r.debut >= 0 && <span className="flex-none font-mono text-tres-doux">{horodatage(r.debut)}</span>}
                  </div>
                  <div className="line-clamp-2 text-[12px] text-doux">
                    {r.locuteur && <span className="text-hud">{r.locuteur} : </span>}
                    {r.texte}
                  </div>
                </div>
              </Ligne>
            ))
          )}
        </Section>
      )}
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
      <Enregistreur />
      <Lancement />
      {detail && <DetailTranscription p={detail} onFermer={() => setChoisie(null)} />}
    </div>
  );
}
