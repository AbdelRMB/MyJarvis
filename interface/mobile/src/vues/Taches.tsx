import { Code2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Bouton, Champ } from "../../../src/components/ui";
import { t } from "../../../src/lib/i18n";
import { envoyer } from "../assistant";
import { useDonnees } from "../moteur/donnees";
import { executerOutil } from "../moteur/outils";
import { allerA, Entete, Section, Zone } from "../ui";

/**
 * Tâches de fond : Claude Code (ou Codex) code sur un de tes ordinateurs pendant que tu fais autre chose.
 * Le téléphone les lance, les suit et les pilote en passant par l'ordinateur.
 */
export function Taches() {
  const ordis = useDonnees((d) => d.appareils).filter((a) => !a.moi && a.plateforme !== "telephone");
  const [appareil, setAppareil] = useState("");
  const [liste, setListe] = useState("");
  const [etat, setEtat] = useState("");
  const [charge, setCharge] = useState(false);
  const [consigne, setConsigne] = useState("");
  const [projet, setProjet] = useState("");

  async function actualiser() {
    setCharge(true);
    setListe("");
    setListe(await executerOutil("lister_taches", { appareil }, { surEtat: setEtat }));
    setEtat("");
    setCharge(false);
  }

  return (
    <div>
      <Entete
        titre={t("Tâches de fond")}
        retour={() => allerA("plus")}
        actions={
          <button className="grid size-9 place-items-center text-doux" onClick={actualiser} aria-label={t("Actualiser")}>
            <RefreshCw className={charge ? "size-4.5 animate-spin" : "size-4.5"} />
          </button>
        }
      />
      <div className="space-y-2 px-3 pt-3">
        <select value={appareil} onChange={(e) => setAppareil(e.target.value)} className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3">
          <option value="">{t("L'ordinateur allumé")}</option>
          {ordis.map((a) => (
            <option key={a.id} value={a.nom}>
              {a.nom} {a.en_ligne ? "" : `(${t("hors ligne")})`}
            </option>
          ))}
        </select>
      </div>
      <Section titre={t("Nouvelle tâche")}>
        <div className="space-y-2 p-3">
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
      <Section titre={t("Tâches")}>
        <div className="p-3 text-[13px] whitespace-pre-wrap text-doux">
          {etat || liste || t("Touche ↻ pour demander la liste à l'ordinateur. Pour suivre ou modifier une tâche, demande-le à Wesley (« où en est la tâche … ? »).")}
        </div>
      </Section>
    </div>
  );
}
