import { Confirmations } from "./components/Confirmation";
import { changerLangue, LANGUE } from "./lib/i18n";
import { useEffect, useRef, useState } from "react";
import { micro } from "./audio/micro";
import { sons } from "./audio/bips";
import { chargerVoix, parler } from "./audio/tts";
import { brancherVoix, stopTout } from "./audio/voix";
import { BarreHaut, BarreLaterale, NavMobile, Toasts } from "./components/Cadre";
import { BandeauAutorisations } from "./components/Autorisations";
import { toast } from "./stores/toasts";
import { Connexion, type Compte } from "./components/Connexion";
import { Demarrage } from "./components/Demarrage";
import { GardeVue } from "./components/GardeVue";
import { api, ouvrirSession } from "./lib/api";
import { majAudio } from "./stores/audio";
import { bus, connecter, useJarvis } from "./stores/jarvis";
import { useReglages, type Vue } from "./stores/reglages";
import { rafraichirSysteme } from "./stores/systeme";
import { VueActivite } from "./views/Activite";
import { VueArsenal } from "./views/Arsenal";
import { VueAssistant } from "./views/Assistant";
import { VueConnecteurs } from "./views/Connecteurs";
import { VueHistorique } from "./views/Historique";
import { VueMemoire } from "./views/Memoire";
import { VueReglages } from "./views/Reglages";
import { VueAutomatisations } from "./views/Automatisations";
import { VueTaches } from "./views/Taches";
import { VueAppareils } from "./views/Appareils";
import { VueMisesAJour } from "./views/MisesAJour";
import { VueSysteme } from "./views/Systeme";

const VUES: Vue[] = ["assistant", "historique", "memoire", "connecteurs", "activite", "arsenal", "taches", "automatisations", "appareils", "systeme", "reglages", "majs"];

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
      if (e.altKey && /^[1-9]$/.test(e.key)) {
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

const PARAMS = new URLSearchParams(location.search);
const FENETRE_BUREAU = PARAMS.has("appli");
if (PARAMS.get("vue") === "majs") useReglages.getState().maj({ vue: "majs" });   // raccourci « Mettre à jour Jarvis »

export default function App() {
  const [demarre, setDemarre] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [compte, setCompte] = useState<Compte | null>(null);
  const session = useJarvis((s) => s.session);
  const vue = useReglages((s) => s.vue);

  useEffect(() => {
    ouvrirSession()
      .then((s) => {
        useJarvis.setState({ session: s });
        api<Compte>("/api/compte").then(setCompte).catch(() => {});
        api<{ config: { langue?: string } }>("/api/config")
          .then((c) => {
            const l = c.config.langue === "en" ? "en" : "fr";
            if (c.config.langue && l !== LANGUE) {
              changerLangue(l);   // langue choisie sur un autre appareil (réglage du compte)
              location.reload();
            }
          })
          .catch(() => {});
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

  // déconnecté depuis un autre appareil : retour à l'écran de connexion
  useEffect(() => {
    const sur = () => location.reload();
    bus.addEventListener("compte_deconnecte", sur);
    return () => bus.removeEventListener("compte_deconnecte", sur);
  }, []);

  // Automatisations : Jarvis prévient à voix haute (voix choisie dans Réglages › Voix), même fenêtre cachée
  useEffect(() => {
    const sur = (ev: Event) => {
      const texte = (ev as CustomEvent<string>).detail;
      parler(texte, true);
      toast(texte, "info");
    };
    bus.addEventListener("annonce", sur);
    return () => bus.removeEventListener("annonce", sur);
  }, []);
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
  };

  demarrerRef.current = demarrer;

  return (
    <div className="grille-hud flex h-full flex-col">
      {compte && (compte.mode === "" || (compte.mode === "en_ligne" && !compte.connecte)) && (
        <Connexion onConnecte={setCompte} choix={compte.mode === ""} />
      )}
      {compte && (compte.connecte || compte.mode === "local") && FENETRE_BUREAU && <BandeauAutorisations />}
      {!demarre && !FENETRE_BUREAU && <Demarrage pret={!!session} erreur={erreur} nbOutils={session?.nb_outils ?? 0} onDemarrer={demarrer} />}
      <div className="flex min-h-0 flex-1">
        <BarreLaterale />
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <BarreHaut />
          <div className="min-h-0 flex-1">
            <GardeVue cle={vue}>
            {vue === "assistant" && <VueAssistant />}
            {vue === "historique" && <VueHistorique />}
            {vue === "memoire" && <VueMemoire />}
            {vue === "connecteurs" && <VueConnecteurs />}
            {vue === "activite" && <VueActivite />}
            {vue === "arsenal" && <VueArsenal />}
            {vue === "systeme" && <VueSysteme />}
            {vue === "reglages" && <VueReglages />}
            {vue === "majs" && <VueMisesAJour />}
            {vue === "automatisations" && <VueAutomatisations />}
            {vue === "taches" && <VueTaches />}
            {vue === "appareils" && <VueAppareils />}
            </GardeVue>
          </div>
        </main>
      </div>
      <NavMobile />
      <Toasts />
      <Confirmations />
    </div>
  );
}
