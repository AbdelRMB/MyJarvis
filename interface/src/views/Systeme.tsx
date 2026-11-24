import { t } from "../lib/i18n";
import { Activity, HardDrive, Layers, Power, Server, Thermometer } from "lucide-react";
import { useEffect, useState } from "react";
import { JaugeRonde, Sparkline } from "../components/Sparkline";
import { Badge, Bouton, EnTetePage, Panneau, Pastille } from "../components/ui";
import { api } from "../lib/api";
import { toast } from "../stores/toasts";
import { cx, duree } from "../lib/format";
import { useSysteme } from "../stores/systeme";

function Carte({ titre, valeur, serie, detail, couleur }: { titre: string; valeur: number; serie: number[]; detail: string; couleur?: string }) {
  return (
    <Panneau titre={titre} actions={<span className="font-display text-sm font-bold">{Math.round(valeur)}%</span>} corpsClassName="space-y-2">
      <Sparkline valeurs={serie} couleur={couleur} className="h-16" />
      <p className="font-mono text-xs text-doux">{detail}</p>
    </Panneau>
  );
}

type Ligne = { nom: string; n: number; echecs: number; taux: number; duree: number; erreur: string };
type Sante = { jours: number; appels: number; echecs: number; outils: Ligne[]; cerveaux: Ligne[] };

/** Ce qui marche et ce qui échoue (outils, cerveaux), compté sur cet appareil : quoi améliorer en priorité. */
function PanneauSante() {
  const [s, setS] = useState<Sante | null>(null);
  const [jours, setJours] = useState(7);
  useEffect(() => {
    api<Sante>(`/api/sante?jours=${jours}`)
      .then(setS)
      .catch(() => {});
  }, [jours]);
  if (!s) return null;
  const enEchec = s.outils.filter((x) => x.echecs > 0).slice(0, 8);
  return (
    <Panneau
      titre={t("Santé de Wesley")}
      icone={<Activity />}
      actions={
        <select value={jours} onChange={(e) => setJours(+e.target.value)} className="h-7 rounded border border-ligne-forte bg-surface-2 px-1 text-[12px]">
          <option value={1}>{t("Aujourd'hui")}</option>
          <option value={7}>{t("7 jours")}</option>
          <option value={30}>{t("30 jours")}</option>
        </select>
      }
      corpsClassName="space-y-3 text-sm"
    >
      <p className="text-doux">
        {t("{n} action(s), {e} en échec ({p} %).", { n: s.appels, e: s.echecs, p: s.appels ? Math.round((s.echecs / s.appels) * 100) : 0 })}
      </p>
      {s.cerveaux.map((c) => (
        <div key={c.nom} className="flex justify-between gap-2 text-[13px]">
          <span>
            {t("Cerveau")} <span className="font-mono">{c.nom}</span>
          </span>
          <span className="font-mono text-doux">
            {t("{n} demandes · {e} échecs · {d} s", { n: c.n, e: c.echecs, d: c.duree })}
          </span>
        </div>
      ))}
      {enEchec.length > 0 ? (
        <div className="space-y-1.5">
          <div className="text-[12px] font-semibold">{t("Outils qui échouent le plus")}</div>
          {enEchec.map((x) => (
            <div key={x.nom} className="text-[12px]" title={x.erreur}>
              <div className="flex justify-between gap-2">
                <span className="font-mono">{x.nom}</span>
                <span className={cx("font-mono", x.taux > 0.3 ? "text-rouge" : "text-ambre")}>
                  {x.echecs}/{x.n}
                </span>
              </div>
              <div className="truncate text-tres-doux">{x.erreur}</div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[13px] text-vert">{t("Aucun outil en échec sur cette période.")}</p>
      )}
    </Panneau>
  );
}

export function VueSysteme() {
  const { dernier: s, serie, joignable } = useSysteme();
  if (!s) return <div className="p-8 text-doux">{joignable ? "Lecture des capteurs…" : "Serveur injoignable."}</div>;
  const vram = s.gpu ? (s.gpu.vram_used / s.gpu.vram_total) * 100 : 0;
  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage titre={t("Système")} sousTitre={t("État de ton PC en temps réel (rafraîchi toutes les 2 secondes).")} />

      <div className="coins mb-6 grid grid-cols-2 gap-6 border border-ligne bg-surface/60 p-6 md:grid-cols-4">
        <JaugeRonde valeur={s.cpu} libelle={t("Processeur")} />
        <JaugeRonde valeur={s.ram} libelle={t("Mémoire")} detail={`${s.ram_used.toFixed(1)} / ${s.ram_total.toFixed(0)} Go`} />
        <JaugeRonde valeur={s.gpu?.util ?? 0} libelle={t("GPU")} detail={s.gpu ? `${s.gpu.temp.toFixed(0)} °C` : "—"} />
        <JaugeRonde valeur={vram} libelle={t("VRAM")} detail={s.gpu ? `${s.gpu.vram_used.toFixed(1)} / ${s.gpu.vram_total.toFixed(0)} Go` : "—"} />
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Carte titre={t("CPU")} valeur={s.cpu} serie={serie.cpu} detail={t("Charge processeur")} />
        <Carte titre={t("RAM")} valeur={s.ram} serie={serie.ram} detail={`${s.ram_used.toFixed(1)} Go utilisés`} />
        <Carte titre={t("GPU")} valeur={s.gpu?.util ?? 0} serie={serie.gpu} detail={s.gpu?.nom ?? "Pas de GPU NVIDIA"} couleur="var(--color-ambre)" />
        <Carte titre={t("VRAM")} valeur={vram} serie={serie.vram} detail={t("Mémoire vidéo")} couleur="var(--color-ambre)" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panneau titre={t("Noyau IA")} icone={<Server />} corpsClassName="space-y-3">
          <Pastille ok={s.ollama}>{s.ollama ? "Ollama en ligne" : "Ollama arrêté"}</Pastille>
          <div className="text-sm">
            {t("Modèle actif : ")}<span className="font-mono text-hud">{s.modele}</span>
          </div>
          {s.charges.length ? (
            <ul className="space-y-2">
              {s.charges.map((c) => {
                const surCpu = c.taille - c.vram > 0.3;
                return (
                  <li key={c.nom} className="rounded border border-ligne p-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs">{c.nom}</span>
                      <Badge ton={surCpu ? "ambre" : "vert"}>{surCpu ? "déborde sur CPU" : "100 % GPU"}</Badge>
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-doux">
                      {c.vram.toFixed(1)} Go en VRAM / {c.taille.toFixed(1)} Go
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm text-doux">{t("Aucun modèle chargé : la prochaine question prendra ~15 s.")}</p>
          )}
          <div className="flex flex-wrap gap-2 pt-1">
            {s.charges.length ? (
              <Bouton taille="sm" onClick={() => api("/api/modele/liberer", { method: "POST" }).then(() => toast(t("VRAM libérée — pratique avant un jeu."), "succes")).catch((e) => toast(e.message, "erreur"))}>
                {t("Libérer la VRAM")}
              </Bouton>
            ) : (
              <Bouton taille="sm" variante="primaire" onClick={() => api("/api/modele/charger", { method: "POST" }).then(() => toast(t("Chargement du modèle…"))).catch((e) => toast(e.message, "erreur"))}>
                {t("Charger le modèle")}
              </Bouton>
            )}
          </div>
        </Panneau>
        <Panneau titre={t("Stockage")} icone={<HardDrive />} corpsClassName="space-y-3">
          <div className="flex items-baseline justify-between text-sm">
            <span>{t("Disque principal")}</span>
            <span className={cx("font-mono", s.disque > 90 ? "text-rouge" : "text-doux")}>{s.disque.toFixed(0)} %</span>
          </div>
          <div className="h-2 overflow-hidden rounded bg-hud/10">
            <div className={cx("h-full", s.disque > 90 ? "bg-rouge" : "bg-hud")} style={{ width: `${s.disque}%` }} />
          </div>
          <p className="text-sm text-doux">{s.disque_libre.toFixed(1)} Go libres{s.disque > 90 && " — pense à faire de la place."}</p>
        </Panneau>
        <Panneau titre={t("Machine")} icone={<Layers />} corpsClassName="space-y-3 text-sm">
          <div className="flex items-center gap-2">
            <Power className="size-4 text-hud" />{t(" Allumé depuis ")}<span className="font-mono text-hud">{duree(s.uptime)}</span>
          </div>
          {s.gpu && (
            <div className="flex items-center gap-2">
              <Thermometer className={cx("size-4", s.gpu.temp > 80 ? "text-rouge" : "text-hud")} /> GPU à{" "}
              <span className="font-mono">{s.gpu.temp.toFixed(0)} °C</span>
            </div>
          )}
          <p className="text-doux">
            {t("Avec 8 Go de VRAM, les autres applis qui utilisent la carte graphique (jeux, LDPlayer, Wallpaper Engine…) font déborder le modèle sur le CPU : Wesley devient plus lent. Libère la VRAM avant de jouer.")}
          </p>
        </Panneau>
        <PanneauSante />
      </div>
    </div>
  );
}
