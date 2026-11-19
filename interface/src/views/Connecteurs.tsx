import { Blocks, CalendarDays, Check, GitBranch, Loader2, Mail, NotebookPen, Plug, Plus, Power, Trash2, X, Zap } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Badge, Bouton, Champ, EnTetePage, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { useOS } from "../lib/os";
import { toast } from "../stores/toasts";

type ChampDef = { nom: string; libelle: string; type: "text" | "secret" | "url" | "choix"; aide?: string; requis?: boolean; choix?: string[] };
type TypeConnecteur = { type: string; nom: string; description: string; icone: string; champs: ChampDef[]; aide: string; multiple: boolean };
type Installe = { type: string; actif: boolean; conf: Record<string, string>; secrets: Record<string, boolean>; erreur: string; outils: string[] };
type Donnees = { catalogue: TypeConnecteur[]; installes: Record<string, Installe> };

const ICONES: Record<string, ReactNode> = {
  mail: <Mail />,
  calendar: <CalendarDays />,
  github: <GitBranch />,
  notebook: <NotebookPen />,
  blocks: <Blocks />,
};
const icone = (n: string) => ICONES[n] ?? <Plug />;

/* ---------- formulaire ---------- */
function Editeur({
  def,
  cid,
  existant,
  onFermer,
  onFini,
}: {
  def: TypeConnecteur;
  cid: string | null;
  existant?: Installe;
  onFermer: () => void;
  onFini: () => void;
}) {
  const os = useOS();
  const [conf, setConf] = useState<Record<string, string>>({ mode: "commande", ...(existant?.conf ?? {}) });
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [envoi, setEnvoi] = useState(false);
  const visible = (c: ChampDef) =>
    def.type !== "mcp" || (conf.mode === "url" ? !["commande", "env"].includes(c.nom) : !["url", "entete"].includes(c.nom));

  const enregistrer = async () => {
    const id = cid ?? (def.multiple ? `${def.type}:${(conf.nom || conf.email || "x").toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 24)}` : def.type);
    setEnvoi(true);
    try {
      const r = await api<Installe>(`/api/connecteurs/${encodeURIComponent(id)}`, {
        method: "POST",
        json: { type: def.type, conf, secrets: Object.fromEntries(Object.entries(secrets).filter(([, v]) => v !== "")), actif: true },
      });
      if (r.erreur) toast(r.erreur, "erreur");
      else toast(`${def.nom} connecté — ${r.outils.length} outil(s) ajouté(s) à Jarvis.`, "succes");
      onFini();
    } catch (e) {
      toast((e as Error).message, "erreur");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/50" onClick={onFermer}>
      <aside className="flex h-full w-[min(520px,100vw)] animate-entree flex-col border-l border-ligne-forte bg-surface" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center gap-3 border-b border-ligne px-5 py-4">
          <span className="text-hud [&>svg]:size-5">{icone(def.icone)}</span>
          <h2 className="titre-hud text-sm text-hud">{def.nom}</h2>
          <button onClick={onFermer} className="ml-auto text-doux hover:text-texte" aria-label="Fermer">
            <X className="size-5" />
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <p className="text-sm text-doux">{def.description}</p>
          {def.aide && <div className="rounded-md border border-hud/25 bg-hud/5 p-3 text-[13px] leading-relaxed whitespace-pre-wrap text-hud-clair">{def.aide}</div>}
          {def.champs.filter(visible).map((c) => (
            <label key={c.nom} className="block">
              <span className="mb-1.5 block text-sm">
                {c.libelle}
                {c.requis === false && <span className="text-tres-doux"> (facultatif)</span>}
              </span>
              {c.type === "choix" ? (
                <select
                  value={conf[c.nom] ?? c.choix?.[0]}
                  onChange={(e) => setConf({ ...conf, [c.nom]: e.target.value })}
                  className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
                >
                  {c.choix?.map((o) => (
                    <option key={o} value={o}>
                      {o === "commande" ? "Commande locale (npx, uvx, python…)" : o === "url" ? "Adresse web (serveur distant)" : o}
                    </option>
                  ))}
                </select>
              ) : c.nom === "env" ? (
                <textarea
                  rows={3}
                  value={secrets[c.nom] ?? ""}
                  onChange={(e) => setSecrets({ ...secrets, [c.nom]: e.target.value })}
                  placeholder={existant?.secrets[c.nom] ? "•••••• enregistré (laisse vide pour garder)" : "CLE_API=xxxx"}
                  className="w-full rounded-md border border-ligne-forte bg-surface-2 p-3 font-mono text-sm outline-none focus:border-hud"
                />
              ) : c.type === "secret" ? (
                <Champ
                  type="password"
                  autoComplete="off"
                  value={secrets[c.nom] ?? ""}
                  onChange={(e) => setSecrets({ ...secrets, [c.nom]: e.target.value })}
                  placeholder={existant?.secrets[c.nom] ? "•••••• enregistré (laisse vide pour garder)" : ""}
                />
              ) : (
                <Champ value={conf[c.nom] ?? ""} onChange={(e) => setConf({ ...conf, [c.nom]: e.target.value })} />
              )}
              {c.aide && <span className="mt-1 block text-[12px] text-tres-doux">{c.aide}</span>}
            </label>
          ))}
          <p className="text-[12px] text-tres-doux">
            Les mots de passe et jetons sont rangés dans le {os.coffre}. Ils rejoignent aussi ton compte, chiffrés avec ton mot de passe : le serveur ne peut pas les lire.
          </p>
        </div>
        <footer className="flex gap-2 border-t border-ligne p-4">
          <Bouton variante="primaire" chargement={envoi} onClick={enregistrer} icone={<Check className="size-4" />}>
            Connecter
          </Bouton>
          <Bouton variante="fantome" onClick={onFermer}>
            Annuler
          </Bouton>
        </footer>
      </aside>
    </div>
  );
}

/* ---------- carte d'un connecteur installé ---------- */
function CarteInstalle({ cid, c, def, onModifier, onMaj }: { cid: string; c: Installe; def?: TypeConnecteur; onModifier: () => void; onMaj: () => void }) {
  const [test, setTest] = useState<{ ok: boolean; texte: string } | null>(null);
  const [enCours, setEnCours] = useState(false);
  const titre = c.conf.nom || c.conf.email || def?.nom || cid;
  const statut = !c.actif ? ["Désactivé", "doux"] : c.erreur ? [c.erreur.startsWith("Identifiants") ? "À configurer sur ce PC" : "Erreur", c.erreur.startsWith("Identifiants") ? "ambre" : "rouge"] : [`Actif · ${c.outils.length} outils`, "vert"];

  const tester = async () => {
    setEnCours(true);
    try {
      setTest({ ok: true, texte: (await api<{ message: string }>(`/api/connecteurs/${encodeURIComponent(cid)}/tester`, { method: "POST" })).message });
    } catch (e) {
      setTest({ ok: false, texte: (e as Error).message });
    } finally {
      setEnCours(false);
    }
  };
  const basculer = async () => {
    try {
      await api(`/api/connecteurs/${encodeURIComponent(cid)}`, { method: "POST", json: { type: c.type, conf: c.conf, secrets: {}, actif: !c.actif } });
      onMaj();
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };
  const supprimer = async () => {
    if (!confirm(`Déconnecter ${titre} ? Ses identifiants seront effacés de ce PC.`)) return;
    await api(`/api/connecteurs/${encodeURIComponent(cid)}`, { method: "DELETE" });
    toast(`${titre} déconnecté.`);
    onMaj();
  };

  return (
    <article className="coins flex flex-col border border-ligne bg-surface/60 p-4">
      <div className="flex items-start gap-3">
        <span className={cx("grid size-10 flex-none place-items-center rounded-md border [&>svg]:size-5", c.actif && !c.erreur ? "border-hud/50 text-hud" : "border-ligne text-doux")}>
          {icone(def?.icone ?? "plug")}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{titre}</div>
          <div className="text-xs text-doux">{def?.nom}</div>
        </div>
        <Badge ton={statut[1] as "vert" | "ambre" | "rouge" | "doux"}>{statut[0]}</Badge>
      </div>
      {c.erreur && <p className={cx("mt-3 text-[13px]", c.erreur.startsWith("Identifiants") ? "text-ambre" : "text-rouge")}>{c.erreur}</p>}
      {c.outils.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {c.outils.slice(0, 8).map((o) => (
            <span key={o} className="rounded border border-ligne px-1.5 py-0.5 font-mono text-[11px] text-tres-doux">
              {o}
            </span>
          ))}
          {c.outils.length > 8 && <span className="text-[11px] text-tres-doux">+{c.outils.length - 8}</span>}
        </div>
      )}
      {test && <p className={cx("mt-3 text-[13px]", test.ok ? "text-vert" : "text-rouge")}>{test.ok ? "✓ " : "✗ "}{test.texte}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <Bouton taille="sm" onClick={tester} chargement={enCours} icone={<Zap className="size-3.5" />} disabled={!c.actif}>
          Tester
        </Bouton>
        <Bouton taille="sm" variante="fantome" onClick={onModifier}>
          Modifier
        </Bouton>
        <Bouton taille="sm" variante="fantome" onClick={basculer} icone={<Power className="size-3.5" />}>
          {c.actif ? "Désactiver" : "Activer"}
        </Bouton>
        <button onClick={supprimer} className="ml-auto rounded p-1.5 text-tres-doux hover:text-rouge" aria-label="Déconnecter" title="Déconnecter">
          <Trash2 className="size-4" />
        </button>
      </div>
    </article>
  );
}

/* ---------- vue ---------- */
export function VueConnecteurs() {
  const [d, setD] = useState<Donnees | null>(null);
  const [edition, setEdition] = useState<{ def: TypeConnecteur; cid: string | null } | null>(null);
  const charger = () => api<Donnees>("/api/connecteurs").then(setD).catch((e) => toast(e.message, "erreur"));
  useEffect(() => {
    charger();
  }, []);

  if (!d)
    return (
      <div className="grid h-full place-items-center text-doux">
        <Loader2 className="size-6 animate-spin" />
      </div>
    );
  const installes = Object.entries(d.installes);
  const def = (t: string) => d.catalogue.find((c) => c.type === t);
  const dejaLa = (t: string) => installes.some(([, c]) => c.type === t);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre="Connecteurs"
        sousTitre="Branche tes services : leurs outils s'ajoutent à Jarvis. La liste est partagée entre tes PC ; les mots de passe restent sur chaque PC."
      />

      <h2 className="titre-hud mb-3 text-[11px] text-hud">Connectés</h2>
      {installes.length === 0 ? (
        <div className="coins mb-8 border border-ligne bg-surface/40">
          <Vide icone={<Plug />} titre="Aucun service connecté" texte="Choisis un service ci-dessous. Par exemple Gmail pour que Jarvis lise et envoie tes mails." />
        </div>
      ) : (
        <div className="mb-8 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {installes.map(([cid, c]) => (
            <CarteInstalle key={cid} cid={cid} c={c} def={def(c.type)} onMaj={charger} onModifier={() => setEdition({ def: def(c.type)!, cid })} />
          ))}
        </div>
      )}

      <h2 className="titre-hud mb-3 text-[11px] text-hud">Ajouter un service</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {d.catalogue.map((t) => {
          const indispo = !t.multiple && dejaLa(t.type);
          return (
            <button
              key={t.type}
              disabled={indispo}
              onClick={() => setEdition({ def: t, cid: null })}
              className="group flex gap-3 rounded-md border border-ligne bg-surface/40 p-4 text-left transition-colors hover:border-hud/50 hover:bg-hud/5 disabled:opacity-40"
            >
              <span className="grid size-10 flex-none place-items-center rounded-md border border-ligne text-hud [&>svg]:size-5">{icone(t.icone)}</span>
              <span className="min-w-0">
                <span className="flex items-center gap-2 font-medium">
                  {t.nom}
                  {indispo ? <Badge ton="vert">connecté</Badge> : <Plus className="size-4 text-tres-doux group-hover:text-hud" />}
                </span>
                <span className="mt-1 block text-[13px] leading-snug text-doux">{t.description}</span>
              </span>
            </button>
          );
        })}
      </div>

      <p className="mt-8 max-w-3xl text-[13px] text-tres-doux">
        Un service n'est pas dans la liste (Spotify, Slack, Home Assistant, Google Drive…) ? Utilise « Serveur MCP ». C'est un standard que des centaines d'outils proposent. Sur la page du serveur MCP, copie la commande ou l'adresse indiquée.
      </p>

      {edition && (
        <Editeur
          def={edition.def}
          cid={edition.cid}
          existant={edition.cid ? d.installes[edition.cid] : undefined}
          onFermer={() => setEdition(null)}
          onFini={() => {
            setEdition(null);
            charger();
          }}
        />
      )}
    </div>
  );
}
