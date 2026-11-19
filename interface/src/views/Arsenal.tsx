import { t } from "../lib/i18n";
import { Code2, Cpu, FolderOpen, Globe, Brain, Monitor, MousePointer2, Search, Sparkles, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge, Champ, EnTetePage } from "../components/ui";
import { api } from "../lib/api";
import type { Outil } from "../lib/types";
import { useReglages } from "../stores/reglages";
import { toast } from "../stores/toasts";

const MODULES: Record<string, { libelle: string; icone: typeof Wrench }> = {
  systeme: { libelle: t("Système"), icone: Cpu },
  fichiers: { libelle: t("Fichiers"), icone: FolderOpen },
  controle: { libelle: t("Souris, clavier & fenêtres"), icone: MousePointer2 },
  ecran: { libelle: t("Vision"), icone: Monitor },
  code: { libelle: t("Code"), icone: Code2 },
  web: { libelle: t("Web"), icone: Globe },
  memoire_outils: { libelle: t("Mémoire"), icone: Brain },
  divers: { libelle: t("Divers"), icone: Sparkles },
};

export function VueArsenal() {
  const [outils, setOutils] = useState<Outil[]>([]);
  const [filtre, setFiltre] = useState("");
  const maj = useReglages((s) => s.maj);

  useEffect(() => {
    api<Outil[]>("/api/outils").then(setOutils).catch((e) => toast(e.message, "erreur"));
  }, []);

  const groupes = useMemo(() => {
    const f = filtre.trim().toLowerCase();
    const g = new Map<string, Outil[]>();
    outils
      .filter((o) => !f || o.nom.includes(f) || o.description.toLowerCase().includes(f))
      .forEach((o) => g.set(o.module, [...(g.get(o.module) ?? []), o]));
    return [...g.entries()];
  }, [outils, filtre]);

  const essayer = (o: Outil) => {
    maj({ vue: "assistant" });
    setTimeout(() => window.dispatchEvent(new CustomEvent("jarvis:pre-remplir", { detail: `Utilise ${o.nom} pour ` })), 50);
  };

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Arsenal")}
        sousTitre={t("{n} outils que Jarvis peut utiliser sur ton PC, sans demander la permission.", { n: outils.length })}
        actions={
          <div className="relative w-64">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-doux" />
            <Champ value={filtre} onChange={(e) => setFiltre(e.target.value)} placeholder={t("Chercher un outil…")} className="h-9 pl-9" />
          </div>
        }
      />
      <div className="space-y-8">
        {groupes.map(([m, os]) => {
          const info = MODULES[m] ?? { libelle: m, icone: Wrench };
          const I = info.icone;
          return (
            <section key={m}>
              <h2 className="mb-3 flex items-center gap-2">
                <I className="size-4 text-hud" />
                <span className="titre-hud text-xs text-hud">{info.libelle}</span>
                <Badge ton="doux">{os.length}</Badge>
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {os.map((o) => (
                  <article key={o.nom} className="group flex flex-col rounded-md border border-ligne bg-surface/60 p-4 transition-colors hover:border-ligne-forte">
                    <div className="font-mono text-[13px] font-semibold text-ambre">{o.nom}</div>
                    <p className="mt-1.5 flex-1 text-sm leading-relaxed text-doux">{o.description}</p>
                    {o.params.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {o.params.map((p) => (
                          <span key={p.nom} title={p.description} className="rounded border border-ligne px-1.5 py-0.5 font-mono text-[11px] text-tres-doux">
                            {p.nom}
                            {!p.requis && "?"}
                            <span className="text-hud-sombre">: {p.type}</span>
                          </span>
                        ))}
                      </div>
                    )}
                    <button onClick={() => essayer(o)} className="mt-3 self-start text-xs text-hud opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100">
                      {t("Utiliser →")}
                    </button>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
