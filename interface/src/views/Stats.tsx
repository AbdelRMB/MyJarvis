import { ChartColumnBig, Download, Laptop, Loader2, RefreshCw, Search, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Bouton, Champ, EnTetePage, Panneau, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";

type Rep = { nom: string; n: number };
type Compte = {
  id: number; prenom: string; email: string; cree: number; admin: boolean; vu: number; en_ligne: boolean;
  appareils: number; plateformes: string | null; version: string | null; souvenirs: number; demandes: number;
};
type Stats = {
  genere: number;
  periode: number;
  resume: {
    comptes: number; nouveaux_7j: number; nouveaux_periode: number; actifs_24h: number; actifs_7j: number; actifs_30j: number;
    appareils: number; en_ligne: number; demandes_periode: number; souvenirs: number; ordres_periode: number; tickets_ouverts: number;
  };
  par_jour: { jours: string[]; inscriptions: number[]; utilisateurs_actifs: number[]; demandes: number[]; ordres: number[] };
  repartition: { plateformes: Rep[]; versions: Rep[]; tickets: Rep[] };
  comptes: Compte[];
  telechargements: { versions: { version: string; date: string; windows: number; mac: number; total: number }[]; total: number; erreur: string };
};

const PERIODES = [7, 30, 90];
const NOMS: Record<string, string> = {
  windows: "Windows", mac: "Mac", darwin: "Mac", mobile: "Téléphone",
  ouvert: "Ouvert", en_cours: "En cours", resolu: "Résolu", ferme: "Fermé",
};
const nf = (n: number) => n.toLocaleString();
const jourCourt = (j: string) => new Date(j + "T12:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });

function ilYa(ts: number) {
  if (!ts) return t("jamais");
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return t("à l'instant");
  if (s < 3600) return t("il y a {n} min", { n: Math.floor(s / 60) });
  if (s < 86400) return t("il y a {n} h", { n: Math.floor(s / 3600) });
  if (s < 30 * 86400) return t("il y a {n} j", { n: Math.floor(s / 86400) });
  return new Date(ts * 1000).toLocaleDateString();
}

/** Chiffre clé. */
function Tuile({ libelle, valeur, detail }: { libelle: string; valeur: number; detail?: string }) {
  return (
    <div className="coins border border-ligne bg-surface/70 p-4">
      <div className="text-[11px] tracking-wider text-doux uppercase">{libelle}</div>
      <div className="mt-1.5 font-display text-2xl text-texte tabular-nums">{nf(valeur)}</div>
      {detail && <div className="mt-1 text-[12px] text-tres-doux">{detail}</div>}
    </div>
  );
}

/** Barres par jour (une seule série) ; le survol affiche la date et la valeur. */
function BarresJour({ titre, unite, jours, valeurs }: { titre: string; unite: string; jours: string[]; valeurs: number[] }) {
  const [survol, setSurvol] = useState<number | null>(null);
  const max = Math.max(1, ...valeurs);
  const total = valeurs.reduce((a, b) => a + b, 0);
  const i = survol ?? valeurs.length - 1;
  return (
    <Panneau titre={titre}>
      <div className="mb-3 flex items-baseline gap-2 text-sm">
        <span className="font-display text-lg text-texte tabular-nums">{nf(valeurs[i] ?? 0)}</span>
        <span className="text-doux">{unite} · {jours[i] ? jourCourt(jours[i]) : ""}</span>
        <span className="ml-auto text-[12px] text-tres-doux">{t("Total : {n}", { n: nf(total) })}</span>
      </div>
      <div className="relative h-36" onMouseLeave={() => setSurvol(null)}>
        <div className="absolute inset-x-0 top-0 border-t border-dashed border-ligne" />
        <span className="absolute -top-2 right-0 bg-surface px-1 text-[10px] text-tres-doux tabular-nums">{nf(max)}</span>
        <div className="absolute inset-0 flex items-end gap-[2px] border-b border-ligne-forte">
          {valeurs.map((v, k) => (
            <button
              key={jours[k]}
              onMouseEnter={() => setSurvol(k)}
              onFocus={() => setSurvol(k)}
              aria-label={`${jourCourt(jours[k])} : ${v} ${unite}`}
              className="flex h-full min-w-0 flex-1 items-end"
            >
              <span
                className={cx("w-full rounded-t-[4px] transition-opacity", v ? "bg-hud" : "bg-ligne", survol !== null && survol !== k && "opacity-40")}
                style={{ height: v ? `${Math.max(3, (v / max) * 100)}%` : "2px" }}
              />
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] text-tres-doux">
        <span>{jours[0] && jourCourt(jours[0])}</span>
        <span>{jours.length > 1 && jourCourt(jours[jours.length - 1])}</span>
      </div>
    </Panneau>
  );
}

/** Répartition en barres horizontales (une seule teinte, longueur = nombre). */
function Repartition({ titre, lignes, vide }: { titre: string; lignes: Rep[]; vide: string }) {
  const max = Math.max(1, ...lignes.map((l) => l.n));
  const total = lignes.reduce((a, l) => a + l.n, 0);
  return (
    <Panneau titre={titre}>
      {lignes.length === 0 ? (
        <p className="text-sm text-tres-doux">{vide}</p>
      ) : (
        <ul className="space-y-2.5">
          {lignes.map((l) => (
            <li key={l.nom} title={`${l.n} (${Math.round((l.n / total) * 100)} %)`}>
              <div className="mb-1 flex text-[13px]">
                <span className="truncate">{t(NOMS[l.nom] ?? l.nom)}</span>
                <span className="ml-auto pl-2 text-doux tabular-nums">
                  {nf(l.n)} <span className="text-tres-doux">· {Math.round((l.n / total) * 100)} %</span>
                </span>
              </div>
              <div className="h-2 rounded-full bg-white/[0.04]">
                <div className="h-full rounded-full bg-hud" style={{ width: `${(l.n / max) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panneau>
  );
}

export function VueStats() {
  const [periode, setPeriode] = useState(30);
  const [s, setS] = useState<Stats | null>(null);
  const [erreur, setErreur] = useState("");
  const [charge, setCharge] = useState(false);
  const [filtre, setFiltre] = useState("");

  const charger = (p = periode) => {
    setCharge(true);
    api<Stats>(`/api/admin/stats?jours=${p}`)
      .then((d) => {
        setS(d);
        setErreur("");
      })
      .catch((e) => setErreur((e as Error).message))
      .finally(() => setCharge(false));
  };
  useEffect(() => {
    charger(periode);
    const i = setInterval(() => charger(periode), 60000);
    return () => clearInterval(i);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periode]);

  const choixPeriode = (
    <div className="flex items-center gap-2">
      <div className="flex rounded-md border border-ligne bg-surface-2 p-0.5" role="radiogroup" aria-label={t("Période")}>
        {PERIODES.map((p) => (
          <button
            key={p}
            role="radio"
            aria-checked={periode === p}
            onClick={() => setPeriode(p)}
            className={cx("h-8 rounded px-3 text-[13px]", periode === p ? "bg-hud/15 text-hud" : "text-doux hover:text-texte")}
          >
            {t("{n} jours", { n: p })}
          </button>
        ))}
      </div>
      <Bouton taille="sm" variante="fantome" onClick={() => charger()} chargement={charge} icone={<RefreshCw className="size-3.5" />}>
        {t("Actualiser")}
      </Bouton>
    </div>
  );

  if (!s)
    return (
      <div className="h-full overflow-y-auto p-4 md:p-8">
        <EnTetePage titre={t("Statistiques")} sousTitre={t("Utilisation de Wesley par tous ses utilisateurs.")} actions={choixPeriode} />
        {erreur ? (
          <Vide icone={<ChartColumnBig />} titre={t("Statistiques indisponibles")} texte={erreur} />
        ) : (
          <div className="grid place-items-center py-20 text-doux">
            <Loader2 className="size-6 animate-spin" />
          </div>
        )}
      </div>
    );

  const r = s.resume;
  const q = filtre.trim().toLowerCase();
  const comptes = s.comptes.filter((c) => !q || `${c.prenom} ${c.email}`.toLowerCase().includes(q));
  const tl = s.telechargements;

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Statistiques")}
        sousTitre={t("Utilisation de Wesley par tous ses utilisateurs. Aucun contenu (messages, souvenirs) : seulement des comptes, des dates et des nombres.")}
        actions={choixPeriode}
      />
      {erreur && <p className="mb-4 text-sm text-rouge">{erreur}</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tuile libelle={t("Comptes")} valeur={r.comptes} detail={t("+{n} sur {p} jours · +{s} cette semaine", { n: r.nouveaux_periode, p: s.periode, s: r.nouveaux_7j })} />
        <Tuile libelle={t("Actifs (7 jours)")} valeur={r.actifs_7j} detail={t("{j} aujourd'hui · {m} sur 30 jours", { j: r.actifs_24h, m: r.actifs_30j })} />
        <Tuile libelle={t("Demandes à Wesley")} valeur={r.demandes_periode} detail={t("sur {p} jours", { p: s.periode })} />
        <Tuile libelle={t("Téléchargements")} valeur={tl.total} detail={tl.erreur || t("toutes versions, Windows + Mac")} />
        <Tuile libelle={t("Appareils actifs")} valeur={r.appareils} detail={t("{n} en ligne maintenant", { n: r.en_ligne })} />
        <Tuile libelle={t("Souvenirs enregistrés")} valeur={r.souvenirs} />
        <Tuile libelle={t("Ordres entre appareils")} valeur={r.ordres_periode} detail={t("sur {p} jours", { p: s.periode })} />
        <Tuile libelle={t("Tickets à traiter")} valeur={r.tickets_ouverts} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <BarresJour titre={t("Utilisateurs actifs par jour")} unite={t("utilisateurs")} jours={s.par_jour.jours} valeurs={s.par_jour.utilisateurs_actifs} />
        <BarresJour titre={t("Demandes par jour")} unite={t("demandes")} jours={s.par_jour.jours} valeurs={s.par_jour.demandes} />
        <BarresJour titre={t("Nouveaux comptes par jour")} unite={t("comptes")} jours={s.par_jour.jours} valeurs={s.par_jour.inscriptions} />
        <BarresJour titre={t("Ordres entre appareils par jour")} unite={t("ordres")} jours={s.par_jour.jours} valeurs={s.par_jour.ordres} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Repartition titre={t("Systèmes (appareils actifs)")} lignes={s.repartition.plateformes} vide={t("Aucun appareil actif.")} />
        <Repartition titre={t("Versions installées")} lignes={s.repartition.versions} vide={t("Aucun appareil actif.")} />
        <Repartition titre={t("Tickets par statut")} lignes={s.repartition.tickets} vide={t("Aucun ticket.")} />
      </div>

      <Panneau titre={t("Téléchargements par version")} icone={<Download />} className="mt-4" corpsClassName="p-0">
        {tl.versions.length === 0 ? (
          <p className="p-4 text-sm text-tres-doux">{tl.erreur || t("Aucune version publiée.")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-[11px] tracking-wider text-doux uppercase">
                <tr className="border-b border-ligne">
                  <th className="px-4 py-2 font-medium">{t("Version")}</th>
                  <th className="px-4 py-2 font-medium">{t("Publiée le")}</th>
                  <th className="px-4 py-2 text-right font-medium">{t("Windows")}</th>
                  <th className="px-4 py-2 text-right font-medium">{t("Mac")}</th>
                  <th className="px-4 py-2 text-right font-medium">{t("Total")}</th>
                </tr>
              </thead>
              <tbody>
                {tl.versions.map((v) => (
                  <tr key={v.version} className="border-b border-ligne/60 last:border-0">
                    <td className="px-4 py-2 font-mono">{v.version}</td>
                    <td className="px-4 py-2 text-doux">{v.date && new Date(v.date + "T12:00").toLocaleDateString()}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{nf(v.windows)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{nf(v.mac)}</td>
                    <td className="px-4 py-2 text-right font-medium tabular-nums">{nf(v.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panneau>

      <Panneau
        titre={t("Comptes ({n})", { n: s.comptes.length })}
        icone={<Users />}
        className="mt-4"
        corpsClassName="p-0"
        actions={
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-tres-doux" />
            <Champ value={filtre} onChange={(e) => setFiltre(e.target.value)} placeholder={t("Chercher un compte")} className="h-8 w-52 pl-8 text-[13px]" />
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-[11px] tracking-wider text-doux uppercase">
              <tr className="border-b border-ligne">
                <th className="px-4 py-2 font-medium">{t("Utilisateur")}</th>
                <th className="px-4 py-2 font-medium">{t("Dernière activité")}</th>
                <th className="px-4 py-2 font-medium">{t("Inscrit le")}</th>
                <th className="px-4 py-2 font-medium">{t("Appareils")}</th>
                <th className="px-4 py-2 font-medium">{t("Version")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("Demandes ({p} j)", { p: s.periode })}</th>
                <th className="px-4 py-2 text-right font-medium">{t("Souvenirs")}</th>
              </tr>
            </thead>
            <tbody>
              {comptes.map((c) => (
                <tr key={c.id} className="border-b border-ligne/60 last:border-0">
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{c.prenom || "—"}</span>
                      {c.admin && <Badge>{t("admin")}</Badge>}
                    </div>
                    <div className="text-[12px] text-tres-doux">{c.email}</div>
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    <span className={cx("mr-1.5 inline-block size-2 rounded-full", c.en_ligne ? "bg-vert" : "bg-white/15")} aria-hidden />
                    {c.en_ligne ? t("en ligne") : ilYa(c.vu)}
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap text-doux">{new Date(c.cree * 1000).toLocaleDateString()}</td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    <span className="inline-flex items-center gap-1.5">
                      <Laptop className="size-3.5 text-tres-doux" />
                      {c.appareils}
                      {c.plateformes && <span className="text-tres-doux">· {c.plateformes.split(",").map((p) => t(NOMS[p] ?? p)).join(", ")}</span>}
                    </span>
                  </td>
                  <td className="px-4 py-2 font-mono text-[13px]">{c.version || "—"}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{nf(c.demandes)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{nf(c.souvenirs)}</td>
                </tr>
              ))}
              {comptes.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-sm text-tres-doux">
                    {t("Aucun compte ne correspond.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panneau>
      <p className="mt-3 text-[12px] text-tres-doux">
        {t("Mis à jour {quand}. Une « demande » est un message envoyé à Wesley ; un utilisateur actif a utilisé Wesley ce jour-là.", { quand: ilYa(s.genere) })}
      </p>
    </div>
  );
}
