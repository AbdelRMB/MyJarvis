import { AlertTriangle, Bell, CheckCircle2, Info, Trash2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { t } from "../lib/i18n";
import { bus } from "../stores/jarvis";
import { useReglages, type Vue } from "../stores/reglages";

type Notif = { id: string; ts: number; titre: string; texte: string; genre: "info" | "succes" | "alerte" | "erreur"; vue: string; lue: boolean };
const ICONE = { info: Info, succes: CheckCircle2, alerte: AlertTriangle, erreur: XCircle };
const COULEUR = { info: "text-hud", succes: "text-vert", alerte: "text-ambre", erreur: "text-rouge" };

function depuis(ts: number) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return t("à l'instant");
  if (s < 3600) return t("il y a {n} min", { n: Math.floor(s / 60) });
  if (s < 86400) return t("il y a {n} h", { n: Math.floor(s / 3600) });
  return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

/** Cloche : tout ce qui s'est passé pendant que tu n'étais pas là (tâches, automatisations, connexions…). */
export function Cloche() {
  const [liste, setListe] = useState<Notif[]>([]);
  const [ouvert, setOuvert] = useState(false);
  const boite = useRef<HTMLDivElement>(null);
  const maj = useReglages((s) => s.maj);
  const charger = () => api<Notif[]>("/api/notifications").then(setListe).catch(() => {});
  useEffect(() => {
    charger();
    const sur = () => charger();
    bus.addEventListener("notifications", sur);
    const clic = (e: MouseEvent) => boite.current && !boite.current.contains(e.target as Node) && setOuvert(false);
    document.addEventListener("mousedown", clic);
    return () => {
      bus.removeEventListener("notifications", sur);
      document.removeEventListener("mousedown", clic);
    };
  }, []);
  const nonLues = liste.filter((n) => !n.lue).length;
  const toutLu = () => api("/api/notifications/lues", { method: "POST", json: {} }).then(charger);
  const ouvrir = (n: Notif) => {
    api("/api/notifications/lues", { method: "POST", json: { ids: [n.id] } }).then(charger);
    if (n.vue) maj({ vue: n.vue as Vue });
    setOuvert(false);
  };
  return (
    <div className="relative" ref={boite}>
      <button
        onClick={() => setOuvert((x) => !x)}
        title={t("Notifications")}
        className="relative grid size-9 place-items-center rounded-md border border-ligne text-hud"
      >
        <Bell className="size-4" />
        {nonLues > 0 && (
          <span className="absolute -top-1.5 -right-1.5 grid min-w-[18px] place-items-center rounded-full bg-rouge px-1 text-[10px] font-bold text-white">
            {nonLues > 99 ? "99+" : nonLues}
          </span>
        )}
      </button>
      {ouvert && (
        <div className="absolute right-0 z-40 mt-2 w-[min(400px,calc(100vw-24px))] rounded-lg border border-ligne-forte bg-surface-2 shadow-glow">
          <div className="flex items-center justify-between border-b border-ligne px-3 py-2">
            <span className="text-sm font-semibold">{t("Notifications")}</span>
            <div className="flex gap-3 text-[12px]">
              {nonLues > 0 && (
                <button onClick={toutLu} className="text-hud hover:underline">
                  {t("Tout marquer comme lu")}
                </button>
              )}
              {liste.length > 0 && (
                <button onClick={() => api("/api/notifications/effacer", { method: "POST", json: {} }).then(charger)} className="text-doux hover:text-rouge" title={t("Tout effacer")}>
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </div>
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {liste.length === 0 ? (
              <p className="p-4 text-center text-sm text-doux">{t("Aucune notification.")}</p>
            ) : (
              liste.map((n) => {
                const I = ICONE[n.genre] ?? Info;
                return (
                  <button key={n.id} onClick={() => ouvrir(n)} className={cx("flex w-full gap-2.5 border-b border-ligne px-3 py-2.5 text-left hover:bg-white/5", !n.lue && "bg-hud/5")}>
                    <I className={cx("mt-0.5 size-4 flex-none", COULEUR[n.genre])} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className={cx("text-sm", !n.lue && "font-semibold")}>{n.titre}</span>
                        <span className="flex-none text-[11px] text-tres-doux">{depuis(n.ts)}</span>
                      </div>
                      {n.texte && <p className="mt-0.5 line-clamp-3 text-[12px] text-doux">{n.texte}</p>}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
