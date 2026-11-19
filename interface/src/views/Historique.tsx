import { t } from "../lib/i18n";
import { History, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Markdown } from "../components/Markdown";
import { Champ, EnTetePage, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx, jourLisible } from "../lib/format";
import type { EntreeHistorique, JourHistorique } from "../lib/types";
import { toast } from "../stores/toasts";

export function VueHistorique() {
  const [jours, setJours] = useState<JourHistorique[]>([]);
  const [jour, setJour] = useState<string | null>(null);
  const [entrees, setEntrees] = useState<EntreeHistorique[]>([]);
  const [filtre, setFiltre] = useState("");

  useEffect(() => {
    api<JourHistorique[]>("/api/historique")
      .then((j) => {
        setJours(j);
        if (j[0]) setJour(j[0].jour);
      })
      .catch((e) => toast(e.message, "erreur"));
  }, []);

  useEffect(() => {
    if (jour) api<EntreeHistorique[]>(`/api/historique/${jour}`).then(setEntrees).catch((e) => toast(e.message, "erreur"));
  }, [jour]);

  const visibles = useMemo(() => {
    const f = filtre.trim().toLowerCase();
    return f ? entrees.filter((e) => e.texte.toLowerCase().includes(f)) : entrees;
  }, [entrees, filtre]);

  return (
    <div className="flex h-full min-h-0 flex-col p-4 md:p-8">
      <EnTetePage titre={t("Historique")} sousTitre={t("Toutes tes conversations avec Jarvis, jour par jour.")} />
      {jours.length === 0 ? (
        <Vide icone={<History />} titre={t("Aucune conversation")} texte={t("Les échanges apparaîtront ici dès ta première demande.")} />
      ) : (
        <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[260px_1fr]">
          <ul className="space-y-1 overflow-y-auto max-md:max-h-40">
            {jours.map((j) => (
              <li key={j.jour}>
                <button
                  onClick={() => setJour(j.jour)}
                  className={cx(
                    "w-full rounded-md border px-3 py-2.5 text-left transition-colors",
                    j.jour === jour ? "border-hud/40 bg-hud/10" : "border-transparent hover:bg-white/[0.03]",
                  )}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className={cx("text-sm font-medium capitalize", j.jour === jour && "text-hud")}>{jourLisible(j.jour)}</span>
                    <span className="font-mono text-[11px] text-tres-doux">{j.nb}</span>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-doux">{j.apercu}</div>
                </button>
              </li>
            ))}
          </ul>
          <div className="coins flex min-h-0 flex-col border border-ligne bg-surface/60">
            <div className="flex items-center gap-3 border-b border-ligne p-3">
              <Search className="size-4 text-doux" />
              <Champ value={filtre} onChange={(e) => setFiltre(e.target.value)} placeholder={t("Chercher dans cette journée…")} className="h-8 border-0 bg-transparent px-0" />
            </div>
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4 md:p-6">
              {visibles.map((e, i) => (
                <div key={i} className={cx("flex gap-4", e.role === "user" && "flex-row-reverse text-right")}>
                  <span className="mt-1 w-16 flex-none font-mono text-[11px] text-tres-doux">
                    {e.heure}
                    {e.pc && <span className="block truncate text-[10px] opacity-70">{e.pc}</span>}
                  </span>
                  <div
                    className={cx(
                      "max-w-[85%] min-w-0",
                      e.role === "user" ? "rounded-2xl rounded-br-sm border border-hud/25 bg-hud/10 px-4 py-2 text-hud-clair" : "border-l-2 border-hud/40 pl-4 text-left",
                    )}
                  >
                    {e.role === "jarvis" ? <Markdown texte={e.texte} /> : <span className="whitespace-pre-wrap">{e.texte}</span>}
                  </div>
                </div>
              ))}
              {visibles.length === 0 && <p className="text-center text-sm text-doux">{t("Rien ne correspond.")}</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
