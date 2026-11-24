import { changerLangue, LANGUE, t, type Langue } from "../lib/i18n";
import { AppWindow, Brain, Cloud, Code2, ShieldCheck, Download, KeyRound, Mic, Monitor, Play, RotateCcw, Save, ScanLine, Sunrise, Trash2, Volume2, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { crete, micro } from "../audio/micro";
import { sons } from "../audio/bips";
import { chargerVoix, listerVoixServeur, parler, taire, type VoixServeur } from "../audio/tts";
import { transcrire } from "../audio/voix";
import { OngletAutorisations } from "../components/Autorisations";
import { Bouton, Champ, Curseur, EnTetePage, Interrupteur, Onglets, Panneau, Selecteur } from "../components/ui";
import { VuMetre } from "../components/VuMetre";
import { api } from "../lib/api";
import { ouvrirLien } from "../lib/liens";
import { cx } from "../lib/format";
import type { ConfigServeur } from "../lib/types";
import { useOS } from "../lib/os";
import { majAudio, useAudio } from "../stores/audio";
import { bus, rescanner, useWesley } from "../stores/wesley";
import { DEFAUT, reglages, useReglages } from "../stores/reglages";
import { toast } from "../stores/toasts";
import { rafraichirSysteme } from "../stores/systeme";

type Onglet = "micro" | "voix" | "cerveau" | "code" | "application" | "autorisations" | "interface";

type EtatAppli = {
  appli: boolean;
  demarrage_auto: boolean;
  machine: string;
  ecoute_fond: boolean;
  ecoute_active: boolean;
  seuil_eveil: number;
  raccourci: string;
};

type AgentCode = { agent: string; nom: string; installe: boolean; connecte: boolean; compte: string; plan: string; expiration: string; renouvellement_auto: boolean; erreur: string; probleme: string };

function dans(iso: string) {
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return "";
  if (ms <= 0) return t("expirée");
  const j = Math.floor(ms / 86400000);
  return j >= 1 ? t("expire dans {n} jour(s)", { n: j }) : t("expire dans {n} h", { n: Math.max(1, Math.floor(ms / 3600000)) });
}

/** Réglages › Code : les agents de code que Wesley pilote dans les tâches de fond, et leur connexion. */
function OngletCode() {
  const [agents, setAgents] = useState<AgentCode[] | null>(null);
  const [action, setAction] = useState("");
  const charger = () => api<AgentCode[]>("/api/agents_code").then(setAgents).catch(() => {});
  useEffect(() => {
    charger();
    const i = setInterval(charger, 5000);   // la connexion se termine dans le navigateur : on relit l'état
    return () => clearInterval(i);
  }, []);
  const agir = async (a: AgentCode, act: string) => {
    setAction(a.agent + act);
    try {
      const r = await api<{ message: string }>(`/api/agents_code/${a.agent}/${act}`, { method: "POST", json: {} });
      toast(r.message, "info");
      charger();
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setAction("");
    }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {agents?.map((a) => (
        <Panneau key={a.agent} titre={a.nom} icone={<Code2 />}>
          <div className="space-y-1.5 text-sm">
            <p>
              {t("État")} :{" "}
              {!a.installe ? <span className="text-ambre">{t("pas installé")}</span> : a.connecte ? <span className="text-vert">{t("connecté")}</span> : <span className="text-rouge">{t("pas connecté")}</span>}
            </p>
            {a.compte && (
              <p>
                {t("Compte")} : <span className="font-mono text-hud">{a.compte}</span> {a.plan && <span className="text-doux">({a.plan})</span>}
              </p>
            )}
            {a.connecte && a.expiration && (
              <p>
                {t("Connexion")} : {dans(a.expiration)}{" "}
                <span className="text-[12px] text-doux">
                  ({new Date(a.expiration).toLocaleString()}){a.renouvellement_auto ? ` — ${t("renouvelée automatiquement")}` : ""}
                </span>
              </p>
            )}
            {a.probleme && <p className="text-[13px] text-ambre">{a.probleme}</p>}
            {a.erreur && <p className="text-[12px] text-rouge">{a.erreur}</p>}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {!a.installe ? (
              <Bouton variante="primaire" chargement={action === a.agent + "installer"} onClick={() => agir(a, "installer")}>
                {t("Installer")}
              </Bouton>
            ) : (
              <>
                <Bouton variante={a.connecte ? "contour" : "primaire"} chargement={action === a.agent + "connecter"} onClick={() => agir(a, "connecter")}>
                  {a.connecte ? t("Se reconnecter") : t("Connecter mon compte")}
                </Bouton>
                {a.connecte && (
                  <Bouton variante="fantome" onClick={() => agir(a, "deconnecter")}>
                    {t("Déconnecter")}
                  </Bouton>
                )}
              </>
            )}
          </div>
          <p className="mt-3 text-[12px] text-doux">
            {a.agent === "claude_code"
              ? t("Utilise ton compte Claude (abonnement Pro / Max) ou un compte de la console Anthropic.")
              : t("Utilise ton compte ChatGPT (Plus / Pro) ou une clé API OpenAI.")}{" "}
            {t("Wesley te prévient par une notification si la connexion expire ou ne marche plus.")}
          </p>
        </Panneau>
      ))}
      <Panneau titre={t("Wesley code lui-même")} icone={<Brain />}>
        <p className="text-[13px] text-doux">{t("Sans agent externe : Wesley code avec ses propres outils et le cerveau choisi dans l'onglet Cerveau (Claude, OpenAI, Gemini, Mistral, Ollama…). Rien à connecter.")}</p>
      </Panneau>
    </div>
  );
}

type Habitudes = { briefing_matin: boolean; conversation_suivie: boolean; maj_auto: boolean; transcription_resume_auto: boolean; transcription_actions_afaire: boolean; transcription_gpu: boolean;
  memoire_semantique: boolean; apprentissage_auto: boolean; modele_rapide_fond: boolean; budget_mensuel: number;
  bilan_soir: boolean; bilan_soir_heure: string };

/** Réglages de comportement gardés par le serveur local (config.json). */
function PanneauHabitudes() {
  const os = useOS();
  const [h, setH] = useState<Habitudes | null>(null);
  useEffect(() => {
    api<{ config: Habitudes }>("/api/config").then((c) => setH(c.config)).catch(() => {});
  }, []);
  const regler = async (p: Partial<Habitudes>) => {
    setH((x) => (x ? { ...x, ...p } : x));
    try {
      await api("/api/config", { method: "POST", json: p });
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  if (!h) return null;
  return (
    <Panneau titre={t("Habitudes")} icone={<Sunrise />}>
      <div className="divide-y divide-ligne">
        <Interrupteur
          label={t("Briefing du matin")}
          aide={t("Au premier échange de la journée (avant midi), Wesley te résume ta liste À faire, tes mails importants, ton agenda, la météo et tes serveurs.")}
          actif={h.briefing_matin}
          onChange={(v) => regler({ briefing_matin: v })}
        />
        <Interrupteur
          label={t("Conversation suivie")}
          aide={t("Après une réponse à l'oral, Wesley écoute ta suite quelques secondes : pas besoin de redire « Wesley ».")}
          actif={h.conversation_suivie}
          onChange={(v) => regler({ conversation_suivie: v })}
        />
        <Interrupteur
          label={t("Mises à jour automatiques")}
          aide={t("Wesley télécharge les nouvelles versions en arrière-plan et les installe au prochain démarrage.")}
          actif={h.maj_auto}
          onChange={(v) => regler({ maj_auto: v })}
        />
        <Interrupteur
          label={t("Bilan du soir")}
          aide={t("Chaque soir, Wesley te dit ce que tu as fait, ce qui reste et ce qui t'attend demain (sur cet appareil).")}
          actif={h.bilan_soir}
          onChange={(v) => regler({ bilan_soir: v })}
        />
        {h.bilan_soir && (
          <label className="flex items-center justify-between gap-4 pb-2.5 pl-4 text-[13px] text-doux">
            {t("Heure du bilan")}
            <input
              type="time"
              value={h.bilan_soir_heure || "19:00"}
              onChange={(e) => regler({ bilan_soir_heure: e.target.value })}
              className="h-9 rounded-md border border-ligne-forte bg-surface-2 px-2 text-sm"
            />
          </label>
        )}
        <Interrupteur
          label={t("Mémoire par le sens")}
          aide={t("Wesley retrouve un souvenir même avec d'autres mots (« ma voiture » → « la Clio est au garage ») et joint à chaque demande les souvenirs utiles. Modèle local de ~270 Mo, téléchargé une fois ; rien ne sort de ton ordinateur.")}
          actif={h.memoire_semantique}
          onChange={(v) => regler({ memoire_semantique: v })}
        />
        <Interrupteur
          label={t("Apprendre de ses erreurs")}
          aide={t("Quand tu le corriges, ou qu'une méthode échoue puis qu'une autre marche, Wesley note tout seul la leçon pour la prochaine fois (Mémoire › Leçons apprises).")}
          actif={h.apprentissage_auto}
          onChange={(v) => regler({ apprentissage_auto: v })}
        />
        <Interrupteur
          label={t("Modèle rapide pour le travail de fond")}
          aide={t("Résumés, rangement de la mémoire, leçons et pilotage des tâches passent par un modèle rapide et bien moins cher (cerveau Claude). La conversation garde ton modèle.")}
          actif={h.modele_rapide_fond}
          onChange={(v) => regler({ modele_rapide_fond: v })}
        />
        <label className="flex items-center justify-between gap-4 py-2.5">
          <span>
            <span className="block text-sm">{t("Budget mensuel (cerveau Claude)")}</span>
            <span className="block text-[12px] text-doux">
              {t("En dollars ; 0 = pas de limite. Alerte à 80 %, puis Wesley passe sur un modèle économique jusqu'à la fin du mois.")}
            </span>
          </span>
          <input
            type="number"
            min={0}
            step={1}
            value={h.budget_mensuel ?? 0}
            onChange={(e) => setH((x) => (x ? { ...x, budget_mensuel: Math.max(0, +e.target.value || 0) } : x))}
            onBlur={(e) => regler({ budget_mensuel: Math.max(0, +e.target.value || 0) })}
            className="h-9 w-24 flex-none rounded-md border border-ligne-forte bg-surface-2 px-2 text-right text-sm"
          />
        </label>
        <Interrupteur
          label={t("Résumé automatique des transcriptions")}
          aide={t("À la fin d'une transcription, Wesley en fait le résumé, adapté à ce qui a été enregistré : notes de cours, décisions d'une réunion, sujets d'une discussion…")}
          actif={h.transcription_resume_auto}
          onChange={(v) => regler({ transcription_resume_auto: v })}
        />
        <Interrupteur
          label={t("Tâches dites → À faire")}
          aide={t("Les tâches et devoirs dits à voix haute pendant une transcription sont ajoutés à ta liste À faire, avec leur échéance.")}
          actif={h.transcription_actions_afaire}
          onChange={(v) => regler({ transcription_actions_afaire: v })}
        />
        {os.mac && (
          <Interrupteur
            label={t("Transcription sur la puce graphique (expérimental)")}
            aide={t("Sur un Mac à puce Apple, la reconnaissance de la parole peut tourner sur la puce graphique : souvent plus rapide. Si ça ne marche pas, Wesley repasse tout seul sur le processeur. Compare le retard affiché pendant une transcription, avec et sans.")}
            actif={h.transcription_gpu}
            onChange={(v) => regler({ transcription_gpu: v })}
          />
        )}
      </div>
    </Panneau>
  );
}

function OngletApplication() {
  const os = useOS();
  const [e, setE] = useState<EtatAppli | null>(null);
  useEffect(() => {
    api<EtatAppli>("/api/appli").then(setE).catch((x) => toast(x.message, "erreur"));
  }, []);
  const [compte, setCompte] = useState<{ email: string; prenom: string; serveur: string; machine: string; mode: string; url_confidentialite?: string; url_mentions?: string } | null>(null);
  const [action, setAction] = useState("");
  useEffect(() => {
    api<{ email: string; prenom: string; serveur: string; machine: string; mode: string; url_confidentialite?: string; url_mentions?: string }>("/api/compte")
      .then(setCompte)
      .catch(() => {});
  }, []);
  const agir = async (a: "importer" | "synchroniser" | "deconnexion" | "changer_mode") => {
    setAction(a);
    try {
      const r = await api<{ import?: { faits: number; lignes: number } }>(`/api/compte/${a}`, { method: "POST" });
      if (a === "importer")
        toast(
          r.import && (r.import.faits || r.import.lignes)
            ? t("Ajouté à ton compte : {faits} souvenir(s), {lignes} ligne(s) d'historique.", { faits: r.import.faits, lignes: r.import.lignes })
            : "Rien de nouveau : tout ce que cet appareil savait est déjà dans ton compte.",
          "succes",
        );
      else if (a === "synchroniser") toast(t("Synchronisé avec ton compte."), "succes");
      else location.reload();   // déconnexion / changement de mode : retour à l'écran de choix   // déconnecté : retour à l'écran de connexion
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setAction("");
    }
  };
  if (!e) return <p className="text-doux">{t("Chargement…")}</p>;
  const regler = async (p: Partial<EtatAppli>) => {
    try {
      const n = await api<EtatAppli>("/api/appli", { method: "POST", json: p });
      setE(n);
      majAudio({ ecouteFond: n.appli && n.ecoute_active });
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const raccourci = os.touches(e.raccourci);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <PanneauHabitudes />
      <Panneau titre={t("Application")} icone={<AppWindow />}>
        {!e.appli && (
          <p className="mb-3 rounded border border-ambre/40 bg-ambre/5 p-3 text-[13px] text-ambre">
            {t("Tu utilises Wesley dans le navigateur. L'écoute de fond et la fenêtre qui s'ouvre toute seule fonctionnent avec l'application (Wesley installé, ou lanceur.pyw).")}
          </p>
        )}
        <div className="divide-y divide-ligne">
          <Interrupteur
            label={t("Lancer Wesley {quand}", { quand: os.demarrage })}
            aide={t("Il démarre caché (icône {zone}) et attend que tu l'appelles.", { zone: os.zoneIcone })}
            actif={e.demarrage_auto}
            onChange={(v) => regler({ demarrage_auto: v })}
          />
          <Interrupteur
            label={t("Écoute « Wesley » en arrière-plan")}
            aide={t("Même fenêtre fermée : dis « Wesley, ouvre Discord » d'une traite, ou « Wesley » puis ta demande. Tout est analysé sur ton PC : rien n'est envoyé tant qu'il n'a pas reconnu son nom.")}
            actif={e.ecoute_fond}
            onChange={(v) => regler({ ecoute_fond: v })}
          />
        </div>
        <Curseur
          label={t("Sensibilité du mot d'activation")}
          valeur={1 - e.seuil_eveil}
          min={0.1}
          max={0.8}
          pas={0.05}
          affichage={e.seuil_eveil <= 0.35 ? "haute" : e.seuil_eveil >= 0.65 ? "basse" : "normale"}
          onChange={(v) => regler({ seuil_eveil: Math.round((1 - v) * 100) / 100 })}
          aide={t("Monte-la s'il ne t'entend pas, baisse-la s'il se déclenche tout seul.")}
        />
        <div className="mt-2 rounded-md border border-ligne bg-black/20 p-3 text-sm">
          {t("Raccourci pour l'appeler : ")}<kbd className="ml-1 rounded border border-ligne-forte bg-surface-3 px-2 py-0.5 font-mono text-xs">{raccourci}</kbd>
          <br />
          {t("Pour le faire taire : dis « Wesley, stop », ou appuie sur ")}<kbd className="ml-1 rounded border border-ligne-forte bg-surface-3 px-2 py-0.5 font-mono text-xs">{os.touches("<ctrl>+<alt>+s")}</kbd>{t(" (même fenêtre cachée).")}
          <p className="mt-1 text-[13px] text-doux">Fermer la fenêtre la cache seulement. Pour quitter : clic sur l'icône Wesley {os.zoneIcone}, puis « Quitter ».</p>
        </div>
      </Panneau>
      {compte?.mode === "local" ? (
        <Panneau titre={t("Wesley en local")} icone={<Cloud />}>
          <p className="text-[13px] leading-relaxed text-doux">
            {t("Tout reste sur cet ordinateur : mémoire, historique, connecteurs, clés. Rien n'est envoyé à un serveur. Mais il n'y a pas de récupération ailleurs : sur un autre appareil, ce sera un nouveau Wesley qui ne sait rien de toi.")}
          </p>
          <p className="mt-3 text-[13px] leading-relaxed text-doux">
            {t("En passant en ligne, tu crées ton compte (ou tu te connectes) et Wesley y envoie toute sa mémoire, ses réglages, tes connecteurs et tes clés (chiffrées avec ton mot de passe).")}
          </p>
          <Bouton className="mt-4" variante="primaire" icone={<Cloud />} chargement={action === "changer_mode"} onClick={() => agir("changer_mode")}>
            {t("Passer en ligne")}
          </Bouton>
        </Panneau>
      ) : (
      <Panneau titre={t("Mon compte")} icone={<Cloud />}>
        <p className="text-sm">
          {t("Connecté : ")}<span className="font-mono text-hud">{compte?.email ?? "…"}</span>
        </p>
        <p className="mt-1 text-sm">
          {t("Cet appareil : ")}<span className="font-mono text-hud">{e.machine}</span>
        </p>
        <p className="mt-3 text-[13px] leading-relaxed text-doux">
          {t("Tes souvenirs, l'historique des conversations, tes connecteurs et tes réglages sont rangés dans ton compte : connecte-toi sur n'importe quel appareil et Wesley se souvient des mêmes choses. Ta clé API et les mots de passe des connecteurs y sont chiffrés avec ton mot de passe : le serveur ne peut pas les lire.")}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Bouton icone={<Cloud />} chargement={action === "importer"} onClick={() => agir("importer")}>
            {t("Envoyer la mémoire de cet appareil")}
          </Bouton>
          <Bouton variante="fantome" chargement={action === "synchroniser"} onClick={() => agir("synchroniser")}>
            {t("Synchroniser")}
          </Bouton>
          <Bouton variante="danger" chargement={action === "deconnexion"} onClick={() => agir("deconnexion")}>
            {t("Se déconnecter")}
          </Bouton>
        </div>
        <p className="mt-2 text-[13px] text-doux">
          {t("« Envoyer » ajoute à ton compte ce que cet appareil savait avant (anciennes versions, OneDrive). Rien n'est écrasé, les doublons sont ignorés.")}
        </p>
        <MesDonnees urlConf={compte?.url_confidentialite ?? ""} urlMentions={compte?.url_mentions ?? ""} />
      </Panneau>
      )}
    </div>
  );
}

/** Confidentialité : pages légales, export des données, suppression du compte (RGPD). */
function MesDonnees({ urlConf, urlMentions }: { urlConf: string; urlMentions: string }) {
  const [export_, setExport] = useState(false);
  const [suppression, setSuppression] = useState(false);
  const [mdp, setMdp] = useState("");
  const [confirme, setConfirme] = useState(false);
  const [envoi, setEnvoi] = useState(false);

  const exporter = async () => {
    setExport(true);
    try {
      const r = await api<{ fichier: string }>("/api/compte/exporter", { method: "POST" });
      toast(t("Tes données sont dans {f}", { f: r.fichier }), "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setExport(false);
    }
  };
  const supprimer = async () => {
    setEnvoi(true);
    try {
      await api("/api/compte/supprimer", { method: "POST", json: { mot_de_passe: mdp } });
      toast(t("Ton compte et toutes ses données ont été supprimés."), "succes");
      setTimeout(() => location.reload(), 1500); // retour à l'écran de choix
    } catch (x) {
      toast((x as Error).message, "erreur");
      setEnvoi(false);
    }
  };

  return (
    <div className="mt-5 border-t border-ligne pt-4">
      <h3 className="mb-2 text-sm font-medium">{t("Mes données")}</h3>
      <div className="flex flex-wrap gap-2">
        <Bouton taille="sm" icone={<Download className="size-3.5" />} chargement={export_} onClick={exporter}>
          {t("Télécharger mes données")}
        </Bouton>
        <Bouton taille="sm" variante="danger" icone={<Trash2 className="size-3.5" />} onClick={() => setSuppression(!suppression)}>
          {t("Supprimer mon compte")}
        </Bouton>
      </div>
      <p className="mt-2 text-[12px] text-tres-doux">
        {t("Le téléchargement crée un fichier avec tout ce que ton compte contient (souvenirs, historique, réglages, appareils, tickets) dans ton dossier Téléchargements.")}
      </p>
      {suppression && (
        <div className="mt-3 space-y-2.5 rounded-md border border-rouge/40 bg-rouge/5 p-3">
          <p className="text-[13px] leading-relaxed text-rouge">
            {t("Ton compte, ta mémoire, ton historique, tes réglages, tes clés et tes tickets seront effacés du serveur pour toujours, et tous tes appareils seront déconnectés. Ce n'est pas réversible.")}
          </p>
          <Champ type="password" placeholder={t("Ton mot de passe, pour confirmer")} value={mdp} onChange={(e) => setMdp(e.target.value)} autoComplete="current-password" />
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={confirme} onChange={(e) => setConfirme(e.target.checked)} className="accent-hud" />
            {t("Je comprends que tout sera supprimé définitivement")}
          </label>
          <Bouton variante="danger" disabled={!mdp || !confirme} chargement={envoi} onClick={supprimer} icone={<Trash2 className="size-4" />}>
            {t("Supprimer définitivement")}
          </Bouton>
        </div>
      )}
      <div className="mt-3 flex gap-4 text-[12px]">
        <button onClick={() => urlConf && ouvrirLien(urlConf)} className="text-hud hover:underline">
          {t("Politique de confidentialité")}
        </button>
        <button onClick={() => urlMentions && ouvrirLien(urlMentions)} className="text-hud hover:underline">
          {t("Mentions légales")}
        </button>
      </div>
    </div>
  );
}

function NiveauDirect() {
  const [v, setV] = useState(0);
  useEffect(() => {
    const i = setInterval(() => setV(micro.niveau), 150);
    return () => clearInterval(i);
  }, []);
  return <span className="font-mono text-xs text-hud">{(v * 100).toFixed(1)}</span>;
}

function TestMicro() {
  const micActif = useAudio((s) => s.micActif);
  const [etat, setEtat] = useState<"repos" | "enregistre" | "analyse">("repos");
  const [res, setRes] = useState<{ crete: number; texte: string } | null>(null);
  const lancer = async () => {
    setRes(null);
    setEtat("enregistre");
    sons.ecoute();
    const m = await micro.enregistrerTest(4000);
    sons.fin();
    micro.rejouer(m);
    setEtat("analyse");
    const c = crete(m);
    try {
      setRes({ crete: c, texte: await transcrire(m) });
    } catch (e) {
      setRes({ crete: c, texte: `Erreur : ${(e as Error).message}` });
    }
    setEtat("repos");
  };
  const verdict = !res ? null : res.crete > 0.98 ? ["Ça sature — baisse le gain.", "text-rouge"] : res.crete < 0.1 ? ["Trop faible — monte le gain.", "text-ambre"] : ["Bon niveau.", "text-vert"];
  return (
    <div className="space-y-3">
      <Bouton onClick={lancer} disabled={!micActif} chargement={etat !== "repos"} icone={<Mic className="size-4" />}>
        {etat === "enregistre" ? "Parle maintenant… (4 s)" : etat === "analyse" ? "Analyse…" : "Tester mon micro"}
      </Bouton>
      {res && verdict && (
        <div className="rounded-md border border-ligne bg-black/20 p-3 text-sm">
          <p>
            {t("Crête : ")}<span className="font-mono">{Math.round(res.crete * 100)} %</span> — <span className={verdict[1]}>{verdict[0]}</span>
          </p>
          <p className="mt-1 text-doux">
            {t("Whisper a compris : ")}<span className="text-texte">« {res.texte || "(rien)"} »</span>
          </p>
        </div>
      )}
      <p className="text-[13px] text-doux">{t("Enregistre 4 secondes, te les fait réécouter et montre ce que la reconnaissance vocale a compris.")}</p>
    </div>
  );
}

function OngletMicro() {
  const r = useReglages();
  const { peripheriques, micActif, erreurMicro } = useAudio();
  const redemarrer = () => setTimeout(() => micro.demarrer(), 0);
  const actuel = r.deviceId || micro.idPeripheriqueActif() || "default";
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panneau titre={t("Entrée")} icone={<Mic />}>
        {erreurMicro && <p className="mb-3 rounded border border-rouge/40 bg-rouge/5 p-3 text-sm text-rouge">{erreurMicro}</p>}
        <Selecteur
          label={t("Périphérique")}
          valeur={actuel}
          options={peripheriques.length ? peripheriques.map((p) => ({ valeur: p.id, libelle: p.nom })) : [{ valeur: "default", libelle: t("Micro par défaut") }]}
          onChange={(v) => {
            r.maj({ deviceId: v });
            redemarrer();
          }}
        />
        <div className="py-2">
          <div className="mb-1.5 flex justify-between text-sm">
            <span>{t("Niveau en direct")}</span>
            {micActif ? <NiveauDirect /> : <span className="text-xs text-rouge">inactif</span>}
          </div>
          <VuMetre segments={50} />
          <p className="mt-1.5 text-[13px] text-doux">
            {t("La ligne orange est le seuil de détection : ta voix doit la dépasser nettement, le silence doit rester en dessous.")}
          </p>
        </div>
        <Curseur label={t("Gain")} valeur={r.gain} min={0.5} max={5} pas={0.1} affichage={`×${r.gain.toFixed(1)}`} onChange={(v) => { r.maj({ gain: v }); micro.setGain(v); }} />
        <Curseur
          label={t("Seuil de détection")}
          valeur={r.seuil}
          min={0}
          max={0.25}
          pas={0.001}
          affichage={r.seuil === 0 ? "0 · auto" : (r.seuil * 100).toFixed(1)}
          onChange={(v) => r.maj({ seuil: v })}
          aide={t("À 0, pas de seuil fixe : Wesley s'adapte au bruit de ta pièce et capte même une voix faible.")}
        />
        <Curseur
          label={t("Silence avant envoi")}
          valeur={r.silence}
          min={500}
          max={10000}
          pas={250}
          affichage={`${(r.silence / 1000).toFixed(1)} s`}
          onChange={(v) => {
            r.maj({ silence: v });
            api("/api/appli", { method: "POST", json: { silence_fin: v / 1000 } }).catch(() => {});
          }}
          aide={t("Wesley t'écoute jusqu'au bout, pauses comprises : il n'envoie ta demande qu'après ce temps de silence. Vaut aussi pour « Wesley, … » fenêtre fermée.")}
        />
      </Panneau>
      <div className="space-y-4">
        <Panneau titre={t("Traitement")}>
          <div className="divide-y divide-ligne">
            <Interrupteur label={t("Suppression du bruit")} aide={t("Filtre les bruits de fond (ventilos, clavier)")} actif={r.bruit} onChange={(v) => { r.maj({ bruit: v }); redemarrer(); }} />
            <Interrupteur label={t("Annulation d'écho")} aide={t("Indispensable si tu es sur haut-parleurs")} actif={r.echo} onChange={(v) => { r.maj({ echo: v }); redemarrer(); }} />
            <Interrupteur label={t("Gain automatique")} aide={t("Le navigateur ajuste le volume tout seul")} actif={r.agc} onChange={(v) => { r.maj({ agc: v }); redemarrer(); }} />
            <Interrupteur label={t("Sourdine pendant que Wesley parle")} aide={t("Évite qu'il s'écoute lui-même en mode mains libres")} actif={r.sourdine} onChange={(v) => r.maj({ sourdine: v })} />
          </div>
        </Panneau>
        <Panneau titre={t("Test")}>
          <TestMicro />
        </Panneau>
      </div>
    </div>
  );
}

type EtatKyutai = {
  compatible: boolean;
  raison: string;
  installe: boolean;
  en_cours: boolean;
  etape: string;
  pct: number;
  erreur: string;
  taille: string;
  actif: boolean;
};

/** Voix Kyutai : téléchargement (environnement + modèle), progression, choix de la voix. */
function PanneauKyutai({ voix }: { voix: { id: string; nom: string }[] }) {
  const r = useReglages();
  const [k, setK] = useState<EtatKyutai | null>(null);
  const charger = () => api<EtatKyutai>("/api/kyutai").then(setK).catch(() => {});
  useEffect(() => {
    charger();
    const sur = (e: Event) => setK((x) => (x ? { ...x, ...(e as CustomEvent<Partial<EtatKyutai>>).detail } : x));
    bus.addEventListener("kyutai", sur);
    const i = setInterval(charger, 5000);
    return () => {
      bus.removeEventListener("kyutai", sur);
      clearInterval(i);
    };
  }, []);
  const agir = async (action: "installer" | "supprimer" | "demarrer") => {
    try {
      setK(await api<EtatKyutai>(`/api/kyutai/${action}`, { method: "POST" }));
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  useEffect(() => {
    if (k?.installe && !k.actif) agir("demarrer"); // charge le modèle à l'avance : la 1re phrase part plus vite
  }, [k?.installe]);
  if (!k) return null;
  if (!k.compatible) return <p className="my-2 rounded border border-ambre/40 bg-ambre/5 p-3 text-[13px] text-ambre">{k.raison}</p>;
  if (k.en_cours || (!k.installe && k.pct > 0 && !k.erreur))
    return (
      <div className="my-2 rounded-md border border-ligne p-3">
        <div className="mb-2 flex justify-between text-[13px]">
          <span>{k.etape}</span>
          <span className="font-mono text-hud">{k.pct} %</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded bg-surface-3">
          <div className="h-full bg-hud transition-all" style={{ width: `${k.pct}%` }} />
        </div>
        <p className="mt-2 text-[12px] text-doux">{t("Tu peux continuer à utiliser Wesley pendant ce temps.")}</p>
      </div>
    );
  if (!k.installe)
    return (
      <div className="my-2 rounded-md border border-ligne p-3">
        <p className="text-[13px] text-doux">
          {t("La voix Kyutai doit être téléchargée une fois ({taille}). Elle tourne ensuite entièrement sur ton ordinateur, sans Internet.", { taille: k.taille })}
        </p>
        {k.erreur && <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 text-[11px] text-rouge">{k.erreur}</pre>}
        <Bouton className="mt-3" variante="primaire" icone={<Download className="size-4" />} onClick={() => agir("installer")}>
          {k.erreur ? t("Réessayer") : t("Télécharger la voix Kyutai")}
        </Bouton>
      </div>
    );
  return (
    <>
      <Selecteur
        label={t("Voix")}
        valeur={r.ttsVoixKyutai}
        options={voix.map((v) => ({ valeur: v.id, libelle: t(v.nom) }))}
        onChange={(v) => r.maj({ ttsVoixKyutai: v })}
        aide={k.actif ? t("Modèle chargé : prêt à parler.") : t("Chargement du modèle… (quelques secondes)")}
      />
      <button className="text-[12px] text-tres-doux hover:text-rouge" onClick={() => confirm(t("Supprimer la voix Kyutai de cet ordinateur ?")) && agir("supprimer")}>
        {t("Supprimer la voix Kyutai (libère l'espace disque)")}
      </button>
    </>
  );
}

function OngletVoix() {
  const r = useReglages();
  const voixNav = useAudio((s) => s.voix);
  const nom = useWesley((s) => s.session?.nom ?? "");
  const [voixServeur, setVoixServeur] = useState<VoixServeur>({ edge: [], piper: [] });
  useEffect(() => {
    chargerVoix();
    listerVoixServeur().then(setVoixServeur).catch(() => {});
  }, []);
  const tester = () => parler(t("Bonjour {nom}. Que puis-je faire pour vous ?", { nom }), true);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panneau titre={t("Voix de Wesley")} icone={<Volume2 />}>
        <Interrupteur label={t("Réponses vocales")} aide={t("Wesley lit ses réponses à voix haute, phrase par phrase, pendant qu'il les écrit")} actif={r.tts} onChange={(v) => r.maj({ tts: v })} />
        <Selecteur
          label={t("Moteur")}
          valeur={r.ttsMoteur}
          options={[
            { valeur: "kyutai", libelle: t("Kyutai — voix humaine, 100 % locale et gratuite (à télécharger)") },
            { valeur: "edge", libelle: t("Neuronal Microsoft — voix humaine (en ligne)") },
            { valeur: "piper", libelle: t("Piper — neuronal 100 % local") },
            { valeur: "navigateur", libelle: t("Navigateur — voix Windows (robotique)") },
          ]}
          onChange={(v) => r.maj({ ttsMoteur: v as typeof r.ttsMoteur })}
          aide={
            r.ttsMoteur === "kyutai"
              ? t("Modèle du labo français Kyutai, sur ton ordinateur : très naturel, rien n'est envoyé. Le débit ne s'applique pas à cette voix.")
              : r.ttsMoteur === "edge"
              ? "Le plus naturel. Le texte des réponses est envoyé à Microsoft pour être lu. Sans Internet, Wesley bascule tout seul sur Piper."
              : r.ttsMoteur === "piper"
                ? "Rien ne sort de ton PC. Un peu moins expressif que Microsoft."
                : "Voix intégrées à Windows / au navigateur. Dépanne, mais sonne robotique."
          }
        />
        {r.ttsMoteur === "kyutai" && <PanneauKyutai voix={voixServeur.kyutai ?? []} />}
        {r.ttsMoteur === "edge" && (
          <Selecteur label={t("Voix")} valeur={r.ttsVoixEdge} options={voixServeur.edge.map((v) => ({ valeur: v.id, libelle: v.nom }))} onChange={(v) => r.maj({ ttsVoixEdge: v })} />
        )}
        {r.ttsMoteur === "piper" && (
          <Selecteur
            label={t("Voix")}
            valeur={r.ttsVoixPiper}
            options={voixServeur.piper.length ? voixServeur.piper.map((v) => ({ valeur: v.id, libelle: v.nom })) : [{ valeur: "", libelle: t("Aucune voix dans le dossier voix/") }]}
            onChange={(v) => r.maj({ ttsVoixPiper: v })}
          />
        )}
        {r.ttsMoteur === "navigateur" && (
          <>
            <Selecteur
              label={t("Voix")}
              valeur={r.voix}
              options={voixNav.length ? voixNav.map((v) => ({ valeur: v.uri, libelle: `${v.nom} — ${v.lang}` })) : [{ valeur: "", libelle: t("Aucune voix trouvée") }]}
              onChange={(v) => r.maj({ voix: v })}
            />
            <Curseur label={t("Hauteur")} valeur={r.hauteur} min={0.5} max={1.5} pas={0.05} affichage={r.hauteur.toFixed(2)} onChange={(v) => r.maj({ hauteur: v })} />
          </>
        )}
        <Curseur label={t("Débit")} valeur={r.debit} min={0.7} max={1.6} pas={0.05} affichage={`×${r.debit.toFixed(2)}`} onChange={(v) => r.maj({ debit: v })} />
        <Curseur label={t("Volume")} valeur={r.volume} min={0} max={1} pas={0.05} affichage={`${Math.round(r.volume * 100)} %`} onChange={(v) => r.maj({ volume: v })} />
        <div className="mt-3 flex gap-2">
          <Bouton icone={<Play className="size-4" />} onClick={tester}>
            {t("Écouter")}
          </Bouton>
          <Bouton variante="fantome" onClick={taire}>
            {t("Stop")}
          </Bouton>
        </div>
      </Panneau>
      <Panneau titre={t("Reconnaissance")}>
        <Selecteur
          label={t("Langue parlée")}
          valeur={r.langue}
          options={[
            { valeur: "fr", libelle: t("Français") },
            { valeur: "en", libelle: t("Anglais") },
            { valeur: "", libelle: t("Détection automatique") },
          ]}
          onChange={(v) => {
            r.maj({ langue: v });
            chargerVoix();
          }}
        />
        <p className="mt-2 text-[13px] text-doux">
          {t("La reconnaissance vocale (Whisper) tourne en local sur ton PC et se charge au démarrage de Wesley. Sa précision se règle dans l'onglet Cerveau.")}
        </p>
      </Panneau>
    </div>
  );
}

type EtatClaude = {
  cle: boolean;
  cle_masquee: string;
  couts: { total: number; aujourdhui: number; appels: number };
  modeles: { id: string; nom: string }[];
};

const dollars = (v: number) => (v < 0.01 ? `${(v * 100).toFixed(2)} ¢` : `${v.toFixed(2)} $`);

function ReglagesClaude({ cfg, enregistrer }: { cfg: ConfigServeur; enregistrer: (p: Partial<ConfigServeur>) => void }) {
  const [etat, setEtat] = useState<EtatClaude | null>(null);
  const [cle, setCle] = useState("");
  const [test, setTest] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const charger = () => api<EtatClaude>("/api/claude").then(setEtat).catch((e) => toast(e.message, "erreur"));
  useEffect(() => {
    charger();
    const i = setInterval(charger, 10000);
    return () => clearInterval(i);
  }, []);

  const sauverCle = async () => {
    try {
      await api("/api/claude/cle", { method: "POST", json: { cle } });
      setCle("");
      toast(t("Clé enregistrée dans le fichier .env de Wesley."), "succes");
      charger();
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };
  const tester = async () => {
    setEnCours(true);
    setTest(null);
    try {
      const r = await api<{ reponse: string; secondes: number }>("/api/claude/tester", { method: "POST" });
      setTest(`✓ « ${r.reponse.trim()} » en ${r.secondes} s`);
      charger();
    } catch (e) {
      setTest(`✗ ${(e as Error).message}`);
    } finally {
      setEnCours(false);
    }
  };

  return (
    <div className="space-y-1">
      <div className="py-2">
        <span className="mb-1.5 block text-sm">{t("Clé API Anthropic")}</span>
        {etat?.cle ? (
          <p className="mb-2 flex items-center gap-2 text-sm text-vert">
            <KeyRound className="size-4" />{t(" Configurée ")}<span className="font-mono text-xs text-doux">{etat.cle_masquee}</span>
          </p>
        ) : (
          <p className="mb-2 text-sm text-ambre">{t("Aucune clé : crée-en une sur platform.claude.com (section API keys).")}</p>
        )}
        <div className="flex gap-2">
          <input
            type="password"
            autoComplete="off"
            value={cle}
            onChange={(e) => setCle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && cle.trim() && sauverCle()}
            placeholder={etat?.cle ? "Remplacer la clé…" : "sk-ant-…"}
            className="h-10 min-w-0 flex-1 rounded-md border border-ligne-forte bg-surface-2 px-3 font-mono text-sm outline-none focus:border-hud"
          />
          <Bouton onClick={sauverCle} disabled={!cle.trim()}>
            {t("Enregistrer")}
          </Bouton>
        </div>
        <p className="mt-1 text-[13px] text-doux">{t("Stockée uniquement dans le fichier .env de Wesley, sur ton PC.")}</p>
      </div>
      <Selecteur
        label={t("Modèle")}
        valeur={cfg.claude_modele}
        options={(etat?.modeles ?? [{ id: cfg.claude_modele, nom: cfg.claude_modele }]).map((m) => ({ valeur: m.id, libelle: m.nom }))}
        onChange={(v) => enregistrer({ claude_modele: v })}
      />
      <Selecteur
        label={t("Effort de réflexion")}
        valeur={cfg.claude_effort}
        options={[
          { valeur: "auto", libelle: t("Automatique — réactif pour discuter, réfléchit à fond pour une vraie tâche (recommandé)") },
          { valeur: "low", libelle: t("Bas — toujours le plus réactif") },
          { valeur: "medium", libelle: t("Moyen") },
          { valeur: "high", libelle: t("Élevé — plus lent et plus cher") },
          { valeur: "xhigh", libelle: t("Très élevé — le plus réfléchi, le plus lent") },
        ]}
        onChange={(v) => enregistrer({ claude_effort: v })}
        aide={t("En automatique, dis « réfléchis bien » pour qu'il prenne le temps de réfléchir au maximum.")}
      />
      <Interrupteur
        label={t("Conseiller Opus")}
        aide={t("Avec Sonnet, Wesley demande l'avis du modèle Opus (plus puissant) avant une décision difficile ou un plan complexe. Un peu plus cher, seulement quand c'est utile.")}
        actif={cfg.conseiller !== false}
        onChange={(v) => enregistrer({ conseiller: v })}
      />
      <Interrupteur
        label={t("Recherche web de Claude")}
        aide={t("Recherche et lecture de pages faites par Anthropic : résultats plus fiables et sources citées. Facturée en plus par Anthropic (environ 1 centime par recherche).")}
        actif={cfg.recherche_web_native !== false}
        onChange={(v) => enregistrer({ recherche_web_native: v })}
      />
      <div className="flex flex-wrap items-center gap-3 py-2">
        <Bouton icone={<Zap className="size-4" />} chargement={enCours} onClick={tester} disabled={!etat?.cle}>
          {t("Tester")}
        </Bouton>
        {test && <span className={cx("text-sm", test.startsWith("✓") ? "text-vert" : "text-rouge")}>{test}</span>}
      </div>
      {etat && (
        <div className="grid grid-cols-3 gap-2 border-t border-ligne pt-3">
          {[
            ["Aujourd'hui", dollars(etat.couts.aujourdhui)],
            ["Total", dollars(etat.couts.total)],
            ["Appels", String(etat.couts.appels)],
          ].map(([l, v]) => (
            <div key={l} className="rounded border border-ligne bg-black/20 p-2.5">
              <div className="titre-hud text-[9px] text-doux">{l}</div>
              <div className="mt-1 font-mono text-sm text-hud">{v}</div>
            </div>
          ))}
          <p className="col-span-3 text-[12px] text-tres-doux">{t("Estimation à partir des tokens facturés (cache compris). Le solde exact est sur platform.claude.com.")}</p>
        </div>
      )}
    </div>
  );
}

/** IA proposée comme cerveau (catalogue de wesley/fournisseurs.py). */
export type IA = { id: string; nom: string; detail: string; cle_ou: string; cle: boolean; local: boolean; perso: boolean };

/** Réglages d'une IA compatible OpenAI : clé API (gardée dans .env + coffre chiffré du compte), adresse (« Autre »),
 *  modèle choisi dans la liste du fournisseur ou écrit à la main. */
function ReglagesIA({ ia, cfg, enregistrer }: { ia: IA; cfg: ConfigServeur; enregistrer: (p: Partial<ConfigServeur>) => void }) {
  type Etat = { cle: boolean; cle_masquee: string; modeles: string[]; modele: string; conseille: string; url: string; erreur: string };
  const cleModele = `${ia.id}_modele` as const;
  const [e, setE] = useState<Etat | null>(null);
  const [cle, setCle] = useState("");
  const [url, setUrl] = useState(cfg.perso_url || "");
  const [modele, setModele] = useState("");
  const [test, setTest] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const charger = () =>
    api<Etat>(`/api/ia/${ia.id}`)
      .then((x) => {
        setE(x);
        setModele(cfg[cleModele] || x.modele || "");
      })
      .catch((x) => toast((x as Error).message, "erreur"));
  useEffect(() => {
    setE(null);
    setTest(null);
    setCle("");
    charger();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ia.id]);
  const sauverCle = async () => {
    try {
      setE(await api<Etat>(`/api/ia/${ia.id}/cle`, { method: "POST", json: { cle } }));
      setCle("");
      toast(t("Clé {nom} enregistrée.", { nom: t(ia.nom) }), "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const sauverUrl = async () => {
    await enregistrer({ perso_url: url.trim() });
    charger();
  };
  const choisirModele = (v: string) => {
    setModele(v);
    if (v.trim() !== (cfg[cleModele] || "")) enregistrer({ [cleModele]: v.trim() } as Partial<ConfigServeur>);
  };
  const tester = async () => {
    setEnCours(true);
    try {
      const r = await api<{ texte: string; secondes: number; modele: string }>(`/api/ia/${ia.id}/tester`, { method: "POST" });
      setTest(`${r.modele} : « ${r.texte} » ${t("en {s} s", { s: r.secondes })}`);
    } catch (x) {
      setTest((x as Error).message);
    } finally {
      setEnCours(false);
    }
  };
  const pret = e?.cle || (ia.local && !ia.cle);
  return (
    <div className="space-y-3">
      {ia.perso && (
        <label className="block text-sm">
          <span className="mb-1.5 block">{t("Adresse de l'API (compatible OpenAI)")}</span>
          <div className="flex gap-2">
            <Champ placeholder="http://localhost:8000/v1" value={url} onChange={(x) => setUrl(x.target.value)} className="flex-1 font-mono" />
            <Bouton variante="primaire" onClick={sauverUrl} disabled={url.trim() === (cfg.perso_url || "")}>
              {t("Enregistrer")}
            </Bouton>
          </div>
        </label>
      )}
      {ia.cle && (
        <label className="block text-sm">
          <span className="mb-1.5 block">
            {t("Clé API {nom}", { nom: t(ia.nom) })}
            {ia.perso && <span className="text-doux">{t(" (facultative)")}</span>}{" "}
            {e?.cle_masquee && <span className="font-mono text-[12px] text-vert">({e.cle_masquee})</span>}
          </span>
          <div className="flex gap-2">
            <Champ type="password" placeholder={t("Colle ta clé ici")} value={cle} onChange={(x) => setCle(x.target.value)} className="flex-1" />
            <Bouton variante="primaire" icone={<KeyRound className="size-4" />} onClick={sauverCle} disabled={!cle.trim()}>
              {t("Enregistrer")}
            </Bouton>
          </div>
        </label>
      )}
      <p className="text-[12px] text-doux">{t(ia.cle_ou)}</p>
      {e?.erreur && <p className="text-[12px] text-ambre">{e.erreur}</p>}
      {e && (pret || e.modeles.length > 0) && (
        <label className="block text-sm">
          <span className="mb-1.5 block">{t("Modèle")}</span>
          <Champ
            list={`modeles-${ia.id}`}
            value={modele}
            placeholder={e.conseille || t("Nom du modèle")}
            onChange={(x) => setModele(x.target.value)}
            onBlur={(x) => choisirModele(x.target.value)}
            onKeyDown={(x) => x.key === "Enter" && choisirModele((x.target as HTMLInputElement).value)}
            className="font-mono"
          />
          <datalist id={`modeles-${ia.id}`}>
            {e.modeles.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <span className="mt-1 block text-[12px] text-doux">
            {e.modeles.length
              ? t("{n} modèles disponibles : choisis dans la liste ou écris un nom. Vide = le meilleur automatiquement.", { n: e.modeles.length })
              : t("Écris le nom du modèle. Vide = le modèle conseillé.")}
          </span>
        </label>
      )}
      {pret && (
        <Bouton icone={<Zap className="size-4" />} chargement={enCours} onClick={tester}>
          {t("Tester")}
        </Bouton>
      )}
      {test && <p className="text-[13px] text-doux">{test}</p>}
    </div>
  );
}

function CarteCerveau({ actif, titre, detail, onClick }: { actif: boolean; titre: string; detail: string; onClick: () => void }) {
  return (
    <button
      role="radio"
      aria-checked={actif}
      onClick={onClick}
      className={cx("rounded-md border px-3 py-2.5 text-left transition-colors", actif ? "border-hud bg-hud/10" : "border-ligne hover:border-ligne-forte")}
    >
      <div className={cx("text-sm font-semibold", actif ? "text-hud" : "text-texte")}>{titre}</div>
      <div className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-doux" title={detail}>{detail}</div>
    </button>
  );
}

function PanneauCerveau({
  cfg,
  maj,
  modeles,
  ias,
  enregistrer,
}: {
  cfg: ConfigServeur;
  maj: (p: Partial<ConfigServeur>) => void;
  modeles: string[];
  ias: IA[];
  enregistrer: (p: Partial<ConfigServeur>) => void;
}) {
  const choisir = (id: string) => cfg.cerveau !== id && enregistrer({ cerveau: id });
  const iaActive = ias.find((i) => i.id === cfg.cerveau);
  const carte = (i: IA) => <CarteCerveau key={i.id} actif={cfg.cerveau === i.id} titre={t(i.nom)} detail={t(i.detail)} onClick={() => choisir(i.id)} />;
  return (
    <Panneau titre={t("Cerveau")} icone={<Brain />}>
      <div role="radiogroup" aria-label={t("Cerveau de Wesley")} className="mb-4 space-y-3">
        <p className="titre-hud text-[10px] text-tres-doux">{t("Dans le cloud (avec une clé API)")}</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          <CarteCerveau
            actif={cfg.cerveau === "claude"}
            titre={t("Claude (API)")}
            detail={t("Le plus intelligent, conseillé. Payant, données envoyées à Anthropic.")}
            onClick={() => choisir("claude")}
          />
          {ias.filter((i) => !i.local && !i.perso).map(carte)}
        </div>
        <p className="titre-hud pt-1 text-[10px] text-tres-doux">{t("Sur ton ordinateur (gratuit, privé)")}</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          <CarteCerveau
            actif={cfg.cerveau === "ollama"}
            titre={t("Ollama (local)")}
            detail={t("Gratuit, 100 % privé. Utilise ta carte graphique.")}
            onClick={() => choisir("ollama")}
          />
          {ias.filter((i) => i.local || i.perso).map(carte)}
        </div>
      </div>
      {cfg.cerveau === "claude" ? (
        <ReglagesClaude cfg={cfg} enregistrer={enregistrer} />
      ) : iaActive ? (
        <ReglagesIA ia={iaActive} cfg={cfg} enregistrer={enregistrer} />
      ) : (
        <>
          <Selecteur label={t("Modèle Ollama")} valeur={cfg.modele} options={modeles.map((m) => ({ valeur: m, libelle: m }))} onChange={(v) => maj({ modele: v })} />
          <Interrupteur label={t("Réflexion approfondie")} aide={t("Le modèle réfléchit avant de répondre : plus malin, plus lent")} actif={cfg.reflexion} onChange={(v) => maj({ reflexion: v })} />
          <Curseur label={t("Température")} valeur={cfg.temperature} min={0} max={1.2} pas={0.05} affichage={cfg.temperature.toFixed(2)} onChange={(v) => maj({ temperature: v })} aide={t("Bas = précis et prévisible, haut = plus créatif.")} />
          <Selecteur
            label={t("Taille du contexte")}
            valeur={String(cfg.num_ctx)}
            options={[8192, 16384, 32768].map((n) => ({ valeur: String(n), libelle: t("{k}k jetons", { k: n / 1024 }) + (n > 16384 ? t(" (plus de VRAM)") : "") }))}
            onChange={(v) => maj({ num_ctx: +v })}
          />
        </>
      )}
      <Curseur label={t("Étapes d'outils max")} valeur={cfg.max_etapes_outils} min={5} max={60} pas={1} affichage={String(cfg.max_etapes_outils)} onChange={(v) => maj({ max_etapes_outils: v })} />
    </Panneau>
  );
}

function OngletCerveau() {
  const [cfg, setCfg] = useState<ConfigServeur | null>(null);
  const [modeles, setModeles] = useState<string[]>([]);
  const [ias, setIas] = useState<IA[]>([]);
  const [sauve, setSauve] = useState(false);
  const [prechargement, setPrechargement] = useState(false);

  useEffect(() => {
    api<{ config: ConfigServeur; modeles: string[] }>("/api/config")
      .then((d) => {
        setCfg(d.config);
        setModeles(d.modeles);
      })
      .catch((e) => toast(e.message, "erreur"));
    api<{ fournisseurs: IA[] }>("/api/ia")
      .then((d) => setIas(d.fournisseurs))
      .catch(() => {});
  }, []);

  if (!cfg) return <p className="text-doux">{t("Chargement…")}</p>;
  const maj = (p: Partial<ConfigServeur>) => setCfg({ ...cfg, ...p });
  // choix du cerveau / modèle Claude / effort : appliqués tout de suite
  const enregistrer = async (p: Partial<ConfigServeur>) => {
    setCfg({ ...cfg, ...p });
    try {
      await api("/api/config", { method: "POST", json: p });
      if (p.cerveau)
        toast(
          p.cerveau === "ollama"
            ? t("Cerveau : Ollama local. Chargement du modèle…")
            : t("Cerveau : {nom}. VRAM libérée.", { nom: p.cerveau === "claude" ? "Claude" : ias.find((i) => i.id === p.cerveau)?.nom ?? p.cerveau }),
          "succes",
        );
      rafraichirSysteme();
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };

  const sauver = async () => {
    setSauve(true);
    try {
      await api("/api/config", { method: "POST", json: { ...cfg, modele_vision: cfg.modele } });
      toast(t("Configuration enregistrée."), "succes");
    } catch (e) {
      toast((e as Error).message, "erreur");
    } finally {
      setSauve(false);
    }
  };

  const precharger = async () => {
    setPrechargement(true);
    try {
      const r = await api<{ secondes: number }>("/api/precharger_whisper", { method: "POST" });
      toast(`Whisper prêt (${r.secondes} s).`, "succes");
    } catch (e) {
      toast((e as Error).message, "erreur");
    } finally {
      setPrechargement(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <PanneauCerveau cfg={cfg} maj={maj} modeles={modeles} ias={ias} enregistrer={enregistrer} />
      <div className="space-y-4">
        <Panneau titre={t("Reconnaissance vocale")}>
          <Selecteur
            label={t("Modèle Whisper")}
            valeur={cfg.whisper_modele}
            options={[
              { valeur: "tiny", libelle: t("tiny — instantané, approximatif") },
              { valeur: "base", libelle: t("base — rapide") },
              { valeur: "small", libelle: t("small — bon équilibre (recommandé)") },
              { valeur: "medium", libelle: t("medium — précis, lent sur CPU") },
              { valeur: "large-v3", libelle: t("large-v3 — très précis, très lent") },
            ]}
            onChange={(v) => maj({ whisper_modele: v })}
          />
          <Bouton className="mt-2" icone={<Download className="size-4" />} chargement={prechargement} onClick={precharger}>
            {t("Précharger Whisper")}
          </Bouton>
          <p className="mt-2 text-[13px] text-doux">{t("Évite d'attendre ~10 s à ta première phrase. Enregistre d'abord si tu as changé de modèle.")}</p>
        </Panneau>
        <Panneau titre={t("Profil")}>
          <label className="block text-sm">
            <span className="mb-1.5 block">{t("Ton prénom")}</span>
            <input
              value={cfg.nom_utilisateur}
              onChange={(e) => maj({ nom_utilisateur: e.target.value })}
              className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 outline-none focus:border-hud"
            />
          </label>
          <div className="mt-4 flex flex-wrap gap-2">
            <Bouton variante="primaire" icone={<Save className="size-4" />} chargement={sauve} onClick={sauver}>
              {t("Enregistrer")}
            </Bouton>
            <Bouton
              icone={<ScanLine className="size-4" />}
              onClick={() => {
                rescanner();
                toast(t("Scan du PC lancé…"));
              }}
            >
              Re-scanner le PC
            </Bouton>
          </div>
        </Panneau>
      </div>
    </div>
  );
}

/** Langue de Wesley : textes de l'interface, réponses, reconnaissance vocale, voix et annonces. */
export async function choisirLangue(l: Langue) {
  changerLangue(l);
  const r = reglages();
  const voixFr = r.ttsVoixEdge.startsWith("fr-");
  r.maj({ langue: l, ...(l === "en" && voixFr ? { ttsVoixEdge: "en-GB-RyanNeural" } : l === "fr" && !voixFr ? { ttsVoixEdge: "fr-FR-HenriNeural" } : {}) });
  try {
    await api("/api/config", { method: "POST", json: { langue: l } });
  } catch {
    /* hors application : la langue de l'interface change quand même */
  }
  location.reload();
}

function OngletInterface() {
  const r = useReglages();
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panneau titre="Langue / Language" icone={<Monitor />}>
        <Selecteur
          label="Wesley"
          valeur={LANGUE}
          options={[
            { valeur: "fr", libelle: "Français" },
            { valeur: "en", libelle: "English" },
          ]}
          onChange={(v) => choisirLangue(v as Langue)}
          aide={t("Textes de l'interface, réponses de Wesley, reconnaissance vocale, voix et annonces.")}
        />
      </Panneau>
      <Panneau titre={t("Interface")} icone={<Monitor />}>
        <div className="divide-y divide-ligne">
          <Interrupteur label={t("Bips d'interface")} aide={t("Petits sons à l'écoute, à l'envoi, à chaque action")} actif={r.bips} onChange={(v) => r.maj({ bips: v })} />
          <Interrupteur label={t("Menu replié")} actif={r.menuReduit} onChange={(v) => r.maj({ menuReduit: v })} />
        </div>
        <Selecteur
          label={t("Animations du réacteur")}
          valeur={r.animations}
          options={[
            { valeur: "legeres", libelle: t("Légères — recommandé") },
            { valeur: "completes", libelle: t("Complètes — lueurs, 60 images/s") },
            { valeur: "aucunes", libelle: t("Désactivées — le plus rapide") },
          ]}
          onChange={(v) => r.maj({ animations: v as typeof r.animations })}
          aide={t("La carte graphique est partagée avec le modèle d'IA. Les animations complètes peuvent rendre Wesley beaucoup plus lent quand la VRAM est presque pleine (jeux, LDPlayer, Wallpaper Engine…).")}
        />
        <Bouton
          variante="danger"
          className="mt-4"
          icone={<RotateCcw className="size-4" />}
          onClick={() => {
            r.maj({ ...DEFAUT, vue: "reglages" });
            micro.setGain(DEFAUT.gain);
            toast(t("Réglages remis par défaut."));
          }}
        >
          Réglages par défaut
        </Bouton>
      </Panneau>
      <Panneau titre={t("Raccourcis clavier")}>
        <dl className="space-y-2.5 text-sm">
          {[
            ["Espace (maintenu)", "Parler (mode Appui)"],
            ["Échap", "Stopper la tâche ou la voix"],
            ["Entrée", "Envoyer le message"],
            ["Maj + Entrée", "Nouvelle ligne"],
            ["Ctrl + K", "Aller à la saisie"],
            ["Alt + 1…7", "Changer d'écran"],
          ].map(([k, v]) => (
            <div key={k} className="flex items-center justify-between gap-4">
              <dt className="text-doux">{v}</dt>
              <dd>
                <kbd className="rounded border border-ligne-forte bg-surface-3 px-2 py-0.5 font-mono text-xs">{k}</kbd>
              </dd>
            </div>
          ))}
        </dl>
      </Panneau>
    </div>
  );
}

export function VueReglages() {
  const [onglet, setOnglet] = useState<Onglet>("micro");
  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage titre={t("Réglages")} sousTitre={t("Micro, voix et cerveau de Wesley. Les réglages audio sont propres à ce navigateur.")} />
      <Onglets<Onglet>
        actif={onglet}
        onChange={setOnglet}
        onglets={[
          { id: "micro", libelle: t("Micro"), icone: <Mic /> },
          { id: "voix", libelle: t("Voix"), icone: <Volume2 /> },
          { id: "cerveau", libelle: t("Cerveau"), icone: <Brain /> },
          { id: "code", libelle: t("Code"), icone: <Code2 /> },
          { id: "application", libelle: t("Application"), icone: <AppWindow /> },
          { id: "autorisations", libelle: t("Autorisations"), icone: <ShieldCheck /> },
          { id: "interface", libelle: t("Interface"), icone: <Monitor /> },
        ]}
      />
      <div className={cx("mt-6")}>
        {onglet === "micro" && <OngletMicro />}
        {onglet === "voix" && <OngletVoix />}
        {onglet === "cerveau" && <OngletCerveau />}
        {onglet === "code" && <OngletCode />}
        {onglet === "application" && <OngletApplication />}
        {onglet === "autorisations" && <OngletAutorisations />}
        {onglet === "interface" && <OngletInterface />}
      </div>
    </div>
  );
}
