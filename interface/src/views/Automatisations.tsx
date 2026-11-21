import { Clock, Mail, Play, Plus, Power, Repeat, Trash2, Volume2, Wand2, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { Bouton, Champ, EnTetePage, Interrupteur, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";
import { useReglages } from "../stores/reglages";
import { toast } from "../stores/toasts";

type TypeDecl = "horaire" | "intervalle" | "demarrage" | "mail" | "commande";
type Regle = {
  id: string;
  nom: string;
  actif: boolean;
  description: string;
  appareil: string;
  declencheur: { type: TypeDecl; phrase?: string };
  action: { type: "prevenir" | "jarvis"; consigne: string; message?: string };
};
type Etat = { regles: Regle[]; boites: { cid: string; nom: string }[]; machine: string };
const JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const VIDE = {
  nom: "", type: "horaire" as TypeDecl, heure: "08:00", jours: [] as number[], minutes: 60,
  expediteur: "", sujet: "", contient: "", connecteur: "", action: "jarvis", consigne: "", message: "", partout: false, phrase: "",
};
const ICONES: Record<TypeDecl, typeof Clock> = { horaire: Clock, intervalle: Repeat, demarrage: Power, mail: Mail, commande: Wand2 };
const EXEMPLES = [
  { nom: "Agenda du matin", type: "horaire", heure: "08:00", jours: [0, 1, 2, 3, 4], consigne: "Lis mon agenda du jour et résume-le-moi en quelques phrases." },
  { nom: "Surveillance du serveur", type: "intervalle", minutes: 60, consigne: "Vérifie l'état de mon serveur (disque, mémoire, conteneurs) et préviens-moi seulement s'il y a un problème." },
  { nom: "Bonjour au démarrage", type: "demarrage", consigne: "Dis-moi la météo du jour et mes rendez-vous importants." },
  { nom: "Mode travail", type: "commande", phrase: "mode travail", consigne: "Ouvre mes applis de travail (VS Code, le terminal, mon navigateur), active le mode Ne pas déranger si tu peux, et dis-moi ce qui est en cours dans ma liste À faire." },
  { nom: "Fin de journée", type: "commande", phrase: "fin de journée", consigne: "Fais le point sur ma liste À faire : ce que j'ai fini aujourd'hui, ce qui reste pour demain (propose de décaler les échéances dépassées), puis souhaite-moi une bonne soirée." },
];

export function VueAutomatisations() {
  const [e, setE] = useState<Etat | null>(null);
  const [f, setF] = useState(VIDE);
  const charger = () => api<Etat>("/api/automatisations").then(setE).catch((x) => toast((x as Error).message, "erreur"));
  useEffect(() => {
    charger();
  }, []);

  const creer = async () => {
    try {
      setE(
        await api<Etat>("/api/automatisations", {
          method: "POST",
          json: { ...f, action: f.type === "commande" ? "jarvis" : f.action, appareil: f.type === "mail" || f.type === "commande" || f.partout ? "" : e?.machine },
        }),
      );
      setF(VIDE);
      toast(t("Automatisation créée."), "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const basculer = async (r: Regle) => setE(await api<Etat>(`/api/automatisations/${r.id}`, { method: "PATCH", json: { actif: !r.actif } }));
  const supprimer = async (r: Regle) => setE(await api<Etat>(`/api/automatisations/${r.id}`, { method: "DELETE" }));
  const lancer = async (r: Regle) => {
    try {
      await api(`/api/automatisations/${r.id}/lancer`, { method: "POST" });
      useReglages.getState().maj({ vue: "assistant" });   // on suit la routine dans la conversation
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const tester = () => api("/api/automatisations/tester", { method: "POST" }).catch(() => {});
  const select = "h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm";

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Automatisations")}
        sousTitre={t("Jarvis agit tout seul : à heure fixe, à intervalle, au démarrage ou quand un mail arrive. Les routines se lancent quand tu dis leur phrase (« mode travail »). Tu peux aussi lui dire : « tous les matins à 8 h, lis-moi mon agenda ».")}
        actions={
          <Bouton variante="fantome" icone={<Volume2 className="size-4" />} onClick={tester}>
            {t("Tester la voix")}
          </Bouton>
        }
      />

      <Panneau titre={t("Nouvelle automatisation")} icone={<Plus />} className="mb-6">
        <div className="mb-3 flex flex-wrap gap-2">
          {EXEMPLES.map((x) => (
            <button
              key={x.nom}
              onClick={() => setF({ ...VIDE, ...x, nom: t(x.nom), consigne: t(x.consigne), type: x.type as TypeDecl })}
              className="rounded-full border border-ligne px-3 py-1 text-[12px] text-doux hover:border-hud hover:text-hud"
            >
              {t(x.nom)}
            </button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Champ placeholder={t("Nom (ex : Agenda du matin)")} value={f.nom} onChange={(x) => setF({ ...f, nom: x.target.value })} />
          <select value={f.type} onChange={(x) => setF({ ...f, type: x.target.value as TypeDecl })} className={select} aria-label={t("Quand")}>
            <option value="horaire">{t("À heure fixe")}</option>
            <option value="intervalle">{t("Toutes les X minutes")}</option>
            <option value="demarrage">{t("Au démarrage de Jarvis")}</option>
            <option value="mail">{t("Quand un mail arrive")}</option>
            <option value="commande">{t("Routine : quand je dis une phrase")}</option>
          </select>

          {f.type === "horaire" && (
            <>
              <Champ type="time" value={f.heure} onChange={(x) => setF({ ...f, heure: x.target.value })} />
              <div className="flex flex-wrap items-center gap-1">
                {JOURS.map((j, i) => (
                  <button
                    key={j}
                    onClick={() => setF({ ...f, jours: f.jours.includes(i) ? f.jours.filter((x) => x !== i) : [...f.jours, i] })}
                    className={cx("h-8 rounded-md border px-2 text-[12px]", f.jours.includes(i) ? "border-hud bg-hud/15 text-hud" : "border-ligne text-doux")}
                  >
                    {t(j)}
                  </button>
                ))}
                <span className="ml-1 text-[11px] text-tres-doux">{f.jours.length ? "" : t("(tous les jours)")}</span>
              </div>
            </>
          )}
          {f.type === "commande" && (
            <Champ placeholder={t("Phrase qui la lance (ex : mode travail)")} value={f.phrase} onChange={(x) => setF({ ...f, phrase: x.target.value })} />
          )}
          {f.type === "intervalle" && (
            <Champ type="number" min={1} value={String(f.minutes)} onChange={(x) => setF({ ...f, minutes: +x.target.value })} placeholder={t("Minutes")} />
          )}
          {f.type === "mail" && (
            <>
              <select value={f.connecteur} onChange={(x) => setF({ ...f, connecteur: x.target.value })} className={select} aria-label={t("Boîte mail")}>
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
            </>
          )}

          <select value={f.action} onChange={(x) => setF({ ...f, action: x.target.value })} className={select} aria-label={t("Action")}>
            <option value="jarvis">{t("Demander quelque chose à Jarvis (il te lit le résultat)")}</option>
            <option value="prevenir">{t("Me dire un message")}</option>
          </select>
          {f.action === "jarvis" ? (
            <Champ
              className="sm:col-span-2"
              placeholder={t("Consigne (ex : lis mon agenda du jour et résume-le)")}
              value={f.consigne}
              onChange={(x) => setF({ ...f, consigne: x.target.value })}
            />
          ) : (
            <Champ className="sm:col-span-2" placeholder={t("Message à dire (vide = annonce par défaut)")} value={f.message} onChange={(x) => setF({ ...f, message: x.target.value })} />
          )}
          {f.type !== "mail" && f.type !== "commande" && (
            <label className="flex items-center gap-2 text-[13px] text-doux sm:col-span-2">
              <input type="checkbox" checked={f.partout} onChange={(x) => setF({ ...f, partout: x.target.checked })} />
              {t("L'exécuter sur tous mes appareils allumés (sinon seulement sur celui-ci)")}
            </label>
          )}
        </div>
        {f.type === "mail" && e && e.boites.length === 0 && (
          <p className="mt-3 text-[13px] text-ambre">{t("Aucune boîte mail connectée : ajoute Gmail ou une autre messagerie dans l'écran Connecteurs.")}</p>
        )}
        <Bouton className="mt-4" variante="primaire" icone={<Plus />} onClick={creer}>
          {t("Créer")}
        </Bouton>
      </Panneau>

      {!e ? null : e.regles.length === 0 ? (
        <Vide icone={<Zap />} titre={t("Aucune automatisation")} texte={t("Crée-en une ci-dessus, ou demande-la à Jarvis.")} />
      ) : (
        <div className="space-y-2">
          {e.regles.map((r) => {
            const I = ICONES[r.declencheur.type] ?? Zap;
            return (
              <div key={r.id} className="flex items-center gap-3 rounded-md border border-ligne bg-surface/60 px-4 py-3">
                <I className="size-4 flex-none text-hud" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{r.nom}</div>
                  <div className="text-[12px] text-doux">{r.description}</div>
                </div>
                {r.declencheur.type === "commande" && (
                  <Bouton taille="sm" icone={<Play className="size-3.5" />} onClick={() => lancer(r)}>
                    {t("Lancer")}
                  </Bouton>
                )}
                <Interrupteur label="" actif={r.actif} onChange={() => basculer(r)} />
                <button onClick={() => supprimer(r)} aria-label={t("Supprimer")} className="rounded p-1 text-tres-doux hover:text-rouge">
                  <Trash2 className="size-4" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
