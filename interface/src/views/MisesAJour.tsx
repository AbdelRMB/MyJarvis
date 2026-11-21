import { t } from "../lib/i18n";
import { CheckCircle2, Download, KeyRound, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Markdown } from "../components/Markdown";
import { Badge, Bouton, Champ, EnTetePage, Panneau } from "../components/ui";
import { api } from "../lib/api";
import { bus } from "../stores/jarvis";
import { toast } from "../stores/toasts";

type Maj = { version: string; titre: string; description: string; date: string; disponible: boolean; taille: number };
type Entree = { version: string; description: string; date: string; installee: boolean; plus_recente: boolean };
type Etat = { version: string; jeton: boolean; installee: boolean; majs: Maj[]; journal: Entree[]; erreur: string; prete?: string };
type Progression = { etape: "telechargement" | "installation" | "erreur"; pct: number; texte: string };

export function VueMisesAJour() {
  const [e, setE] = useState<Etat | null>(null);
  const [verif, setVerif] = useState(false);
  const [jeton, setJeton] = useState("");
  const [prog, setProg] = useState<Progression | null>(null);

  const verifier = async () => {
    setVerif(true);
    try {
      const r = await api<Etat>("/api/majs");
      setE(r);
      if (!r.erreur && r.majs.length === 0) toast(`Jarvis est à jour (version ${r.version}).`, "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setVerif(false);
    }
  };

  useEffect(() => {
    verifier();
    const sur = (ev: Event) => {
      const p = (ev as CustomEvent).detail as Progression;
      setProg(p);
      if (p.etape === "erreur") toast(p.texte, "erreur");
    };
    bus.addEventListener("maj", sur);
    return () => bus.removeEventListener("maj", sur);
  }, []);

  const enregistrerJeton = async () => {
    try {
      setE(await api<Etat>("/api/majs/jeton", { method: "POST", json: { jeton } }));
      setJeton("");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };

  const installer = async (version: string) => {
    setProg({ etape: "telechargement", pct: 0, texte: t("Préparation de Jarvis {version}…", { version }) });
    try {
      await api("/api/majs/installer", { method: "POST", json: { version } });
    } catch (x) {
      setProg(null);
      toast((x as Error).message, "erreur");
    }
  };

  const enCours = prog && prog.etape !== "erreur";
  const derniere = e?.majs.find((m) => m.disponible);

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <EnTetePage
        titre={t("Mises à jour")}
        sousTitre={e ? t("Version installée : {version}", { version: e.version }) : t("Recherche…")}
        actions={
          <Bouton icone={<RefreshCw />} chargement={verif} disabled={!!enCours} onClick={verifier}>
            {t("Vérifier les mises à jour")}
          </Bouton>
        }
      />

      {prog && (
        <Panneau titre={prog.etape === "erreur" ? "Échec de la mise à jour" : "Mise à jour en cours"} icone={<Download />} className="mb-4">
          <p className="text-sm">{prog.texte}</p>
          {prog.etape !== "erreur" && (
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-black/30">
              <div className="h-full bg-hud transition-all" style={{ width: `${prog.pct}%` }} />
            </div>
          )}
        </Panneau>
      )}

      {e && e.erreur.startsWith("Jeton") && (
        <Panneau titre={t("Accès aux mises à jour")} icone={<KeyRound />} className="mb-4">
          <p className="text-sm leading-relaxed text-doux">
            {t("Ton jeton GitHub n'est plus valide. Les mises à jour n'en ont pas besoin (le dépôt est public) : laisse le champ vide et enregistre pour le retirer, ou colle un nouveau jeton.")}
          </p>
          <div className="mt-3 flex gap-2">
            <Champ type="password" placeholder={t("github_pat_…")} value={jeton} onChange={(x) => setJeton(x.target.value)} className="flex-1" />
            <Bouton variante="primaire" onClick={enregistrerJeton}>
              {t("Enregistrer")}
            </Bouton>
          </div>
        </Panneau>
      )}

      {e?.prete && (
        <p className="mb-4 rounded-md border border-hud/40 bg-hud/5 p-3 text-sm text-hud">
          {t("La version {v} est déjà téléchargée : elle s'installera toute seule au prochain démarrage de Jarvis.", { v: e.prete })}
        </p>
      )}
      {e?.erreur && <p className="mb-4 rounded-md border border-rouge/40 bg-rouge/5 p-3 text-sm text-rouge">{e.erreur}</p>}
      {e && !e.installee && (
        <p className="mb-4 rounded-md border border-ambre/40 bg-ambre/5 p-3 text-sm text-ambre">
          {t("Jarvis tourne depuis le code source : tu peux voir les versions ici, mais pour mettre à jour fais « git pull ».")}
        </p>
      )}

      {e && !e.erreur && e.majs.length === 0 && (
        <div className="flex items-center gap-3 rounded-md border border-vert/40 bg-vert/5 p-4 text-sm">
          <CheckCircle2 className="size-5 text-vert" />{t(" Jarvis est à jour.")}
        </div>
      )}

      {e && e.majs.length > 0 && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <p className="text-sm">
              {e.majs.length} mise{e.majs.length > 1 ? "s" : ""} à jour disponible{e.majs.length > 1 ? "s" : ""}.
            </p>
            {derniere && (
              <Bouton variante="primaire" icone={<Download />} disabled={!!enCours || !e.installee} onClick={() => installer(derniere.version)}>
                Tout installer (version {derniere.version})
              </Bouton>
            )}
          </div>
          <p className="mb-4 text-[13px] text-doux">
            {t("Chaque version contient aussi les précédentes : installer une version applique tout ce qui est listé en dessous d'elle. Ta mémoire et tes réglages ne bougent pas, rien n'est désinstallé.")}
          </p>
          <div className="space-y-3">
            {e.majs.map((m) => (
              <Panneau
                key={m.version}
                titre={m.titre}
                icone={<Download />}
                actions={
                  <div className="flex items-center gap-2">
                    {m.date && <Badge ton="doux">{m.date}</Badge>}
                    {m === derniere && <Badge ton="vert">{t("dernière")}</Badge>}
                    <Bouton taille="sm" disabled={!m.disponible || !!enCours || !e.installee} onClick={() => installer(m.version)}>
                      {m.disponible ? t("Installer celle-ci") + (m.taille ? ` (${Math.round(m.taille / 1048576)} ${t("Mo")})` : "") : t("Pas encore prête pour cet appareil")}
                    </Bouton>
                  </div>
                }
              >
                <div className="text-sm">{m.description ? <Markdown texte={m.description} /> : <span className="text-doux">{t("Pas de description.")}</span>}</div>
              </Panneau>
            ))}
          </div>
        </>
      )}

      {e && e.journal.length > 0 && (
        <div className="mt-8">
          <h2 className="titre-hud mb-3 text-[11px] text-ambre">{t("Journal des mises à jour")}</h2>
          <div className="space-y-3">
            {e.journal.map((v) => (
              <details key={v.version} open={v.installee} className="rounded-md border border-ligne bg-surface/60 px-4 py-3">
                <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                  Jarvis {v.version}
                  {v.date && <Badge ton="doux">{v.date}</Badge>}
                  {v.installee && <Badge ton="vert">{t("installée")}</Badge>}
                  {v.plus_recente && <Badge ton="hud">disponible</Badge>}
                </summary>
                <div className="mt-2 text-sm">{v.description ? <Markdown texte={v.description} /> : <span className="text-doux">{t("Pas de description.")}</span>}</div>
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
