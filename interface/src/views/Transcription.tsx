import { AudioLines, Check, Copy, FileAudio, FileText, FolderOpen, Loader2, Merge, Mic, Monitor, Pencil, Play, Square, Trash2, Upload, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Bouton, Champ, EnTetePage, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { LANGUE, t } from "../lib/i18n";
import { bus } from "../stores/wesley";
import { toast } from "../stores/toasts";

type Source = "systeme" | "micro" | "fichier";
type Etat = "preparation" | "en_cours" | "finalisation" | "terminee" | "erreur" | "interrompue";
type Resume = {
  id: string;
  titre: string;
  debut: number;
  duree: number;
  source: Source;
  avec_micro: boolean;
  etat: Etat;
  fichier: string;
  erreur: string;
  nb_locuteurs: number;
  nb_phrases: number;
};
type Segment = { debut: number; fin: number; locuteur: number; texte: string };
type Locuteur = { id: number; nom: string; duree: number; phrases: number };
type Session = Resume & {
  segments: Segment[];
  noms: Record<string, string>;
  langue: string;
  modele: string;
  empreinte: string;
  locuteurs?: Locuteur[];
  regroupable?: boolean;
  niveau?: number;
  retard?: number;
};
type Liste = { liste: Resume[]; en_cours: Session | null; modeles: string[]; modele: string; dossier: string; plateforme: string };

const COULEURS = ["#3ce8ff", "#ffb547", "#5ef38c", "#ff6b9d", "#b18cff", "#ff8a4c", "#4cc3ff", "#e8e35a", "#7cf0d0", "#ff5c5c"];
const couleur = (l: number) => COULEURS[(l - 1) % COULEURS.length];

const ETATS: Record<Etat, [string, "hud" | "ambre" | "rouge" | "vert" | "doux"]> = {
  preparation: ["Préparation…", "ambre"],
  en_cours: ["En cours", "hud"],
  finalisation: ["Finalisation…", "ambre"],
  terminee: ["Terminée", "vert"],
  erreur: ["Erreur", "rouge"],
  interrompue: ["Interrompue", "doux"],
};

function horodatage(s: number) {
  const x = Math.max(0, Math.floor(s));
  const h = Math.floor(x / 3600);
  const m = Math.floor((x % 3600) / 60);
  const sec = x % 60;
  const p = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(sec)}` : `${p(m)}:${p(sec)}`;
}

const nomDe = (s: Session, l: number) => s.noms?.[String(l)]?.trim() || t("Locuteur {n}", { n: l });
const actif = (e?: Etat) => e === "preparation" || e === "en_cours" || e === "finalisation";

function Pastille({ l, nom, petite }: { l: number; nom: string; petite?: boolean }) {
  return (
    <span className={cx("inline-flex max-w-full items-center gap-1.5 font-medium", petite ? "text-[12px]" : "text-[13px]")} style={{ color: couleur(l) }}>
      <span className="size-2 flex-none rounded-full" style={{ background: couleur(l), boxShadow: `0 0 6px ${couleur(l)}` }} />
      <span className="truncate">{nom}</span>
    </span>
  );
}

/** Lancement : source (son de l'ordinateur, micro, fichier), options, et suivi de la transcription en cours. */
function PanneauLancement({ infos, enCours, onLance }: { infos: Liste | null; enCours: Session | null; onLance: (id: string) => void }) {
  const [source, setSource] = useState<Source>("systeme");
  const [avecMicro, setAvecMicro] = useState(true);
  const [titre, setTitre] = useState("");
  const [langue, setLangue] = useState(LANGUE === "en" ? "en" : "fr");
  const [modele, setModele] = useState("");
  const [nombre, setNombre] = useState(0);
  const [envoi, setEnvoi] = useState(false);
  const fichier = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (infos && !modele) setModele(infos.modele);
  }, [infos]);

  const lancer = async () => {
    setEnvoi(true);
    try {
      const s = await api<Session>("/api/transcriptions/demarrer", { method: "POST", json: { source, avec_micro: avecMicro, titre, langue, modele, nb_locuteurs: nombre } });
      setTitre("");
      onLance(s.id);
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi(false);
    }
  };
  const importer = async (f: File) => {
    setEnvoi(true);
    try {
      const q = new URLSearchParams({ nom: f.name, langue, modele, nb_locuteurs: String(nombre) });
      const s = await api<Session>(`/api/transcriptions/importer?${q}`, { method: "POST", body: f, headers: { "content-type": "application/octet-stream" } });
      onLance(s.id);
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi(false);
      if (fichier.current) fichier.current.value = "";
    }
  };
  const arreter = async () => {
    try {
      await api("/api/transcriptions/arreter", { method: "POST" });
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };

  if (enCours) {
    const niveau = Math.min(1, Math.sqrt((enCours.niveau ?? 0) / 0.25));
    const fichierEnCours = enCours.source === "fichier";
    return (
      <Panneau titre={t("Transcription en cours")} icone={<AudioLines />}>
        <div className="truncate text-sm font-medium">{enCours.titre}</div>
        <div className="mt-1 flex items-center gap-2 text-[12px] text-doux">
          {enCours.etat === "en_cours" ? <span className="size-2 animate-pulse rounded-full bg-rouge shadow-[0_0_8px] shadow-rouge" /> : <Loader2 className="size-3.5 animate-spin" />}
          {t(ETATS[enCours.etat]?.[0] ?? enCours.etat)}
          <span className="ml-auto font-mono text-base text-texte">{horodatage(enCours.duree)}</span>
        </div>
        {!fichierEnCours && enCours.etat === "en_cours" && (
          <div className="mt-2 h-1.5 overflow-hidden rounded bg-white/5" title={t("Niveau du son capté")}>
            <div className="h-full bg-hud transition-[width] duration-200" style={{ width: `${Math.round(niveau * 100)}%` }} />
          </div>
        )}
        <p className="mt-2 text-[12px] text-doux">
          {enCours.etat === "preparation"
            ? t("Chargement des modèles (la première fois, ils sont téléchargés)…")
            : enCours.etat === "finalisation"
              ? t("Wesley termine les dernières phrases et regroupe les voix…")
              : t("{n} phrase(s), {l} locuteur(s) pour l'instant.", { n: enCours.segments.length, l: new Set(enCours.segments.map((s) => s.locuteur)).size })}
          {!!enCours.retard && enCours.retard > 5 && <> {t("({s} s de retard : le modèle est un peu lent pour cet ordinateur)", { s: Math.round(enCours.retard) })}</>}
        </p>
        {enCours.etat !== "finalisation" && (
          <Bouton className="mt-3 w-full" variante="danger" icone={<Square />} onClick={arreter}>
            {fichierEnCours ? t("Annuler") : t("Arrêter la transcription")}
          </Bouton>
        )}
      </Panneau>
    );
  }

  const SOURCES: { id: Source; libelle: string; aide: string; icone: typeof Mic }[] = [
    { id: "systeme", libelle: t("Réunion en ligne"), aide: t("Le son de l'ordinateur (Teams, Zoom, Meet…)"), icone: Monitor },
    { id: "micro", libelle: t("Réunion physique"), aide: t("Wesley écoute la pièce avec le micro"), icone: Mic },
    { id: "fichier", libelle: t("Fichier audio"), aide: t("Un enregistrement (mp3, m4a, wav, vidéo…)"), icone: FileAudio },
  ];
  return (
    <Panneau titre={t("Nouvelle transcription")} icone={<Play />}>
      <div className="grid gap-1.5">
        {SOURCES.map(({ id, libelle, aide, icone: I }) => (
          <button
            key={id}
            onClick={() => setSource(id)}
            className={cx("flex items-center gap-3 rounded-md border px-3 py-2 text-left", source === id ? "border-hud bg-hud/10" : "border-ligne hover:border-ligne-forte")}
          >
            <I className={cx("size-4 flex-none", source === id ? "text-hud" : "text-doux")} />
            <span className="min-w-0">
              <span className="block text-sm">{libelle}</span>
              <span className="block text-[11px] text-tres-doux">{aide}</span>
            </span>
          </button>
        ))}
      </div>
      {source === "systeme" && (
        <label className="mt-2 flex items-center gap-2 text-[13px] text-doux">
          <input type="checkbox" checked={avecMicro} onChange={(e) => setAvecMicro(e.target.checked)} />
          {t("Ajouter mon micro (pour transcrire aussi ma voix)")}
        </label>
      )}
      {source === "systeme" && infos?.plateforme === "mac" && (
        <p className="mt-1 text-[11px] text-tres-doux">{t("Sur Mac, Wesley a besoin de l'autorisation « Enregistrement de l'écran » pour entendre le son de l'ordinateur.")}</p>
      )}
      {source !== "fichier" && <Champ className="mt-2" placeholder={t("Titre (facultatif)")} value={titre} onChange={(e) => setTitre(e.target.value)} />}
      <div className="mt-2 grid grid-cols-3 gap-2">
        <select value={langue} onChange={(e) => setLangue(e.target.value)} title={t("Langue parlée")} className="h-9 rounded-md border border-ligne-forte bg-surface-2 px-2 text-[13px]">
          <option value="fr">{t("Français")}</option>
          <option value="en">{t("Anglais")}</option>
          <option value="">{t("Auto")}</option>
        </select>
        <select value={modele} onChange={(e) => setModele(e.target.value)} title={t("Modèle de reconnaissance (plus gros = plus précis, plus lent)")} className="h-9 rounded-md border border-ligne-forte bg-surface-2 px-2 text-[13px]">
          {(infos?.modeles ?? ["small"]).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select value={nombre} onChange={(e) => setNombre(+e.target.value)} title={t("Nombre de personnes, s'il est connu")} className="h-9 rounded-md border border-ligne-forte bg-surface-2 px-2 text-[13px]">
          <option value={0}>{t("Personnes : auto")}</option>
          {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
            <option key={n} value={n}>
              {t("{n} personne(s)", { n })}
            </option>
          ))}
        </select>
      </div>
      {source === "fichier" ? (
        <>
          <input ref={fichier} type="file" accept="audio/*,video/*,.m4a,.mp3,.wav,.ogg,.opus,.flac,.webm,.mp4,.mov" className="hidden" onChange={(e) => e.target.files?.[0] && importer(e.target.files[0])} />
          <Bouton className="mt-3 w-full" variante="primaire" icone={<Upload />} chargement={envoi} onClick={() => fichier.current?.click()}>
            {t("Choisir un fichier…")}
          </Bouton>
        </>
      ) : (
        <Bouton className="mt-3 w-full" variante="primaire" icone={<Play />} chargement={envoi} onClick={lancer}>
          {t("Lancer la transcription")}
        </Bouton>
      )}
      <p className="mt-2 text-[11px] text-tres-doux">{t("Tout reste sur ton ordinateur : reconnaissance de la parole et des voix en local.")}</p>
    </Panneau>
  );
}

/** Locuteurs : nommer, fusionner deux étiquettes, refaire la répartition des voix. */
function PanneauLocuteurs({ s, agir }: { s: Session; agir: (action: string, corps: object) => Promise<void> }) {
  const locs = s.locuteurs ?? [];
  const [noms, setNoms] = useState<Record<string, string>>({});
  const [nombre, setNombre] = useState(0);
  useEffect(() => setNoms(Object.fromEntries(locs.map((l) => [String(l.id), s.noms?.[String(l.id)] ?? ""]))), [s.id, JSON.stringify(s.noms), locs.length]);
  const modifie = locs.some((l) => (noms[String(l.id)] ?? "") !== (s.noms?.[String(l.id)] ?? ""));
  const bloque = actif(s.etat);

  return (
    <div className="border-b border-ligne p-4">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold tracking-[0.18em] text-tres-doux uppercase">
        <Users className="size-3.5" /> {t("Locuteurs")}
      </div>
      {locs.length === 0 ? (
        <p className="text-[13px] text-doux">{t("Personne n'a encore parlé.")}</p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {locs.map((l) => (
            <div key={l.id} className="flex items-center gap-2 rounded-md border border-ligne bg-surface-2/40 px-2 py-1.5">
              <span className="size-2.5 flex-none rounded-full" style={{ background: couleur(l.id) }} />
              <input
                value={noms[String(l.id)] ?? ""}
                disabled={bloque}
                placeholder={t("Locuteur {n}", { n: l.id })}
                onChange={(e) => setNoms({ ...noms, [String(l.id)]: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && modifie && agir("noms", { noms })}
                className="h-8 min-w-0 flex-1 rounded border border-transparent bg-transparent px-1.5 text-sm outline-none focus:border-hud"
              />
              <span className="font-mono text-[10px] text-tres-doux" title={t("Temps de parole")}>
                {horodatage(l.duree)}
              </span>
              {locs.length > 1 && !bloque && (
                <label className="relative grid size-7 flex-none cursor-pointer place-items-center rounded text-doux hover:bg-white/5 hover:text-hud" title={t("Fusionner avec un autre locuteur (même personne)")}>
                  <Merge className="size-3.5" />
                <select
                  value=""
                  onChange={(e) => e.target.value && agir("fusionner", { source: l.id, cible: +e.target.value })}
                  className="absolute inset-0 cursor-pointer opacity-0"
                >
                  <option value="">{t("Fusionner avec…")}</option>
                  {locs
                    .filter((x) => x.id !== l.id)
                    .map((x) => (
                      <option key={x.id} value={x.id} className="text-sm">
                        {t("Fusionner dans « {nom} »", { nom: nomDe(s, x.id) })}
                      </option>
                    ))}
                </select>
                </label>
              )}
            </div>
          ))}
        </div>
      )}
      {!bloque && locs.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Bouton taille="sm" variante={modifie ? "primaire" : "contour"} icone={<Check />} disabled={!modifie} onClick={() => agir("noms", { noms })}>
            {t("Enregistrer les noms")}
          </Bouton>
          {s.regroupable && (
            <span className="ml-auto flex items-center gap-1.5">
              <select value={nombre} onChange={(e) => setNombre(+e.target.value)} className="h-8 rounded-md border border-ligne-forte bg-surface-2 px-2 text-[12px]">
                <option value={0}>{t("Auto")}</option>
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                  <option key={n} value={n}>
                    {t("{n} personne(s)", { n })}
                  </option>
                ))}
              </select>
              <Bouton
                taille="sm"
                variante="fantome"
                icone={<Merge />}
                title={t("Refait la répartition des voix ; les noms donnés sont effacés")}
                onClick={() => confirm(t("Refaire la répartition des voix ? Les noms donnés aux locuteurs seront effacés.")) && agir("regrouper", { nombre })}
              >
                {t("Regrouper les voix")}
              </Bouton>
            </span>
          )}
        </div>
      )}
      <p className="mt-2 text-[11px] text-tres-doux">
        {t("Clique sur le nom d'une phrase pour l'attribuer à quelqu'un d'autre. L'icône de fusion réunit deux locuteurs qui sont la même personne.")}
      </p>
    </div>
  );
}

function LignePhrase({ s, i, seg, precedent, agir }: { s: Session; i: number; seg: Segment; precedent?: Segment; agir: (action: string, corps: object) => Promise<void> }) {
  const [edition, setEdition] = useState(false);
  const [texte, setTexte] = useState(seg.texte);
  const nouveauTour = !precedent || precedent.locuteur !== seg.locuteur;
  const bloque = actif(s.etat);
  const locs = s.locuteurs ?? [];
  return (
    <div className={cx("group grid grid-cols-[52px_1fr] gap-x-3", nouveauTour && i > 0 && "mt-3")}>
      <span className="pt-0.5 font-mono text-[11px] text-tres-doux">{horodatage(seg.debut)}</span>
      <div className="min-w-0">
        {nouveauTour &&
          (bloque ? (
            <Pastille l={seg.locuteur} nom={nomDe(s, seg.locuteur)} />
          ) : (
            <label className="relative inline-flex max-w-full cursor-pointer" title={t("Attribuer cette phrase à…")}>
              <Pastille l={seg.locuteur} nom={nomDe(s, seg.locuteur)} />
              <select
                value={seg.locuteur}
                onChange={(e) => agir("locuteur", { index: i, locuteur: +e.target.value })}
                className="absolute inset-0 cursor-pointer opacity-0"
              >
                {locs.map((l) => (
                  <option key={l.id} value={l.id}>
                    {nomDe(s, l.id)}
                  </option>
                ))}
                <option value={0}>{t("+ Nouveau locuteur")}</option>
              </select>
            </label>
          ))}
        {edition ? (
          <textarea
            autoFocus
            rows={2}
            value={texte}
            onChange={(e) => setTexte(e.target.value)}
            onBlur={() => {
              setEdition(false);
              if (texte.trim() !== seg.texte) agir("texte", { index: i, texte });
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) (e.target as HTMLTextAreaElement).blur();
              if (e.key === "Escape") {
                setTexte(seg.texte);
                setEdition(false);
              }
            }}
            className="mt-0.5 w-full rounded border border-hud bg-surface-2 p-1.5 text-[14px] outline-none"
          />
        ) : (
          <p className="flex items-start gap-2 text-[14px] leading-relaxed">
            <span className="min-w-0 flex-1 break-words">{seg.texte}</span>
            {!bloque && (
              <span className="flex flex-none gap-1 opacity-0 group-hover:opacity-100">
                {!nouveauTour && (
                  <label className="relative cursor-pointer" title={t("Attribuer cette phrase à…")}>
                    <span className="size-2.5 rounded-full" style={{ background: couleur(seg.locuteur), display: "inline-block" }} />
                    <select value={seg.locuteur} onChange={(e) => agir("locuteur", { index: i, locuteur: +e.target.value })} className="absolute inset-0 cursor-pointer opacity-0">
                      {locs.map((l) => (
                        <option key={l.id} value={l.id}>
                          {nomDe(s, l.id)}
                        </option>
                      ))}
                      <option value={0}>{t("+ Nouveau locuteur")}</option>
                    </select>
                  </label>
                )}
                <button
                  onClick={() => {
                    setTexte(seg.texte);
                    setEdition(true);
                  }}
                  title={t("Corriger le texte")}
                  className="text-tres-doux hover:text-hud"
                >
                  <Pencil className="size-3.5" />
                </button>
              </span>
            )}
          </p>
        )}
      </div>
    </div>
  );
}

function Detail({ s, recharger, supprime }: { s: Session; recharger: (x?: Session) => void; supprime: () => void }) {
  const [titre, setTitre] = useState(s.titre);
  const defilement = useRef<HTMLDivElement>(null);
  const suivre = useRef(true);
  useEffect(() => setTitre(s.titre), [s.id, s.titre]);
  useEffect(() => {
    const d = defilement.current;
    if (d && actif(s.etat) && suivre.current) d.scrollTop = d.scrollHeight;
  }, [s.segments.length]);

  const agir = async (action: string, corps: object) => {
    try {
      recharger(await api<Session>(`/api/transcriptions/${s.id}/${action}`, { method: "POST", json: corps }));
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const exporter = async (format: "md" | "txt", ouvrir = false) => {
    try {
      const r = await api<{ fichier: string }>(`/api/transcriptions/${s.id}/exporter`, { method: "POST", json: { format, ouvrir } });
      toast(t("Enregistré : {f}", { f: r.fichier }), "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const copier = async () => {
    try {
      const r = await api<{ texte: string }>(`/api/transcriptions/${s.id}/exporter`, { method: "POST", json: { format: "txt" } });
      await navigator.clipboard.writeText(r.texte);
      toast(t("Transcription copiée."), "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const supprimer = async () => {
    if (!confirm(t("Supprimer cette transcription ? Le fichier Markdown dans tes Documents est aussi effacé."))) return;
    try {
      await api(`/api/transcriptions/${s.id}?fichier=true`, { method: "DELETE" });
      supprime();
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const [libelle, ton] = ETATS[s.etat] ?? [s.etat, "doux"];
  const bloque = actif(s.etat);

  return (
    <>
      <div className="border-b border-ligne p-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={titre}
            disabled={bloque}
            onChange={(e) => setTitre(e.target.value)}
            onBlur={() => titre.trim() && titre !== s.titre && agir("titre", { titre })}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
            className="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 text-base font-semibold outline-none hover:border-ligne focus:border-hud"
          />
          <Badge ton={ton}>{t(libelle)}</Badge>
        </div>
        <p className="mt-1 px-1 text-[12px] text-doux">
          {new Date(s.debut * 1000).toLocaleString()} · {horodatage(s.duree)} ·{" "}
          {s.source === "systeme" ? t("son de l'ordinateur") + (s.avec_micro ? " + " + t("micro") : "") : s.source === "micro" ? t("micro") : t("fichier audio")}
          {s.empreinte && ` · ${t("voix")} : ${s.empreinte}`}
        </p>
        {s.erreur && <p className="mt-1 px-1 text-[12px] text-rouge">{s.erreur}</p>}
        {s.fichier && <p className="mt-1 truncate px-1 font-mono text-[11px] text-tres-doux" title={s.fichier}>{s.fichier}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          <Bouton taille="sm" icone={<FileText />} disabled={bloque} onClick={() => exporter("md", true)}>
            {t("Exporter en Markdown")}
          </Bouton>
          <Bouton taille="sm" icone={<FileText />} disabled={bloque} onClick={() => exporter("txt", true)}>
            {t("Exporter en texte")}
          </Bouton>
          <Bouton taille="sm" variante="fantome" icone={<Copy />} onClick={copier}>
            {t("Copier")}
          </Bouton>
          <Bouton taille="sm" variante="fantome" icone={<FolderOpen />} onClick={() => agir("ouvrir", {})}>
            {t("Ouvrir le fichier")}
          </Bouton>
          {!bloque && (
            <Bouton taille="sm" variante="fantome" icone={<Trash2 />} onClick={supprimer}>
              {t("Supprimer")}
            </Bouton>
          )}
        </div>
      </div>
      <PanneauLocuteurs s={s} agir={agir} />
      <div
        ref={defilement}
        onScroll={(e) => {
          const d = e.currentTarget;
          suivre.current = d.scrollHeight - d.scrollTop - d.clientHeight < 80;
        }}
        className="min-h-0 flex-1 overflow-y-auto p-4"
      >
        {s.segments.length === 0 ? (
          <div className="grid h-full place-items-center text-sm text-doux">
            {bloque ? t("Wesley écoute… les phrases apparaissent ici au fil de la conversation.") : t("Rien n'a été transcrit.")}
          </div>
        ) : (
          s.segments.map((seg, i) => <LignePhrase key={`${s.id}-${i}-${seg.debut}`} s={s} i={i} seg={seg} precedent={s.segments[i - 1]} agir={agir} />)
        )}
      </div>
    </>
  );
}

export function VueTranscription() {
  const [infos, setInfos] = useState<Liste | null>(null);
  const [choisie, setChoisie] = useState<string | null>(null);
  const [detail, setDetail] = useState<Session | null>(null);
  const choisieRef = useRef<string | null>(null);

  const charger = () =>
    api<Liste>("/api/transcriptions")
      .then((l) => {
        setInfos(l);
        if (l.en_cours && l.en_cours.id === choisieRef.current) setDetail((d) => ({ ...(d ?? l.en_cours!), ...l.en_cours! }));
      })
      .catch(() => {});
  const chargerDetail = (id: string) =>
    api<Session>(`/api/transcriptions/${id}`)
      .then((s) => id === choisieRef.current && setDetail(s))
      .catch(() => {});

  useEffect(() => {
    charger();
    const sur = (e: Event) => {
      charger();
      const id = (e as CustomEvent<string>).detail;
      if (id && id === choisieRef.current) chargerDetail(id);
    };
    bus.addEventListener("transcription_maj", sur);
    return () => bus.removeEventListener("transcription_maj", sur);
  }, []);
  useEffect(() => {
    choisieRef.current = choisie;
    if (choisie) chargerDetail(choisie);
    else setDetail(null);
  }, [choisie]);
  // pendant une transcription : chronomètre et niveau sonore rafraîchis chaque seconde
  const enCours = infos?.en_cours ?? null;
  useEffect(() => {
    if (!enCours) return;
    const i = setInterval(charger, 1000);
    return () => clearInterval(i);
  }, [enCours?.id]);
  useEffect(() => {
    if (!choisie && infos?.liste.length) setChoisie(infos.en_cours?.id ?? infos.liste[0].id);
  }, [infos?.liste.length]);

  const liste = useMemo(() => infos?.liste ?? [], [infos]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-4 md:p-8 lg:overflow-hidden">
      <EnTetePage
        titre={t("Transcription")}
        sousTitre={t("Wesley écrit tout ce qui se dit pendant une réunion, reconnaît les voix (Locuteur 1, Locuteur 2…) et horodate chaque phrase. Tu nommes ensuite chaque personne et tu exportes le texte.")}
      />
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[340px_1fr]">
        <div className="flex min-h-0 flex-col gap-3">
          <PanneauLancement infos={infos} enCours={enCours} onLance={(id) => { setChoisie(id); charger(); }} />
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
            {liste.length === 0 ? (
              <Vide icone={<AudioLines />} titre={t("Aucune transcription")} texte={t("Lance-en une, ou dis à Wesley : « transcris la réunion »")} />
            ) : (
              liste.map((x) => (
                <button
                  key={x.id}
                  onClick={() => setChoisie(x.id)}
                  className={cx("w-full rounded-md border px-3 py-2.5 text-left", choisie === x.id ? "border-hud bg-hud/10" : "border-ligne bg-surface/60 hover:border-ligne-forte")}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">{x.titre}</span>
                    {actif(x.etat) ? <Loader2 className="size-3.5 flex-none animate-spin text-hud" /> : x.etat !== "terminee" && <Badge ton={ETATS[x.etat]?.[1] ?? "doux"}>{t(ETATS[x.etat]?.[0] ?? x.etat)}</Badge>}
                  </div>
                  <div className="mt-0.5 flex gap-2 text-[11px] text-tres-doux">
                    <span>{new Date(x.debut * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}</span>
                    <span>· {horodatage(x.duree || 0)}</span>
                    <span>· {t("{n} locuteur(s)", { n: x.nb_locuteurs })}</span>
                  </div>
                </button>
              ))
            )}
          </div>
          {infos?.dossier && (
            <p className="truncate font-mono text-[10px] text-tres-doux" title={infos.dossier}>
              {t("Fichiers")} : {infos.dossier}
            </p>
          )}
        </div>

        <div className="flex min-h-[420px] flex-col rounded-md border border-ligne bg-surface/40 lg:min-h-0">
          {!detail ? (
            <div className="grid flex-1 place-items-center text-sm text-doux">{t("Choisis une transcription pour la relire.")}</div>
          ) : (
            <Detail
              s={detail}
              recharger={(x) => {
                if (x) setDetail(x);
                else if (choisie) chargerDetail(choisie);
                charger();
              }}
              supprime={() => {
                setChoisie(null);
                charger();
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
