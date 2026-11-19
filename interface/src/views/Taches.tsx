import { Bot, CheckCircle2, CircleDot, FolderOpen, ListTodo, Loader2, Play, Plus, Send, Square, Trash2, User, Wrench, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Badge, Bouton, Champ, EnTetePage, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";
import { bus } from "../stores/jarvis";
import { toast } from "../stores/toasts";

type Statut = "en_cours" | "terminee" | "echec" | "arretee" | "interrompue";
type Resume = { id: string; titre: string; statut: Statut; outil: string; projet: string; branche: string; dossier: string; cree: number; maj: number; etape: number; bilan: string };
type Entree = { ts: number; genre: "utilisateur" | "jarvis" | "claude" | "outil" | "info" | "erreur"; texte: string };
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
  jarvis: ["Jarvis → agent", Bot],
  claude: ["Agent", Bot],
  outil: ["Action", Wrench],
  info: ["Info", CircleDot],
  erreur: ["Erreur", XCircle],
};

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
  const [nouvelle, setNouvelle] = useState({ consigne: "", projet: "", outil: "claude_code" });
  const [ajout, setAjout] = useState("");
  const fin = useRef<HTMLDivElement>(null);

  const charger = () => api<Resume[]>("/api/taches").then(setListe).catch(() => {});
  const chargerDetail = (id: string) => api<Tache>(`/api/taches/${id}`).then(setDetail).catch(() => {});
  useEffect(() => {
    charger();
    const sur = (e: Event) => {
      charger();
      const id = (e as CustomEvent<string>).detail;
      if (id && id === choisieRef.current) chargerDetail(id);
    };
    bus.addEventListener("tache_maj", sur);
    return () => bus.removeEventListener("tache_maj", sur);
  }, []);
  const choisieRef = useRef<string | null>(null);
  useEffect(() => {
    choisieRef.current = choisie;
    if (choisie) chargerDetail(choisie);
  }, [choisie]);
  useEffect(() => fin.current?.scrollIntoView({ block: "end" }), [detail?.journal.length]);

  const creer = async () => {
    try {
      const r = await api<Resume>("/api/taches", { method: "POST", json: nouvelle });
      setNouvelle({ ...nouvelle, consigne: "" });
      setChoisie(r.id);
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const agir = async (action: string, corps?: object) => {
    if (!detail) return;
    try {
      const r = await api<{ message?: string }>(`/api/taches/${detail.id}/${action}`, { method: "POST", json: corps ?? {} });
      if (r.message) toast(r.message, "succes");
      chargerDetail(detail.id);
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const supprimer = async () => {
    if (!detail || !confirm(t("Supprimer cette tâche de la liste ? (la branche et son code restent)"))) return;
    await api(`/api/taches/${detail.id}`, { method: "DELETE" });
    setChoisie(null);
    setDetail(null);
    charger();
  };

  return (
    <div className="flex h-full min-h-0 flex-col p-4 md:p-8">
      <EnTetePage
        titre={t("Tâches")}
        sousTitre={t("Le code que Jarvis fait en arrière-plan (avec Claude Code ou lui-même), chacun sur sa branche. Continue à lui parler pendant ce temps : il peut changer une tâche en cours.")}
      />
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[340px_1fr]">
        <div className="flex min-h-0 flex-col gap-3">
          <Panneau titre={t("Nouvelle tâche")} icone={<Plus />}>
            <textarea
              rows={3}
              value={nouvelle.consigne}
              onChange={(e) => setNouvelle({ ...nouvelle, consigne: e.target.value })}
              placeholder={t("Ce qu'il faut coder… (ou demande-le simplement à Jarvis)")}
              className="w-full rounded-md border border-ligne-forte bg-surface-2 p-2 text-sm outline-none focus:border-hud"
            />
            <Champ className="mt-2" placeholder={t("Dossier du projet (ex : ~/Desktop/mon-projet)")} value={nouvelle.projet} onChange={(e) => setNouvelle({ ...nouvelle, projet: e.target.value })} />
            <select
              value={nouvelle.outil}
              onChange={(e) => setNouvelle({ ...nouvelle, outil: e.target.value })}
              className="mt-2 h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
            >
              <option value="claude_code">{t("Claude Code, piloté par Jarvis")}</option>
              <option value="jarvis">{t("Jarvis code lui-même")}</option>
            </select>
            <Bouton className="mt-2" variante="primaire" icone={<Play />} disabled={!nouvelle.consigne.trim() || !nouvelle.projet.trim()} onClick={creer}>
              {t("Lancer")}
            </Bouton>
          </Panneau>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
            {liste.length === 0 ? (
              <Vide icone={<ListTodo />} titre={t("Aucune tâche")} texte={t("Dis à Jarvis : « code-moi … dans mon projet … »")} />
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
                  <Badge ton="doux">{detail.outil === "claude_code" ? "Claude Code" : "Jarvis"}</Badge>
                  <Badge ton="doux">
                    {t("étape")} {detail.etape}
                  </Badge>
                </div>
                <p className="mt-1 font-mono text-[11px] text-tres-doux">
                  {detail.branche ? `${detail.branche} · ` : ""}
                  {detail.dossier || detail.projet}
                </p>
                {detail.bilan && <p className="mt-2 text-[13px] text-doux">{detail.bilan}</p>}
                <div className="mt-3 flex flex-wrap gap-2">
                  {detail.statut === "en_cours" ? (
                    <Bouton taille="sm" variante="danger" icone={<Square />} onClick={() => agir("arreter")}>
                      {t("Arrêter")}
                    </Bouton>
                  ) : (
                    <Bouton taille="sm" icone={<Play />} onClick={() => agir("reprendre")}>
                      {t("Reprendre")}
                    </Bouton>
                  )}
                  {detail.dossier && (
                    <Bouton taille="sm" variante="fantome" icone={<FolderOpen />} onClick={() => agir("ouvrir")}>
                      {t("Ouvrir le dossier")}
                    </Bouton>
                  )}
                  <Bouton taille="sm" variante="fantome" icone={<Trash2 />} onClick={supprimer}>
                    {t("Supprimer")}
                  </Bouton>
                </div>
              </div>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
                {detail.journal.map((e, i) => {
                  const [qui, Icone] = QUI[e.genre] ?? [e.genre, CircleDot];
                  return (
                    <div key={i} className={cx("flex gap-2 text-[13px]", e.genre === "outil" && "text-doux")}>
                      <Icone className={cx("mt-0.5 size-4 flex-none", e.genre === "utilisateur" ? "text-ambre" : e.genre === "erreur" ? "text-rouge" : "text-hud")} />
                      <div className="min-w-0 flex-1">
                        <span className="mr-2 font-mono text-[10px] text-tres-doux">
                          {new Date(e.ts * 1000).toLocaleTimeString()} · {t(qui)}
                        </span>
                        <span className={cx("whitespace-pre-wrap break-words", e.genre === "outil" && "font-mono text-[12px]")}>{e.texte}</span>
                      </div>
                    </div>
                  );
                })}
                <div ref={fin} />
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
