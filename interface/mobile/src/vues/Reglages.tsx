import { Download, KeyRound, LogOut, Trash2, Volume2 } from "lucide-react";
import { useState } from "react";
import { Bouton, Champ, Curseur, Interrupteur, Selecteur } from "../../../src/components/ui";
import { changerLangue, LANGUE, t } from "../../../src/lib/i18n";
import { cerveauActif } from "../moteur/cerveau";
import { api, cleApi, deconnecter, modifierCoffre, supprimerCompte, VERSION_MOBILE } from "../moteur/compte";
import { modifierProfil, useDonnees } from "../moteur/donnees";
import { CHOIX_CERVEAUX, CLAUDE_DEFAUT, CLAUDE_MODELES, PAR_ID } from "../moteur/fournisseurs";
import { autoriserNotifications } from "../moteur/rappels";
import { majReglagesTel, nomParDefaut, reglagesTel, session, type ReglagesTel } from "../moteur/stockage";
import { presence } from "../moteur/synchro";
import { parler } from "../moteur/voix";
import { allerA, Entete, erreurToast, Feuille, Section, toast } from "../ui";

const ENV_CLAUDE = "ANTHROPIC_API_KEY";

export function Reglages({ onDeconnecte }: { onDeconnecte: () => void }) {
  const [r, setR] = useState(reglagesTel());
  const profil = useDonnees((d) => d.profil);
  const appareils = useDonnees((d) => d.appareils).filter((a) => !a.moi && a.plateforme !== "telephone");
  const [cle, setCle] = useState("");
  const [suppression, setSuppression] = useState(false);
  const [, forcer] = useState(0);
  const maj = (p: Partial<ReglagesTel>) => {
    majReglagesTel(p);
    setR(reglagesTel());
    if ("nom" in p || "accepte" in p || "confirmation" in p) void presence();
  };

  const idCompte = String(profil.cerveau || "claude");
  const id = r.cerveau || idCompte;
  const env = id === "claude" ? ENV_CLAUDE : PAR_ID[id]?.env;
  const actif = cerveauActif();

  async function enregistrerCle() {
    if (!env) return;
    try {
      await modifierCoffre((c) => void (c[env] = cle.trim()));
      setCle("");
      forcer((x) => x + 1);
      toast(t("Clé enregistrée dans ton compte (chiffrée) : tes ordinateurs l'ont aussi."));
    } catch (e) {
      erreurToast(e);
    }
  }

  async function exporter() {
    try {
      const d = await api("GET", "/moi/export");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(d, null, 1)], { type: "application/json" }));
      a.download = `wesley-mes-donnees-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
    } catch (e) {
      erreurToast(e);
    }
  }

  return (
    <div className="pb-8">
      <Entete titre={t("Réglages")} retour={() => allerA("plus")} />

      <Section titre={t("Cerveau")}>
        <div className="px-3 pb-2">
          <Selecteur
            label={t("IA utilisée sur ce téléphone")}
            valeur={r.cerveau}
            onChange={(v) => maj({ cerveau: v })}
            options={[
              { valeur: "", libelle: t("Comme mes ordinateurs ({nom})", { nom: CHOIX_CERVEAUX.find((c) => c.id === idCompte)?.nom || idCompte }) },
              ...CHOIX_CERVEAUX.map((c) => ({ valeur: c.id, libelle: c.nom })),
            ]}
            aide={t("En ce moment : {nom}", { nom: actif.nom + (actif.raison ? ` — ${actif.raison}` : "") })}
          />
          {id === "claude" && (
            <Selecteur
              label={t("Modèle Claude (commun à tous tes appareils)")}
              valeur={String(profil.claude_modele || CLAUDE_DEFAUT)}
              onChange={(v) => modifierProfil({ claude_modele: v }).catch(erreurToast)}
              options={Object.entries(CLAUDE_MODELES).map(([v, l]) => ({ valeur: v, libelle: l }))}
            />
          )}
          {env && (
            <div className="py-2">
              <div className="mb-1.5 flex items-center gap-2 text-sm">
                <KeyRound className="size-4 text-hud" />
                {t("Clé API")} {cleApi(env) ? <span className="text-vert">· {t("enregistrée")}</span> : <span className="text-ambre">· {t("manquante")}</span>}
              </div>
              <div className="flex gap-2">
                <Champ type="password" value={cle} onChange={(e) => setCle(e.target.value)} placeholder={cleApi(env) ? "••••••••" : t("Colle ta clé")} autoComplete="off" />
                <Bouton variante="contour" disabled={!cle.trim()} onClick={enregistrerCle}>
                  OK
                </Bouton>
              </div>
              <p className="mt-1 text-[12px] text-doux">{id === "claude" ? t("platform.claude.com › API keys (l'abonnement Claude Pro n'en inclut pas).") : PAR_ID[id]?.detail}</p>
            </div>
          )}
          {id === "ollama" && (
            <label className="block py-2 text-sm">
              {t("Adresse HTTPS d'Ollama (facultatif)")}
              <Champ value={r.ollama_url} onChange={(e) => maj({ ollama_url: e.target.value.trim() })} placeholder="https://ollama.mon-domaine.fr" />
              <span className="mt-1 block text-[12px] text-doux">{t("Sans adresse HTTPS, ton ordinateur traite les demandes (relais).")}</span>
            </label>
          )}
          <Selecteur
            label={t("Ordinateur de relais")}
            valeur={r.relais}
            onChange={(v) => maj({ relais: v })}
            options={[{ valeur: "", libelle: t("Le premier allumé") }, ...appareils.map((a) => ({ valeur: a.id, libelle: a.nom }))]}
            aide={t("Il exécute ce que le téléphone ne peut pas faire (applis, fichiers, mails, SSH…).")}
          />
        </div>
      </Section>

      <Section titre={t("Voix")}>
        <div className="px-3">
          <Interrupteur actif={r.voix} onChange={(v) => maj({ voix: v })} label={t("Réponses à voix haute")} />
          <Interrupteur actif={r.suivie} onChange={(v) => maj({ suivie: v })} label={t("Conversation suivie")} aide={t("Après une réponse à l'oral, Wesley réécoute la suite sans retoucher le micro.")} />
          <Curseur label={t("Vitesse de la voix")} valeur={r.vitesse} affichage={`${r.vitesse.toFixed(2)}×`} min={0.7} max={1.6} pas={0.05} onChange={(v) => maj({ vitesse: v })} />
          <Bouton variante="fantome" taille="sm" icone={<Volume2 className="size-4" />} className="mb-2" onClick={() => void parler(t("Bonjour, je suis Wesley."))}>
            {t("Essayer")}
          </Bouton>
        </div>
      </Section>

      <Section titre={t("Ce téléphone")}>
        <div className="px-3">
          <label className="block py-2 text-sm">
            {t("Nom dans « Mes appareils »")}
            <Champ value={r.nom} onChange={(e) => maj({ nom: e.target.value })} placeholder={nomParDefaut()} />
          </label>
          <Interrupteur actif={r.accepte} onChange={(v) => maj({ accepte: v })} label={t("Accepter les ordres de mes autres appareils")} aide={t("« Sur mon téléphone, ajoute… » depuis ton ordinateur.")} />
          {r.accepte && <Interrupteur actif={r.confirmation} onChange={(v) => maj({ confirmation: v })} label={t("Me demander confirmation avant")} />}
          <Bouton
            variante="fantome"
            taille="sm"
            className="mb-2"
            onClick={async () => toast((await autoriserNotifications()) ? t("Notifications activées.") : t("Notifications refusées : autorise-les dans les réglages du navigateur."))}
          >
            {t("Activer les notifications (rappels)")}
          </Bouton>
          <Selecteur
            label={t("Langue")}
            valeur={LANGUE}
            onChange={(v) => {
              changerLangue(v as "fr" | "en");
              location.reload();
            }}
            options={[
              { valeur: "fr", libelle: "Français" },
              { valeur: "en", libelle: "English" },
            ]}
          />
        </div>
      </Section>

      <Section titre={t("Compte")}>
        <div className="space-y-2 px-3 py-3">
          <p className="text-sm">
            {session()?.prenom} · <span className="text-doux">{session()?.email}</span>
          </p>
          <Bouton variante="contour" className="w-full" icone={<Download className="size-4" />} onClick={exporter}>
            {t("Télécharger mes données")}
          </Bouton>
          <Bouton
            variante="contour"
            className="w-full"
            icone={<LogOut className="size-4" />}
            onClick={async () => {
              if (!confirm(t("Te déconnecter de Wesley sur ce téléphone ?"))) return;
              await deconnecter();
              onDeconnecte();
            }}
          >
            {t("Se déconnecter")}
          </Bouton>
          <Bouton variante="danger" className="w-full" icone={<Trash2 className="size-4" />} onClick={() => setSuppression(true)}>
            {t("Supprimer mon compte")}
          </Bouton>
        </div>
      </Section>
      <p className="px-4 pt-4 text-[12px] text-tres-doux">
        Wesley mobile {VERSION_MOBILE} ·{" "}
        <a className="underline" href="/mobile/confidentialite.html" target="_blank">
          {t("Confidentialité")}
        </a>{" "}
        ·{" "}
        <a className="underline" href="/mobile/mentions-legales.html" target="_blank">
          {t("Mentions légales")}
        </a>
        <br />
        {t("Astuce : « Ajouter à l'écran d'accueil » (menu du navigateur) pour l'ouvrir comme une appli.")}
      </p>
      {suppression && <Suppression onFermer={() => setSuppression(false)} onSupprime={onDeconnecte} />}
    </div>
  );
}

function Suppression({ onFermer, onSupprime }: { onFermer: () => void; onSupprime: () => void }) {
  const [mdp, setMdp] = useState("");
  const [charge, setCharge] = useState(false);
  return (
    <Feuille titre={t("Supprimer mon compte")} onFermer={onFermer}>
      <p className="text-sm text-doux">{t("Tout est effacé définitivement : mémoire, historique, réglages, coffre, sur tous tes appareils. Tape ton mot de passe pour confirmer.")}</p>
      <Champ type="password" className="mt-3" value={mdp} onChange={(e) => setMdp(e.target.value)} placeholder={t("Mot de passe")} />
      <Bouton
        variante="danger"
        className="mt-3 w-full"
        chargement={charge}
        disabled={!mdp}
        onClick={async () => {
          setCharge(true);
          try {
            await supprimerCompte(mdp);
            onSupprime();
          } catch (e) {
            erreurToast(e);
          } finally {
            setCharge(false);
          }
        }}
      >
        {t("Supprimer définitivement")}
      </Bouton>
    </Feuille>
  );
}
