import { ChevronRight, Code2, LifeBuoy, Plug, Settings, Workflow } from "lucide-react";
import { t } from "../../../src/lib/i18n";
import { useDonnees } from "../moteur/donnees";
import { session } from "../moteur/stockage";
import { allerA, Entete, Ligne, type Vue } from "../ui";

const ENTREES: { vue: Vue; titre: string; detail: string; icone: typeof Plug }[] = [
  { vue: "automatisations", titre: "Automatisations", detail: "Règles « quand… alors… » et routines", icone: Workflow },
  { vue: "services", titre: "Services connectés", detail: "Mails, GitHub, SSH, navigateur, sites appris", icone: Plug },
  { vue: "taches", titre: "Tâches de fond", detail: "Code avec Claude Code sur tes ordinateurs", icone: Code2 },
  { vue: "tickets", titre: "Tickets", detail: "Bugs, idées, questions au développeur", icone: LifeBuoy },
  { vue: "reglages", titre: "Réglages", detail: "Cerveau, voix, compte, ce téléphone", icone: Settings },
];

export function Plus() {
  const { automatisations, connecteurs, tickets } = useDonnees();
  const compteurs: Partial<Record<Vue, number>> = {
    automatisations: automatisations.length,
    services: Object.keys(connecteurs).length,
    tickets: tickets.filter((x) => x.statut !== "ferme").length,
  };
  return (
    <div>
      <Entete titre={t("Plus")} sous={session()?.email} />
      <div className="mt-3 border-t border-ligne">
        {ENTREES.map((e) => (
          <Ligne key={e.vue} onClick={() => allerA(e.vue)}>
            <e.icone className="size-5 flex-none text-hud" />
            <div className="min-w-0 flex-1">
              <div className="text-[15px]">{t(e.titre)}</div>
              <div className="truncate text-[12px] text-doux">{t(e.detail)}</div>
            </div>
            {!!compteurs[e.vue] && <span className="font-mono text-[12px] text-doux">{compteurs[e.vue]}</span>}
            <ChevronRight className="size-4 text-tres-doux" />
          </Ligne>
        ))}
      </div>
    </div>
  );
}
