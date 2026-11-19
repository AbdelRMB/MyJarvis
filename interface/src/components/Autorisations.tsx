import { CheckCircle2, CircleHelp, ExternalLink, ShieldCheck, ShieldOff, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { toast } from "../stores/toasts";
import { Bouton, Panneau } from "./ui";

type Autorisation = { id: string; nom: string; role: string; etat: "accorde" | "refuse" | "a_demander" | "inconnu"; demande_faite: boolean };
type Etat = { plateforme: "mac" | "windows"; autorisations: Autorisation[]; a_proposer: string[] };
type Reponse = Etat & { resultat: string };

const LIBELLE: Record<Autorisation["etat"], string> = { accorde: "Autorisé", refuse: "Refusé", a_demander: "Pas encore autorisé", inconnu: "À vérifier" };

function useAutorisations() {
  const [e, setE] = useState<Etat | null>(null);
  const charger = () => api<Etat>("/api/autorisations").then(setE).catch(() => {});
  useEffect(() => {
    charger();
    // l'utilisateur répond dans une fenêtre du système : on relit l'état régulièrement
    const i = setInterval(charger, 3000);
    return () => clearInterval(i);
  }, []);
  const agir = async (action: "demander" | "retirer" | "reglages" | "ignorer", corps: object) => {
    try {
      const r = await api<Reponse>(`/api/autorisations/${action}`, { method: "POST", json: corps });
      setE(r);
      if (r.resultat === "reglages") toast("Réglages Système ouverts : active Jarvis dans la liste, puis reviens ici.", "info");
      if (r.resultat === "retire") toast("Accès retiré. Jarvis le redemandera s'il en a besoin.", "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  return { e, agir };
}

function Pastille({ etat }: { etat: Autorisation["etat"] }) {
  const Icone = etat === "accorde" ? CheckCircle2 : etat === "refuse" ? XCircle : CircleHelp;
  return (
    <span className={cx("inline-flex items-center gap-1 text-[12px]", etat === "accorde" ? "text-vert" : etat === "refuse" ? "text-rouge" : "text-ambre")}>
      <Icone className="size-3.5" /> {LIBELLE[etat]}
    </span>
  );
}

/** Réglages › Autorisations : tout voir, accorder ou retirer. */
export function OngletAutorisations() {
  const { e, agir } = useAutorisations();
  if (!e) return null;
  const mac = e.plateforme === "mac";
  return (
    <Panneau titre="Autorisations" icone={<ShieldCheck />}>
      <p className="mb-3 text-[13px] leading-relaxed text-doux">
        {mac
          ? "macOS ne laisse aucune appli s'accorder ces accès toute seule : c'est toi qui acceptes, une seule fois. Ils restent acquis après les mises à jour de Jarvis."
          : "Sous Windows, les applis de bureau ont déjà accès aux fichiers, à l'écran, au clavier et à la souris. Seul le micro peut être coupé dans les Paramètres."}
      </p>
      <div className="divide-y divide-ligne">
        {e.autorisations.map((a) => (
          <div key={a.id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-[220px] flex-1">
              <div className="flex items-center gap-2 text-sm font-medium">
                {a.nom} <Pastille etat={a.etat} />
              </div>
              <p className="mt-0.5 text-[12px] text-doux">{a.role}</p>
            </div>
            {mac && a.etat !== "accorde" && (
              <Bouton taille="sm" variante="primaire" onClick={() => agir("demander", { id: a.id })}>
                Autoriser
              </Bouton>
            )}
            {mac && a.etat === "accorde" && (
              <Bouton taille="sm" variante="fantome" icone={<ShieldOff />} onClick={() => agir("retirer", { id: a.id })}>
                Retirer
              </Bouton>
            )}
            {(mac || a.id === "micro") && (
              <Bouton taille="sm" variante="fantome" icone={<ExternalLink />} onClick={() => agir("reglages", { id: a.id })}>
                Réglages
              </Bouton>
            )}
          </div>
        ))}
      </div>
    </Panneau>
  );
}

/** Au premier lancement : demande chaque accès UNE fois. Ce qui a été demandé (accepté ou non) ne revient plus. */
export function BandeauAutorisations() {
  const { e, agir } = useAutorisations();
  const [ferme, setFerme] = useState(false);
  if (!e || ferme || e.a_proposer.length === 0) return null;
  const aProposer = e.autorisations.filter((a) => e.a_proposer.includes(a.id));
  return (
    <div className="fixed right-4 bottom-4 z-40 w-[min(420px,calc(100vw-32px))] rounded-lg border border-hud/40 bg-surface-2/95 p-4 shadow-glow backdrop-blur">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-hud">
        <ShieldCheck className="size-4" /> Jarvis a besoin de quelques accès
      </div>
      <p className="mb-3 text-[12px] text-doux">Une seule fois : ton choix est retenu, tu pourras le changer dans Réglages › Autorisations.</p>
      <div className="space-y-2">
        {aProposer.map((a) => (
          <div key={a.id} className="flex items-center gap-2">
            <div className="flex-1">
              <div className="text-sm">{a.nom}</div>
              <div className="text-[11px] text-doux">{a.role}</div>
            </div>
            <Bouton taille="sm" variante="primaire" onClick={() => agir("demander", { id: a.id })}>
              Autoriser
            </Bouton>
          </div>
        ))}
      </div>
      <div className="mt-3 text-right">
        <Bouton
          taille="sm"
          variante="fantome"
          onClick={() => {
            agir("ignorer", { ids: e.a_proposer });
            setFerme(true);
          }}
        >
          Non merci / plus tard
        </Bouton>
      </div>
    </div>
  );
}
