import { Download, Laptop, LogOut, Monitor, RefreshCw, Send, Share2, Smartphone, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Bouton, Champ } from "../../../src/components/ui";
import { cx } from "../../../src/lib/format";
import { t } from "../../../src/lib/i18n";
import { envoyer as envoyerOrdre } from "../moteur/appareils";
import { deb64 } from "../moteur/crypto";
import { chargerAppareils, deconnecterAppareil, supprimerFichier, useDonnees } from "../moteur/donnees";
import type { Appareil, FichierRecu } from "../moteur/types";
import { Entete, erreurToast, Feuille, Ligne, Section, tempsRelatif, toast } from "../ui";

const icone = (a: Appareil) => (a.plateforme === "telephone" ? Smartphone : a.plateforme === "mac" ? Laptop : Monitor);

function blob(f: FichierRecu) {
  return new Blob([deb64(f.contenu)]);
}

/** Tes appareils (même compte) : qui est allumé, leur envoyer une demande, journal des ordres, fichiers reçus. */
export function Appareils() {
  const { appareils, ordres, fichiers } = useDonnees();
  const [cible, setCible] = useState<Appareil | null>(null);
  const [charge, setCharge] = useState(false);

  const actualiser = () => {
    setCharge(true);
    chargerAppareils()
      .catch(erreurToast)
      .finally(() => setCharge(false));
  };
  useEffect(actualiser, []);

  async function partager(f: FichierRecu) {
    const fichier = new File([blob(f)], f.nom);
    if (navigator.canShare?.({ files: [fichier] })) await navigator.share({ files: [fichier] }).catch(() => {});
    else telecharger(f);
  }
  function telecharger(f: FichierRecu) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob(f));
    a.download = f.nom;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  }

  return (
    <div>
      <Entete
        titre={t("Appareils")}
        sous={t("{n} en ligne", { n: appareils.filter((a) => a.en_ligne).length })}
        actions={
          <button onClick={actualiser} className="grid size-9 place-items-center text-doux" aria-label={t("Actualiser")}>
            <RefreshCw className={cx("size-4.5", charge && "animate-spin")} />
          </button>
        }
      />
      <Section titre={t("Mes appareils")}>
        {appareils.map((a) => {
          const I = icone(a);
          return (
            <Ligne key={a.id} onClick={a.moi ? undefined : () => setCible(a)}>
              <I className={cx("size-5 flex-none", a.en_ligne ? "text-hud" : "text-tres-doux")} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[15px]">
                  {a.nom || t("Appareil")} {a.moi && <Badge>{t("ce téléphone")}</Badge>}
                </div>
                <div className="truncate text-[12px] text-doux">
                  {a.en_ligne ? (a.occupe ? t("occupé") : t("en ligne")) : `${t("hors ligne")} · ${tempsRelatif(a.vu)}`}
                  {a.version && ` · v${a.version}`}
                  {!a.moi && a.en_ligne && !a.accepte && ` · ${t("refuse les ordres")}`}
                </div>
              </div>
              <span className={cx("size-2 flex-none rounded-full", a.en_ligne ? "bg-vert shadow-[0_0_8px] shadow-vert" : "bg-tres-doux")} />
            </Ligne>
          );
        })}
      </Section>

      {fichiers.length > 0 && (
        <Section titre={t("Fichiers reçus · {n}", { n: fichiers.length })}>
          {[...fichiers].reverse().map((f) => (
            <Ligne key={f.id}>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[14px]">{f.nom}</div>
                <div className="text-[12px] text-doux">
                  {Math.ceil(f.taille / 1024)} Ko · {f.de} · {tempsRelatif(f.ts)}
                </div>
              </div>
              <button onClick={() => void partager(f)} className="grid size-9 place-items-center text-hud" aria-label={t("Partager")}>
                <Share2 className="size-4.5" />
              </button>
              <button onClick={() => telecharger(f)} className="grid size-9 place-items-center text-doux" aria-label={t("Télécharger")}>
                <Download className="size-4.5" />
              </button>
              <button onClick={() => supprimerFichier(f.id)} className="grid size-9 place-items-center text-tres-doux" aria-label={t("Supprimer")}>
                <Trash2 className="size-4" />
              </button>
            </Ligne>
          ))}
        </Section>
      )}

      <Section titre={t("Journal des ordres")}>
        {[...ordres]
          .reverse()
          .slice(0, 50)
          .map((o, i) => (
            <Ligne key={i}>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-[11px] text-doux">
                  <Badge ton={o.statut === "ok" ? "vert" : o.statut === "refuse" ? "ambre" : "rouge"}>{o.sens === "envoye" ? `→ ${o.appareil}` : `← ${o.appareil}`}</Badge>
                  {tempsRelatif(o.ts)}
                </div>
                <div className="truncate text-[13px]">{o.quoi}</div>
                {o.resultat && <div className="line-clamp-2 text-[12px] text-doux">{o.resultat}</div>}
              </div>
            </Ligne>
          ))}
        {!ordres.length && <p className="px-3 py-4 text-[13px] text-doux">{t("Aucun ordre pour l'instant. Dis par exemple « sur mon PC, ouvre Discord ».")}</p>}
      </Section>
      {cible && <Piloter a={cible} onFermer={() => setCible(null)} />}
    </div>
  );
}

function Piloter({ a, onFermer }: { a: Appareil; onFermer: () => void }) {
  const [texte, setTexte] = useState("");
  const [etat, setEtat] = useState("");
  const [reponse, setReponse] = useState("");
  const [charge, setCharge] = useState(false);

  async function go(contenu: Record<string, unknown>) {
    setCharge(true);
    setReponse("");
    try {
      const r = await envoyerOrdre(a, contenu, setEtat);
      setReponse(r.resultat || "OK");
    } catch (e) {
      setReponse((e as Error).message);
    } finally {
      setCharge(false);
      setEtat("");
    }
  }

  return (
    <Feuille titre={a.nom} onFermer={onFermer}>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (texte.trim()) void go({ type: "demande", texte });
        }}
      >
        <Champ value={texte} onChange={(e) => setTexte(e.target.value)} placeholder={t("Que doit-il faire ?")} disabled={!a.en_ligne} />
        <Bouton type="submit" variante="primaire" chargement={charge} disabled={!a.en_ligne} aria-label={t("Envoyer")}>
          <Send className="size-4" />
        </Bouton>
      </form>
      {!a.en_ligne && <p className="mt-2 text-sm text-ambre">{t("{nom} est hors ligne (éteint ou Wesley fermé).", { nom: a.nom })}</p>}
      {etat && <p className="mt-3 text-sm text-doux">{etat}</p>}
      {reponse && <p className="mt-3 rounded-md border border-ligne bg-surface-2 p-3 text-sm whitespace-pre-wrap">{reponse}</p>}
      <div className="mt-5 grid grid-cols-2 gap-2">
        <Bouton variante="contour" disabled={!a.en_ligne || charge} onClick={() => void go({ type: "ping" })}>
          {t("Tester")}
        </Bouton>
        {a.plateforme !== "telephone" && (
          <Bouton variante="contour" disabled={!a.en_ligne || charge} onClick={() => void go({ type: "mettre_a_jour" })}>
            {t("Mettre à jour")}
          </Bouton>
        )}
        <Bouton
          variante="danger"
          icone={<LogOut className="size-4" />}
          className="col-span-2"
          onClick={() =>
            confirm(t("Déconnecter {nom} de ton compte ?", { nom: a.nom })) &&
            deconnecterAppareil(a.id).then(() => (toast(t("Appareil déconnecté.")), void chargerAppareils(), onFermer()), erreurToast)
          }
        >
          {t("Déconnecter cet appareil")}
        </Bouton>
      </div>
    </Feuille>
  );
}
