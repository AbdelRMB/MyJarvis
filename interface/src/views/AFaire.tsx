import { ArrowLeft, ArrowRight, Bell, CalendarClock, CheckCircle2, Circle, Flag, ListChecks, Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Bouton, Champ, EnTetePage, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";
import { bus } from "../stores/wesley";
import { toast } from "../stores/toasts";

type Statut = "a_faire" | "en_cours" | "fait";
type Priorite = "basse" | "normale" | "haute";
type Tache = { id: string; titre: string; note: string; echeance: string; rappel?: string; priorite: Priorite; statut: Statut; cree: string; modifie: string; fait_le: string };

const COLONNES: { id: Statut; libelle: string; icone: typeof Circle; couleur: string }[] = [
  { id: "a_faire", libelle: "À faire", icone: Circle, couleur: "text-doux" },
  { id: "en_cours", libelle: "En cours", icone: Loader2, couleur: "text-hud" },
  { id: "fait", libelle: "Fait", icone: CheckCircle2, couleur: "text-vert" },
];
const ORDRE: Statut[] = ["a_faire", "en_cours", "fait"];
const VIDE = { titre: "", note: "", echeance: "", rappel: "", priorite: "normale" as Priorite };

function enRetard(x: Tache) {
  if (!x.echeance || x.statut === "fait") return false;
  return x.echeance.slice(0, 10) < new Date().toISOString().slice(0, 10);
}

function Carte({ x, deplacer, supprimer }: { x: Tache; deplacer: (s: Statut) => void; supprimer: () => void }) {
  const i = ORDRE.indexOf(x.statut);
  return (
    <div className="group rounded-md border border-ligne bg-surface/60 px-3 py-2.5">
      <div className="flex items-start gap-2">
        {x.priorite === "haute" && <Flag className="mt-0.5 size-3.5 flex-none text-rouge" aria-label={t("Prioritaire")} />}
        <div className={cx("min-w-0 flex-1 text-sm", x.statut === "fait" && "text-doux line-through")}>{x.titre}</div>
        <button onClick={supprimer} aria-label={t("Supprimer")} className="rounded p-0.5 text-tres-doux opacity-0 group-hover:opacity-100 hover:text-rouge focus:opacity-100">
          <Trash2 className="size-3.5" />
        </button>
      </div>
      {x.note && <div className="mt-1 text-[12px] text-doux">{x.note}</div>}
      <div className="mt-2 flex items-center gap-2">
        {x.echeance && (
          <span className={cx("inline-flex items-center gap-1 text-[11px]", enRetard(x) ? "text-rouge" : "text-tres-doux")}>
            <CalendarClock className="size-3" />
            {x.echeance.replace("T", " ")}
          </span>
        )}
        {x.rappel && x.statut !== "fait" && (
          <span className="inline-flex items-center gap-1 text-[11px] text-hud" title={t("Rappel")}>
            <Bell className="size-3" />
            {x.rappel.replace("T", " ")}
          </span>
        )}
        <div className="ml-auto flex gap-1">
          {i > 0 && (
            <button onClick={() => deplacer(ORDRE[i - 1])} title={t(COLONNES[i - 1].libelle)} className="rounded border border-ligne p-1 text-doux hover:border-hud hover:text-hud">
              <ArrowLeft className="size-3.5" />
            </button>
          )}
          {i < 2 && (
            <button onClick={() => deplacer(ORDRE[i + 1])} title={t(COLONNES[i + 1].libelle)} className="rounded border border-ligne p-1 text-doux hover:border-hud hover:text-hud">
              <ArrowRight className="size-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function VueAFaire() {
  const [liste, setListe] = useState<Tache[] | null>(null);
  const [f, setF] = useState(VIDE);
  const charger = () => api<Tache[]>("/api/afaire").then(setListe).catch((x) => toast((x as Error).message, "erreur"));
  useEffect(() => {
    charger();
    const sur = () => charger();
    bus.addEventListener("afaire_maj", sur);
    return () => bus.removeEventListener("afaire_maj", sur);
  }, []);

  const agir = async (p: Promise<Tache[]>) => {
    try {
      setListe(await p);
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const creer = async () => {
    if (!f.titre.trim()) return;
    await agir(api<Tache[]>("/api/afaire", { method: "POST", json: f }));
    setF(VIDE);
  };
  const deplacer = (x: Tache, statut: Statut) => agir(api<Tache[]>(`/api/afaire/${x.id}`, { method: "PATCH", json: { statut } }));
  const supprimer = (x: Tache) => agir(api<Tache[]>(`/api/afaire/${x.id}`, { method: "DELETE" }));
  const viderFaits = () => agir(api<Tache[]>("/api/afaire/faits", { method: "DELETE" }));
  const select = "h-10 rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm";
  const nbFaits = liste?.filter((x) => x.statut === "fait").length ?? 0;

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("À faire")}
        sousTitre={t("Ce que tu as prévu de faire. Dis simplement à Wesley : « souviens-toi que je dois appeler le garage », « rappelle-moi de sortir les poubelles à 20 h », puis « qu'est-ce que j'ai prévu ? » ou « c'est fait ».")}
        actions={
          nbFaits > 0 && (
            <Bouton variante="fantome" icone={<Trash2 className="size-4" />} onClick={viderFaits}>
              {t("Retirer les tâches faites")}
            </Bouton>
          )
        }
      />

      <Panneau titre={t("Nouvelle tâche")} icone={<Plus />} className="mb-6">
        <form
          className="grid gap-3 sm:grid-cols-[1fr_190px_130px_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            creer();
          }}
        >
          <Champ placeholder={t("Ex : appeler le garage")} value={f.titre} onChange={(x) => setF({ ...f, titre: x.target.value })} />
          <Champ type="datetime-local" aria-label={t("Échéance")} value={f.echeance} onChange={(x) => setF({ ...f, echeance: x.target.value })} />
          <select value={f.priorite} onChange={(x) => setF({ ...f, priorite: x.target.value as Priorite })} className={select} aria-label={t("Priorité")}>
            <option value="basse">{t("Basse")}</option>
            <option value="normale">{t("Normale")}</option>
            <option value="haute">{t("Haute")}</option>
          </select>
          <Bouton variante="primaire" icone={<Plus />} type="submit">
            {t("Ajouter")}
          </Bouton>
          <Champ className="sm:col-span-3" placeholder={t("Note (optionnel)")} value={f.note} onChange={(x) => setF({ ...f, note: x.target.value })} />
          <label className="flex items-center gap-2 text-[12px] text-doux sm:col-span-1" title={t("Rappel")}>
            <Bell className="size-4 flex-none text-hud" />
            <Champ type="datetime-local" aria-label={t("Rappel")} value={f.rappel} onChange={(x) => setF({ ...f, rappel: x.target.value })} />
          </label>
        </form>
      </Panneau>

      {!liste ? null : liste.length === 0 ? (
        <Vide icone={<ListChecks />} titre={t("Rien de prévu")} texte={t("Ajoute une tâche ci-dessus, ou dis à Wesley ce que tu dois faire.")} />
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {COLONNES.map((c) => {
            const items = liste
              .filter((x) => x.statut === c.id)
              .sort((a, b) =>
                c.id === "fait"
                  ? (b.fait_le || b.modifie).localeCompare(a.fait_le || a.modifie)
                  : (a.priorite === "haute" ? 0 : 1) - (b.priorite === "haute" ? 0 : 1) || (a.echeance || "9999").localeCompare(b.echeance || "9999"),
              );
            const I = c.icone;
            return (
              <section key={c.id} className="min-w-0">
                <h2 className={cx("titre-hud mb-2 flex items-center gap-2 text-[11px]", c.couleur)}>
                  <I className="size-3.5" />
                  {t(c.libelle)}
                  <span className="text-tres-doux">{items.length}</span>
                </h2>
                <div className="space-y-2">
                  {items.map((x) => (
                    <Carte key={x.id} x={x} deplacer={(s) => deplacer(x, s)} supprimer={() => supprimer(x)} />
                  ))}
                  {items.length === 0 && <div className="rounded-md border border-dashed border-ligne px-3 py-4 text-center text-[12px] text-tres-doux">{t("Vide")}</div>}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
