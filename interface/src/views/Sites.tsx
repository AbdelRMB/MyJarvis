import { BookOpen, Circle, Compass, Download, ExternalLink, Globe, KeyRound, Lightbulb, LogIn, Plus, Square, Trash2, Video } from "lucide-react";
import { useEffect, useState } from "react";
import { Bouton, Champ, EnTetePage, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";
import { bus } from "../stores/jarvis";
import { toast } from "../stores/toasts";

type Resume = { id: string; nom: string; url: string; pages: number; procedures: number; astuces: number; guide: boolean; modifie: string; explore: string };
type Exploration = { en_cours: boolean; site: string; pages: number; max: number; etape: string; erreur: string };
type Nav = {
  executable: string;
  ouvert: boolean;
  installation: { en_cours: boolean; pct: number; erreur: string };
  enregistrement: { actif: boolean; site: string; etapes: number };
};
type Etat = { sites: Resume[]; navigateur: Nav; exploration: Exploration };
type Page = { url: string; titre: string; chemin: string[]; boutons: string[]; champs: string[] };
type Procedure = { id: string; nom: string; texte: string[]; date: string };
type Astuce = { id: string; texte: string; date: string };
type Detail = Omit<Resume, "pages" | "procedures" | "astuces" | "guide"> & {
  pages: Page[];
  procedures: Procedure[];
  astuces: Astuce[];
  guide: string;
  connexion?: { identifiant: boolean; mot_de_passe: boolean; totp: boolean };
};

/** Identifiants du site (envoyés une fois, jamais réaffichés) et code 2FA du moment pour vérifier la clé. */
function ConnexionAuto({ id, connexion, onMaj }: { id: string; connexion?: Detail["connexion"]; onMaj: () => void }) {
  const [f, setF] = useState({ identifiant: "", mot_de_passe: "", totp: "" });
  const [code, setCode] = useState<{ code: string; reste: number } | null>(null);
  const [enCours, setEnCours] = useState(false);
  useEffect(() => {
    if (!connexion?.totp) return setCode(null);
    const lire = () => api<{ code: string; reste: number }>(`/api/sites/${id}/code`, { method: "POST", json: {} }).then(setCode).catch(() => {});
    lire();
    const i = setInterval(lire, 1000);
    return () => clearInterval(i);
  }, [id, connexion?.totp]);
  const enregistrer = async () => {
    const json = Object.fromEntries(Object.entries(f).filter(([, v]) => v.trim()));
    if (!Object.keys(json).length) return;
    try {
      await api(`/api/sites/${id}/identifiants`, { method: "POST", json });
      setF({ identifiant: "", mot_de_passe: "", totp: "" });
      toast(t("Enregistré dans ton coffre chiffré."), "succes");
      onMaj();
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const connecter = async () => {
    setEnCours(true);
    try {
      const r = await api<{ resultat: string }>(`/api/sites/${id}/connecter`, { method: "POST", json: {} });
      toast(r.resultat, r.resultat.startsWith("Connecté") ? "succes" : "info");
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnCours(false);
    }
  };
  const ok = (b?: boolean) => (b ? <span className="text-vert">✓</span> : <span className="text-tres-doux">—</span>);
  return (
    <details className="mb-4 rounded-md border border-ligne px-3 py-2">
      <summary className="flex cursor-pointer items-center gap-2 text-[13px]">
        <KeyRound className="size-4 text-hud" /> {t("Connexion automatique")}
        <span className="ml-auto text-[12px] text-doux">
          {t("identifiant")} {ok(connexion?.identifiant)} · {t("mot de passe")} {ok(connexion?.mot_de_passe)} · {t("code 2FA")} {ok(connexion?.totp)}
        </span>
      </summary>
      <p className="mt-2 text-[12px] text-doux">
        {t("Jarvis se connecte tout seul, même avec double authentification. Tes identifiants vont dans ton coffre chiffré : ils ne sont jamais réaffichés ni montrés à l'IA.")}
      </p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <Champ placeholder={connexion?.identifiant ? t("Identifiant (déjà enregistré)") : t("Identifiant")} value={f.identifiant} onChange={(x) => setF({ ...f, identifiant: x.target.value })} />
        <Champ type="password" placeholder={connexion?.mot_de_passe ? t("Mot de passe (déjà enregistré)") : t("Mot de passe")} value={f.mot_de_passe} onChange={(x) => setF({ ...f, mot_de_passe: x.target.value })} />
        <Champ
          className="sm:col-span-2"
          type="password"
          placeholder={connexion?.totp ? t("Clé de double authentification (déjà enregistrée)") : t("Clé secrète de l'appli d'authentification (ou adresse otpauth://)")}
          value={f.totp}
          onChange={(x) => setF({ ...f, totp: x.target.value })}
        />
      </div>
      <p className="mt-1 text-[11px] text-tres-doux">
        {t("La clé secrète s'obtient en ajoutant une appli d'authentification sur le portail : sous le QR code, « Impossible de scanner ? » affiche la clé. Ajoute-la aussi dans ton appli habituelle pour garder les deux.")}
      </p>
      {code && (
        <p className="mt-2 text-[13px]">
          {t("Code du moment : ")}<span className="font-mono text-lg tracking-widest text-hud">{code.code}</span>{" "}
          <span className="text-[11px] text-tres-doux">({code.reste} s) — {t("il doit être identique à celui de ton appli.")}</span>
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Bouton taille="sm" onClick={enregistrer}>{t("Enregistrer")}</Bouton>
        <Bouton taille="sm" variante="primaire" icone={<LogIn className="size-3.5" />} chargement={enCours} disabled={!connexion?.identifiant && !connexion?.mot_de_passe} onClick={connecter}>
          {t("Me connecter automatiquement")}
        </Bouton>
      </div>
    </details>
  );
}

function DetailSite({ id, etat, recharger }: { id: string; etat: Etat; recharger: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [onglet, setOnglet] = useState<"guide" | "procedures" | "astuces" | "pages">("procedures");
  const [astuce, setAstuce] = useState("");
  const [nomDemo, setNomDemo] = useState("");
  const [filtre, setFiltre] = useState("");
  const charger = () => api<Detail>(`/api/sites/${id}`).then(setD).catch(() => {});
  useEffect(() => {
    charger();
    bus.addEventListener("sites_maj", charger);
    return () => bus.removeEventListener("sites_maj", charger);
  }, [id]);
  const agir = async (action: string, json: unknown = {}) => {
    try {
      const r = await api<{ etapes?: number }>(`/api/sites/${id}/${action}`, { method: "POST", json });
      if (action === "demo_fin") toast(r.etapes ? t("Procédure enregistrée ({n} étapes).", { n: r.etapes }) : t("Aucune étape enregistrée."), r.etapes ? "succes" : "info");
      recharger();
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  if (!d) return null;
  const ex = etat.exploration;
  const exploreIci = ex.en_cours && ex.site === id;
  const enreg = etat.navigateur.enregistrement;
  const demoIci = enreg.actif && enreg.site === id;
  const pages = d.pages.filter((p) => !filtre || (p.titre + p.chemin.join(" ") + p.boutons.join(" ")).toLowerCase().includes(filtre.toLowerCase()));

  return (
    <Panneau titre={d.nom} icone={<Globe />} actions={<a href={d.url} target="_blank" rel="noreferrer" className="text-doux hover:text-hud"><ExternalLink className="size-4" /></a>}>
      <ConnexionAuto id={id} connexion={d.connexion} onMaj={charger} />
      <ol className="mb-4 space-y-3 text-[13px]">
        <li className="flex flex-wrap items-center gap-3">
          <span className="w-5 text-hud">1.</span>
          <span className="flex-1 text-doux">{t("Ouvre le site dans le navigateur de Jarvis et connecte-toi (une seule fois, la session est gardée).")}</span>
          <Bouton taille="sm" icone={<LogIn className="size-3.5" />} onClick={() => agir("ouvrir")}>{t("Ouvrir pour me connecter")}</Bouton>
        </li>
        <li className="flex flex-wrap items-center gap-3">
          <span className="w-5 text-hud">2.</span>
          <span className="flex-1 text-doux">{t("Jarvis parcourt le site sans rien modifier et apprend ses pages, menus, boutons et formulaires.")}</span>
          {exploreIci ? (
            <Bouton taille="sm" variante="danger" icone={<Square className="size-3.5" />} onClick={() => agir("arreter")}>{t("Arrêter")}</Bouton>
          ) : (
            <Bouton taille="sm" icone={<Compass className="size-3.5" />} disabled={ex.en_cours} onClick={() => agir("explorer", { max_pages: 80 })}>
              {d.explore ? t("Réexplorer") : t("Explorer le site")}
            </Bouton>
          )}
        </li>
        {exploreIci && (
          <li className="ml-8">
            <div className="mb-1 flex justify-between text-[12px] text-doux">
              <span className="truncate">{ex.etape}</span>
              <span className="font-mono text-hud">{ex.pages}/{ex.max}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-surface-3">
              <div className="h-full bg-hud transition-all" style={{ width: `${Math.min(100, (ex.pages / Math.max(1, ex.max)) * 100)}%` }} />
            </div>
          </li>
        )}
        {!ex.en_cours && ex.site === id && ex.erreur && <li className="ml-8 text-rouge">{ex.erreur}</li>}
        <li className="flex flex-wrap items-center gap-3">
          <span className="w-5 text-hud">3.</span>
          <span className="flex-1 text-doux">{t("Montre-lui une tâche : fais-la dans son navigateur, il enregistre tes étapes (jamais tes mots de passe).")}</span>
          {!demoIci && <Bouton taille="sm" icone={<Video className="size-3.5" />} disabled={enreg.actif} onClick={() => agir("demo")}>{t("Enregistrer une démonstration")}</Bouton>}
        </li>
        {demoIci && (
          <li className="ml-8 rounded-md border border-rouge/40 bg-rouge/5 p-3">
            <div className="mb-2 flex items-center gap-2 text-rouge">
              <Circle className="size-3 animate-pulse fill-current" /> {t("Enregistrement en cours : {n} étape(s)", { n: enreg.etapes })}
            </div>
            <div className="flex flex-wrap gap-2">
              <Champ className="flex-1" placeholder={t("Nom de la tâche (ex : créer une facture)")} value={nomDemo} onChange={(x) => setNomDemo(x.target.value)} />
              <Bouton taille="sm" variante="primaire" onClick={() => { agir("demo_fin", { nom: nomDemo }); setNomDemo(""); }}>{t("Terminer et enregistrer")}</Bouton>
              <Bouton taille="sm" variante="fantome" onClick={() => agir("demo_fin", { garder: false })}>{t("Annuler")}</Bouton>
            </div>
          </li>
        )}
      </ol>

      <div className="mb-3 flex flex-wrap gap-1 border-b border-ligne">
        {(
          [
            ["procedures", `${t("Procédures")} (${d.procedures.length})`],
            ["astuces", `${t("Astuces")} (${d.astuces.length})`],
            ["guide", t("Guide")],
            ["pages", `${t("Pages")} (${d.pages.length})`],
          ] as const
        ).map(([k, l]) => (
          <button key={k} onClick={() => setOnglet(k)} className={cx("-mb-px border-b-2 px-3 py-2 text-[13px]", onglet === k ? "border-hud text-hud" : "border-transparent text-doux")}>
            {l}
          </button>
        ))}
      </div>

      {onglet === "procedures" &&
        (d.procedures.length === 0 ? (
          <p className="text-[13px] text-tres-doux">{t("Aucune procédure : enregistre une démonstration (étape 3).")}</p>
        ) : (
          d.procedures.map((p) => (
            <details key={p.id} className="mb-2 rounded-md border border-ligne px-3 py-2">
              <summary className="flex cursor-pointer items-center gap-2 text-sm">
                <span className="flex-1">{p.nom}</span>
                <span className="text-[11px] text-tres-doux">{p.texte.length} {t("étapes")}</span>
                <button onClick={(e) => { e.preventDefault(); agir("retirer", { quoi: "procedures", id: p.id }); }} className="text-tres-doux hover:text-rouge" aria-label={t("Supprimer")}>
                  <Trash2 className="size-3.5" />
                </button>
              </summary>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-[12px] text-doux">{p.texte.map((e, i) => <li key={i}>{e}</li>)}</ol>
            </details>
          ))
        ))}

      {onglet === "astuces" && (
        <>
          <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (astuce.trim()) { agir("astuce", { texte: astuce }); setAstuce(""); } }}>
            <Champ placeholder={t("Ex : pour exporter, c'est Rapports › Export, bouton en haut à droite")} value={astuce} onChange={(x) => setAstuce(x.target.value)} />
            <Bouton type="submit" icone={<Plus className="size-4" />}>{t("Ajouter")}</Bouton>
          </form>
          {d.astuces.map((a) => (
            <div key={a.id} className="mb-1.5 flex items-start gap-2 text-[13px]">
              <Lightbulb className="mt-0.5 size-3.5 flex-none text-ambre" />
              <span className="flex-1">{a.texte}</span>
              <button onClick={() => agir("retirer", { quoi: "astuces", id: a.id })} className="text-tres-doux hover:text-rouge" aria-label={t("Supprimer")}>
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </>
      )}

      {onglet === "guide" &&
        (d.guide ? <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-doux">{d.guide}</pre> : <p className="text-[13px] text-tres-doux">{t("Le guide est rédigé à la fin de l'exploration (étape 2).")}</p>)}

      {onglet === "pages" && (
        <>
          <Champ className="mb-2" placeholder={t("Filtrer les pages…")} value={filtre} onChange={(x) => setFiltre(x.target.value)} />
          <div className="max-h-96 space-y-1 overflow-auto">
            {pages.map((p) => (
              <div key={p.url} className="rounded border border-ligne px-2 py-1.5 text-[12px]">
                <div className="truncate font-medium">{p.titre || p.url}</div>
                <div className="truncate text-tres-doux">{p.chemin.join(" › ") || t("accueil")}</div>
              </div>
            ))}
          </div>
        </>
      )}

      <button className="mt-4 text-[12px] text-tres-doux hover:text-rouge" onClick={async () => {
        if (!confirm(t("Oublier ce site et tout ce que Jarvis en a appris ?"))) return;
        await api(`/api/sites/${id}`, { method: "DELETE" }).catch(() => {});
        recharger();
      }}>
        {t("Oublier ce site")}
      </button>
    </Panneau>
  );
}

export function VueSites() {
  const [e, setE] = useState<Etat | null>(null);
  const [choisi, setChoisi] = useState<string | null>(null);
  const [f, setF] = useState({ nom: "", url: "" });
  const charger = () => api<Etat>("/api/sites").then((x) => { setE(x); setChoisi((c) => c ?? x.sites[0]?.id ?? null); }).catch(() => {});
  useEffect(() => {
    charger();
    const i = setInterval(charger, 3000);
    const sur = () => charger();
    bus.addEventListener("sites_maj", sur);
    bus.addEventListener("exploration", sur);
    return () => {
      clearInterval(i);
      bus.removeEventListener("sites_maj", sur);
      bus.removeEventListener("exploration", sur);
    };
  }, []);
  const ajouter = async () => {
    try {
      const s = await api<Resume>("/api/sites", { method: "POST", json: f });
      setF({ nom: "", url: "" });
      setChoisi(s.id);
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const nav = e?.navigateur;

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Sites appris")}
        sousTitre={t("Fais apprendre par cœur tes sites (intranet, logiciels d'entreprise…) à Jarvis : il saura directement où aller et quoi faire. Ce qu'il apprend reste sur cet ordinateur.")}
      />
      {nav && !nav.executable && (
        <div className="mb-6 rounded-md border border-ambre/40 bg-ambre/5 p-4 text-[13px]">
          <p className="mb-3 text-ambre">{t("Jarvis a besoin d'un navigateur à lui (Chrome, Edge ou Brave). Aucun n'est installé : télécharge Chrome for Testing, le Chrome officiel de Google pour l'automatisation (environ 150 Mo).")}</p>
          {nav.installation.en_cours ? (
            <div className="h-1.5 overflow-hidden rounded bg-surface-3"><div className="h-full bg-hud" style={{ width: `${nav.installation.pct}%` }} /></div>
          ) : (
            <Bouton variante="primaire" icone={<Download className="size-4" />} onClick={() => api<Nav>("/api/navigateur/installer", { method: "POST" }).then(charger).catch((x) => toast((x as Error).message, "erreur"))}>
              {t("Télécharger le navigateur de Jarvis")}
            </Bouton>
          )}
          {nav.installation.erreur && <p className="mt-2 text-rouge">{nav.installation.erreur}</p>}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <div className="space-y-3">
          <Panneau titre={t("Nouveau site")} icone={<Plus />}>
            <form className="space-y-2" onSubmit={(x) => { x.preventDefault(); if (f.url.trim()) ajouter(); }}>
              <Champ placeholder={t("Nom (ex : Intranet, Sage, Pronote)")} value={f.nom} onChange={(x) => setF({ ...f, nom: x.target.value })} />
              <Champ placeholder={t("Adresse (ex : intranet.entreprise.fr)")} value={f.url} onChange={(x) => setF({ ...f, url: x.target.value })} />
              <Bouton type="submit" variante="primaire" icone={<Plus className="size-4" />} disabled={!f.url.trim()}>{t("Ajouter")}</Bouton>
            </form>
          </Panneau>
          {e?.sites.map((s) => (
            <button key={s.id} onClick={() => setChoisi(s.id)} className={cx("w-full rounded-md border px-3 py-2.5 text-left", choisi === s.id ? "border-hud bg-hud/10" : "border-ligne bg-surface/60 hover:border-ligne-forte")}>
              <div className="text-sm font-medium">{s.nom}</div>
              <div className="text-[11px] text-tres-doux">{t("{p} pages · {r} procédures · {a} astuces", { p: s.pages, r: s.procedures, a: s.astuces })}</div>
            </button>
          ))}
        </div>
        {e && choisi && e.sites.some((s) => s.id === choisi) ? (
          <DetailSite key={choisi} id={choisi} etat={e} recharger={charger} />
        ) : (
          <Vide icone={<BookOpen />} titre={t("Aucun site appris")} texte={t("Ajoute un site, connecte-toi dans le navigateur de Jarvis, puis lance l'exploration. Tu peux aussi lui dire : « apprends le site de mon intranet ».")} />
        )}
      </div>
    </div>
  );
}
