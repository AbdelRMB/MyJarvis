import { Download, Mic, Send, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Bouton, Champ } from "../../../src/components/ui";
import { t } from "../../../src/lib/i18n";
import { ORDINATEURS } from "../moteur/appareils";
import { useDonnees } from "../moteur/donnees";
import { chargerPartages, envoyerAudio, horodatage } from "../moteur/partages";
import { erreurToast, Section, toast } from "../ui";

type Phase = "pret" | "enregistre" | "envoi" | "echec";

/** Format accepté par le navigateur du téléphone (Android : webm/opus ; iPhone : mp4/aac). */
function formatAudio() {
  for (const f of ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg;codecs=opus"]) if (MediaRecorder.isTypeSupported?.(f)) return f;
  return "";
}

/**
 * Le téléphone comme micro : il enregistre la pièce (cours, réunion, discussion), puis envoie l'enregistrement,
 * chiffré, à un de tes ordinateurs qui le transcrit (voix reconnues, résumé). Rien n'est perdu si l'envoi
 * échoue : l'enregistrement reste sur l'écran pour réessayer ou le télécharger.
 */
export function Enregistreur() {
  const ordis = useDonnees((d) => d.appareils).filter((a) => !a.moi && ORDINATEURS.includes(a.plateforme));
  const [phase, setPhase] = useState<Phase>("pret");
  const [secondes, setSecondes] = useState(0);
  const [titre, setTitre] = useState("");
  const [sur, setSur] = useState("");
  const [progres, setProgres] = useState("");
  const [erreur, setErreur] = useState("");
  const audio = useRef<Blob | null>(null);
  const enregistreur = useRef<MediaRecorder | null>(null);
  const morceaux = useRef<Blob[]>([]);
  const veille = useRef<{ release: () => Promise<void> } | null>(null);
  const debut = useRef(0);
  const choisi = ordis.find((a) => a.id === sur) ?? ordis.find((a) => a.en_ligne && a.accepte) ?? ordis[0];

  useEffect(() => {
    if (phase !== "enregistre") return;
    const i = setInterval(() => setSecondes((Date.now() - debut.current) / 1000), 500);
    // quitter la page pendant l'enregistrement le perdrait : le navigateur demande confirmation
    const avant = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", avant);
    return () => (clearInterval(i), window.removeEventListener("beforeunload", avant));
  }, [phase]);

  const commencer = async () => {
    try {
      // pas de suppression de bruit agressive : elle efface les voix lointaines (cours, réunion autour d'une table)
      const flux = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: true } });
      const format = formatAudio();
      const r = new MediaRecorder(flux, { ...(format ? { mimeType: format } : {}), audioBitsPerSecond: 32_000 });
      morceaux.current = [];
      r.ondataavailable = (e) => e.data.size && morceaux.current.push(e.data);
      r.onstop = () => {
        flux.getTracks().forEach((p) => p.stop());
        audio.current = new Blob(morceaux.current, { type: r.mimeType || format || "audio/webm" });
        void veille.current?.release().catch(() => {});
        veille.current = null;
        void envoyer();
      };
      r.start(5000);
      enregistreur.current = r;
      debut.current = Date.now();
      setSecondes(0);
      setErreur("");
      setPhase("enregistre");
      // l'écran reste allumé : un téléphone verrouillé coupe le micro de l'appli web
      veille.current = await (navigator as any).wakeLock?.request("screen").catch(() => null);
    } catch (e) {
      erreurToast(new Error(t("Micro inaccessible : autorise le micro pour Wesley dans le navigateur. ({e})", { e: (e as Error).message })));
    }
  };

  const envoyer = async () => {
    if (!audio.current || !choisi) {
      setErreur(t("Aucun ordinateur pour transcrire : allume Wesley sur ton Mac ou ton PC, puis réessaie."));
      setPhase("echec");
      return;
    }
    setPhase("envoi");
    setErreur("");
    try {
      const nom = titre.trim() || t("Enregistrement du {date}", { date: new Date().toLocaleString([], { dateStyle: "short", timeStyle: "short" }) });
      const msg = await envoyerAudio(choisi.id, audio.current, { titre: nom }, (fait, total) =>
        setProgres(total > 1 ? t("Envoi à {appareil}… {p} %", { appareil: choisi.nom, p: Math.round((fait / total) * 100) }) : t("Envoi à {appareil}…", { appareil: choisi.nom })),
      );
      toast(msg);
      audio.current = null;
      setTitre("");
      setPhase("pret");
      void chargerPartages();
    } catch (e) {
      setErreur((e as Error).message);
      setPhase("echec");
    } finally {
      setProgres("");
    }
  };

  const telecharger = () => {
    if (!audio.current) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(audio.current);
    a.download = `${titre.trim() || "enregistrement"}.${audio.current.type.includes("mp4") ? "m4a" : "webm"}`;
    a.click();
  };

  if (typeof MediaRecorder === "undefined") return null;
  return (
    <Section titre={t("Enregistrer avec le téléphone")}>
      <div className="space-y-2 p-3">
        {phase === "enregistre" ? (
          <>
            <div className="flex items-center gap-3">
              <span className="size-3 animate-pulse rounded-full bg-rouge shadow-[0_0_8px] shadow-rouge" />
              <span className="font-mono text-2xl">{horodatage(secondes)}</span>
            </div>
            <p className="text-[12px] text-doux">{t("Garde Wesley ouvert, écran allumé, jusqu'à la fin.")}</p>
            <Bouton variante="danger" className="w-full" icone={<Square className="size-4" />} onClick={() => enregistreur.current?.stop()}>
              {t("Arrêter et transcrire")}
            </Bouton>
          </>
        ) : (
          <>
            <Champ value={titre} onChange={(e) => setTitre(e.target.value)} placeholder={t("Titre (facultatif) : Cours de PHP, Réunion…")} />
            {ordis.length > 1 && (
              <select value={choisi?.id ?? ""} onChange={(e) => setSur(e.target.value)} className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3">
                {ordis.map((a) => (
                  <option key={a.id} value={a.id}>
                    {t("Transcrit par {appareil}", { appareil: a.nom })} {a.en_ligne ? "" : `(${t("hors ligne")})`}
                  </option>
                ))}
              </select>
            )}
            {phase === "envoi" ? (
              <p className="text-[13px] text-doux">{progres || t("Envoi…")}</p>
            ) : phase === "echec" ? (
              <>
                <p className="text-[12px] text-rouge">{erreur}</p>
                <div className="grid grid-cols-2 gap-2">
                  <Bouton variante="primaire" icone={<Send className="size-4" />} onClick={() => void envoyer()}>
                    {t("Réessayer")}
                  </Bouton>
                  <Bouton icone={<Download className="size-4" />} onClick={telecharger}>
                    {t("Télécharger")}
                  </Bouton>
                </div>
              </>
            ) : (
              <Bouton variante="primaire" className="w-full" icone={<Mic className="size-4" />} onClick={commencer}>
                {t("Enregistrer")}
              </Bouton>
            )}
            <p className="text-[11px] text-tres-doux">
              {t("Le téléphone enregistre, puis envoie le son (chiffré) à ton ordinateur qui le transcrit et reconnaît les voix.")}
            </p>
          </>
        )}
      </div>
    </Section>
  );
}
