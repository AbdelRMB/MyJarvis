import { useEffect, useRef, useState } from "react";
import { micro } from "./audio/micro";
import { sons } from "./audio/bips";
import { chargerVoix, parler } from "./audio/tts";
import { brancherVoix, stopTout } from "./audio/voix";
import { BarreHaut, BarreLaterale, NavMobile, Toasts } from "./components/Cadre";
import { Demarrage } from "./components/Demarrage";
import { api, ouvrirSession } from "./lib/api";
import { majAudio } from "./stores/audio";
import { connecter, useJarvis } from "./stores/jarvis";
import { useReglages, type Vue } from "./stores/reglages";
import { rafraichirSysteme } from "./stores/systeme";
import { VueActivite } from "./views/Activite";
import { VueArsenal } from "./views/Arsenal";
import { VueAssistant } from "./views/Assistant";
import { VueConnecteurs } from "./views/Connecteurs";
import { VueHistorique } from "./views/Historique";
import { VueMemoire } from "./views/Memoire";
import { VueReglages } from "./views/Reglages";
import { VueSysteme } from "./views/Systeme";

const VUES: Vue[] = ["assistant", "historique", "memoire", "connecteurs", "activite", "arsenal", "systeme", "reglages"];

function useRaccourcis() {
  useEffect(() => {
    let espace = false;
    const bas = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      const dansChamp = !!el && (/INPUT|SELECT|TEXTAREA/.test(el.tagName) || el.isContentEditable);
      if (e.key === "Escape") return stopTout();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        useReglages.getState().maj({ vue: "assistant" });
        setTimeout(() => document.getElementById("saisie")?.focus(), 30);
        return;
      }
      if (e.altKey && /^[1-8]$/.test(e.key)) {
        e.preventDefault();
        useReglages.getState().maj({ vue: VUES[+e.key - 1] });
        return;
      }
      if (e.code === "Space" && !dansChamp && !e.repeat) {
        e.preventDefault();
        espace = true;
        micro.debutEnregistrement();
      }
    };
    const haut = (e: KeyboardEvent) => {
      if (e.code === "Space" && espace) {
        espace = false;
        micro.finEnregistrement();
      }
    };
    addEventListener("keydown", bas);
    addEventListener("keyup", haut);
    return () => {
      removeEventListener("keydown", bas);
      removeEventListener("keyup", haut);
    };
  }, []);
}

export default function App() {
  const [demarre, setDemarre] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const session = useJarvis((s) => s.session);
  const vue = useReglages((s) => s.vue);

  useEffect(() => {
    ouvrirSession()
      .then((s) => {
        useJarvis.setState({ session: s });
        connecter();
        rafraichirSysteme();
        api<{ appli: boolean; ecoute_active: boolean; silence_fin: number }>("/api/appli")
          .then((a) => {
            majAudio({ ecouteFond: a.appli && a.ecoute_active });
            if (a.silence_fin) useReglages.getState().maj({ silence: Math.round(a.silence_fin * 1000) });
            if (a.appli) demarrerRef.current?.(); // fenêtre de bureau : prêt tout de suite, même cachée
          })
          .catch(() => {});
      })
      .catch((e) => setErreur(e.message));
    const i = setInterval(rafraichirSysteme, 2000);
    return () => clearInterval(i);
  }, []);

  useRaccourcis();
  const demarreRef = useRef(false);
  const demarrerRef = useRef<(() => void) | null>(null);

  const demarrer = async () => {
    if (demarreRef.current) return;
    demarreRef.current = true;
    setDemarre(true);
    brancherVoix();
    chargerVoix();
    await micro.initialiser();
    sons.demarrage();
    await micro.demarrer();
    if (useJarvis.getState().messages.length === 0) {
      const h = new Date().getHours();
      parler(`${h < 5 || h >= 18 ? "Bonsoir" : "Bonjour"} ${session?.nom ?? ""}. Tous les systèmes sont opérationnels.`);
    }
  };

  demarrerRef.current = demarrer;

  return (
    <div className="grille-hud flex h-full flex-col">
      {!demarre && <Demarrage pret={!!session} erreur={erreur} nbOutils={session?.nb_outils ?? 0} onDemarrer={demarrer} />}
      <div className="flex min-h-0 flex-1">
        <BarreLaterale />
        <main className="flex min-w-0 flex-1 flex-col">
          <BarreHaut />
          <div className="min-h-0 flex-1">
            {vue === "assistant" && <VueAssistant />}
            {vue === "historique" && <VueHistorique />}
            {vue === "memoire" && <VueMemoire />}
            {vue === "connecteurs" && <VueConnecteurs />}
            {vue === "activite" && <VueActivite />}
            {vue === "arsenal" && <VueArsenal />}
            {vue === "systeme" && <VueSysteme />}
            {vue === "reglages" && <VueReglages />}
          </div>
        </main>
      </div>
      <NavMobile />
      <Toasts />
    </div>
  );
}
