import { Brain, Plus, Search, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bouton, Champ, EnTetePage, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import type { Fait } from "../lib/types";
import { toast } from "../stores/toasts";

const CATEGORIES = ["identite", "preference", "projet", "contact", "habitude", "general"];
const LIBELLES: Record<string, string> = {
  identite: "Identité",
  preference: "Préférences",
  projet: "Projets",
  contact: "Contacts",
  habitude: "Habitudes",
  general: "Général",
};

export function VueMemoire() {
  const [faits, setFaits] = useState<Fait[]>([]);
  const [filtre, setFiltre] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [nouveau, setNouveau] = useState("");
  const [nouvelleCat, setNouvelleCat] = useState("general");
  const [analyse, setAnalyse] = useState(false);

  const charger = () => api<Fait[]>("/api/memoire").then(setFaits).catch((e) => toast(e.message, "erreur"));
  useEffect(() => {
    charger();
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
      await api("/api/memoire", { method: "DELETE", json: { fait: f.fait } });
      setFaits((x) => x.filter((y) => y.fait !== f.fait));
      toast("Souvenir effacé.");
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };

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
        titre="Mémoire"
        sousTitre={`${faits.length} souvenirs sur toi — Jarvis les relit à chaque conversation.`}
        actions={
          <Bouton icone={<Sparkles className="size-4" />} chargement={analyse} onClick={memoriserSession}>
            Mémoriser la session
          </Bouton>
        }
      />

      <div className="coins mb-6 flex flex-wrap gap-2 border border-ligne bg-surface/60 p-3">
        <Champ
          value={nouveau}
          onChange={(e) => setNouveau(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ajouter()}
          placeholder="Apprendre quelque chose à Jarvis… (ex : je bosse surtout le soir)"
          className="min-w-[240px] flex-1"
        />
        <select
          value={nouvelleCat}
          onChange={(e) => setNouvelleCat(e.target.value)}
          className="h-10 rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
          aria-label="Catégorie"
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {LIBELLES[c]}
            </option>
          ))}
        </select>
        <Bouton variante="primaire" icone={<Plus className="size-4" />} onClick={ajouter} disabled={!nouveau.trim()}>
          Ajouter
        </Bouton>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <div className="relative mr-2 w-full sm:w-64">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-doux" />
          <Champ value={filtre} onChange={(e) => setFiltre(e.target.value)} placeholder="Rechercher…" className="h-9 pl-9" />
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
        <Vide icone={<Brain />} titre={faits.length ? "Aucun résultat" : "Mémoire vide"} texte="Jarvis mémorise tout seul ce qu'il apprend sur toi au fil des conversations." />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {groupes.map(([c, fs]) => (
            <section key={c}>
              <h2 className="titre-hud mb-3 text-[11px] text-ambre">{LIBELLES[c] ?? c}</h2>
              <ul className="space-y-1.5">
                {fs.map((f) => (
                  <li key={f.fait} className="group flex items-start gap-3 rounded-md border border-ligne bg-surface/60 px-3.5 py-2.5 hover:border-ligne-forte">
                    <span className="mt-2 size-1.5 flex-none rounded-full bg-hud" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm leading-relaxed">{f.fait}</p>
                      {f.date && <p className="mt-0.5 font-mono text-[11px] text-tres-doux">{f.date}</p>}
                    </div>
                    <button
                      onClick={() => supprimer(f)}
                      aria-label="Oublier"
                      title="Oublier"
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
