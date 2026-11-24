import { Code2, Loader2, Play, RefreshCw, Send, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { Bouton, Champ } from "../../../src/components/ui";
import { t } from "../../../src/lib/i18n";
import { envoyer } from "../assistant";
import { useDonnees } from "../moteur/donnees";
import { agirPartage, chargerPartages, lirePartage, origine, usePartages, type Partage } from "../moteur/partages";
import { allerA, Entete, erreurToast, Feuille, Ligne, Section, tempsRelatif, toast, Zone } from "../ui";

const STATUTS: Record<string, [string, string]> = {
  en_cours: ["En cours", "text-hud"],
  terminee: ["Terminée", "text-vert"],
  echec: ["Échec", "text-rouge"],
  arretee: ["Arrêtée", "text-doux"],
  interrompue: ["Interrompue", "text-ambre"],
};

/** Ordinateur d'origine (point vert : allumé avec Wesley ouvert). */
export function Origine({ p }: { p: Partage }) {
  useDonnees((d) => d.appareils); // se met à jour avec l'onglet Appareils
  const a = origine(p);
  return (
    <span className="inline-flex min-w-0 items-center gap-1 text-[11px] text-doux">
      <span className={a?.en_ligne ? "size-1.5 flex-none rounded-full bg-vert" : "size-1.5 flex-none rounded-full bg-tres-doux"} />
      <span className="truncate">{t("sur {appareil}", { appareil: p.resume.appareil_nom || "?" })}</span>
    </span>
  );
}

type Entree = { ts: number; genre: string; texte: string };

function DetailTache({ p, onFermer }: { p: Partage; onFermer: () => void }) {
  const [journal, setJournal] = useState<Entree[] | null>(null);
  const [attente, setAttente] = useState("");
  const [etat, setEtat] = useState("");
  const [consigne, setConsigne] = useState("");
  useEffect(() => {
    lirePartage<{ journal: Entree[] }>("tache", p.resume.id)
      .then((c) => setJournal(c.journal ?? []))
      .catch((e) => (erreurToast(e), setJournal([])));
  }, [p.resume.id, p.modifie]);

  const agir = async (action: string, params: Record<string, unknown> = {}) => {
    setAttente(action);
    try {
      toast(await agirPartage(p, action, params, setEtat));
      if (action === "consigne") setConsigne("");
    } catch (e) {
      erreurToast(e);
    } finally {
      setAttente("");
      setEtat("");
    }
  };
  const r = p.resume;
  const [libelle, couleur] = STATUTS[r.statut || ""] ?? [r.statut || "", "text-doux"];
  const sur = ` ${t("sur {appareil}", { appareil: r.appareil_nom || "?" })}`;
  return (
    <Feuille titre={r.titre} onFermer={onFermer}>
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className={couleur}>{t(libelle)}</span>
        <Origine p={p} />
        {r.etape !== undefined && <span className="text-doux">· {t("étape")} {r.etape}</span>}
      </div>
      <p className="mt-1 truncate font-mono text-[11px] text-tres-doux">{r.branche || r.projet}</p>
      {r.bilan && <p className="mt-2 text-[13px] text-doux">{r.bilan}</p>}
      <div className="mt-3 grid gap-2">
        {r.statut === "en_cours" ? (
          <Bouton variante="danger" icone={<Square className="size-4" />} chargement={attente === "arreter"} onClick={() => agir("arreter")}>
            {t("Arrêter") + sur}
          </Bouton>
        ) : (
          <Bouton variante="primaire" icone={<Play className="size-4" />} chargement={attente === "reprendre"} onClick={() => agir("reprendre")}>
            {t("Reprendre") + sur}
          </Bouton>
        )}
        {etat && <p className="text-[12px] text-doux">{etat}</p>}
        <div className="flex gap-2">
          <Champ className="flex-1" value={consigne} onChange={(e) => setConsigne(e.target.value)} placeholder={t("Changer ou préciser la tâche…")} />
          <Bouton icone={<Send className="size-4" />} disabled={!consigne.trim()} chargement={attente === "consigne"} onClick={() => agir("consigne", { texte: consigne.trim() })} />
        </div>
      </div>
      <h3 className="titre-hud mt-4 mb-1 text-[10px] text-tres-doux">{t("Déroulé")}</h3>
      {journal === null ? (
        <Loader2 className="size-4 animate-spin text-doux" />
      ) : (
        <div className="space-y-1.5">
          {journal.slice(-80).map((e, i) => (
            <div key={i} className="text-[12px]">
              <span className="mr-1.5 font-mono text-[10px] text-tres-doux">{new Date(e.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
              <span className={e.genre === "erreur" ? "text-rouge" : e.genre === "utilisateur" ? "text-ambre" : e.genre === "outil" ? "text-doux" : ""}>
                {String(e.texte ?? "").slice(0, 600)}
              </span>
            </div>
          ))}
          {!journal.length && <p className="text-[12px] text-doux">{t("Rien pour l'instant.")}</p>}
        </div>
      )}
    </Feuille>
  );
}

/**
 * Tâches de fond : Claude Code (ou Codex) code sur un de tes ordinateurs pendant que tu fais autre chose.
 * Toutes celles de tes ordinateurs sont listées ici ; reprendre ou arrêter est demandé à l'ordinateur qui l'a lancée.
 */
export function Taches() {
  const ordis = useDonnees((d) => d.appareils).filter((a) => !a.moi && a.plateforme !== "telephone");
  const { liste, charge } = usePartages();
  const taches = liste.filter((x) => x.genre === "tache").sort((a, b) => (b.resume.cree || 0) - (a.resume.cree || 0));
  const [appareil, setAppareil] = useState("");
  const [consigne, setConsigne] = useState("");
  const [projet, setProjet] = useState("");
  const [choisie, setChoisie] = useState<string | null>(null);
  const detail = taches.find((x) => x.resume.id === choisie);
  useEffect(() => void chargerPartages(), []);

  return (
    <div>
      <Entete
        titre={t("Tâches de fond")}
        retour={() => allerA("plus")}
        actions={
          <button className="grid size-9 place-items-center text-doux" onClick={() => void chargerPartages()} aria-label={t("Actualiser")}>
            <RefreshCw className={charge ? "size-4.5 animate-spin" : "size-4.5"} />
          </button>
        }
      />
      <Section titre={t("Tâches")}>
        {taches.length === 0 ? (
          <p className="p-3 text-[13px] text-doux">{t("Aucune tâche sur tes ordinateurs pour l'instant.")}</p>
        ) : (
          taches.map((p) => {
            const [libelle, couleur] = STATUTS[p.resume.statut || ""] ?? [p.resume.statut || "", "text-doux"];
            return (
              <Ligne key={p.resume.id} onClick={() => setChoisie(p.resume.id)}>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[14px]">{p.resume.titre}</div>
                  <div className="flex items-center gap-2">
                    <Origine p={p} />
                    {p.resume.maj && <span className="text-[11px] text-tres-doux">· {tempsRelatif(p.resume.maj)}</span>}
                  </div>
                </div>
                <span className={`flex-none text-[12px] ${couleur}`}>
                  {p.resume.statut === "en_cours" && <Loader2 className="mr-1 inline size-3 animate-spin" />}
                  {t(libelle)}
                </span>
              </Ligne>
            );
          })
        )}
      </Section>
      <Section titre={t("Nouvelle tâche")}>
        <div className="space-y-2 p-3">
          <select value={appareil} onChange={(e) => setAppareil(e.target.value)} className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3">
            <option value="">{t("L'ordinateur allumé")}</option>
            {ordis.map((a) => (
              <option key={a.id} value={a.nom}>
                {a.nom} {a.en_ligne ? "" : `(${t("hors ligne")})`}
              </option>
            ))}
          </select>
          <Zone rows={3} value={consigne} onChange={(e) => setConsigne(e.target.value)} placeholder={t("Ce qu'il faut coder ou corriger…")} />
          <Champ value={projet} onChange={(e) => setProjet(e.target.value)} placeholder={t("Projet (dossier sur l'ordinateur, facultatif)")} />
          <Bouton
            variante="primaire"
            className="w-full"
            icone={<Code2 className="size-4" />}
            disabled={!consigne.trim()}
            onClick={() => {
              allerA("assistant");
              void envoyer(
                t("Lance une tâche de code en arrière-plan{sur} : {c}{p}", {
                  sur: appareil ? ` sur ${appareil}` : "",
                  c: consigne.trim(),
                  p: projet.trim() ? ` (projet : ${projet.trim()})` : "",
                }),
              );
            }}
          >
            {t("Lancer avec Claude Code")}
          </Bouton>
        </div>
      </Section>
      {detail && <DetailTache p={detail} onFermer={() => setChoisie(null)} />}
    </div>
  );
}
