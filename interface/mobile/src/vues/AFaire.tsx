import { Bell, CalendarClock, CheckCircle2, Circle, CircleDot, Flag, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bouton, Champ } from "../../../src/components/ui";
import { cx } from "../../../src/lib/format";
import { t } from "../../../src/lib/i18n";
import { ajouterAFaire, ETAPES, LIBELLES_ETAPES, modifierAFaire, supprimerAFaire, useDonnees } from "../moteur/donnees";
import { autoriserNotifications } from "../moteur/rappels";
import type { TacheAFaire } from "../moteur/types";
import { Entete, erreurToast, Feuille, Ligne, Section, Zone } from "../ui";

const ICONES = { a_faire: Circle, en_cours: CircleDot, fait: CheckCircle2 };
const suivante = (s: TacheAFaire["statut"]) => ETAPES[(ETAPES.indexOf(s) + 1) % 3];
const date = (s: string) => (s ? new Date(s.length > 10 ? s : s + "T00:00").toLocaleString("fr-FR", { day: "numeric", month: "short", ...(s.length > 10 ? { hour: "2-digit", minute: "2-digit" } : {}) }) : "");

/** La liste « À faire » du compte (la même que sur les ordinateurs) : toucher le rond passe à l'étape suivante. */
export function AFaire() {
  const liste = useDonnees((d) => d.afaire);
  const [titre, setTitre] = useState("");
  const [edition, setEdition] = useState<TacheAFaire | null>(null);
  const [faitsVisibles, setFaitsVisibles] = useState(false);

  async function ajouter(e: React.FormEvent) {
    e.preventDefault();
    if (!titre.trim()) return;
    const v = titre;
    setTitre("");
    await ajouterAFaire({ titre: v }).catch(erreurToast);
  }

  const auj = new Date().toISOString().slice(0, 10);
  const ordre = (a: TacheAFaire, b: TacheAFaire) =>
    Number(b.priorite === "haute") - Number(a.priorite === "haute") || (a.echeance || "9999").localeCompare(b.echeance || "9999");

  return (
    <div>
      <Entete titre={t("À faire")} sous={t("{n} en cours ou à faire", { n: liste.filter((x) => x.statut !== "fait").length })} />
      <form onSubmit={ajouter} className="flex gap-2 px-3 pt-3">
        <Champ value={titre} onChange={(e) => setTitre(e.target.value)} placeholder={t("Nouvelle tâche…")} className="h-11" />
        <Bouton type="submit" variante="primaire" className="h-11 px-3" aria-label={t("Ajouter")}>
          <Plus className="size-5" />
        </Bouton>
      </form>
      {(["en_cours", "a_faire", "fait"] as const).map((s) => {
        const items = liste.filter((x) => x.statut === s).sort(ordre);
        if (!items.length) return null;
        const cache = s === "fait" && !faitsVisibles;
        return (
          <Section
            key={s}
            titre={`${t(LIBELLES_ETAPES[s])} · ${items.length}`}
            actions={
              s === "fait" && (
                <button className="text-[12px] text-doux" onClick={() => setFaitsVisibles(!faitsVisibles)}>
                  {faitsVisibles ? t("Masquer") : t("Afficher")}
                </button>
              )
            }
          >
            {!cache &&
              items.map((x) => {
                const I = ICONES[x.statut];
                const retard = x.statut !== "fait" && x.echeance && x.echeance.slice(0, 10) < auj;
                return (
                  <Ligne key={x.id}>
                    <button
                      onClick={() => modifierAFaire(x.id, { statut: suivante(x.statut) }).catch(erreurToast)}
                      className={cx("-m-2 grid size-11 flex-none place-items-center", x.statut === "fait" ? "text-vert" : x.statut === "en_cours" ? "text-ambre" : "text-doux")}
                      aria-label={t("Étape suivante")}
                    >
                      <I className="size-5.5" />
                    </button>
                    <button className="min-w-0 flex-1 text-left" onClick={() => setEdition(x)}>
                      <div className={cx("truncate text-[15px]", x.statut === "fait" && "text-tres-doux line-through")}>
                        {x.priorite === "haute" && <Flag className="mr-1 inline size-3.5 text-rouge" />}
                        {x.titre}
                      </div>
                      {(x.echeance || x.rappel || x.note) && (
                        <div className="flex gap-3 truncate text-[12px] text-doux">
                          {x.echeance && (
                            <span className={cx(retard && "text-rouge")}>
                              <CalendarClock className="mr-0.5 inline size-3" />
                              {date(x.echeance)}
                            </span>
                          )}
                          {x.rappel && (
                            <span>
                              <Bell className="mr-0.5 inline size-3" />
                              {date(x.rappel)}
                            </span>
                          )}
                          {x.note && <span className="truncate">{x.note}</span>}
                        </div>
                      )}
                    </button>
                  </Ligne>
                );
              })}
          </Section>
        );
      })}
      {!liste.length && <p className="px-6 py-16 text-center text-sm text-doux">{t("Rien de prévu. Dis « rappelle-moi de… » ou écris une tâche ci-dessus.")}</p>}
      {edition && <Edition tache={edition} onFermer={() => setEdition(null)} />}
    </div>
  );
}

function Edition({ tache, onFermer }: { tache: TacheAFaire; onFermer: () => void }) {
  const [x, setX] = useState(tache);
  const maj = (p: Partial<TacheAFaire>) => setX({ ...x, ...p });
  return (
    <Feuille titre={t("Tâche")} onFermer={onFermer}>
      <div className="space-y-3">
        <Champ value={x.titre} onChange={(e) => maj({ titre: e.target.value })} />
        <Zone rows={3} value={x.note} onChange={(e) => maj({ note: e.target.value })} placeholder={t("Note…")} />
        <label className="block text-[13px] text-doux">
          {t("Échéance")}
          <Champ type="datetime-local" value={x.echeance.length === 10 ? x.echeance + "T09:00" : x.echeance} onChange={(e) => maj({ echeance: e.target.value })} />
        </label>
        <label className="block text-[13px] text-doux">
          {t("Rappel (notification + voix)")}
          <Champ type="datetime-local" value={x.rappel} onChange={(e) => (maj({ rappel: e.target.value }), void autoriserNotifications())} />
        </label>
        <div className="grid grid-cols-3 gap-1 text-sm">
          {(["basse", "normale", "haute"] as const).map((p) => (
            <button key={p} onClick={() => maj({ priorite: p })} className={cx("rounded-md border py-2", x.priorite === p ? "border-hud bg-hud/15 text-hud" : "border-ligne text-doux")}>
              {t(p)}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-1 text-sm">
          {ETAPES.map((s) => (
            <button key={s} onClick={() => maj({ statut: s })} className={cx("rounded-md border py-2", x.statut === s ? "border-hud bg-hud/15 text-hud" : "border-ligne text-doux")}>
              {t(LIBELLES_ETAPES[s])}
            </button>
          ))}
        </div>
        <div className="flex gap-2 pt-2">
          <Bouton
            variante="danger"
            icone={<Trash2 className="size-4" />}
            onClick={() => confirm(t("Supprimer cette tâche ?")) && supprimerAFaire(x.id).then(onFermer, erreurToast)}
          >
            {t("Supprimer")}
          </Bouton>
          <Bouton
            variante="primaire"
            className="flex-1"
            onClick={() =>
              modifierAFaire(x.id, { titre: x.titre, note: x.note, echeance: x.echeance, rappel: x.rappel, priorite: x.priorite, ...(x.statut !== tache.statut ? { statut: x.statut } : {}) }).then(
                onFermer,
                erreurToast,
              )
            }
          >
            {t("Enregistrer")}
          </Bouton>
        </div>
      </div>
    </Feuille>
  );
}
