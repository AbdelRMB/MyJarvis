import { Bug, HelpCircle, Inbox, Lightbulb, LifeBuoy, MessageSquare, Send, Shield, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Bouton, Champ, EnTetePage, Onglets, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";
import { bus } from "../stores/jarvis";
import { toast } from "../stores/toasts";

type Genre = "bug" | "amelioration" | "idee" | "question" | "autre";
type StatutT = "ouvert" | "en_cours" | "resolu" | "ferme";
type Ticket = {
  id: number;
  genre: Genre;
  titre: string;
  description: string;
  statut: StatutT;
  reponse: string;
  version: string;
  plateforme: string;
  appareil: string;
  cree: number;
  modifie: number;
  email?: string;
  prenom?: string;
};
type Etat = { connecte: boolean; admin: boolean; miens: Ticket[]; tous: Ticket[] };

const GENRES: Record<Genre, [string, typeof Bug]> = {
  bug: ["Bug", Bug],
  amelioration: ["Amélioration", Sparkles],
  idee: ["Idée", Lightbulb],
  question: ["Question", HelpCircle],
  autre: ["Autre", MessageSquare],
};
const STATUTS: Record<StatutT, [string, "hud" | "ambre" | "vert" | "doux"]> = {
  ouvert: ["Ouvert", "ambre"],
  en_cours: ["En cours", "hud"],
  resolu: ["Résolu", "vert"],
  ferme: ["Fermé", "doux"],
};
const date = (ts: number) => new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });

function LigneTicket({ x, admin, onMaj, onSupprimer }: { x: Ticket; admin: boolean; onMaj?: (statut: string, reponse?: string) => void; onSupprimer?: () => void }) {
  const [ouvert, setOuvert] = useState(false);
  const [reponse, setReponse] = useState(x.reponse);
  useEffect(() => setReponse(x.reponse), [x.reponse]);
  const [g, I] = GENRES[x.genre] ?? GENRES.autre;
  const [s, ton] = STATUTS[x.statut] ?? STATUTS.ouvert;
  return (
    <div className="rounded-md border border-ligne bg-surface/60">
      <button onClick={() => setOuvert(!ouvert)} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <I className="size-4 flex-none text-hud" aria-label={t(g)} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">
            <span className="text-tres-doux">#{x.id}</span> {x.titre}
          </div>
          <div className="text-[12px] text-doux">
            {t(g)} · {date(x.cree)}
            {admin && x.email && ` · ${x.prenom ? `${x.prenom} (${x.email})` : x.email}`}
            {x.version && ` · v${x.version} ${x.plateforme}`}
          </div>
        </div>
        {x.reponse && !admin && <MessageSquare className="size-4 flex-none text-hud" aria-label={t("Réponse")} />}
        <Badge ton={ton}>{t(s)}</Badge>
      </button>
      {ouvert && (
        <div className="space-y-3 border-t border-ligne px-4 py-3 text-sm">
          {x.description ? <p className="whitespace-pre-wrap text-doux">{x.description}</p> : <p className="text-tres-doux">{t("(pas de description)")}</p>}
          {!admin && x.reponse && (
            <div className="rounded-md border border-hud/30 bg-hud/5 p-3">
              <div className="titre-hud mb-1 text-[10px] text-hud">{t("Réponse")}</div>
              <p className="whitespace-pre-wrap">{x.reponse}</p>
            </div>
          )}
          {admin && onMaj && (
            <>
              <textarea
                rows={3}
                value={reponse}
                onChange={(e) => setReponse(e.target.value)}
                placeholder={t("Réponse à l'auteur (il la verra dans son Jarvis)")}
                className="w-full rounded-md border border-ligne-forte bg-surface-2 p-2 text-sm outline-none focus:border-hud"
              />
              <div className="flex flex-wrap items-center gap-2">
                {(Object.keys(STATUTS) as StatutT[]).map((k) => (
                  <button
                    key={k}
                    onClick={() => onMaj(k)}
                    className={cx("h-8 rounded-md border px-3 text-[12px]", x.statut === k ? "border-hud bg-hud/15 text-hud" : "border-ligne text-doux hover:text-texte")}
                  >
                    {t(STATUTS[k][0])}
                  </button>
                ))}
                <Bouton taille="sm" variante="primaire" icone={<Send className="size-3.5" />} className="ml-auto" disabled={reponse === x.reponse} onClick={() => onMaj("", reponse)}>
                  {t("Envoyer la réponse")}
                </Bouton>
                {onSupprimer && (
                  <button onClick={onSupprimer} aria-label={t("Supprimer")} className="rounded p-1.5 text-tres-doux hover:text-rouge">
                    <Trash2 className="size-4" />
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function VueTickets() {
  const [e, setE] = useState<Etat | null>(null);
  const [onglet, setOnglet] = useState<"miens" | "admin">("miens");
  const [filtre, setFiltre] = useState<StatutT | "actifs" | "">("actifs");
  const [f, setF] = useState({ genre: "bug" as Genre, titre: "", description: "" });
  const [envoi, setEnvoi] = useState(false);

  const charger = () => api<Etat>("/api/tickets").then(setE).catch((x) => toast((x as Error).message, "erreur"));
  useEffect(() => {
    charger();
    const sur = () => charger();
    bus.addEventListener("tickets_maj", sur);
    return () => bus.removeEventListener("tickets_maj", sur);
  }, []);

  const envoyer = async () => {
    setEnvoi(true);
    try {
      setE(await api<Etat>("/api/tickets", { method: "POST", json: f }));
      setF({ genre: f.genre, titre: "", description: "" });
      toast(t("Ticket envoyé. Tu seras prévenu de la réponse."), "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi(false);
    }
  };
  const maj = async (x: Ticket, statut: string, reponse?: string) => {
    try {
      setE(await api<Etat>(`/api/tickets/${x.id}`, { method: "PATCH", json: { statut, ...(reponse !== undefined && { reponse }) } }));
      if (reponse !== undefined) toast(t("Réponse envoyée."), "succes");
    } catch (er) {
      toast((er as Error).message, "erreur");
    }
  };
  const supprimer = async (x: Ticket) => {
    if (!confirm(t("Supprimer définitivement ce ticket ?"))) return;
    try {
      setE(await api<Etat>(`/api/tickets/${x.id}`, { method: "DELETE" }));
    } catch (er) {
      toast((er as Error).message, "erreur");
    }
  };
  const select = "h-10 rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm";

  if (e && !e.connecte)
    return (
      <div className="h-full overflow-y-auto p-4 md:p-8">
        <EnTetePage titre={t("Tickets")} />
        <Vide icone={<LifeBuoy />} titre={t("Connecte-toi à un compte Jarvis")} texte={t("Les tickets sont envoyés depuis ton compte en ligne.")} />
      </div>
    );

  const tous = (e?.tous ?? []).filter((x) => (filtre === "actifs" ? x.statut === "ouvert" || x.statut === "en_cours" : !filtre || x.statut === filtre));
  const nbActifs = (e?.tous ?? []).filter((x) => x.statut === "ouvert" || x.statut === "en_cours").length;

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage titre={t("Tickets")} sousTitre={t("Un bug, une idée, une amélioration ? Envoie-la au développeur de Jarvis. Tu peux aussi le dire à Jarvis : « signale un bug : … ».")} />

      {e?.admin && (
        <div className="mb-6">
          <Onglets
            onglets={[
              { id: "miens", libelle: t("Mes tickets"), icone: <Inbox /> },
              { id: "admin", libelle: `${t("Tous les tickets")}${nbActifs ? ` (${nbActifs})` : ""}`, icone: <Shield /> },
            ]}
            actif={onglet}
            onChange={setOnglet}
          />
        </div>
      )}

      {onglet === "miens" || !e?.admin ? (
        <>
          <Panneau titre={t("Nouveau ticket")} icone={<Send />} className="mb-6">
            <div className="grid gap-3 sm:grid-cols-[170px_1fr]">
              <select value={f.genre} onChange={(x) => setF({ ...f, genre: x.target.value as Genre })} className={select} aria-label={t("Type")}>
                {(Object.keys(GENRES) as Genre[]).map((g) => (
                  <option key={g} value={g}>
                    {t(GENRES[g][0])}
                  </option>
                ))}
              </select>
              <Champ placeholder={t("Titre (ex : le micro se coupe tout seul)")} value={f.titre} onChange={(x) => setF({ ...f, titre: x.target.value })} />
              <textarea
                rows={4}
                value={f.description}
                onChange={(x) => setF({ ...f, description: x.target.value })}
                placeholder={t("Détails : ce qui s'est passé, ce que tu attendais, comment le reproduire…")}
                className="w-full rounded-md border border-ligne-forte bg-surface-2 p-2 text-sm outline-none focus:border-hud sm:col-span-2"
              />
            </div>
            <Bouton className="mt-3" variante="primaire" icone={<Send />} chargement={envoi} disabled={f.titre.trim().length < 3} onClick={envoyer}>
              {t("Envoyer")}
            </Bouton>
          </Panneau>
          {e && e.miens.length === 0 ? (
            <Vide icone={<LifeBuoy />} titre={t("Aucun ticket")} texte={t("Tes tickets et leurs réponses apparaîtront ici.")} />
          ) : (
            <div className="space-y-2">
              {e?.miens.map((x) => (
                <LigneTicket key={x.id} x={x} admin={false} />
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            {(
              [
                ["actifs", "Ouverts et en cours"],
                ["", "Tous"],
                ["resolu", "Résolus"],
                ["ferme", "Fermés"],
              ] as const
            ).map(([k, l]) => (
              <button
                key={k}
                onClick={() => setFiltre(k)}
                className={cx("rounded-full border px-3 py-1 text-[12px]", filtre === k ? "border-hud text-hud" : "border-ligne text-doux hover:text-texte")}
              >
                {t(l)}
              </button>
            ))}
          </div>
          {tous.length === 0 ? (
            <Vide icone={<Inbox />} titre={t("Aucun ticket")} />
          ) : (
            <div className="space-y-2">
              {tous.map((x) => (
                <LigneTicket key={x.id} x={x} admin onMaj={(s, r) => maj(x, s, r)} onSupprimer={() => supprimer(x)} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
