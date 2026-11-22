import { useEffect, useState } from "react";
import { Badge, Bouton, Champ } from "../../../src/components/ui";
import { cx } from "../../../src/lib/format";
import { t } from "../../../src/lib/i18n";
import { chargerTickets, envoyerTicket, traiterTicket, useDonnees } from "../moteur/donnees";
import { session } from "../moteur/stockage";
import type { Ticket } from "../moteur/types";
import { allerA, Entete, erreurToast, Feuille, Ligne, Section, tempsRelatif, toast, Zone } from "../ui";

const GENRES = [
  { id: "bug", libelle: "Bug" },
  { id: "amelioration", libelle: "Amélioration" },
  { id: "idee", libelle: "Idée" },
  { id: "question", libelle: "Question" },
];
const STATUTS: Record<string, string> = { ouvert: "ouvert", en_cours: "en cours", resolu: "résolu", ferme: "fermé" };
const ton = (s: string) => (s === "resolu" ? "vert" : s === "en_cours" ? "ambre" : s === "ferme" ? "doux" : "hud") as "vert" | "ambre" | "doux" | "hud";

/** Tickets envoyés au développeur (et, pour les administrateurs, ceux de tous les utilisateurs). */
export function Tickets() {
  const { tickets, ticketsAdmin } = useDonnees();
  const admin = !!session()?.admin;
  const [onglet, setOnglet] = useState<"miens" | "tous">("miens");
  const [genre, setGenre] = useState("bug");
  const [titre, setTitre] = useState("");
  const [desc, setDesc] = useState("");
  const [charge, setCharge] = useState(false);
  const [detail, setDetail] = useState<Ticket | null>(null);
  useEffect(() => void chargerTickets().catch(() => {}), []);

  async function envoyerT() {
    setCharge(true);
    try {
      await envoyerTicket(genre, titre.trim(), desc.trim());
      setTitre("");
      setDesc("");
      toast(t("Ticket envoyé."));
    } catch (e) {
      erreurToast(e);
    } finally {
      setCharge(false);
    }
  }

  const liste = onglet === "tous" ? ticketsAdmin : tickets;
  return (
    <div>
      <Entete titre={t("Tickets")} retour={() => allerA("plus")} />
      <Section titre={t("Nouveau ticket")}>
        <div className="space-y-2 p-3">
          <div className="grid grid-cols-4 gap-1">
            {GENRES.map((g) => (
              <button key={g.id} onClick={() => setGenre(g.id)} className={cx("rounded border py-1.5 text-[12px]", genre === g.id ? "border-hud bg-hud/15 text-hud" : "border-ligne text-doux")}>
                {t(g.libelle)}
              </button>
            ))}
          </div>
          <Champ value={titre} onChange={(e) => setTitre(e.target.value)} placeholder={t("Titre")} />
          <Zone rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={t("Détails…")} />
          <Bouton variante="primaire" className="w-full" chargement={charge} disabled={titre.trim().length < 3} onClick={envoyerT}>
            {t("Envoyer au développeur")}
          </Bouton>
        </div>
      </Section>
      {admin && (
        <div className="mt-3 grid grid-cols-2 px-3 text-sm">
          {(["miens", "tous"] as const).map((o) => (
            <button key={o} onClick={() => setOnglet(o)} className={cx("border-b-2 py-2", onglet === o ? "border-hud text-hud" : "border-transparent text-doux")}>
              {o === "miens" ? t("Mes tickets") : t("Tous (admin) · {n}", { n: ticketsAdmin.length })}
            </button>
          ))}
        </div>
      )}
      <Section titre={t("Tickets · {n}", { n: liste.length })}>
        {liste.map((x) => (
          <Ligne key={x.id} onClick={() => setDetail(x)}>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-[11px] text-doux">
                <Badge ton={ton(x.statut)}>{t(STATUTS[x.statut] || x.statut)}</Badge>n°{x.id} · {tempsRelatif(x.modifie)}
                {x.prenom && ` · ${x.prenom}`}
              </div>
              <div className="truncate text-[14px]">{x.titre}</div>
              {x.reponse && <div className="truncate text-[12px] text-hud-clair">↳ {x.reponse}</div>}
            </div>
          </Ligne>
        ))}
        {!liste.length && <p className="px-3 py-4 text-[13px] text-doux">{t("Aucun ticket.")}</p>}
      </Section>
      {detail && <Detail x={detail} admin={admin && onglet === "tous"} onFermer={() => setDetail(null)} />}
    </div>
  );
}

function Detail({ x, admin, onFermer }: { x: Ticket; admin: boolean; onFermer: () => void }) {
  const [reponse, setReponse] = useState(x.reponse);
  return (
    <Feuille titre={`n°${x.id} · ${x.genre}`} onFermer={onFermer}>
      <p className="font-medium">{x.titre}</p>
      <p className="mt-2 text-sm whitespace-pre-wrap text-doux">{x.description || "—"}</p>
      <p className="mt-2 text-[12px] text-tres-doux">
        {x.plateforme} · {x.version} · {x.appareil} {x.email && `· ${x.email}`}
      </p>
      {!admin && x.reponse && <p className="mt-3 rounded-md border border-ligne bg-surface-2 p-3 text-sm">{x.reponse}</p>}
      {admin && (
        <div className="mt-4 space-y-2">
          <Zone rows={3} value={reponse} onChange={(e) => setReponse(e.target.value)} placeholder={t("Réponse à l'utilisateur…")} />
          <div className="grid grid-cols-2 gap-1">
            {Object.entries(STATUTS).map(([s, l]) => (
              <Bouton key={s} variante={x.statut === s ? "primaire" : "contour"} taille="sm" onClick={() => traiterTicket(x.id, s, reponse).then(onFermer, erreurToast)}>
                {t(l)}
              </Bouton>
            ))}
          </div>
        </div>
      )}
    </Feuille>
  );
}
