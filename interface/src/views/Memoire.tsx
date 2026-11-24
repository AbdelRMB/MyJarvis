import { t } from "../lib/i18n";
import { Brain, Check, FileText, FolderPlus, History, Pencil, Plus, RefreshCw, RotateCcw, Search, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bouton, Champ, EnTetePage, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import type { Fait } from "../lib/types";
import { bus } from "../stores/wesley";
import { toast } from "../stores/toasts";

const CATEGORIES = ["consigne", "identite", "preference", "projet", "contact", "habitude", "general", "lecon", "journal"];
const LIBELLES: Record<string, string> = {
  identite: "Identité",
  preference: "Préférences",
  projet: "Projets",
  contact: "Contacts",
  habitude: "Habitudes",
  general: "Général",
  lecon: "Leçons apprises",
  consigne: "Consignes pour Wesley",
  journal: "Résumés des semaines",
};

type Intelligence = {
  semantique: { active: boolean; disponible: boolean; telechargement: boolean; erreur: string };
  propositions: { id: string; question: string; ancien: string; garde: string; type?: string }[];
  rangement?: { fusions: number; contradictions: number; semaine?: string | null; date: string } | null;
  couts: { mois?: number; budget?: number; economie?: boolean };
  nb_lecons: number;
};

type EtatDocs = { dossiers: string[]; fichiers: number; passages: number; illisibles: string[]; indexation: boolean; erreur: string };
type Passage = { fichier: string; page: number; texte: string };

/** Les documents que Wesley sait lire (PDF, Word, textes), indexés par le sens sur cet ordinateur. */
function PanneauDocuments() {
  const [e, setE] = useState<EtatDocs | null>(null);
  const [chemin, setChemin] = useState("");
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Passage[] | null>(null);
  const charger = () =>
    api<EtatDocs>("/api/documents")
      .then(setE)
      .catch(() => {});
  useEffect(() => {
    charger();
    const i = setInterval(charger, 10_000);
    return () => clearInterval(i);
  }, []);
  const agir = async (action: string, corps: object = {}) => {
    try {
      setE(await api<EtatDocs>(`/api/documents/${action}`, { method: "POST", json: corps }));
      if (action === "ajouter") setChemin("");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const chercher = async () => {
    if (!q.trim()) return;
    try {
      setRes((await api<{ resultats: Passage[] }>("/api/documents/chercher", { method: "POST", json: { question: q } })).resultats);
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  if (!e) return null;
  return (
    <div className="coins mb-6 border border-ligne bg-surface/60 p-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-doux">
        <span className="flex items-center gap-1.5 font-semibold text-texte">
          <FileText className="size-4 text-hud" /> {t("Documents")}
        </span>
        <span>
          {t("{f} fichier(s), {p} passage(s)", { f: e.fichiers, p: e.passages })}
          {e.indexation && ` · ${t("lecture en cours…")}`}
        </span>
        <span className="text-tres-doux">{t("PDF, Word, textes : Wesley y cherche par le sens et cite le fichier et la page.")}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {e.dossiers.map((d) => (
          <span key={d} className="inline-flex items-center gap-1 rounded border border-ligne px-2 py-0.5 font-mono text-[11px]">
            {d}
            <button onClick={() => agir("retirer", { chemin: d })} title={t("Retirer")} className="text-tres-doux hover:text-rouge">
              <X className="size-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <Champ className="min-w-48 flex-1" placeholder={t("Dossier à lire (ex : ~/Documents/Administratif)")} value={chemin} onChange={(x) => setChemin(x.target.value)} />
        <Bouton taille="sm" icone={<FolderPlus className="size-4" />} disabled={!chemin.trim()} onClick={() => agir("ajouter", { chemin })}>
          {t("Ajouter")}
        </Bouton>
        {e.dossiers.length > 0 && (
          <>
            <Champ
              className="min-w-48 flex-1"
              placeholder={t("Essayer : qu'est-ce que dit mon bail sur le préavis ?")}
              value={q}
              onChange={(x) => setQ(x.target.value)}
              onKeyDown={(x) => x.key === "Enter" && chercher()}
            />
            <Bouton taille="sm" variante="fantome" icone={<Search className="size-4" />} onClick={chercher}>
              {t("Chercher")}
            </Bouton>
          </>
        )}
      </div>
      {res && (
        <div className="mt-2 max-h-72 space-y-2 overflow-y-auto">
          {res.length === 0 ? (
            <p className="text-[12px] text-doux">{t("Rien trouvé.")}</p>
          ) : (
            res.map((r, i) => (
              <div key={i} className="rounded border border-ligne p-2 text-[12px]">
                <div className="font-mono text-[11px] text-hud" title={r.fichier}>
                  {r.fichier.split(/[\/]/).pop()}
                  {r.page ? ` · p. ${r.page}` : ""}
                </div>
                <div className="line-clamp-4 text-doux">{r.texte}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

/** Ce qui rend Wesley plus malin : mémoire par le sens, rangement automatique, leçons, budget. */
function PanneauIntelligence({ recharger }: { recharger: () => void }) {
  const [e, setE] = useState<Intelligence | null>(null);
  const [rangement, setRangement] = useState(false);
  const charger = () =>
    api<Intelligence>("/api/memoire/intelligence")
      .then(setE)
      .catch(() => {});
  useEffect(() => {
    charger();
    const i = setInterval(charger, 15_000);
    return () => clearInterval(i);
  }, []);
  if (!e) return null;
  const repondre = async (id: string, accepter: boolean) => {
    try {
      toast((await api<{ message: string }>(`/api/memoire/propositions/${id}`, { method: "POST", json: { accepter } })).message, "succes");
      charger();
      recharger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const ranger = async () => {
    setRangement(true);
    try {
      const r = await api<{ fusions: number; contradictions: number; semaine?: string }>("/api/memoire/ranger", { method: "POST" });
      toast(t("Mémoire rangée : {f} doublon(s) fusionné(s), {c} à vérifier.", { f: r.fusions ?? 0, c: r.contradictions ?? 0 }), "succes");
      charger();
      recharger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setRangement(false);
    }
  };
  const s = e.semantique;
  const sens = !s.active
    ? t("désactivée (Réglages › Habitudes)")
    : s.disponible
      ? t("prête")
      : s.telechargement
        ? t("téléchargement du modèle (~270 Mo, une seule fois)…")
        : t("modèle pas encore téléchargé") + (s.erreur ? ` (${s.erreur.slice(0, 80)})` : "");
  return (
    <div className="coins mb-6 border border-ligne bg-surface/60 p-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-doux">
        <span className="flex items-center gap-1.5 font-semibold text-texte">
          <Brain className="size-4 text-hud" /> {t("Intelligence")}
        </span>
        <span>
          {t("Recherche par le sens")} : <span className={s.disponible && s.active ? "text-vert" : ""}>{sens}</span>
        </span>
        <span>{t("{n} leçon(s) apprise(s)", { n: e.nb_lecons })}</span>
        {e.rangement && <span>{t("Dernier rangement : {d}", { d: new Date(e.rangement.date).toLocaleString([], { dateStyle: "short", timeStyle: "short" }) })}</span>}
        {!!e.couts?.budget && (
          <span className={e.couts.economie ? "text-ambre" : ""}>
            {t("Ce mois-ci : {m} $ / {b} $", { m: (e.couts.mois ?? 0).toFixed(2), b: e.couts.budget.toFixed(2) })}
            {e.couts.economie && ` · ${t("mode économie")}`}
          </span>
        )}
        <Bouton taille="sm" variante="fantome" className="ml-auto" icone={<Sparkles className="size-4" />} chargement={rangement} onClick={ranger}>
          {t("Ranger maintenant")}
        </Bouton>
      </div>
      {e.propositions.length > 0 && (
        <div className="mt-3 space-y-2">
          <div className="text-[12px] font-semibold text-ambre">{t("À vérifier")}</div>
          {e.propositions.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center gap-2 rounded-md border border-ambre/40 bg-ambre/5 px-3 py-2 text-[13px]">
              <span className="min-w-0 flex-1">
                {p.question}
                {p.type !== "routine" && (
                  <span className="block text-[11px] text-tres-doux">
                    {t("Souvenir concerné")} : « {p.ancien} »
                  </span>
                )}
              </span>
              <Bouton taille="sm" variante="primaire" icone={<Check className="size-4" />} onClick={() => repondre(p.id, true)}>
                {p.type === "routine" ? t("Oui, automatise") : t("Oui, mets à jour")}
              </Bouton>
              <Bouton taille="sm" variante="fantome" icone={<X className="size-4" />} onClick={() => repondre(p.id, false)}>
                {p.type === "routine" ? t("Non merci") : t("Non, garde-le")}
              </Bouton>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function VueMemoire() {
  const [faits, setFaits] = useState<Fait[]>([]);
  const [filtre, setFiltre] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [nouveau, setNouveau] = useState("");
  const [nouvelleCat, setNouvelleCat] = useState("general");
  const [analyse, setAnalyse] = useState(false);
  const [actualisation, setActualisation] = useState(false);

  /** Récupère du compte ce que tes autres appareils ont appris (sans attendre la synchro automatique). */
  const actualiser = async () => {
    setActualisation(true);
    try {
      const avant = faits.length;
      await api("/api/compte/synchroniser", { method: "POST" });
      const apres = await api<Fait[]>("/api/memoire");
      setFaits(apres);
      const n = apres.length - avant;
      toast(n > 0 ? `${n} nouveau${n > 1 ? "x" : ""} souvenir${n > 1 ? "s" : ""} récupéré${n > 1 ? "s" : ""}.` : "Mémoire à jour.", "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setActualisation(false);
    }
  };

  const charger = () => api<Fait[]>("/api/memoire").then(setFaits).catch((e) => toast(e.message, "erreur"));
  useEffect(() => {
    charger();
    // un autre appareil a ajouté, modifié ou supprimé un souvenir : la liste se met à jour toute seule
    const sur = () => charger();
    bus.addEventListener("memoire_maj", sur);
    return () => bus.removeEventListener("memoire_maj", sur);
  }, []);

  const categories = useMemo(() => {
    const c = new Map<string, number>();
    faits.forEach((f) => c.set(f.categorie, (c.get(f.categorie) ?? 0) + 1));
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  }, [faits]);

  const groupes = useMemo(() => {
    const f = filtre.trim().toLowerCase();
    const g = new Map<string, Fait[]>();
    faits
      .filter((x) => (!cat || x.categorie === cat) && (!f || x.fait.toLowerCase().includes(f)))
      .forEach((x) => g.set(x.categorie, [...(g.get(x.categorie) ?? []), x]));
    return [...g.entries()];
  }, [faits, filtre, cat]);

  const ajouter = async () => {
    if (!nouveau.trim()) return;
    try {
      const r = await api<{ message: string }>("/api/memoire", { method: "POST", json: { fait: nouveau, categorie: nouvelleCat } });
      toast(r.message, "succes");
      setNouveau("");
      charger();
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };

  const supprimer = async (f: Fait) => {
    try {
      await api("/api/memoire", { method: "DELETE", json: { fid: f.fid ?? "", fait: f.fait } });
      setFaits((x) => x.filter((y) => (f.fid ? y.fid !== f.fid : y.fait !== f.fait)));
      toast(t("Souvenir effacé sur tous tes appareils."));
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };

  const [edition, setEdition] = useState<{ fid: string; texte: string } | null>(null);
  const enregistrerEdition = async () => {
    if (!edition?.texte.trim()) return setEdition(null);
    try {
      await api("/api/memoire", { method: "PUT", json: { fid: edition.fid, fait: edition.texte } });
      setEdition(null);
      charger();
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };

  const [journalOuvert, setJournalOuvert] = useState(false);

  const memoriserSession = async () => {
    setAnalyse(true);
    try {
      const r = await api<{ faits: string[] }>("/api/memoriser_session", { method: "POST" });
      toast(r.faits.length ? `${r.faits.length} nouveau(x) souvenir(s)` : "Rien de nouveau à retenir.", "succes");
      charger();
    } catch (e) {
      toast((e as Error).message, "erreur");
    } finally {
      setAnalyse(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Mémoire")}
        sousTitre={t("{n} souvenirs sur toi — Wesley les relit à chaque conversation.", { n: faits.length })}
        actions={
          <div className="flex flex-wrap gap-2">
            <Bouton variante="fantome" icone={<RefreshCw className="size-4" />} chargement={actualisation} onClick={actualiser}>
              {t("Actualiser")}
            </Bouton>
            <Bouton variante="fantome" icone={<History className="size-4" />} onClick={() => setJournalOuvert((x) => !x)}>
              {t("Historique")}
            </Bouton>
            <Bouton icone={<Sparkles className="size-4" />} chargement={analyse} onClick={memoriserSession}>
              {t("Mémoriser la session")}
            </Bouton>
          </div>
        }
      />

      {journalOuvert && <JournalMemoire onRestaure={charger} />}

      <PanneauIntelligence recharger={charger} />
      <PanneauDocuments />

      <div className="coins mb-6 flex flex-wrap gap-2 border border-ligne bg-surface/60 p-3">
        <Champ
          value={nouveau}
          onChange={(e) => setNouveau(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ajouter()}
          placeholder={t("Apprendre quelque chose à Wesley… (ex : je bosse surtout le soir)")}
          className="min-w-[240px] flex-1"
        />
        <select
          value={nouvelleCat}
          onChange={(e) => setNouvelleCat(e.target.value)}
          className="h-10 rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
          aria-label={t("Catégorie")}
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {LIBELLES[c]}
            </option>
          ))}
        </select>
        <Bouton variante="primaire" icone={<Plus className="size-4" />} onClick={ajouter} disabled={!nouveau.trim()}>
          {t("Ajouter")}
        </Bouton>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <div className="relative mr-2 w-full sm:w-64">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-doux" />
          <Champ value={filtre} onChange={(e) => setFiltre(e.target.value)} placeholder={t("Rechercher…")} className="h-9 pl-9" />
        </div>
        {[["", faits.length] as [string, number], ...categories].map(([c, n]) => (
          <button
            key={c || "tout"}
            onClick={() => setCat(c || null)}
            className={cx(
              "h-8 rounded-full border px-3 text-[13px] transition-colors",
              (cat ?? "") === c ? "border-hud bg-hud/15 text-hud" : "border-ligne text-doux hover:text-texte",
            )}
          >
            {c ? (LIBELLES[c] ?? c) : "Tout"} <span className="ml-1 font-mono text-[11px] opacity-60">{n}</span>
          </button>
        ))}
      </div>

      {groupes.length === 0 ? (
        <Vide icone={<Brain />} titre={faits.length ? "Aucun résultat" : "Mémoire vide"} texte={t("Wesley mémorise tout seul ce qu'il apprend sur toi au fil des conversations.")} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {groupes.map(([c, fs]) => (
            <section key={c}>
              <h2 className="titre-hud mb-3 text-[11px] text-ambre">{LIBELLES[c] ?? c}</h2>
              <ul className="space-y-1.5">
                {fs.map((f) => (
                  <li key={f.fid ?? f.fait} className="group flex items-start gap-3 rounded-md border border-ligne bg-surface/60 px-3.5 py-2.5 hover:border-ligne-forte">
                    <span className="mt-2 size-1.5 flex-none rounded-full bg-hud" />
                    <div className="min-w-0 flex-1">
                      {edition && edition.fid === f.fid ? (
                        <div className="flex gap-1">
                          <Champ
                            autoFocus
                            value={edition.texte}
                            onChange={(e) => setEdition({ ...edition, texte: e.target.value })}
                            onKeyDown={(e) => (e.key === "Enter" ? enregistrerEdition() : e.key === "Escape" && setEdition(null))}
                            className="h-8 flex-1 text-sm"
                          />
                          <button onClick={enregistrerEdition} aria-label={t("Enregistrer")} className="rounded p-1 text-vert hover:bg-white/5">
                            <Check className="size-4" />
                          </button>
                          <button onClick={() => setEdition(null)} aria-label={t("Annuler")} className="rounded p-1 text-doux hover:bg-white/5">
                            <X className="size-4" />
                          </button>
                        </div>
                      ) : (
                        <p className="text-sm leading-relaxed">{f.fait}</p>
                      )}
                      {f.date && <p className="mt-0.5 font-mono text-[11px] text-tres-doux">{f.date}</p>}
                    </div>
                    {f.fid && !edition && (
                      <button
                        onClick={() => setEdition({ fid: f.fid!, texte: f.fait })}
                        aria-label={t("Modifier")}
                        title={t("Modifier")}
                        className="rounded p-1 text-tres-doux opacity-0 transition-opacity group-hover:opacity-100 hover:text-hud focus:opacity-100"
                      >
                        <Pencil className="size-4" />
                      </button>
                    )}
                    <button
                      onClick={() => supprimer(f)}
                      aria-label={t("Oublier")}
                      title={t("Oublier")}
                      className="rounded p-1 text-tres-doux opacity-0 transition-opacity group-hover:opacity-100 hover:text-rouge focus:opacity-100"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

type EntreeJournal = { fid: string; action: string; fait: string; categorie: string; appareil: string; ts: number; supprime_actuellement: number | null };
const ACTIONS: Record<string, [string, string]> = {
  ajout: ["Ajouté", "text-vert"],
  modification: ["Modifié", "text-hud"],
  utilisation: ["Utilisé", "text-doux"],
  restauration: ["Restauré", "text-vert"],
  suppression: ["Supprimé", "text-rouge"],
};

/** Historique gardé par le serveur : tout ce qui est arrivé à ta mémoire, sur tous tes appareils. */
function JournalMemoire({ onRestaure }: { onRestaure: () => void }) {
  const [j, setJ] = useState<EntreeJournal[] | null>(null);
  const charger = () => api<EntreeJournal[]>("/api/memoire/journal").then(setJ).catch((e) => toast((e as Error).message, "erreur"));
  useEffect(() => {
    charger();
    const sur = () => charger();
    bus.addEventListener("memoire_maj", sur);
    return () => bus.removeEventListener("memoire_maj", sur);
  }, []);
  const restaurer = async (e: EntreeJournal) => {
    try {
      await api("/api/memoire/restaurer", { method: "POST", json: { fid: e.fid, fait: e.fait, categorie: e.categorie } });
      toast(t("Souvenir restauré sur tous tes appareils."), "succes");
      onRestaure();
      setTimeout(charger, 1500);
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  return (
    <div className="coins mb-6 max-h-[360px] overflow-y-auto border border-ligne bg-surface/60 p-3">
      <h2 className="titre-hud mb-2 text-[11px] text-ambre">{t("Historique de ta mémoire (tous tes appareils)")}</h2>
      {!j ? (
        <p className="text-sm text-doux">{t("Chargement…")}</p>
      ) : j.length === 0 ? (
        <p className="text-sm text-doux">{t("Rien pour l'instant.")}</p>
      ) : (
        <ul className="divide-y divide-ligne text-sm">
          {j.map((e, i) => {
            const [libelle, couleur] = ACTIONS[e.action] ?? [e.action, "text-doux"];
            return (
              <li key={i} className="flex items-center gap-3 py-1.5">
                <span className="w-[120px] flex-none font-mono text-[11px] text-tres-doux">
                  {new Date(e.ts * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}
                </span>
                <span className={cx("w-[72px] flex-none text-[12px]", couleur)}>{libelle}</span>
                <span className="min-w-0 flex-1 truncate" title={e.fait}>
                  {e.fait}
                </span>
                {e.appareil && <span className="hidden flex-none font-mono text-[11px] text-tres-doux sm:inline">{e.appareil}</span>}
                {e.action === "suppression" && e.supprime_actuellement === 1 && (
                  <button onClick={() => restaurer(e)} title={t("Restaurer")} className="flex-none rounded p-1 text-doux hover:text-vert">
                    <RotateCcw className="size-4" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
