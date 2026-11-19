import { ArrowDownLeft, ArrowUpRight, Laptop, LogOut, Monitor, Send, Smartphone } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Bouton, Champ, EnTetePage, Interrupteur, Panneau, Selecteur, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";
import { bus } from "../stores/jarvis";
import { toast } from "../stores/toasts";

type Appareil = { id: string; nom: string; plateforme: string; version: string; vu: number; en_ligne: boolean; occupe: boolean; accepte: boolean; mode: string; connecte_depuis: number; moi: boolean };
type Entree = { ts: number; sens: "envoye" | "recu"; appareil: string; quoi: string; resultat: string; statut: string };
type Etat = { appareils: Appareil[]; reglages: { accepte: boolean; mode: string }; journal: Entree[]; connecte: boolean; mode: string; erreur: string };

function ilYa(ts: number) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return t("à l'instant");
  if (s < 3600) return t("il y a {n} min", { n: Math.floor(s / 60) });
  if (s < 86400) return t("il y a {n} h", { n: Math.floor(s / 3600) });
  return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

export function VueAppareils() {
  const [e, setE] = useState<Etat | null>(null);
  const [demande, setDemande] = useState<Record<string, string>>({});
  const [envoi, setEnvoi] = useState("");
  const charger = () => api<Etat>("/api/appareils").then(setE).catch(() => {});
  useEffect(() => {
    charger();
    const i = setInterval(charger, 15000);
    const sur = () => charger();
    bus.addEventListener("appareils_maj", sur);
    return () => {
      clearInterval(i);
      bus.removeEventListener("appareils_maj", sur);
    };
  }, []);

  const deconnecter = async (a: Appareil) => {
    if (!confirm(a.moi ? t("Te déconnecter de cet appareil ?") : t("Déconnecter {nom} ? Il devra se reconnecter à ton compte, et ses clés seront retirées.", { nom: a.nom }))) return;
    const r = await api<{ moi?: boolean }>(`/api/appareils/${a.id}/deconnecter`, { method: "POST", json: {} }).catch((x) => toast((x as Error).message, "erreur"));
    if (r && r.moi) location.reload();
    else charger();
  };
  const regler = async (p: object) => setE(await api<Etat>("/api/appareils/reglages", { method: "POST", json: p }));
  const envoyer = async (a: Appareil) => {
    const texte = demande[a.id]?.trim();
    if (!texte) return;
    setEnvoi(a.id);
    try {
      const r = await api<{ resultat: string; ok: boolean }>(`/api/appareils/${a.id}/demander`, { method: "POST", json: { texte } });
      toast(`${a.nom} : ${r.resultat}`, r.ok ? "succes" : "erreur");
      setDemande({ ...demande, [a.id]: "" });
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi("");
    }
  };

  if (e && !e.connecte)
    return (
      <div className="p-8">
        <EnTetePage titre={t("Mes appareils")} />
        <Vide icone={<Laptop />} titre={t("Mode local")} texte={t("Les appareils et le pilotage à distance demandent un compte en ligne (Réglages › Application › Passer en ligne).")} />
      </div>
    );

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Mes appareils")}
        sousTitre={t("Tous les ordinateurs où Jarvis est connecté à ton compte. Dis par exemple : « sur mon PC, lance Discord » — le Jarvis de l'autre appareil le fait et te répond.")}
      />
      {e?.erreur && <p className="mb-4 text-sm text-rouge">{e.erreur}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        {e?.appareils.map((a) => (
          <Panneau key={a.id} titre={a.nom || t("Appareil")} icone={a.plateforme === "mac" ? <Laptop /> : a.plateforme ? <Monitor /> : <Smartphone />}>
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
              <span className={cx("inline-flex items-center gap-1.5", a.en_ligne ? "text-vert" : "text-doux")}>
                <span className={cx("size-2 rounded-full", a.en_ligne ? "bg-vert" : "bg-tres-doux")} />
                {a.en_ligne ? (a.occupe ? t("Allumé — Jarvis occupé") : t("Allumé — Jarvis disponible")) : t("Hors ligne (éteint ou Jarvis fermé)")}
              </span>
              {a.moi && <Badge ton="hud">{t("cet appareil")}</Badge>}
              {a.version && <Badge ton="doux">v{a.version}</Badge>}
              {!a.moi && a.en_ligne && !a.accepte && <Badge ton="ambre">{t("refuse les ordres")}</Badge>}
              {!a.moi && a.en_ligne && a.accepte && a.mode === "confirmation" && <Badge ton="ambre">{t("demande confirmation")}</Badge>}
            </div>
            <p className="mt-1.5 text-[12px] text-doux">
              {t("Vu")} : {a.vu ? ilYa(a.vu) : "—"} · {t("connecté depuis")} {a.connecte_depuis ? new Date(a.connecte_depuis * 1000).toLocaleDateString() : "—"}
              {!a.plateforme && ` · ${t("ancienne version de Jarvis")}`}
            </p>

            {a.moi && e && (
              <div className="mt-3 rounded-md border border-ligne p-3">
                <Interrupteur
                  label={t("Accepter les ordres de mes autres appareils")}
                  aide={t("Seuls tes appareils peuvent en envoyer : ils sont chiffrés avec la clé de ton compte, le serveur ne peut ni les lire ni les fabriquer.")}
                  actif={e.reglages.accepte}
                  onChange={(v) => regler({ accepte: v })}
                />
                {e.reglages.accepte && (
                  <Selecteur
                    label={t("Quand un ordre arrive")}
                    valeur={e.reglages.mode}
                    options={[
                      { valeur: "libre", libelle: t("L'exécuter directement (même si personne n'est devant)") },
                      { valeur: "confirmation", libelle: t("Me demander « Autoriser / Refuser » sur cet appareil") },
                    ]}
                    onChange={(v) => regler({ mode: v })}
                  />
                )}
              </div>
            )}

            {!a.moi && a.en_ligne && a.accepte && (
              <div className="mt-3 flex gap-2">
                <Champ
                  className="flex-1"
                  placeholder={t("Demander à {nom}… (ex : lance Discord)", { nom: a.nom })}
                  value={demande[a.id] ?? ""}
                  onChange={(x) => setDemande({ ...demande, [a.id]: x.target.value })}
                  onKeyDown={(x) => x.key === "Enter" && envoyer(a)}
                />
                <Bouton icone={<Send />} chargement={envoi === a.id} onClick={() => envoyer(a)}>
                  {t("Envoyer")}
                </Bouton>
              </div>
            )}
            <Bouton className="mt-3" taille="sm" variante="fantome" icone={<LogOut />} onClick={() => deconnecter(a)}>
              {a.moi ? t("Me déconnecter de cet appareil") : t("Déconnecter cet appareil")}
            </Bouton>
          </Panneau>
        ))}
      </div>

      {e && e.journal.length > 0 && (
        <div className="mt-8">
          <h2 className="titre-hud mb-3 text-[11px] text-ambre">{t("Journal des ordres")}</h2>
          <div className="space-y-1.5">
            {e.journal.map((j, i) => (
              <div key={i} className="flex gap-2 rounded-md border border-ligne bg-surface/60 px-3 py-2 text-[13px]">
                {j.sens === "envoye" ? <ArrowUpRight className="mt-0.5 size-4 flex-none text-hud" /> : <ArrowDownLeft className="mt-0.5 size-4 flex-none text-ambre" />}
                <div className="min-w-0 flex-1">
                  <div>
                    <span className="font-medium">{j.sens === "envoye" ? t("Envoyé à {nom}", { nom: j.appareil }) : t("Reçu de {nom}", { nom: j.appareil })}</span>
                    <span className="ml-2 text-[11px] text-tres-doux">{ilYa(j.ts)}</span>
                    <span className={cx("ml-2 text-[11px]", j.statut === "ok" ? "text-vert" : "text-rouge")}>{j.statut}</span>
                  </div>
                  <div className="text-doux">{j.quoi}</div>
                  {j.resultat && <div className="mt-0.5 whitespace-pre-wrap text-[12px]">→ {j.resultat}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
