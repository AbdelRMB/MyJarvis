import { t } from "../lib/i18n";
import { Activity, ChevronRight, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bouton, Champ, EnTetePage, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import type { Action } from "../lib/types";
import { bus } from "../stores/wesley";
import { toast } from "../stores/toasts";

const estErreur = (r: string | null) => !!r && /^Erreur/.test(r);

function Ligne({ a }: { a: Action }) {
  const [ouvert, setOuvert] = useState(false);
  const args = Object.entries(a.args);
  return (
    <li className="border-b border-ligne last:border-0">
      <button onClick={() => setOuvert(!ouvert)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-white/[0.02]" aria-expanded={ouvert}>
        <span className={cx("size-2 flex-none rounded-full", a.resultat === null ? "bg-ambre" : estErreur(a.resultat) ? "bg-rouge" : "bg-vert")} />
        <span className="w-36 flex-none font-mono text-xs text-tres-doux max-sm:hidden">{a.date}</span>
        <span className="w-44 flex-none truncate font-mono text-[13px] text-ambre">{a.outil}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-doux">{args.map(([k, v]) => `${k}=${String(v)}`).join("  ")}</span>
        <ChevronRight className={cx("size-4 flex-none text-tres-doux transition-transform", ouvert && "rotate-90")} />
      </button>
      {ouvert && (
        <div className="grid gap-3 bg-black/20 px-4 pt-1 pb-4 lg:grid-cols-2">
          <div>
            <div className="titre-hud mb-1.5 text-[10px] text-doux">{t("Paramètres")}</div>
            <pre className="max-h-72 overflow-auto rounded bg-black/40 p-3 font-mono text-xs whitespace-pre-wrap text-texte">{JSON.stringify(a.args, null, 2)}</pre>
          </div>
          <div>
            <div className="titre-hud mb-1.5 text-[10px] text-doux">{t("Résultat")}</div>
            <pre className={cx("max-h-72 overflow-auto rounded bg-black/40 p-3 font-mono text-xs whitespace-pre-wrap", estErreur(a.resultat) ? "text-rouge" : "text-doux")}>
              {a.resultat ?? "(pas de résultat enregistré)"}
            </pre>
          </div>
        </div>
      )}
    </li>
  );
}

export function VueActivite() {
  const [actions, setActions] = useState<Action[]>([]);
  const [filtre, setFiltre] = useState("");
  const [chargement, setChargement] = useState(false);

  const charger = async () => {
    setChargement(true);
    try {
      setActions(await api<Action[]>("/api/actions?n=400"));
    } catch (e) {
      toast((e as Error).message, "erreur");
    } finally {
      setChargement(false);
    }
  };

  useEffect(() => {
    charger();
    const maj = () => setTimeout(charger, 300);
    bus.addEventListener("fin", maj);
    return () => bus.removeEventListener("fin", maj);
  }, []);

  const stats = useMemo(() => {
    const c = new Map<string, number>();
    actions.forEach((a) => c.set(a.outil, (c.get(a.outil) ?? 0) + 1));
    return [...c.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [actions]);

  const visibles = useMemo(() => {
    const f = filtre.trim().toLowerCase();
    return f ? actions.filter((a) => a.outil.includes(f) || JSON.stringify(a.args).toLowerCase().includes(f)) : actions;
  }, [actions, filtre]);

  const erreurs = actions.filter((a) => estErreur(a.resultat)).length;

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Activité")}
        sousTitre={t("Journal de toutes les actions exécutées sur ton PC (logs/actions.log).")}
        actions={
          <Bouton icone={<RefreshCw className={cx("size-4", chargement && "animate-spin")} />} onClick={charger}>
            {t("Actualiser")}
          </Bouton>
        }
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        {[
          ["Actions", actions.length, "text-hud"],
          ["Outils différents", new Set(actions.map((a) => a.outil)).size, "text-hud"],
          ["Erreurs", erreurs, erreurs ? "text-rouge" : "text-vert"],
        ].map(([l, v, c]) => (
          <div key={l as string} className="coins border border-ligne bg-surface/60 p-4">
            <div className="titre-hud text-[10px] text-doux">{l}</div>
            <div className={cx("mt-1 font-display text-2xl font-bold", c as string)}>{v}</div>
          </div>
        ))}
      </div>

      {stats.length > 0 && (
        <div className="mb-6 flex flex-wrap gap-2">
          {stats.map(([o, n]) => (
            <button key={o} onClick={() => setFiltre(filtre === o ? "" : o)} className={cx("rounded-full border px-3 py-1 font-mono text-xs", filtre === o ? "border-ambre bg-ambre/10 text-ambre" : "border-ligne text-doux hover:text-texte")}>
              {o} <span className="opacity-60">×{n}</span>
            </button>
          ))}
        </div>
      )}

      <div className="coins border border-ligne bg-surface/60">
        <div className="flex items-center gap-3 border-b border-ligne px-4 py-2">
          <Search className="size-4 text-doux" />
          <Champ value={filtre} onChange={(e) => setFiltre(e.target.value)} placeholder={t("Filtrer par outil ou paramètre…")} className="h-9 border-0 bg-transparent px-0" />
        </div>
        {visibles.length === 0 ? (
          <Vide icone={<Activity />} titre={t("Aucune action")} texte={t("Les actions de Wesley sur ton PC apparaîtront ici.")} />
        ) : (
          <ul>
            {visibles.map((a, i) => (
              <Ligne key={`${a.date}-${i}`} a={a} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
