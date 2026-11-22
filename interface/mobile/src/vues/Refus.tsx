import { Smartphone } from "lucide-react";
import { t } from "../../../src/lib/i18n";

/** Affiché à la place de l'appli quand la page est ouverte ailleurs que sur un téléphone. */
export function RefusOrdinateur() {
  const url = `${location.origin}/mobile/`;
  return (
    <div className="grille-hud grid min-h-dvh place-items-center p-6">
      <div className="coins max-w-md border border-ligne-forte bg-surface p-7 text-center">
        <Smartphone className="mx-auto size-10 text-hud" />
        <h1 className="titre-hud mt-4 text-lg font-bold text-hud">Wesley</h1>
        <p className="mt-3 font-medium">{t("Wesley mobile ne fonctionne que sur un téléphone.")}</p>
        <p className="mt-2 text-sm text-doux">
          {t("Ouvre cette adresse sur ton iPhone ou ton téléphone Android, puis ajoute-la à l'écran d'accueil :")}
        </p>
        <p className="mt-2 font-mono text-sm text-hud-clair">{url}</p>
        <p className="mt-4 text-sm text-doux">{t("Sur ordinateur, installe l'appli de bureau Wesley (Mac et Windows).")}</p>
      </div>
    </div>
  );
}
