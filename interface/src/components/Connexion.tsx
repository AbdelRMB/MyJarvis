import { LANGUE, t } from "../lib/i18n";
import { choisirLangue } from "../views/Reglages";
import { Cloud, HardDrive, LogIn, UserPlus } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { useJarvis } from "../stores/jarvis";
import { toast } from "../stores/toasts";
import { Bouton, Champ } from "./ui";

export type Compte = { connecte: boolean; mode: "" | "local" | "en_ligne"; email: string; prenom: string; serveur: string; machine: string; admin?: boolean };
type Reponse = Compte & { import?: { faits: number; lignes: number; erreur?: string } | null };

/** Écran affiché tant que personne n'est connecté : chaque utilisateur a sa mémoire, sa clé, ses connecteurs. */
export function Connexion({ onConnecte, choix }: { onConnecte: (c: Compte) => void; choix: boolean }) {
  const [etape, setEtape] = useState<"choix" | "compte">(choix ? "choix" : "compte");
  const [mode, setMode] = useState<"connexion" | "inscription">(choix ? "inscription" : "connexion");
  const [email, setEmail] = useState("");
  const [mdp, setMdp] = useState("");
  const [mdp2, setMdp2] = useState("");
  const [prenom, setPrenom] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const inscription = mode === "inscription";

  const valider = async (e: React.FormEvent) => {
    e.preventDefault();
    if (inscription && mdp !== mdp2) return toast(t("Les deux mots de passe ne sont pas identiques."), "erreur");
    setEnvoi(true);
    try {
      const r = await api<Reponse>(`/api/compte/${mode}`, { method: "POST", json: { email, mot_de_passe: mdp, prenom } });
      if (r.import && !r.import.erreur && (r.import.faits || r.import.lignes))
        toast(`Mémoire de cet appareil ajoutée à ton compte : ${r.import.faits} souvenir(s), ${r.import.lignes} ligne(s) d'historique.`, "succes");
      else if (r.import?.erreur) toast(`Import de la mémoire de cet appareil : ${r.import.erreur}`, "erreur");
      useJarvis.setState((s) => ({ session: s.session ? { ...s.session, nom: r.prenom || s.session.nom } : s.session }));
      onConnecte(r);
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi(false);
    }
  };

  const local = async () => {
    try {
      onConnecte(await api<Compte>("/api/compte/local", { method: "POST", json: {} }));
    } catch (x) {
      toast((x as Error).message, "erreur");
    }
  };

  if (etape === "choix")
    return (
      <div className="grille-hud fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-fond p-4">
        <div className="w-[min(760px,100%)]">
          <div className="mb-4 flex justify-center gap-1 text-[12px]">
            {(["fr", "en"] as const).map((l) => (
              <button
                key={l}
                onClick={() => l !== LANGUE && choisirLangue(l)}
                className={cx("rounded px-2.5 py-1", LANGUE === l ? "bg-hud/15 text-hud" : "text-doux hover:text-texte")}
              >
                {l === "fr" ? "Français" : "English"}
              </button>
            ))}
          </div>
          <h1 className="mb-2 text-center font-display text-2xl font-black tracking-[0.35em] text-hud">{t("J.A.R.V.I.S.")}</h1>
          <p className="mb-6 text-center text-sm text-doux">{t("Où veux-tu garder ta mémoire, tes réglages et tes clés ?")}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <button
              onClick={() => setEtape("compte")}
              className="rounded-xl border border-hud/50 bg-surface-2/80 p-5 text-left transition-colors hover:border-hud hover:bg-hud/5"
            >
              <Cloud className="mb-3 size-7 text-hud" />
              <div className="font-semibold">{t("En ligne, avec un compte")}</div>
              <p className="mt-2 text-[13px] leading-relaxed text-doux">
                {t("Ta mémoire, ton historique, tes connecteurs et tes clés te suivent sur tous tes appareils : connecte-toi sur un autre ordinateur et Jarvis te connaît déjà. Tes clés et mots de passe sont chiffrés avec ton mot de passe : le serveur ne peut pas les lire.")}
              </p>
            </button>
            <button
              onClick={local}
              className="rounded-xl border border-ligne-forte bg-surface-2/80 p-5 text-left transition-colors hover:border-hud hover:bg-hud/5"
            >
              <HardDrive className="mb-3 size-7 text-hud" />
              <div className="font-semibold">{t("En local, sur cet appareil")}</div>
              <p className="mt-2 text-[13px] leading-relaxed text-doux">
                {t("Pas de compte, rien n'est envoyé à un serveur : tout reste sur cet ordinateur. Mais aucune récupération ailleurs : sur un autre appareil, ce sera un nouveau Jarvis qui ne sait rien de toi. Tu pourras passer en ligne plus tard (Réglages › Application) et tout envoyer dans ton compte.")}
              </p>
            </button>
          </div>
        </div>
      </div>
    );

  return (
    <div className="grille-hud fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-fond p-4">
      <form onSubmit={valider} className="w-[min(420px,100%)] rounded-xl border border-ligne bg-surface-2/80 p-6 shadow-glow">
        <h1 className="mb-1 text-center font-display text-2xl font-black tracking-[0.35em] text-hud">{t("J.A.R.V.I.S.")}</h1>
        <p className="mb-6 text-center text-sm text-doux">
          {inscription ? "Crée ton compte : ta mémoire te suit sur tous tes appareils." : "Connecte-toi pour retrouver ta mémoire."}
        </p>
        <div className="mb-5 grid grid-cols-2 gap-1 rounded-md border border-ligne p-1 text-sm">
          {(["connexion", "inscription"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={cx("rounded px-3 py-1.5", mode === m ? "bg-hud/15 text-hud" : "text-doux hover:text-texte")}
            >
              {m === "connexion" ? "Se connecter" : "Créer un compte"}
            </button>
          ))}
        </div>
        <div className="space-y-3">
          {inscription && <Champ placeholder={t("Ton prénom")} value={prenom} onChange={(e) => setPrenom(e.target.value)} autoComplete="given-name" />}
          <Champ type="email" placeholder={t("Adresse e-mail")} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
          <Champ
            type="password"
            placeholder={t("Mot de passe")}
            value={mdp}
            onChange={(e) => setMdp(e.target.value)}
            autoComplete={inscription ? "new-password" : "current-password"}
            minLength={inscription ? 8 : undefined}
            required
          />
          {inscription && (
            <Champ type="password" placeholder={t("Confirme le mot de passe")} value={mdp2} onChange={(e) => setMdp2(e.target.value)} autoComplete="new-password" required />
          )}
        </div>
        {inscription && (
          <p className="mt-3 text-[12px] leading-relaxed text-doux">
            {t("Ton mot de passe ne quitte jamais cet appareil : il chiffre ta clé API et les mots de passe de tes connecteurs avant l'envoi, le serveur ne peut pas les lire. Choisis-le bien : la récupération d'un mot de passe oublié arrive dans une prochaine version.")}
          </p>
        )}
        <Bouton type="submit" variante="primaire" className="mt-5 w-full justify-center" chargement={envoi} icone={inscription ? <UserPlus /> : <LogIn />}>
          {inscription ? "Créer mon compte" : "Se connecter"}
        </Bouton>
        {envoi && <p className="mt-3 text-center text-[12px] text-doux">{t("Chiffrement et récupération de ta mémoire…")}</p>}
        {choix && (
          <button type="button" onClick={() => setEtape("choix")} className="mt-4 w-full text-center text-[12px] text-doux hover:text-texte">
            {t("← Utiliser Jarvis en local plutôt")}
          </button>
        )}
      </form>
    </div>
  );
}
