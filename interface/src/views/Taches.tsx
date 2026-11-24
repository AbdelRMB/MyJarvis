import { Bot, CheckCircle2, CircleDot, FolderOpen, ListTodo, Loader2, Monitor, Play, Plus, Send, Square, Trash2, User, Wrench, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Badge, Bouton, Champ, EnTetePage, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";
import { bus } from "../stores/wesley";
import { toast } from "../stores/toasts";
import { useOrdinateurs } from "./Transcription";

type Statut = "en_cours" | "terminee" | "echec" | "arretee" | "interrompue";
type Resume = {
  id: string;
  titre: string;
  statut: Statut;
  outil: string;
  projet: string;
  branche: string;
  dossier: string;
  cree: number;
  maj: number;
  etape: number;
  bilan: string;
  wesley_md?: string[] | null;
  /** Lancée sur un autre appareil du compte : c'est lui qui la reprend, l'arrête ou la change. */
  distant?: boolean;
  appareil?: string;
  en_ligne?: boolean;
};
type Entree = { ts: number; genre: "utilisateur" | "wesley" | "claude" | "outil" | "info" | "erreur"; texte: string };
type Tache = Resume & { consigne: string; ajouts: string[]; journal: Entree[] };

const STATUTS: Record<Statut, [string, string]> = {
  en_cours: ["En cours", "text-hud"],
  terminee: ["Terminée", "text-vert"],
  echec: ["Échec", "text-rouge"],
  arretee: ["Arrêtée", "text-doux"],
  interrompue: ["Interrompue", "text-ambre"],
};
const QUI: Record<Entree["genre"], [string, typeof User]> = {
  utilisateur: ["Toi", User],
  wesley: ["Wesley → agent", Bot],
  claude: ["Agent", Bot],
  outil: ["Action", Wrench],
  info: ["Info", CircleDot],
  erreur: ["Erreur", XCircle],
};

/** Appareil d'origine d'une tâche lancée ailleurs (point vert : allumé avec Wesley ouvert). */
export function Origine({ appareil, enLigne }: { appareil?: string; enLigne?: boolean }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1 text-[11px] text-doux" title={enLigne ? t("En ligne") : t("Hors ligne")}>
      <Monitor className="size-3 flex-none" />
      <span className="truncate">{t("sur {appareil}", { appareil: appareil ?? "?" })}</span>
      <span className={cx("size-1.5 flex-none rounded-full", enLigne ? "bg-vert" : "bg-tres-doux")} />
    </span>
  );
}

function Pastille({ s }: { s: Statut }) {
  const [l, c] = STATUTS[s] ?? [s, "text-doux"];
  return (
    <span className={cx("inline-flex items-center gap-1 text-[12px]", c)}>
      {s === "en_cours" ? <Loader2 className="size-3.5 animate-spin" /> : s === "terminee" ? <CheckCircle2 className="size-3.5" /> : <CircleDot className="size-3.5" />}
      {t(l)}
    </span>
  );
}

export function VueTaches() {
  const [liste, setListe] = useState<Resume[]>([]);
  const [choisie, setChoisie] = useState<string | null>(null);
  const [detail, setDetail] = useState<Tache | null>(null);
  const [nouvelle, setNouvelle] = useState({ consigne: "", projet: "", outil: "claude_code", appareil: "" });
  const ordis = useOrdinateurs();
  const [ajout, setAjout] = useState("");
  const defilement = useRef<HTMLDivElement>(null);

  const charger = () => api<Resume[]>("/api/taches").then(setListe).catch(() => {});
  const chargerDetail = (id: string) => api<Tache>(`/api/taches/${id}`).then(setDetail).catch(() => {});
  useEffect(() => {
    charger();
    const sur = (e: Event) => {
      charger();
      // id vide : une tâche d'un autre appareil a changé (elle peut être celle qu'on regarde)
      const id = (e as CustomEvent<string>).detail;
      if (choisieRef.current && (!id || id === choisieRef.current)) chargerDetail(choisieRef.current);
    };
    bus.addEventListener("tache_maj", sur);
    return () => bus.removeEventListener("tache_maj", sur);
  }, []);
  const choisieRef = useRef<string | null>(null);
  useEffect(() => {
    choisieRef.current = choisie;
    if (choisie) chargerDetail(choisie);
  }, [choisie]);
  // on fait défiler le journal lui-même : scrollIntoView décalait aussi toute la fenêtre (écran noir)
  useEffect(() => {
    const d = defilement.current;
    if (d) d.scrollTop = d.scrollHeight;
  }, [detail?.id, detail?.journal?.length]);

  const creer = async () => {
    try {
      const r = await api<Resume & { message?: string; distant?: boolean }>("/api/taches", { method: "POST", json: nouvelle });
      setNouvelle({ ...nouvelle, consigne: "" });
      if (r.distant) toast(r.message ?? "", "succes");
      else setChoisie(r.id);
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  // tâche d'un autre appareil : l'action lui est demandée (jusqu'à ~1 min) ; s'il ne peut pas, on dit pourquoi
  const [attente, setAttente] = useState("");
  const agir = async (action: string, corps?: object) => {
    if (!detail) return;
    setAttente(action);
    try {
      const r = await api<{ message?: string }>(`/api/taches/${detail.id}/${action}`, { method: "POST", json: corps ?? {} });
      if (r.message) toast(r.message, "succes");
      chargerDetail(detail.id);
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setAttente("");
    }
  };
  const supprimer = async () => {
    if (!detail) return;
    const question = detail.distant
      ? t("Supprimer cette tâche ? Elle sera retirée de {appareil} et de tous tes appareils (la branche et son code restent).", { appareil: detail.appareil ?? "?" })
      : t("Supprimer cette tâche de la liste ? (la branche et son code restent)");
    if (!confirm(question)) return;
    setAttente("supprimer");
    try {
      const r = await api<{ message?: string }>(`/api/taches/${detail.id}`, { method: "DELETE" });
      if (r.message) toast(r.message, "succes");
      setChoisie(null);
      setDetail(null);
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setAttente("");
    }
  };
  const sur = detail?.distant ? ` ${t("sur {appareil}", { appareil: detail.appareil ?? "?" })}` : "";

  return (
    <div className="flex h-full min-h-0 flex-col p-4 md:p-8">
      <EnTetePage
        titre={t("Tâches")}
        sousTitre={t("Le code que Wesley fait en arrière-plan (avec Claude Code ou lui-même), chacun sur sa branche. Continue à lui parler pendant ce temps : il peut changer une tâche en cours.")}
      />
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[340px_1fr]">
        <div className="flex min-h-0 flex-col gap-3">
          <Panneau titre={t("Nouvelle tâche")} icone={<Plus />}>
            <textarea
              rows={3}
              value={nouvelle.consigne}
              onChange={(e) => setNouvelle({ ...nouvelle, consigne: e.target.value })}
              placeholder={t("Ce qu'il faut coder… (ou demande-le simplement à Wesley)")}
              className="w-full rounded-md border border-ligne-forte bg-surface-2 p-2 text-sm outline-none focus:border-hud"
            />
            {ordis.length > 0 && (
              <select
                value={nouvelle.appareil}
                onChange={(e) => setNouvelle({ ...nouvelle, appareil: e.target.value })}
                className="mt-2 h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
              >
                <option value="">{t("Sur cet ordinateur")}</option>
                {ordis.map((o) => (
                  <option key={o.id} value={o.id}>
                    {t("Sur {appareil}", { appareil: o.nom })} {o.en_ligne ? "" : `(${t("hors ligne")})`}
                  </option>
                ))}
              </select>
            )}
            <Champ className="mt-2" placeholder={t("Dossier du projet (ex : ~/Desktop/mon-projet)")} value={nouvelle.projet} onChange={(e) => setNouvelle({ ...nouvelle, projet: e.target.value })} />
            <select
              value={nouvelle.outil}
              onChange={(e) => setNouvelle({ ...nouvelle, outil: e.target.value })}
              className="mt-2 h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
            >
              <option value="claude_code">{t("Claude Code, piloté par Wesley")}</option>
              <option value="codex">{t("Codex (OpenAI), piloté par Wesley")}</option>
              <option value="wesley">{t("Wesley code lui-même (cerveau choisi)")}</option>
            </select>
            <Bouton className="mt-2" variante="primaire" icone={<Play />} disabled={!nouvelle.consigne.trim() || !nouvelle.projet.trim()} onClick={creer}>
              {t("Lancer")}
            </Bouton>
          </Panneau>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
            {liste.length === 0 ? (
              <Vide icone={<ListTodo />} titre={t("Aucune tâche")} texte={t("Dis à Wesley : « code-moi … dans mon projet … »")} />
            ) : (
              liste.map((x) => (
                <button
                  key={x.id}
                  onClick={() => setChoisie(x.id)}
                  className={cx("w-full rounded-md border px-3 py-2.5 text-left", choisie === x.id ? "border-hud bg-hud/10" : "border-ligne bg-surface/60 hover:border-ligne-forte")}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">{x.titre}</span>
                    <Pastille s={x.statut} />
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[11px] text-tres-doux">{x.branche || x.projet}</div>
                  {x.distant && <Origine appareil={x.appareil} enLigne={x.en_ligne} />}
                </button>
              ))
            )}
          </div>
        </div>

        <div className="flex min-h-0 flex-col rounded-md border border-ligne bg-surface/40">
          {!detail ? (
            <div className="grid flex-1 place-items-center text-sm text-doux">{t("Choisis une tâche pour voir son déroulé.")}</div>
          ) : (
            <>
              <div className="border-b border-ligne p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-semibold">{detail.titre}</h2>
                  <Pastille s={detail.statut} />
                  <Badge ton="doux">{detail.outil === "claude_code" ? "Claude Code" : detail.outil === "codex" ? "Codex" : "Wesley"}</Badge>
                  <Badge ton="doux">
                    {t("étape")} {detail.etape}
                  </Badge>
                  {detail.distant && <Origine appareil={detail.appareil} enLigne={detail.en_ligne} />}
                </div>
                <p className="mt-1 font-mono text-[11px] text-tres-doux">
                  {detail.branche ? `${detail.branche} · ` : ""}
                  {detail.dossier || detail.projet}
                </p>
                {!!detail.wesley_md?.length && (
                  <p className="mt-1 text-[11px] text-tres-doux" title={t("Instructions du projet transmises à l'agent, qui les tient à jour")}>
                    {t("Suit")} <span className="font-mono">{detail.wesley_md.join(", ")}</span>
                  </p>
                )}
                {detail.distant && (
                  <p className="mt-2 rounded-md border border-ligne bg-surface-2/40 px-2 py-1.5 text-[12px] text-doux">
                    {detail.en_ligne
                      ? t("Lancée sur {appareil} : c'est lui qui la fait tourner. Reprendre, arrêter ou changer la consigne lui est demandé.", { appareil: detail.appareil ?? "?" })
                      : t("Lancée sur {appareil}, hors ligne pour l'instant : ouvre Wesley dessus pour la reprendre ou l'arrêter.", { appareil: detail.appareil ?? "?" })}
                  </p>
                )}
                {detail.bilan && <p className="mt-2 text-[13px] text-doux">{detail.bilan}</p>}
                <div className="mt-3 flex flex-wrap gap-2">
                  {detail.statut === "en_cours" ? (
                    <Bouton taille="sm" variante="danger" icone={<Square />} chargement={attente === "arreter"} onClick={() => agir("arreter")}>
                      {t("Arrêter") + sur}
                    </Bouton>
                  ) : (
                    <Bouton
                      taille="sm"
                      icone={<Play />}
                      chargement={attente === "reprendre"}
                      title={detail.distant ? t("Wesley demande à {appareil} de relancer la tâche ; s'il ne peut pas, il te dit pourquoi.", { appareil: detail.appareil ?? "?" }) : undefined}
                      onClick={() => agir("reprendre")}
                    >
                      {t("Reprendre") + sur}
                    </Bouton>
                  )}
                  {detail.dossier && !detail.distant && (
                    <Bouton taille="sm" variante="fantome" icone={<FolderOpen />} onClick={() => agir("ouvrir")}>
                      {t("Ouvrir le dossier")}
                    </Bouton>
                  )}
                  <Bouton taille="sm" variante="fantome" icone={<Trash2 />} chargement={attente === "supprimer"} onClick={supprimer}>
                    {t("Supprimer")}
                  </Bouton>
                </div>
              </div>
              <div ref={defilement} className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
                {(detail.journal ?? []).map((e, i) => {
                  const [qui, Icone] = QUI[e.genre] ?? [e.genre, CircleDot];
                  return (
                    <div key={i} className={cx("flex gap-2 text-[13px]", e.genre === "outil" && "text-doux")}>
                      <Icone className={cx("mt-0.5 size-4 flex-none", e.genre === "utilisateur" ? "text-ambre" : e.genre === "erreur" ? "text-rouge" : "text-hud")} />
                      <div className="min-w-0 flex-1">
                        <span className="mr-2 font-mono text-[10px] text-tres-doux">
                          {new Date(e.ts * 1000).toLocaleTimeString()} · {t(qui)}
                        </span>
                        <span className={cx("whitespace-pre-wrap break-words", e.genre === "outil" && "font-mono text-[12px]")}>{String(e.texte ?? "")}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex gap-2 border-t border-ligne p-3">
                <Champ
                  className="flex-1"
                  placeholder={t("Changer ou préciser la tâche… (prise en compte tout de suite)")}
                  value={ajout}
                  onChange={(e) => setAjout(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && ajout.trim()) {
                      agir("consigne", { texte: ajout });
                      setAjout("");
                    }
                  }}
                />
                <Bouton
                  icone={<Send />}
                  disabled={!ajout.trim()}
                  onClick={() => {
                    agir("consigne", { texte: ajout });
                    setAjout("");
                  }}
                >
                  {t("Envoyer")}
                </Bouton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
