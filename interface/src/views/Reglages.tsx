import { changerLangue, LANGUE, t, type Langue } from "../lib/i18n";
import { AppWindow, Brain, Cloud, Code2, ShieldCheck, Download, KeyRound, Mic, Monitor, Play, RotateCcw, Save, ScanLine, Trash2, Volume2, Zap } from "lucide-react";
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
import { rescanner, useJarvis } from "../stores/jarvis";
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

/** Réglages › Code : les agents de code que Jarvis pilote dans les tâches de fond, et leur connexion. */
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
            {t("Jarvis te prévient par une notification si la connexion expire ou ne marche plus.")}
          </p>
        </Panneau>
      ))}
      <Panneau titre={t("Jarvis code lui-même")} icone={<Brain />}>
        <p className="text-[13px] text-doux">{t("Sans agent externe : Jarvis code avec ses propres outils et le cerveau choisi dans l'onglet Cerveau (Claude, OpenAI ou Ollama). Rien à connecter.")}</p>
      </Panneau>
    </div>
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
      <Panneau titre={t("Application")} icone={<AppWindow />}>
        {!e.appli && (
          <p className="mb-3 rounded border border-ambre/40 bg-ambre/5 p-3 text-[13px] text-ambre">
            {t("Tu utilises Jarvis dans le navigateur. L'écoute de fond et la fenêtre qui s'ouvre toute seule fonctionnent avec l'application (Jarvis installé, ou lanceur.pyw).")}
          </p>
        )}
        <div className="divide-y divide-ligne">
          <Interrupteur
            label={t("Lancer Jarvis {quand}", { quand: os.demarrage })}
            aide={t("Il démarre caché (icône {zone}) et attend que tu l'appelles.", { zone: os.zoneIcone })}
            actif={e.demarrage_auto}
            onChange={(v) => regler({ demarrage_auto: v })}
          />
          <Interrupteur
            label={t("Écoute « Jarvis » en arrière-plan")}
            aide={t("Même fenêtre fermée : dis « Jarvis, ouvre Discord » d'une traite, ou « Jarvis » puis ta demande. Tout est analysé sur ton PC : rien n'est envoyé tant qu'il n'a pas reconnu son nom.")}
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
          {t("Pour le faire taire : dis « Jarvis, stop », ou appuie sur ")}<kbd className="ml-1 rounded border border-ligne-forte bg-surface-3 px-2 py-0.5 font-mono text-xs">{os.touches("<ctrl>+<alt>+s")}</kbd>{t(" (même fenêtre cachée).")}
          <p className="mt-1 text-[13px] text-doux">Fermer la fenêtre la cache seulement. Pour quitter : clic sur l'icône Jarvis {os.zoneIcone}, puis « Quitter ».</p>
        </div>
      </Panneau>
      {compte?.mode === "local" ? (
        <Panneau titre={t("Jarvis en local")} icone={<Cloud />}>
          <p className="text-[13px] leading-relaxed text-doux">
            {t("Tout reste sur cet ordinateur : mémoire, historique, connecteurs, clés. Rien n'est envoyé à un serveur. Mais il n'y a pas de récupération ailleurs : sur un autre appareil, ce sera un nouveau Jarvis qui ne sait rien de toi.")}
          </p>
          <p className="mt-3 text-[13px] leading-relaxed text-doux">
            {t("En passant en ligne, tu crées ton compte (ou tu te connectes) et Jarvis y envoie toute sa mémoire, ses réglages, tes connecteurs et tes clés (chiffrées avec ton mot de passe).")}
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
          {t("Tes souvenirs, l'historique des conversations, tes connecteurs et tes réglages sont rangés dans ton compte : connecte-toi sur n'importe quel appareil et Jarvis se souvient des mêmes choses. Ta clé API et les mots de passe des connecteurs y sont chiffrés avec ton mot de passe : le serveur ne peut pas les lire.")}
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
          aide={t("À 0, pas de seuil fixe : Jarvis s'adapte au bruit de ta pièce et capte même une voix faible.")}
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
          aide={t("Jarvis t'écoute jusqu'au bout, pauses comprises : il n'envoie ta demande qu'après ce temps de silence. Vaut aussi pour « Jarvis, … » fenêtre fermée.")}
        />
      </Panneau>
      <div className="space-y-4">
        <Panneau titre={t("Traitement")}>
          <div className="divide-y divide-ligne">
            <Interrupteur label={t("Suppression du bruit")} aide={t("Filtre les bruits de fond (ventilos, clavier)")} actif={r.bruit} onChange={(v) => { r.maj({ bruit: v }); redemarrer(); }} />
            <Interrupteur label={t("Annulation d'écho")} aide={t("Indispensable si tu es sur haut-parleurs")} actif={r.echo} onChange={(v) => { r.maj({ echo: v }); redemarrer(); }} />
            <Interrupteur label={t("Gain automatique")} aide={t("Le navigateur ajuste le volume tout seul")} actif={r.agc} onChange={(v) => { r.maj({ agc: v }); redemarrer(); }} />
            <Interrupteur label={t("Sourdine pendant que Jarvis parle")} aide={t("Évite qu'il s'écoute lui-même en mode mains libres")} actif={r.sourdine} onChange={(v) => r.maj({ sourdine: v })} />
          </div>
        </Panneau>
        <Panneau titre={t("Test")}>
          <TestMicro />
        </Panneau>
      </div>
    </div>
  );
}

function OngletVoix() {
  const r = useReglages();
  const voixNav = useAudio((s) => s.voix);
  const nom = useJarvis((s) => s.session?.nom ?? "");
  const [voixServeur, setVoixServeur] = useState<VoixServeur>({ edge: [], piper: [] });
  useEffect(() => {
    chargerVoix();
    listerVoixServeur().then(setVoixServeur).catch(() => {});
  }, []);
  const tester = () => parler(t("Bonjour {nom}. Que puis-je faire pour vous ?", { nom }), true);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panneau titre={t("Voix de Jarvis")} icone={<Volume2 />}>
        <Interrupteur label={t("Réponses vocales")} aide={t("Jarvis lit ses réponses à voix haute, phrase par phrase, pendant qu'il les écrit")} actif={r.tts} onChange={(v) => r.maj({ tts: v })} />
        <Selecteur
          label={t("Moteur")}
          valeur={r.ttsMoteur}
          options={[
            { valeur: "edge", libelle: t("Neuronal Microsoft — voix humaine (en ligne)") },
            { valeur: "piper", libelle: t("Piper — neuronal 100 % local") },
            { valeur: "navigateur", libelle: t("Navigateur — voix Windows (robotique)") },
          ]}
          onChange={(v) => r.maj({ ttsMoteur: v as typeof r.ttsMoteur })}
          aide={
            r.ttsMoteur === "edge"
              ? "Le plus naturel. Le texte des réponses est envoyé à Microsoft pour être lu. Sans Internet, Jarvis bascule tout seul sur Piper."
              : r.ttsMoteur === "piper"
                ? "Rien ne sort de ton PC. Un peu moins expressif que Microsoft."
                : "Voix intégrées à Windows / au navigateur. Dépanne, mais sonne robotique."
          }
        />
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
          {t("La reconnaissance vocale (Whisper) tourne en local sur ton PC et se charge au démarrage de Jarvis. Sa précision se règle dans l'onglet Cerveau.")}
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
      toast(t("Clé enregistrée dans le fichier .env de Jarvis."), "succes");
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
        <p className="mt-1 text-[13px] text-doux">{t("Stockée uniquement dans le fichier .env de Jarvis, sur ton PC.")}</p>
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
          { valeur: "low", libelle: t("Bas — le plus réactif, idéal à l'oral (recommandé)") },
          { valeur: "medium", libelle: t("Moyen — mieux pour les longues tâches avec outils") },
          { valeur: "high", libelle: t("Élevé — plus lent et plus cher") },
        ]}
        onChange={(v) => enregistrer({ claude_effort: v })}
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

/** Cerveau OpenAI : clé API (gardée dans .env + coffre chiffré du compte) et modèle choisi parmi ceux de la clé. */
function ReglagesOpenAI({ cfg, enregistrer }: { cfg: ConfigServeur; enregistrer: (p: Partial<ConfigServeur>) => void }) {
  type Etat = { cle: boolean; cle_masquee: string; modeles: string[]; modele: string; erreur: string };
  const [e, setE] = useState<Etat | null>(null);
  const [cle, setCle] = useState("");
  const [test, setTest] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  useEffect(() => {
    api<Etat>("/api/openai").then(setE).catch(() => {});
  }, []);
  const sauverCle = async () => {
    try {
      setE(await api<Etat>("/api/openai/cle", { method: "POST", json: { cle } }));
      setCle("");
      toast(t("Clé OpenAI enregistrée."), "succes");
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };
  const tester = async () => {
    setEnCours(true);
    try {
      const r = await api<{ texte: string; secondes: number; modele: string }>("/api/openai/tester", { method: "POST" });
      setTest(`${r.modele} : « ${r.texte} » en ${r.secondes} s`);
    } catch (x) {
      setTest((x as Error).message);
    } finally {
      setEnCours(false);
    }
  };
  return (
    <div className="space-y-3">
      <label className="block text-sm">
        <span className="mb-1.5 block">Clé API OpenAI {e?.cle && <span className="font-mono text-[12px] text-vert">({e.cle_masquee})</span>}</span>
        <div className="flex gap-2">
          <Champ type="password" placeholder={t("sk-…")} value={cle} onChange={(x) => setCle(x.target.value)} className="flex-1" />
          <Bouton variante="primaire" icone={<KeyRound className="size-4" />} onClick={sauverCle} disabled={!cle.trim()}>
            {t("Enregistrer")}
          </Bouton>
        </div>
        <span className="mt-1 block text-[12px] text-doux">{t("platform.openai.com › API keys. L'abonnement ChatGPT Plus n'inclut pas de crédit API.")}</span>
      </label>
      {e?.erreur && <p className="text-[12px] text-rouge">{e.erreur}</p>}
      {e && e.modeles.length > 0 && (
        <Selecteur
          label={t("Modèle")}
          valeur={cfg.openai_modele || e.modele || e.modeles[0]}
          options={e.modeles.map((m) => ({ valeur: m, libelle: m }))}
          onChange={(v) => enregistrer({ openai_modele: v })}
        />
      )}
      {e?.cle && (
        <Bouton icone={<Zap className="size-4" />} chargement={enCours} onClick={tester}>
          {t("Tester")}
        </Bouton>
      )}
      {test && <p className="text-[13px] text-doux">{test}</p>}
    </div>
  );
}

function PanneauCerveau({
  cfg,
  maj,
  modeles,
  enregistrer,
}: {
  cfg: ConfigServeur;
  maj: (p: Partial<ConfigServeur>) => void;
  modeles: string[];
  enregistrer: (p: Partial<ConfigServeur>) => void;
}) {
  return (
    <Panneau titre={t("Cerveau")} icone={<Brain />}>
      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-3" role="radiogroup" aria-label={t("Cerveau de Jarvis")}>
        {[
          { id: "claude", titre: t("Claude (API)"), detail: t("Plus intelligent, ne touche pas ta carte graphique. Payant, données envoyées à Anthropic.") },
          { id: "openai", titre: t("OpenAI (API)"), detail: t("Avec ta clé API OpenAI (GPT). Payant, données envoyées à OpenAI.") },
          { id: "ollama", titre: t("Ollama (local)"), detail: t("Gratuit, 100 % privé. Utilise ta carte graphique.") },
        ].map((o) => (
          <button
            key={o.id}
            role="radio"
            aria-checked={cfg.cerveau === o.id}
            onClick={() => cfg.cerveau !== o.id && enregistrer({ cerveau: o.id as ConfigServeur["cerveau"] })}
            className={cx(
              "rounded-md border p-3 text-left transition-colors",
              cfg.cerveau === o.id ? "border-hud bg-hud/10" : "border-ligne hover:border-ligne-forte",
            )}
          >
            <div className={cx("text-sm font-semibold", cfg.cerveau === o.id ? "text-hud" : "text-texte")}>{o.titre}</div>
            <div className="mt-1 text-[12px] leading-snug text-doux">{o.detail}</div>
          </button>
        ))}
      </div>
      {cfg.cerveau === "claude" ? (
        <ReglagesClaude cfg={cfg} enregistrer={enregistrer} />
      ) : cfg.cerveau === "openai" ? (
        <ReglagesOpenAI cfg={cfg} enregistrer={enregistrer} />
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
  const [sauve, setSauve] = useState(false);
  const [prechargement, setPrechargement] = useState(false);

  useEffect(() => {
    api<{ config: ConfigServeur; modeles: string[] }>("/api/config")
      .then((d) => {
        setCfg(d.config);
        setModeles(d.modeles);
      })
      .catch((e) => toast(e.message, "erreur"));
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
          p.cerveau === "claude" ? "Cerveau : Claude. VRAM libérée." : p.cerveau === "openai" ? "Cerveau : OpenAI. VRAM libérée." : "Cerveau : Ollama local. Chargement du modèle…",
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
      <PanneauCerveau cfg={cfg} maj={maj} modeles={modeles} enregistrer={enregistrer} />
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

/** Langue de Jarvis : textes de l'interface, réponses, reconnaissance vocale, voix et annonces. */
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
          label="Jarvis"
          valeur={LANGUE}
          options={[
            { valeur: "fr", libelle: "Français" },
            { valeur: "en", libelle: "English" },
          ]}
          onChange={(v) => choisirLangue(v as Langue)}
          aide={t("Textes de l'interface, réponses de Jarvis, reconnaissance vocale, voix et annonces.")}
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
          aide={t("La carte graphique est partagée avec le modèle d'IA. Les animations complètes peuvent rendre Jarvis beaucoup plus lent quand la VRAM est presque pleine (jeux, LDPlayer, Wallpaper Engine…).")}
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
      <EnTetePage titre={t("Réglages")} sousTitre={t("Micro, voix et cerveau de Jarvis. Les réglages audio sont propres à ce navigateur.")} />
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
