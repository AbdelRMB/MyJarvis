import { useState } from "react";
import { Bouton, Champ } from "../../../src/components/ui";
import { changerLangue, LANGUE, t } from "../../../src/lib/i18n";
import { accepterPolitique, connecter, inscrire, POLITIQUE } from "../moteur/compte";
import { dernierEmail, type Session } from "../moteur/stockage";

/** Connexion ou création du compte Wesley (le même que sur les ordinateurs). */
export function Connexion({ onConnecte }: { onConnecte: (s: Session) => void }) {
  const [mode, setMode] = useState<"connexion" | "inscription">(dernierEmail() ? "connexion" : "inscription");
  const [email, setEmail] = useState(dernierEmail());
  const [mdp, setMdp] = useState("");
  const [prenom, setPrenom] = useState("");
  const [accord, setAccord] = useState(false);
  const [erreur, setErreur] = useState("");
  const [charge, setCharge] = useState(false);

  async function valider(e: React.FormEvent) {
    e.preventDefault();
    setErreur("");
    setCharge(true);
    await new Promise((r) => setTimeout(r, 30)); // laisse l'écran se mettre à jour (le calcul de la clé prend ~1 s)
    try {
      onConnecte(mode === "connexion" ? await connecter(email, mdp) : await inscrire(email, mdp, prenom, accord));
    } catch (x) {
      setErreur((x as Error).message);
    } finally {
      setCharge(false);
      setMdp("");
    }
  }

  return (
    <div className="grille-hud zone-sure flex min-h-dvh flex-col justify-center px-5 py-8">
      <div className="mx-auto w-full max-w-sm">
        <h1 className="titre-hud text-center text-2xl font-black text-hud">Wesley</h1>
        <p className="mt-2 text-center text-sm text-doux">{t("Ton assistant, aussi sur ton téléphone.")}</p>
        <div className="mt-6 grid grid-cols-2 rounded-md border border-ligne-forte p-0.5 text-sm">
          {(["connexion", "inscription"] as const).map((m) => (
            <button key={m} type="button" onClick={() => setMode(m)} className={mode === m ? "rounded bg-hud/15 py-2 text-hud" : "py-2 text-doux"}>
              {m === "connexion" ? t("Se connecter") : t("Créer un compte")}
            </button>
          ))}
        </div>
        <form onSubmit={valider} className="mt-4 space-y-2.5">
          {mode === "inscription" && <Champ value={prenom} onChange={(e) => setPrenom(e.target.value)} placeholder={t("Prénom")} autoComplete="given-name" required />}
          <Champ type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("Adresse e-mail")} autoComplete="email" required />
          <Champ
            type="password"
            value={mdp}
            onChange={(e) => setMdp(e.target.value)}
            placeholder={t("Mot de passe")}
            autoComplete={mode === "connexion" ? "current-password" : "new-password"}
            minLength={mode === "inscription" ? 8 : undefined}
            required
          />
          {mode === "inscription" && (
            <label className="flex items-start gap-2 py-1 text-[13px] text-doux">
              <input type="checkbox" checked={accord} onChange={(e) => setAccord(e.target.checked)} className="mt-0.5 size-4 accent-[#3ce8ff]" />
              <span>
                {t("J'accepte la")}{" "}
                <a href="/mobile/confidentialite.html" target="_blank" className="text-hud underline">
                  {t("politique de confidentialité")}
                </a>
              </span>
            </label>
          )}
          <Bouton type="submit" variante="primaire" className="w-full" chargement={charge}>
            {mode === "connexion" ? t("Se connecter") : t("Créer mon compte")}
          </Bouton>
        </form>
        {erreur && <p className="mt-3 text-center text-sm text-rouge">{erreur}</p>}
        <p className="mt-5 text-center text-[12px] leading-relaxed text-tres-doux">
          {t("Ton mot de passe ne quitte pas ce téléphone : il sert à chiffrer tes clés et tes ordres, que seuls tes appareils peuvent lire.")}
        </p>
        <button
          className="mx-auto mt-4 block text-[13px] text-doux underline"
          onClick={() => {
            changerLangue(LANGUE === "fr" ? "en" : "fr");
            location.reload();
          }}
        >
          {LANGUE === "fr" ? "English" : "Français"}
        </button>
      </div>
    </div>
  );
}

/** Nouvelle politique de confidentialité à accepter (comme sur le bureau). */
export function AccordPolitique({ onAccepte }: { onAccepte: () => void }) {
  const [charge, setCharge] = useState(false);
  return (
    <div className="zone-sure flex min-h-dvh flex-col justify-center px-5">
      <div className="mx-auto max-w-sm text-center">
        <h1 className="titre-hud text-lg font-bold text-hud">{t("Confidentialité")}</h1>
        <p className="mt-3 text-sm text-doux">
          {t("La politique de confidentialité de Wesley a changé ({v}). Lis-la et accepte-la pour continuer.", { v: POLITIQUE })}
        </p>
        <a href="/mobile/confidentialite.html" target="_blank" className="mt-3 block text-sm text-hud underline">
          {t("Lire la politique de confidentialité")}
        </a>
        <Bouton
          variante="primaire"
          className="mt-5 w-full"
          chargement={charge}
          onClick={async () => {
            setCharge(true);
            try {
              await accepterPolitique();
              onAccepte();
            } finally {
              setCharge(false);
            }
          }}
        >
          {t("J'accepte")}
        </Bouton>
      </div>
    </div>
  );
}
