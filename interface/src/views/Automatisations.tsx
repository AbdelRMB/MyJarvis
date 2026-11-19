import { t } from "../lib/i18n";
import { Mail, Plus, Trash2, Volume2, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { Bouton, Champ, EnTetePage, Interrupteur, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { toast } from "../stores/toasts";

type Regle = {
  id: string;
  nom: string;
  actif: boolean;
  description: string;
  declencheur: { type: string; expediteur: string; sujet: string; contient: string; connecteur: string };
  action: { type: "prevenir" | "jarvis"; consigne: string };
};
type Etat = { regles: Regle[]; boites: { cid: string; nom: string }[] };
const VIDE = { nom: "", expediteur: "", sujet: "", contient: "", connecteur: "", action: "prevenir", consigne: "" };

export function VueAutomatisations() {
  const [e, setE] = useState<Etat | null>(null);
  const [f, setF] = useState(VIDE);
  const charger = () => api<Etat>("/api/automatisations").then(setE).catch((x) => toast((x as Error).message, "erreur"));
  useEffect(() => {
    charger();
  }, []);

  const creer = async () => {
    try {
      setE(await api<Etat>("/api/automatisations", { method: "POST", json: f }));
      setF(VIDE);
      toast(t("Automatisation créée (sur tous tes appareils)."), "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const basculer = async (r: Regle) => setE(await api<Etat>(`/api/automatisations/${r.id}`, { method: "PATCH", json: { actif: !r.actif } }));
  const supprimer = async (r: Regle) => setE(await api<Etat>(`/api/automatisations/${r.id}`, { method: "DELETE" }));
  const tester = () => api("/api/automatisations/tester", { method: "POST" }).catch(() => {});

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Automatisations")}
        sousTitre={t("Jarvis agit tout seul quand quelque chose arrive. Tu peux aussi lui dire : « quand je reçois un mail de mon père, préviens-moi ».")}
        actions={
          <Bouton variante="fantome" icone={<Volume2 className="size-4" />} onClick={tester}>
            {t("Tester la voix")}
          </Bouton>
        }
      />

      <Panneau titre={t("Nouvelle automatisation")} icone={<Plus />} className="mb-6">
        <div className="grid gap-3 sm:grid-cols-2">
          <Champ placeholder={t("Nom (ex : Mail de papa)")} value={f.nom} onChange={(x) => setF({ ...f, nom: x.target.value })} />
          <select
            value={f.connecteur}
            onChange={(x) => setF({ ...f, connecteur: x.target.value })}
            className="h-10 rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
            aria-label={t("Boîte mail")}
          >
            <option value="">{t("Toutes mes boîtes mail")}</option>
            {e?.boites.map((b) => (
              <option key={b.cid} value={b.cid}>
                {b.nom}
              </option>
            ))}
          </select>
          <Champ placeholder={t("Expéditeur (adresse ou nom)")} value={f.expediteur} onChange={(x) => setF({ ...f, expediteur: x.target.value })} />
          <Champ placeholder={t("Mot dans le sujet (optionnel)")} value={f.sujet} onChange={(x) => setF({ ...f, sujet: x.target.value })} />
          <Champ placeholder={t("Mot dans le texte (optionnel)")} value={f.contient} onChange={(x) => setF({ ...f, contient: x.target.value })} />
          <select
            value={f.action}
            onChange={(x) => setF({ ...f, action: x.target.value })}
            className="h-10 rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
            aria-label={t("Action")}
          >
            <option value="prevenir">{t("Me prévenir à voix haute")}</option>
            <option value="jarvis">{t("Demander quelque chose à Jarvis")}</option>
          </select>
          {f.action === "jarvis" && (
            <Champ
              className="sm:col-span-2"
              placeholder={t("Consigne (ex : résume-le-moi en une phrase)")}
              value={f.consigne}
              onChange={(x) => setF({ ...f, consigne: x.target.value })}
            />
          )}
        </div>
        {e && e.boites.length === 0 && (
          <p className="mt-3 text-[13px] text-ambre">{t("Aucune boîte mail connectée : ajoute Gmail ou une autre messagerie dans l'écran Connecteurs.")}</p>
        )}
        <Bouton className="mt-4" variante="primaire" icone={<Plus />} onClick={creer} disabled={!(f.expediteur || f.sujet || f.contient)}>
          {t("Créer")}
        </Bouton>
      </Panneau>

      {!e ? null : e.regles.length === 0 ? (
        <Vide icone={<Zap />} titre={t("Aucune automatisation")} texte={t("Crée-en une ci-dessus, ou demande-la à Jarvis.")} />
      ) : (
        <div className="space-y-2">
          {e.regles.map((r) => (
            <div key={r.id} className="flex items-center gap-3 rounded-md border border-ligne bg-surface/60 px-4 py-3">
              <Mail className="size-4 flex-none text-hud" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{r.nom}</div>
                <div className="text-[12px] text-doux">{r.description}</div>
              </div>
              <Interrupteur label="" actif={r.actif} onChange={() => basculer(r)} />
              <button onClick={() => supprimer(r)} aria-label={t("Supprimer")} className="rounded p-1 text-tres-doux hover:text-rouge">
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
