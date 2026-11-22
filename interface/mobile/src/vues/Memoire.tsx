import { History, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Bouton, Champ } from "../../../src/components/ui";
import { t } from "../../../src/lib/i18n";
import { journalMemoire, memoriser, modifierSouvenir, oublierSouvenir, useDonnees } from "../moteur/donnees";
import type { Fait } from "../moteur/types";
import { Entete, erreurToast, Feuille, Ligne, Section, tempsRelatif } from "../ui";

const CATEGORIES = ["general", "preference", "personne", "projet", "consigne", "lecon"];

/** Ce que Wesley sait de toi (mémoire du compte, partagée avec tes ordinateurs). */
export function Memoire() {
  const faits = useDonnees((d) => d.faits);
  const [q, setQ] = useState("");
  const [edition, setEdition] = useState<Fait | "nouveau" | null>(null);
  const [journal, setJournal] = useState<Awaited<ReturnType<typeof journalMemoire>> | null>(null);

  const groupes = useMemo(() => {
    const r: Record<string, Fait[]> = {};
    const m = q.trim().toLowerCase();
    for (const f of faits) if (!m || f.fait.toLowerCase().includes(m)) (r[f.categorie] ||= []).push(f);
    return Object.entries(r).sort(([a], [b]) => (a === "consigne" ? -1 : b === "consigne" ? 1 : a.localeCompare(b)));
  }, [faits, q]);

  return (
    <div>
      <Entete
        titre={t("Mémoire")}
        sous={t("{n} souvenirs, sur tous tes appareils", { n: faits.length })}
        actions={
          <>
            <button className="grid size-9 place-items-center text-doux" aria-label={t("Journal")} onClick={() => journalMemoire().then(setJournal, erreurToast)}>
              <History className="size-4.5" />
            </button>
            <button className="grid size-9 place-items-center text-hud" aria-label={t("Ajouter")} onClick={() => setEdition("nouveau")}>
              <Plus className="size-5" />
            </button>
          </>
        }
      />
      <div className="relative px-3 pt-3">
        <Search className="absolute top-6 left-6 size-4 text-tres-doux" />
        <Champ value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Chercher…")} className="pl-9" />
      </div>
      {groupes.map(([cat, l]) => (
        <Section key={cat} titre={`${cat === "consigne" ? t("consignes (prioritaires)") : cat} · ${l.length}`}>
          {l.map((f) => (
            <Ligne key={f.fid} onClick={() => setEdition(f)}>
              <span className="min-w-0 flex-1 text-[14px] leading-snug">{f.fait}</span>
            </Ligne>
          ))}
        </Section>
      ))}
      {!faits.length && <p className="px-6 py-16 text-center text-sm text-doux">{t("Wesley n'a encore rien retenu. Parle-lui de toi !")}</p>}
      {edition && <EditionFait fait={edition === "nouveau" ? null : edition} onFermer={() => setEdition(null)} />}
      {journal && (
        <Feuille titre={t("Journal de la mémoire")} onFermer={() => setJournal(null)}>
          <div className="-mx-4 -my-4">
            {journal.slice(0, 200).map((j, i) => (
              <Ligne key={i}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-[11px] text-doux">
                    <Badge ton={j.action === "suppression" ? "rouge" : j.action === "ajout" ? "vert" : "doux"}>{j.action}</Badge>
                    {j.appareil} · {tempsRelatif(j.ts)}
                  </div>
                  <div className="truncate text-[13px]">{j.fait}</div>
                </div>
              </Ligne>
            ))}
          </div>
        </Feuille>
      )}
    </div>
  );
}

function EditionFait({ fait, onFermer }: { fait: Fait | null; onFermer: () => void }) {
  const [texte, setTexte] = useState(fait?.fait || "");
  const [cat, setCat] = useState(fait?.categorie || "general");
  return (
    <Feuille titre={fait ? t("Souvenir") : t("Nouveau souvenir")} onFermer={onFermer}>
      <div className="space-y-3">
        <textarea
          value={texte}
          onChange={(e) => setTexte(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-ligne-forte bg-surface-2 px-3 py-2 outline-none focus:border-hud"
        />
        <div className="flex flex-wrap gap-1">
          {[...new Set([...CATEGORIES, cat])].map((c) => (
            <button key={c} onClick={() => setCat(c)} className={c === cat ? "rounded border border-hud bg-hud/15 px-2 py-1 text-[13px] text-hud" : "rounded border border-ligne px-2 py-1 text-[13px] text-doux"}>
              {c}
            </button>
          ))}
        </div>
        <div className="flex gap-2 pt-1">
          {fait && (
            <Bouton variante="danger" onClick={() => confirm(t("Oublier ce souvenir sur tous tes appareils ?")) && (oublierSouvenir(fait.fid), onFermer())}>
              {t("Oublier")}
            </Bouton>
          )}
          <Bouton
            variante="primaire"
            className="flex-1"
            disabled={!texte.trim()}
            onClick={() => {
              if (fait) modifierSouvenir(fait.fid, texte, cat);
              else memoriser(texte, cat);
              onFermer();
            }}
          >
            {t("Enregistrer")}
          </Bouton>
        </div>
      </div>
    </Feuille>
  );
}
