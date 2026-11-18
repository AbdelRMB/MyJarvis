import { AppWindow, Brain, Cloud, Download, KeyRound, Mic, Monitor, Play, RotateCcw, Save, ScanLine, Volume2, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { crete, micro } from "../audio/micro";
import { sons } from "../audio/bips";
import { chargerVoix, listerVoixServeur, parler, taire, type VoixServeur } from "../audio/tts";
import { transcrire } from "../audio/voix";
import { Bouton, Curseur, EnTetePage, Interrupteur, Onglets, Panneau, Selecteur } from "../components/ui";
import { VuMetre } from "../components/VuMetre";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import type { ConfigServeur } from "../lib/types";
import { useOS } from "../lib/os";
import { majAudio, useAudio } from "../stores/audio";
import { rescanner, useJarvis } from "../stores/jarvis";
import { DEFAUT, useReglages } from "../stores/reglages";
import { toast } from "../stores/toasts";
import { rafraichirSysteme } from "../stores/systeme";

type Onglet = "micro" | "voix" | "cerveau" | "application" | "interface";

type EtatAppli = {
  appli: boolean;
  demarrage_auto: boolean;
  machine: string;
  dossier_partage: string;
  ecoute_fond: boolean;
  ecoute_active: boolean;
  seuil_eveil: number;
  raccourci: string;
};

function OngletApplication() {
  const os = useOS();
  const [e, setE] = useState<EtatAppli | null>(null);
  useEffect(() => {
    api<EtatAppli>("/api/appli").then(setE).catch((x) => toast(x.message, "erreur"));
  }, []);
  if (!e) return <p className="text-doux">Chargement…</p>;
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
      <Panneau titre="Application" icone={<AppWindow />}>
        {!e.appli && (
          <p className="mb-3 rounded border border-ambre/40 bg-ambre/5 p-3 text-[13px] text-ambre">
            Tu utilises Jarvis dans le navigateur. L'écoute de fond et la fenêtre qui s'ouvre toute seule fonctionnent avec l'application (Jarvis installé, ou lanceur.pyw).
          </p>
        )}
        <div className="divide-y divide-ligne">
          <Interrupteur
            label={`Lancer Jarvis ${os.demarrage}`}
            aide={`Il démarre caché (icône ${os.zoneIcone}) et attend que tu l'appelles.`}
            actif={e.demarrage_auto}
            onChange={(v) => regler({ demarrage_auto: v })}
          />
          <Interrupteur
            label="Écoute « Jarvis » en arrière-plan"
            aide="Même fenêtre fermée : dis « Jarvis, ouvre Discord » d'une traite, ou « Jarvis » puis ta demande. Tout est analysé sur ton PC : rien n'est envoyé tant qu'il n'a pas reconnu son nom."
            actif={e.ecoute_fond}
            onChange={(v) => regler({ ecoute_fond: v })}
          />
        </div>
        <Curseur
          label="Sensibilité du mot d'activation"
          valeur={1 - e.seuil_eveil}
          min={0.1}
          max={0.8}
          pas={0.05}
          affichage={e.seuil_eveil <= 0.35 ? "haute" : e.seuil_eveil >= 0.65 ? "basse" : "normale"}
          onChange={(v) => regler({ seuil_eveil: Math.round((1 - v) * 100) / 100 })}
          aide="Monte-la s'il ne t'entend pas, baisse-la s'il se déclenche tout seul."
        />
        <div className="mt-2 rounded-md border border-ligne bg-black/20 p-3 text-sm">
          Raccourci pour l'appeler : <kbd className="ml-1 rounded border border-ligne-forte bg-surface-3 px-2 py-0.5 font-mono text-xs">{raccourci}</kbd>
          <br />
          Pour le faire taire : dis « Jarvis, stop », ou appuie sur <kbd className="ml-1 rounded border border-ligne-forte bg-surface-3 px-2 py-0.5 font-mono text-xs">{os.touches("<ctrl>+<alt>+s")}</kbd> (même fenêtre cachée).
          <p className="mt-1 text-[13px] text-doux">Fermer la fenêtre la cache seulement. Pour quitter : clic sur l'icône Jarvis {os.zoneIcone}, puis « Quitter ».</p>
        </div>
      </Panneau>
      <Panneau titre="Mémoire partagée entre tes PC" icone={<Cloud />}>
        <p className="text-sm">
          Ce PC : <span className="font-mono text-hud">{e.machine}</span>
        </p>
        <p className="mt-3 text-sm">Dossier partagé :</p>
        <p className="mt-1 rounded border border-ligne bg-black/20 p-2 font-mono text-xs break-all text-hud-clair">{e.dossier_partage}</p>
        <p className="mt-3 text-[13px] leading-relaxed text-doux">
          Les souvenirs, l'historique des conversations et la liste des connecteurs sont rangés ici. OneDrive les synchronise : sur tes autres ordinateurs, PC ou Mac avec le même compte Microsoft, Jarvis se souvient des mêmes choses. Les mots de passe des connecteurs et la clé API restent sur chaque machine.
        </p>
      </Panneau>
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
            Crête : <span className="font-mono">{Math.round(res.crete * 100)} %</span> — <span className={verdict[1]}>{verdict[0]}</span>
          </p>
          <p className="mt-1 text-doux">
            Whisper a compris : <span className="text-texte">« {res.texte || "(rien)"} »</span>
          </p>
        </div>
      )}
      <p className="text-[13px] text-doux">Enregistre 4 secondes, te les fait réécouter et montre ce que la reconnaissance vocale a compris.</p>
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
      <Panneau titre="Entrée" icone={<Mic />}>
        {erreurMicro && <p className="mb-3 rounded border border-rouge/40 bg-rouge/5 p-3 text-sm text-rouge">{erreurMicro}</p>}
        <Selecteur
          label="Périphérique"
          valeur={actuel}
          options={peripheriques.length ? peripheriques.map((p) => ({ valeur: p.id, libelle: p.nom })) : [{ valeur: "default", libelle: "Micro par défaut" }]}
          onChange={(v) => {
            r.maj({ deviceId: v });
            redemarrer();
          }}
        />
        <div className="py-2">
          <div className="mb-1.5 flex justify-between text-sm">
            <span>Niveau en direct</span>
            {micActif ? <NiveauDirect /> : <span className="text-xs text-rouge">inactif</span>}
          </div>
          <VuMetre segments={50} />
          <p className="mt-1.5 text-[13px] text-doux">
            La ligne orange est le seuil de détection : ta voix doit la dépasser nettement, le silence doit rester en dessous.
          </p>
        </div>
        <Curseur label="Gain" valeur={r.gain} min={0.5} max={5} pas={0.1} affichage={`×${r.gain.toFixed(1)}`} onChange={(v) => { r.maj({ gain: v }); micro.setGain(v); }} />
        <Curseur
          label="Seuil de détection"
          valeur={r.seuil}
          min={0}
          max={0.25}
          pas={0.001}
          affichage={r.seuil === 0 ? "0 · auto" : (r.seuil * 100).toFixed(1)}
          onChange={(v) => r.maj({ seuil: v })}
          aide="À 0, pas de seuil fixe : Jarvis s'adapte au bruit de ta pièce et capte même une voix faible."
        />
        <Curseur
          label="Silence avant envoi"
          valeur={r.silence}
          min={500}
          max={10000}
          pas={250}
          affichage={`${(r.silence / 1000).toFixed(1)} s`}
          onChange={(v) => {
            r.maj({ silence: v });
            api("/api/appli", { method: "POST", json: { silence_fin: v / 1000 } }).catch(() => {});
          }}
          aide="Jarvis t'écoute jusqu'au bout, pauses comprises : il n'envoie ta demande qu'après ce temps de silence. Vaut aussi pour « Jarvis, … » fenêtre fermée."
        />
      </Panneau>
      <div className="space-y-4">
        <Panneau titre="Traitement">
          <div className="divide-y divide-ligne">
            <Interrupteur label="Suppression du bruit" aide="Filtre les bruits de fond (ventilos, clavier)" actif={r.bruit} onChange={(v) => { r.maj({ bruit: v }); redemarrer(); }} />
            <Interrupteur label="Annulation d'écho" aide="Indispensable si tu es sur haut-parleurs" actif={r.echo} onChange={(v) => { r.maj({ echo: v }); redemarrer(); }} />
            <Interrupteur label="Gain automatique" aide="Le navigateur ajuste le volume tout seul" actif={r.agc} onChange={(v) => { r.maj({ agc: v }); redemarrer(); }} />
            <Interrupteur label="Sourdine pendant que Jarvis parle" aide="Évite qu'il s'écoute lui-même en mode mains libres" actif={r.sourdine} onChange={(v) => r.maj({ sourdine: v })} />
          </div>
        </Panneau>
        <Panneau titre="Test">
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
  const tester = () => parler(`Bonjour ${nom}. Tous les systèmes sont opérationnels. Que puis-je faire pour vous ?`, true);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panneau titre="Voix de Jarvis" icone={<Volume2 />}>
        <Interrupteur label="Réponses vocales" aide="Jarvis lit ses réponses à voix haute, phrase par phrase, pendant qu'il les écrit" actif={r.tts} onChange={(v) => r.maj({ tts: v })} />
        <Selecteur
          label="Moteur"
          valeur={r.ttsMoteur}
          options={[
            { valeur: "edge", libelle: "Neuronal Microsoft — voix humaine (en ligne)" },
            { valeur: "piper", libelle: "Piper — neuronal 100 % local" },
            { valeur: "navigateur", libelle: "Navigateur — voix Windows (robotique)" },
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
          <Selecteur label="Voix" valeur={r.ttsVoixEdge} options={voixServeur.edge.map((v) => ({ valeur: v.id, libelle: v.nom }))} onChange={(v) => r.maj({ ttsVoixEdge: v })} />
        )}
        {r.ttsMoteur === "piper" && (
          <Selecteur
            label="Voix"
            valeur={r.ttsVoixPiper}
            options={voixServeur.piper.length ? voixServeur.piper.map((v) => ({ valeur: v.id, libelle: v.nom })) : [{ valeur: "", libelle: "Aucune voix dans le dossier voix/" }]}
            onChange={(v) => r.maj({ ttsVoixPiper: v })}
          />
        )}
        {r.ttsMoteur === "navigateur" && (
          <>
            <Selecteur
              label="Voix"
              valeur={r.voix}
              options={voixNav.length ? voixNav.map((v) => ({ valeur: v.uri, libelle: `${v.nom} — ${v.lang}` })) : [{ valeur: "", libelle: "Aucune voix trouvée" }]}
              onChange={(v) => r.maj({ voix: v })}
            />
            <Curseur label="Hauteur" valeur={r.hauteur} min={0.5} max={1.5} pas={0.05} affichage={r.hauteur.toFixed(2)} onChange={(v) => r.maj({ hauteur: v })} />
          </>
        )}
        <Curseur label="Débit" valeur={r.debit} min={0.7} max={1.6} pas={0.05} affichage={`×${r.debit.toFixed(2)}`} onChange={(v) => r.maj({ debit: v })} />
        <Curseur label="Volume" valeur={r.volume} min={0} max={1} pas={0.05} affichage={`${Math.round(r.volume * 100)} %`} onChange={(v) => r.maj({ volume: v })} />
        <div className="mt-3 flex gap-2">
          <Bouton icone={<Play className="size-4" />} onClick={tester}>
            Écouter
          </Bouton>
          <Bouton variante="fantome" onClick={taire}>
            Stop
          </Bouton>
        </div>
      </Panneau>
      <Panneau titre="Reconnaissance">
        <Selecteur
          label="Langue parlée"
          valeur={r.langue}
          options={[
            { valeur: "fr", libelle: "Français" },
            { valeur: "en", libelle: "Anglais" },
            { valeur: "", libelle: "Détection automatique" },
          ]}
          onChange={(v) => {
            r.maj({ langue: v });
            chargerVoix();
          }}
        />
        <p className="mt-2 text-[13px] text-doux">
          La reconnaissance vocale (Whisper) tourne en local sur ton PC et se charge au démarrage de Jarvis. Sa précision se règle dans l'onglet Cerveau.
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
      toast("Clé enregistrée dans le fichier .env de Jarvis.", "succes");
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
        <span className="mb-1.5 block text-sm">Clé API Anthropic</span>
        {etat?.cle ? (
          <p className="mb-2 flex items-center gap-2 text-sm text-vert">
            <KeyRound className="size-4" /> Configurée <span className="font-mono text-xs text-doux">{etat.cle_masquee}</span>
          </p>
        ) : (
          <p className="mb-2 text-sm text-ambre">Aucune clé : crée-en une sur platform.claude.com (section API keys).</p>
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
            Enregistrer
          </Bouton>
        </div>
        <p className="mt-1 text-[13px] text-doux">Stockée uniquement dans le fichier .env de Jarvis, sur ton PC.</p>
      </div>
      <Selecteur
        label="Modèle"
        valeur={cfg.claude_modele}
        options={(etat?.modeles ?? [{ id: cfg.claude_modele, nom: cfg.claude_modele }]).map((m) => ({ valeur: m.id, libelle: m.nom }))}
        onChange={(v) => enregistrer({ claude_modele: v })}
      />
      <Selecteur
        label="Effort de réflexion"
        valeur={cfg.claude_effort}
        options={[
          { valeur: "low", libelle: "Bas — le plus réactif, idéal à l'oral (recommandé)" },
          { valeur: "medium", libelle: "Moyen — mieux pour les longues tâches avec outils" },
          { valeur: "high", libelle: "Élevé — plus lent et plus cher" },
        ]}
        onChange={(v) => enregistrer({ claude_effort: v })}
      />
      <div className="flex flex-wrap items-center gap-3 py-2">
        <Bouton icone={<Zap className="size-4" />} chargement={enCours} onClick={tester} disabled={!etat?.cle}>
          Tester
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
          <p className="col-span-3 text-[12px] text-tres-doux">Estimation à partir des tokens facturés (cache compris). Le solde exact est sur platform.claude.com.</p>
        </div>
      )}
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
    <Panneau titre="Cerveau" icone={<Brain />}>
      <div className="mb-3 grid grid-cols-2 gap-2" role="radiogroup" aria-label="Cerveau de Jarvis">
        {[
          { id: "claude", titre: "Claude (API)", detail: "Plus intelligent, ne touche pas ta carte graphique. Payant, données envoyées à Anthropic." },
          { id: "ollama", titre: "Ollama (local)", detail: "Gratuit, 100 % privé. Utilise ta carte graphique." },
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
      ) : (
        <>
          <Selecteur label="Modèle Ollama" valeur={cfg.modele} options={modeles.map((m) => ({ valeur: m, libelle: m }))} onChange={(v) => maj({ modele: v })} />
          <Interrupteur label="Réflexion approfondie" aide="Le modèle réfléchit avant de répondre : plus malin, plus lent" actif={cfg.reflexion} onChange={(v) => maj({ reflexion: v })} />
          <Curseur label="Température" valeur={cfg.temperature} min={0} max={1.2} pas={0.05} affichage={cfg.temperature.toFixed(2)} onChange={(v) => maj({ temperature: v })} aide="Bas = précis et prévisible, haut = plus créatif." />
          <Selecteur
            label="Taille du contexte"
            valeur={String(cfg.num_ctx)}
            options={[8192, 16384, 32768].map((n) => ({ valeur: String(n), libelle: `${n / 1024}k jetons${n > 16384 ? " (plus de VRAM)" : ""}` }))}
            onChange={(v) => maj({ num_ctx: +v })}
          />
        </>
      )}
      <Curseur label="Étapes d'outils max" valeur={cfg.max_etapes_outils} min={5} max={60} pas={1} affichage={String(cfg.max_etapes_outils)} onChange={(v) => maj({ max_etapes_outils: v })} />
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

  if (!cfg) return <p className="text-doux">Chargement…</p>;
  const maj = (p: Partial<ConfigServeur>) => setCfg({ ...cfg, ...p });
  // choix du cerveau / modèle Claude / effort : appliqués tout de suite
  const enregistrer = async (p: Partial<ConfigServeur>) => {
    setCfg({ ...cfg, ...p });
    try {
      await api("/api/config", { method: "POST", json: p });
      if (p.cerveau) toast(p.cerveau === "claude" ? "Cerveau : Claude. VRAM libérée." : "Cerveau : Ollama local. Chargement du modèle…", "succes");
      rafraichirSysteme();
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };

  const sauver = async () => {
    setSauve(true);
    try {
      await api("/api/config", { method: "POST", json: { ...cfg, modele_vision: cfg.modele } });
      toast("Configuration enregistrée.", "succes");
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
        <Panneau titre="Reconnaissance vocale">
          <Selecteur
            label="Modèle Whisper"
            valeur={cfg.whisper_modele}
            options={[
              { valeur: "tiny", libelle: "tiny — instantané, approximatif" },
              { valeur: "base", libelle: "base — rapide" },
              { valeur: "small", libelle: "small — bon équilibre (recommandé)" },
              { valeur: "medium", libelle: "medium — précis, lent sur CPU" },
              { valeur: "large-v3", libelle: "large-v3 — très précis, très lent" },
            ]}
            onChange={(v) => maj({ whisper_modele: v })}
          />
          <Bouton className="mt-2" icone={<Download className="size-4" />} chargement={prechargement} onClick={precharger}>
            Précharger Whisper
          </Bouton>
          <p className="mt-2 text-[13px] text-doux">Évite d'attendre ~10 s à ta première phrase. Enregistre d'abord si tu as changé de modèle.</p>
        </Panneau>
        <Panneau titre="Profil">
          <label className="block text-sm">
            <span className="mb-1.5 block">Ton prénom</span>
            <input
              value={cfg.nom_utilisateur}
              onChange={(e) => maj({ nom_utilisateur: e.target.value })}
              className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 outline-none focus:border-hud"
            />
          </label>
          <div className="mt-4 flex flex-wrap gap-2">
            <Bouton variante="primaire" icone={<Save className="size-4" />} chargement={sauve} onClick={sauver}>
              Enregistrer
            </Bouton>
            <Bouton
              icone={<ScanLine className="size-4" />}
              onClick={() => {
                rescanner();
                toast("Scan du PC lancé…");
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

function OngletInterface() {
  const r = useReglages();
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panneau titre="Interface" icone={<Monitor />}>
        <div className="divide-y divide-ligne">
          <Interrupteur label="Bips d'interface" aide="Petits sons à l'écoute, à l'envoi, à chaque action" actif={r.bips} onChange={(v) => r.maj({ bips: v })} />
          <Interrupteur label="Menu replié" actif={r.menuReduit} onChange={(v) => r.maj({ menuReduit: v })} />
        </div>
        <Selecteur
          label="Animations du réacteur"
          valeur={r.animations}
          options={[
            { valeur: "legeres", libelle: "Légères — recommandé" },
            { valeur: "completes", libelle: "Complètes — lueurs, 60 images/s" },
            { valeur: "aucunes", libelle: "Désactivées — le plus rapide" },
          ]}
          onChange={(v) => r.maj({ animations: v as typeof r.animations })}
          aide="La carte graphique est partagée avec le modèle d'IA. Les animations complètes peuvent rendre Jarvis beaucoup plus lent quand la VRAM est presque pleine (jeux, LDPlayer, Wallpaper Engine…)."
        />
        <Bouton
          variante="danger"
          className="mt-4"
          icone={<RotateCcw className="size-4" />}
          onClick={() => {
            r.maj({ ...DEFAUT, vue: "reglages" });
            micro.setGain(DEFAUT.gain);
            toast("Réglages remis par défaut.");
          }}
        >
          Réglages par défaut
        </Bouton>
      </Panneau>
      <Panneau titre="Raccourcis clavier">
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
      <EnTetePage titre="Réglages" sousTitre="Micro, voix et cerveau de Jarvis. Les réglages audio sont propres à ce navigateur." />
      <Onglets<Onglet>
        actif={onglet}
        onChange={setOnglet}
        onglets={[
          { id: "micro", libelle: "Micro", icone: <Mic /> },
          { id: "voix", libelle: "Voix", icone: <Volume2 /> },
          { id: "cerveau", libelle: "Cerveau", icone: <Brain /> },
          { id: "application", libelle: "Application", icone: <AppWindow /> },
          { id: "interface", libelle: "Interface", icone: <Monitor /> },
        ]}
      />
      <div className={cx("mt-6")}>
        {onglet === "micro" && <OngletMicro />}
        {onglet === "voix" && <OngletVoix />}
        {onglet === "cerveau" && <OngletCerveau />}
        {onglet === "application" && <OngletApplication />}
        {onglet === "interface" && <OngletInterface />}
      </div>
    </div>
  );
}
