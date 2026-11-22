import { t } from "../lib/i18n";
import { HardDrive, Layers, Power, Server, Thermometer } from "lucide-react";
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
      </div>
    </div>
  );
}
