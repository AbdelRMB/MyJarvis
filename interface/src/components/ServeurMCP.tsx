import { Copy, KeyRound, Network } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import { toast } from "../stores/toasts";
import { Bouton, Interrupteur, Panneau, Pastille } from "./ui";

type EtatMCP = { actif: boolean; en_marche: boolean; url: string; cle: string; erreur: string; outils: string[]; claude_code: string; claude_desktop: string };

function BlocACopier({ titre, texte }: { titre: string; texte: string }) {
  return (
    <div className="mt-3">
      <div className="mb-1 flex items-center justify-between text-[12px] text-doux">
        <span>{titre}</span>
        <button
          onClick={() => navigator.clipboard.writeText(texte).then(() => toast(t("Copié."), "succes"))}
          className="flex items-center gap-1 text-hud hover:underline"
        >
          <Copy className="size-3" />
          {t("Copier")}
        </button>
      </div>
      <pre className="max-h-40 overflow-auto rounded-md border border-ligne bg-fond/60 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all">{texte}</pre>
    </div>
  );
}

/** Wesley comme serveur MCP : Claude Desktop, Claude Code… interrogent sa mémoire, ses transcriptions, tes documents. */
export function PanneauServeurMCP() {
  const [e, setE] = useState<EtatMCP | null>(null);
  const [envoi, setEnvoi] = useState(false);
  useEffect(() => {
    api<EtatMCP>("/api/mcp").then(setE).catch(() => {});
  }, []);
  const regler = async (corps: object) => {
    setEnvoi(true);
    try {
      const n = await api<EtatMCP>("/api/mcp", { method: "POST", json: corps });
      setE(n);
      if (n.erreur) toast(n.erreur, "erreur");
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi(false);
    }
  };
  if (!e) return null;
  return (
    <Panneau titre={t("Serveur MCP (Claude Desktop, Claude Code…)")} icone={<Network />}>
      <Interrupteur
        label={t("Partager Wesley avec mes autres assistants")}
        aide={t("Claude Desktop, Claude Code ou tout client MCP peuvent chercher dans ta mémoire, tes transcriptions, tes documents et ta liste À faire, et y ajouter un souvenir ou une tâche. Seulement sur cet ordinateur, avec une clé. Jamais la souris, le clavier, tes fichiers ni tes commandes.")}
        actif={e.actif}
        onChange={(v) => regler({ actif: v })}
      />
      {e.actif && (
        <>
          <p className="mt-2 flex items-center gap-2 text-[13px]">
            <Pastille ok={e.en_marche}>{e.en_marche ? t("En marche") : t("Arrêté")}</Pastille>
            <span className="font-mono text-[12px] text-doux">{e.url}</span>
          </p>
          {e.erreur && <p className="mt-1 text-[12px] text-rouge">{e.erreur}</p>}
          <BlocACopier titre={t("Claude Code : colle cette commande dans un terminal")} texte={e.claude_code} />
          <BlocACopier titre={t("Claude Desktop : ajoute ceci à claude_desktop_config.json (Node.js requis)")} texte={e.claude_desktop} />
          <p className="mt-2 text-[12px] text-tres-doux">{t("Outils partagés : {liste}.", { liste: e.outils.join(", ") })}</p>
          <Bouton className="mt-3" taille="sm" variante="fantome" icone={<KeyRound className="size-3.5" />} chargement={envoi} onClick={() => regler({ nouvelle_cle: true })}>
            {t("Changer la clé")}
          </Bouton>
          <p className="mt-1 text-[12px] text-tres-doux">{t("L'ancienne clé ne marchera plus : recopie la commande dans tes assistants.")}</p>
        </>
      )}
    </Panneau>
  );
}
