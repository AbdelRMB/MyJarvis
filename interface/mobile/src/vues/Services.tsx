import { GitBranch, Plug, Plus } from "lucide-react";
import { useState } from "react";
import { Badge, Bouton, Champ } from "../../../src/components/ui";
import { t } from "../../../src/lib/i18n";
import { envoyer } from "../assistant";
import { modifierCoffre, secret } from "../moteur/compte";
import { modifierConnecteurs, nouvelId, useDonnees } from "../moteur/donnees";
import { etiquetteConnecteur } from "../moteur/outils";
import { allerA, Entete, erreurToast, Feuille, Ligne, Section, toast } from "../ui";

/**
 * Services connectés du compte. Ils tournent sur les ordinateurs (mails IMAP, SSH, navigateur, MCP…) : le
 * téléphone les utilise en passant par eux. GitHub fonctionne directement depuis le téléphone.
 */
export function Services() {
  const connecteurs = useDonnees((d) => d.connecteurs);
  const [github, setGithub] = useState(false);
  const entrees = Object.entries(connecteurs);
  return (
    <div>
      <Entete
        titre={t("Services connectés")}
        retour={() => allerA("plus")}
        actions={
          <button className="grid size-9 place-items-center text-hud" onClick={() => setGithub(true)} aria-label={t("Ajouter GitHub")}>
            <Plus className="size-5" />
          </button>
        }
      />
      <Section titre={t("Tes services · {n}", { n: entrees.length })}>
        {entrees.map(([cid, c]) => {
          const direct = c.type === "github" && !!secret(`${cid}:jeton`);
          return (
            <Ligne
              key={cid}
              onClick={() => {
                allerA("assistant");
                void envoyer(t("Teste mon service « {nom} » et dis-moi s'il marche.", { nom: etiquetteConnecteur(c) }));
              }}
            >
              {c.type === "github" ? <GitBranch className="size-5 text-hud" /> : <Plug className="size-5 text-hud" />}
              <div className="min-w-0 flex-1">
                <div className="truncate text-[15px]">{etiquetteConnecteur(c)}</div>
                <div className="text-[12px] text-doux">{direct ? t("direct depuis le téléphone") : t("via tes ordinateurs")}</div>
              </div>
              {c.actif === false && <Badge ton="doux">{t("désactivé")}</Badge>}
            </Ligne>
          );
        })}
        {!entrees.length && <p className="px-3 py-4 text-[13px] text-doux">{t("Aucun service. Ajoute tes boîtes mail, serveurs SSH… dans l'appli de bureau (onglet Connecteurs).")}</p>}
      </Section>
      <p className="px-4 pt-4 text-[12px] leading-relaxed text-tres-doux">
        {t(
          "Mails, agenda, SSH, navigateur de Wesley, sites appris, WhatsApp et serveurs MCP tournent sur tes ordinateurs : demande-les simplement à Wesley (« lis mes derniers mails »), il passe par l'ordinateur allumé. Touche un service pour le tester.",
        )}
      </p>
      {github && <AjoutGitHub onFermer={() => setGithub(false)} />}
    </div>
  );
}

function AjoutGitHub({ onFermer }: { onFermer: () => void }) {
  const [jeton, setJeton] = useState("");
  const [charge, setCharge] = useState(false);
  async function enregistrer() {
    setCharge(true);
    try {
      const r = await fetch("https://api.github.com/user", { headers: { Authorization: `Bearer ${jeton.trim()}` } });
      if (!r.ok) throw new Error(t("Jeton GitHub refusé ({s}).", { s: r.status }));
      const login = (await r.json()).login as string;
      const existant = Object.entries(useDonnees.getState().connecteurs).find(([, c]) => c.type === "github");
      const cid = existant?.[0] || `github_${nouvelId(6)}`;
      await modifierCoffre((c) => void (c.trousseau![`${cid}:jeton`] = jeton.trim()));
      await modifierConnecteurs((c) => void (c[cid] = { ...(c[cid] || {}), type: "github", actif: true, conf: { ...((c[cid]?.conf as object) || {}), nom: login } }));
      toast(t("GitHub connecté : {login}", { login }));
      onFermer();
    } catch (e) {
      erreurToast(e);
    } finally {
      setCharge(false);
    }
  }
  return (
    <Feuille titre="GitHub" onFermer={onFermer}>
      <p className="mb-3 text-[13px] text-doux">
        {t("github.com › Settings › Developer settings › Personal access tokens › Fine-grained tokens. Le jeton est chiffré dans ton compte : tes ordinateurs l'utilisent aussi.")}
      </p>
      <Champ type="password" value={jeton} onChange={(e) => setJeton(e.target.value)} placeholder="github_pat_…" autoComplete="off" />
      <Bouton variante="primaire" className="mt-3 w-full" chargement={charge} disabled={!jeton.trim()} onClick={enregistrer}>
        {t("Connecter")}
      </Bouton>
    </Feuille>
  );
}
