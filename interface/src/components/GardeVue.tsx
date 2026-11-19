import { Component, type ReactNode } from "react";
import { t } from "../lib/i18n";

type P = { cle: string; children: ReactNode };
type S = { erreur: Error | null; cle: string };

/** Si une page plante, on affiche l'erreur à sa place au lieu de laisser toute la fenêtre noire. */
export class GardeVue extends Component<P, S> {
  state: S = { erreur: null, cle: this.props.cle };

  static getDerivedStateFromError(erreur: Error) {
    return { erreur };
  }

  static getDerivedStateFromProps(p: P, s: S) {
    // changer d'onglet efface l'erreur
    return p.cle !== s.cle ? { erreur: null, cle: p.cle } : null;
  }

  componentDidCatch(erreur: Error) {
    console.error(erreur);
  }

  render() {
    if (!this.state.erreur) return this.props.children;
    return (
      <div className="grid h-full place-items-center p-8">
        <div className="max-w-lg rounded-md border border-rouge/40 bg-surface-2 p-5 text-sm">
          <p className="font-semibold text-rouge">{t("Cette page a rencontré un problème.")}</p>
          <p className="mt-2 font-mono text-[12px] break-words text-doux">{this.state.erreur.message}</p>
          <button onClick={() => this.setState({ erreur: null })} className="mt-4 rounded-md border border-ligne-forte px-3 py-1.5 text-hud hover:bg-white/5">
            {t("Réessayer")}
          </button>
        </div>
      </div>
    );
  }
}
