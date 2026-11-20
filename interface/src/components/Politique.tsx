import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import { ouvrirLien } from "../lib/liens";
import { toast } from "../stores/toasts";
import type { Compte } from "./Connexion";
import { Bouton } from "./ui";

/** Comptes existants (ou politique modifiée) : la politique de confidentialité est présentée et doit être acceptée. */
export function AccordPolitique({ compte, onAccepte }: { compte: Compte; onAccepte: (c: Compte) => void }) {
  const [envoi, setEnvoi] = useState(false);
  const accepter = async () => {
    setEnvoi(true);
    try {
      onAccepte(await api<Compte>("/api/compte/politique", { method: "POST" }));
    } catch (x) {
      toast((x as Error).message, "erreur");
    } finally {
      setEnvoi(false);
    }
  };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-labelledby="titre-politique">
      <div className="w-[min(480px,100%)] rounded-xl border border-ligne-forte bg-surface-2 p-6 shadow-glow">
        <ShieldCheck className="mb-3 size-7 text-hud" />
        <h2 id="titre-politique" className="text-lg font-semibold">
          {t("Ta vie privée")}
        </h2>
        <p className="mt-2 text-[14px] leading-relaxed text-doux">
          {t("La politique de confidentialité de Jarvis explique quelles données ton compte garde, pourquoi, combien de temps, et comment les télécharger ou tout supprimer. Lis-la puis accepte-la pour continuer à utiliser ton compte.")}
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          <Bouton variante="primaire" chargement={envoi} onClick={accepter}>
            {t("J'accepte")}
          </Bouton>
          <Bouton variante="fantome" onClick={() => compte.url_confidentialite && ouvrirLien(compte.url_confidentialite)}>
            {t("Lire la politique")}
          </Bouton>
        </div>
        <p className="mt-4 text-[12px] leading-relaxed text-tres-doux">
          {t("Tu ne veux pas ? Déconnecte-toi : tu pourras utiliser Jarvis en local, sans compte. Pour faire supprimer ton compte, écris à l'adresse indiquée dans la politique.")}{" "}
          <button
            onClick={() => api("/api/compte/deconnexion", { method: "POST" }).then(() => location.reload()).catch((x) => toast((x as Error).message, "erreur"))}
            className="text-doux underline underline-offset-2 hover:text-texte"
          >
            {t("Me déconnecter")}
          </button>
        </p>
      </div>
    </div>
  );
}
