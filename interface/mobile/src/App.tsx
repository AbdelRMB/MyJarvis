import { Bot, Check, ListChecks, Brain, MonitorSmartphone, Menu, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { Bouton } from "../../src/components/ui";
import { cx } from "../../src/lib/format";
import { t } from "../../src/lib/i18n";
import { annonce, demandeRecue, useAssistant } from "./assistant";
import { recepteur } from "./moteur/appareils";
import { chargerCoffre, quandSessionRevoquee } from "./moteur/compte";
import { useDonnees } from "./moteur/donnees";
import { notifier, surveillerRappels } from "./moteur/rappels";
import { definirSession, session, type Session } from "./moteur/stockage";
import { arreterSynchro, demarrerSynchro, presence } from "./moteur/synchro";
import { debloquerVoix } from "./moteur/voix";
import { allerA, demanderConfirmation, toast, useUi, type Vue } from "./ui";
import { AFaire } from "./vues/AFaire";
import { Appareils } from "./vues/Appareils";
import { Assistant } from "./vues/Assistant";
import { Automatisations } from "./vues/Automatisations";
import { AccordPolitique, Connexion } from "./vues/Connexion";
import { Memoire } from "./vues/Memoire";
import { Plus } from "./vues/Plus";
import { Reglages } from "./vues/Reglages";
import { Services } from "./vues/Services";
import { Taches } from "./vues/Taches";
import { Tickets } from "./vues/Tickets";
import { Transcriptions } from "./vues/Transcriptions";

// ordres reçus des autres appareils : exécutés par le Wesley du téléphone, avec confirmation à l'écran
recepteur.demande = demandeRecue;
// sans réponse en 2 min (téléphone dans la poche), l'ordre est refusé
recepteur.confirmer = (titre, detail) =>
  Promise.race([
    demanderConfirmation(titre, detail),
    new Promise<boolean>((ok) => setTimeout(() => (useUi.setState({ confirmation: null }), ok(false)), 120_000)),
  ]);
recepteur.notifier = (titre, texte) => {
  toast(titre);
  void notifier(titre, texte);
};

const ONGLETS: { id: Vue; libelle: string; icone: typeof Bot }[] = [
  { id: "assistant", libelle: "Wesley", icone: Bot },
  { id: "afaire", libelle: "À faire", icone: ListChecks },
  { id: "memoire", libelle: "Mémoire", icone: Brain },
  { id: "appareils", libelle: "Appareils", icone: MonitorSmartphone },
  { id: "plus", libelle: "Plus", icone: Menu },
];
const SOUS_PLUS: Vue[] = ["automatisations", "services", "taches", "transcriptions", "tickets", "reglages"];

export default function App() {
  const [s, setS] = useState<Session | undefined>(session());
  useEffect(() => quandSessionRevoquee(() => (definirSession(undefined), arreterSynchro(), setS(undefined))), []);

  useEffect(() => {
    if (!s) return;
    void chargerCoffre().catch(() => {});
    demarrerSynchro();
    void presence();
    surveillerRappels((titre) => annonce(`Rappel : ${titre}`));
    const debloquer = () => {
      debloquerVoix();
      window.removeEventListener("touchend", debloquer);
    };
    window.addEventListener("touchend", debloquer);
  }, [s]);

  if (!s) return <Connexion onConnecte={setS} />;
  if (s.politique_actuelle && s.politique !== s.politique_actuelle) return <AccordPolitique onAccepte={() => setS(session())} />;
  return <Coque onDeconnecte={() => (arreterSynchro(), setS(undefined))} />;
}

function Coque({ onDeconnecte }: { onDeconnecte: () => void }) {
  const vue = useUi((u) => u.vue);
  const enLigne = useDonnees((d) => d.enLigne);
  const enCours = useAssistant((a) => a.enCours);
  const ongletActif = SOUS_PLUS.includes(vue) ? "plus" : vue;
  return (
    <div className="zone-sure flex h-dvh flex-col bg-fond">
      {!enLigne && (
        <div className="flex items-center justify-center gap-2 bg-ambre/15 py-1 text-[12px] text-ambre">
          <WifiOff className="size-3.5" /> {t("Hors ligne : tes changements partiront au retour du réseau")}
        </div>
      )}
      <main className="min-h-0 flex-1 overflow-y-auto">
        {vue === "assistant" && <Assistant />}
        {vue === "afaire" && <AFaire />}
        {vue === "memoire" && <Memoire />}
        {vue === "appareils" && <Appareils />}
        {vue === "plus" && <Plus />}
        {vue === "automatisations" && <Automatisations />}
        {vue === "services" && <Services />}
        {vue === "taches" && <Taches />}
        {vue === "transcriptions" && <Transcriptions />}
        {vue === "tickets" && <Tickets />}
        {vue === "reglages" && <Reglages onDeconnecte={onDeconnecte} />}
      </main>
      <nav className="bas-sur grid grid-cols-5 border-t border-ligne bg-surface/95">
        {ONGLETS.map((o) => (
          <button
            key={o.id}
            onClick={() => allerA(o.id)}
            className={cx("relative flex flex-col items-center gap-0.5 pt-2 pb-1 text-[11px]", ongletActif === o.id ? "text-hud" : "text-tres-doux")}
          >
            <o.icone className="size-5" />
            {t(o.libelle)}
            {o.id === "assistant" && enCours && <span className="absolute top-1.5 right-[30%] size-2 animate-pulse rounded-full bg-hud" />}
          </button>
        ))}
      </nav>
      <Toast />
      <Confirmation />
    </div>
  );
}

function Toast() {
  const toastActuel = useUi((u) => u.toast);
  if (!toastActuel) return null;
  return (
    <div
      key={toastActuel.id}
      className={cx(
        "animate-entree fixed inset-x-3 bottom-[calc(64px+env(safe-area-inset-bottom))] z-50 rounded-md border px-3 py-2.5 text-sm shadow-lg",
        toastActuel.erreur ? "border-rouge/50 bg-[#2a0d12] text-rouge" : "border-ligne-forte bg-surface-3 text-texte",
      )}
    >
      {toastActuel.texte}
    </div>
  );
}

function Confirmation() {
  const c = useUi((u) => u.confirmation);
  if (!c) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-5">
      <div className="coins w-full max-w-sm border border-ambre/50 bg-surface p-5">
        <p className="font-medium text-ambre">{c.titre}</p>
        <p className="mt-2 text-sm whitespace-pre-wrap">{c.detail}</p>
        <div className="mt-5 grid grid-cols-2 gap-2">
          <Bouton variante="danger" onClick={() => c.repondre(false)}>
            {t("Refuser")}
          </Bouton>
          <Bouton variante="primaire" icone={<Check className="size-4" />} onClick={() => c.repondre(true)}>
            {t("Accepter")}
          </Bouton>
        </div>
      </div>
    </div>
  );
}
