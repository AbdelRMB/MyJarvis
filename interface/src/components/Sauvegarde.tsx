import { ArchiveRestore, HardDriveDownload, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import { toast } from "../stores/toasts";
import { Bouton, Champ, Panneau } from "./ui";

type Contenu = { souvenirs: number; jours: number; transcriptions: number };
type Repris = { souvenirs: number; historique: number; afaire: number; automatisations: number; sites: number; profil: boolean; transcriptions: number };

/** Sauvegarde complète chiffrée (un fichier .wesley) et restauration qui ajoute ce qui manque, sans rien écraser. */
export function PanneauSauvegarde() {
  const [mdp, setMdp] = useState("");
  const [envoi, setEnvoi] = useState<"" | "creer" | "restaurer">("");
  const fichier = useRef<HTMLInputElement>(null);

  const creer = async () => {
    setEnvoi("creer");
    try {
      const r = await api<{ fichier: string; contenu: Contenu }>("/api/sauvegarde", { method: "POST", json: { mot_de_passe: mdp } });
      toast(
        t("Sauvegarde enregistrée : {f} ({s} souvenirs, {j} jours de conversation, {tr} transcriptions).", {
          f: r.fichier,
          s: r.contenu.souvenirs,
          j: r.contenu.jours,
          tr: r.contenu.transcriptions,
        }),
        "succes",
      );
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi("");
    }
  };

  const restaurer = async (f: File) => {
    setEnvoi("restaurer");
    try {
      const r = await api<{ repris: Repris }>("/api/sauvegarde/restaurer", {
        method: "POST",
        body: f,
        headers: { "content-type": "application/octet-stream", "x-mot-de-passe": encodeURIComponent(mdp) },
      });
      const p = r.repris;
      toast(
        t("Restauré : {s} souvenirs, {h} lignes de conversation, {a} tâches, {au} automatisations, {tr} transcriptions ajoutés.", {
          s: p.souvenirs,
          h: p.historique,
          a: p.afaire,
          au: p.automatisations,
          tr: p.transcriptions,
        }),
        "succes",
      );
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi("");
      if (fichier.current) fichier.current.value = "";
    }
  };

  const assez = mdp.length >= 8;
  return (
    <Panneau titre={t("Sauvegarde complète")} icone={<ArchiveRestore />}>
      <p className="text-[13px] leading-relaxed text-doux">
        {t("Un seul fichier chiffré avec tes souvenirs, tes conversations, ta liste À faire, tes automatisations, tes sites appris et tes transcriptions. Pour changer d'ordinateur, garder une copie à toi ou repartir en local. Les clés et mots de passe des connecteurs n'y sont pas.")}
      </p>
      <Champ
        className="mt-3"
        type="password"
        autoComplete="new-password"
        placeholder={t("Mot de passe de la sauvegarde (8 caractères ou plus)")}
        value={mdp}
        onChange={(e) => setMdp(e.target.value)}
      />
      <p className="mt-1 text-[12px] text-tres-doux">{t("Sans ce mot de passe, la sauvegarde est illisible : personne ne peut le retrouver.")}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Bouton icone={<HardDriveDownload className="size-4" />} chargement={envoi === "creer"} disabled={!assez || !!envoi} onClick={creer}>
          {t("Créer une sauvegarde")}
        </Bouton>
        <Bouton variante="fantome" icone={<Upload className="size-4" />} chargement={envoi === "restaurer"} disabled={!assez || !!envoi} onClick={() => fichier.current?.click()}>
          {t("Restaurer…")}
        </Bouton>
        <input ref={fichier} type="file" accept=".wesley" className="hidden" onChange={(e) => e.target.files?.[0] && restaurer(e.target.files[0])} />
      </div>
      <p className="mt-2 text-[12px] text-tres-doux">{t("Restaurer ajoute seulement ce qui manque : rien n'est écrasé ni mis en double.")}</p>
    </Panneau>
  );
}
