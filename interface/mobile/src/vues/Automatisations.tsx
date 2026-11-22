import { Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bouton, Champ, Interrupteur } from "../../../src/components/ui";
import { cx } from "../../../src/lib/format";
import { t } from "../../../src/lib/i18n";
import { envoyer } from "../assistant";
import { basculerAutomatisation, creerAutomatisation, decrireAutomatisation, JOURS, supprimerAutomatisation, useDonnees } from "../moteur/donnees";
import type { Automatisation } from "../moteur/types";
import { allerA, Entete, erreurToast, Feuille, Ligne, Section, Zone } from "../ui";

type Type = Automatisation["declencheur"]["type"];
const TYPES: { id: Type; libelle: string }[] = [
  { id: "commande", libelle: "Routine (phrase)" },
  { id: "horaire", libelle: "À heure fixe" },
  { id: "intervalle", libelle: "Intervalle" },
  { id: "mail", libelle: "Mail reçu" },
  { id: "demarrage", libelle: "Démarrage" },
];

/** Automatisations du compte : exécutées par tes ordinateurs ; les routines se lancent aussi depuis le téléphone. */
export function Automatisations() {
  const liste = useDonnees((d) => d.automatisations);
  const [nouvelle, setNouvelle] = useState(false);
  const routines = liste.filter((r) => r.declencheur.type === "commande");
  const regles = liste.filter((r) => r.declencheur.type !== "commande");
  const ligne = (r: Automatisation) => (
    <Ligne key={r.id}>
      <div className="min-w-0 flex-1">
        <div className={cx("truncate text-[15px]", !r.actif && "text-tres-doux")}>{r.nom}</div>
        <div className="line-clamp-2 text-[12px] text-doux">{decrireAutomatisation(r)}</div>
      </div>
      {r.declencheur.type === "commande" && r.actif && (
        <button
          className="grid size-9 place-items-center text-hud"
          aria-label={t("Lancer")}
          onClick={() => {
            allerA("assistant");
            void envoyer(r.declencheur.phrase || r.nom);
          }}
        >
          <Play className="size-4.5" />
        </button>
      )}
      <input
        type="checkbox"
        checked={r.actif}
        onChange={(e) => basculerAutomatisation(r.id, e.target.checked).catch(erreurToast)}
        className="size-5 accent-[#3ce8ff]"
        aria-label={t("Active")}
      />
      <button className="grid size-9 place-items-center text-tres-doux" aria-label={t("Supprimer")} onClick={() => confirm(t("Supprimer « {nom} » ?", { nom: r.nom })) && supprimerAutomatisation(r.id).catch(erreurToast)}>
        <Trash2 className="size-4" />
      </button>
    </Ligne>
  );
  return (
    <div>
      <Entete
        titre={t("Automatisations")}
        retour={() => allerA("plus")}
        sous={t("Exécutées par tes ordinateurs allumés")}
        actions={
          <button className="grid size-9 place-items-center text-hud" onClick={() => setNouvelle(true)} aria-label={t("Ajouter")}>
            <Plus className="size-5" />
          </button>
        }
      />
      {routines.length > 0 && <Section titre={t("Routines · {n}", { n: routines.length })}>{routines.map(ligne)}</Section>}
      {regles.length > 0 && <Section titre={t("Règles · {n}", { n: regles.length })}>{regles.map(ligne)}</Section>}
      {!liste.length && (
        <p className="px-6 py-16 text-center text-sm text-doux">{t("Aucune automatisation. Dis par exemple « tous les matins à 8 h, lis-moi mon agenda ».")}</p>
      )}
      {nouvelle && <Nouvelle onFermer={() => setNouvelle(false)} />}
    </div>
  );
}

function Nouvelle({ onFermer }: { onFermer: () => void }) {
  const appareils = useDonnees((d) => d.appareils).filter((a) => !a.moi && a.plateforme !== "telephone");
  const [type, setType] = useState<Type>("commande");
  const [nom, setNom] = useState("");
  const [heure, setHeure] = useState("08:00");
  const [jours, setJours] = useState<number[]>([]);
  const [minutes, setMinutes] = useState(60);
  const [expediteur, setExpediteur] = useState("");
  const [sujet, setSujet] = useState("");
  const [prevenir, setPrevenir] = useState(false);
  const [consigne, setConsigne] = useState("");
  const [appareil, setAppareil] = useState("");
  const [charge, setCharge] = useState(false);

  async function creer() {
    setCharge(true);
    try {
      await creerAutomatisation({
        nom,
        type,
        heure,
        jours,
        minutes,
        expediteur,
        sujet,
        phrase: nom,
        action: prevenir ? "prevenir" : "wesley",
        consigne: prevenir ? "" : consigne,
        message: prevenir ? consigne : "",
        appareil,
      });
      onFermer();
    } catch (e) {
      erreurToast(e);
    } finally {
      setCharge(false);
    }
  }

  return (
    <Feuille titre={t("Nouvelle automatisation")} onFermer={onFermer}>
      <div className="space-y-3">
        <div className="flex flex-wrap gap-1">
          {TYPES.map((x) => (
            <button key={x.id} onClick={() => setType(x.id)} className={cx("rounded border px-2 py-1.5 text-[13px]", type === x.id ? "border-hud bg-hud/15 text-hud" : "border-ligne text-doux")}>
              {t(x.libelle)}
            </button>
          ))}
        </div>
        <Champ value={nom} onChange={(e) => setNom(e.target.value)} placeholder={type === "commande" ? t("Phrase : « mode travail »") : t("Nom : « Agenda du matin »")} />
        {type === "horaire" && (
          <>
            <Champ type="time" value={heure} onChange={(e) => setHeure(e.target.value)} />
            <div className="grid grid-cols-7 gap-1">
              {JOURS.map((j, i) => (
                <button
                  key={j}
                  onClick={() => setJours(jours.includes(i) ? jours.filter((x) => x !== i) : [...jours, i])}
                  className={cx("rounded border py-1.5 text-[12px]", jours.includes(i) ? "border-hud bg-hud/15 text-hud" : "border-ligne text-doux")}
                >
                  {t(j).slice(0, 2)}
                </button>
              ))}
            </div>
            <p className="text-[12px] text-tres-doux">{t("Aucun jour choisi = tous les jours.")}</p>
          </>
        )}
        {type === "intervalle" && <Champ type="number" min={1} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} placeholder={t("Minutes")} />}
        {type === "mail" && (
          <>
            <Champ value={expediteur} onChange={(e) => setExpediteur(e.target.value)} placeholder={t("Expéditeur (adresse ou nom)")} />
            <Champ value={sujet} onChange={(e) => setSujet(e.target.value)} placeholder={t("Mot du sujet (facultatif)")} />
          </>
        )}
        {type !== "commande" && <Interrupteur actif={prevenir} onChange={setPrevenir} label={t("Simplement me prévenir")} aide={t("Sinon, Wesley exécute la consigne avec tous ses outils.")} />}
        <Zone rows={3} value={consigne} onChange={(e) => setConsigne(e.target.value)} placeholder={prevenir ? t("Message à dire") : t("Ce que Wesley doit faire (toutes les étapes)")} />
        {type !== "commande" && type !== "mail" && (
          <select value={appareil} onChange={(e) => setAppareil(e.target.value)} className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3">
            <option value="">{t("Sur tous mes ordinateurs")}</option>
            {appareils.map((a) => (
              <option key={a.id} value={a.nom}>
                {a.nom}
              </option>
            ))}
          </select>
        )}
        <Bouton variante="primaire" className="w-full" chargement={charge} disabled={!nom.trim() || (!consigne.trim() && !prevenir)} onClick={creer}>
          {t("Créer")}
        </Bouton>
      </div>
    </Feuille>
  );
}
