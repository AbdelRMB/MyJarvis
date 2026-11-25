import { AudioLines, Brain, FileText, History, ListChecks, Loader2, Search, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { t } from "../lib/i18n";
import { useReglages } from "../stores/reglages";
import { ouvrirTranscription } from "../views/Transcription";

type Resultats = {
  souvenirs: { fid: string; fait: string; categorie: string }[];
  historique: { jour: string; texte: string }[];
  transcriptions: { id: string; titre: string; date: number | null; heure: string; locuteur: string; texte: string; appareil: string }[];
  documents: { fichier: string; page: number; texte: string }[];
  afaire: { id: string; titre: string; statut: string; echeance: string }[];
  erreurs: Record<string, string>;
};

const nomFichier = (c: string) => c.split(/[\\/]/).pop() || c;

function Section({ titre, icone, children }: { titre: string; icone: ReactNode; children: ReactNode }) {
  return (
    <section className="border-b border-ligne px-3 py-2.5 last:border-b-0">
      <h3 className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-tres-doux [&>svg]:size-3.5">
        {icone}
        {titre}
      </h3>
      <ul className="space-y-0.5">{children}</ul>
    </section>
  );
}

function Ligne({ onClick, haut, bas }: { onClick: () => void; haut: ReactNode; bas?: ReactNode }) {
  return (
    <li>
      <button onClick={onClick} className="w-full rounded px-2 py-1.5 text-left hover:bg-hud/10">
        <div className="line-clamp-2 text-[13px]">{haut}</div>
        {bas && <div className="mt-0.5 truncate text-[11px] text-doux">{bas}</div>}
      </button>
    </li>
  );
}

/** Recherche unique (Ctrl+Maj+F) : souvenirs, conversations, transcriptions, documents et À faire en une question. */
export function RechercheGlobale() {
  const [ouvert, setOuvert] = useState(false);
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Resultats | null>(null);
  const [charge, setCharge] = useState(false);
  const champ = useRef<HTMLInputElement>(null);
  const maj = useReglages((s) => s.maj);

  useEffect(() => {
    const touche = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "f") {
        e.preventDefault();
        setOuvert(true);
      } else if (e.key === "Escape") setOuvert(false);
    };
    addEventListener("keydown", touche);
    return () => removeEventListener("keydown", touche);
  }, []);
  useEffect(() => {
    if (ouvert) setTimeout(() => champ.current?.focus(), 20);
  }, [ouvert]);

  // on cherche dès qu'on arrête de taper
  useEffect(() => {
    const requete = q.trim();
    if (requete.length < 2) {
      setRes(null);
      return;
    }
    let annule = false;
    const minuteur = setTimeout(() => {
      setCharge(true);
      api<Resultats>(`/api/recherche?q=${encodeURIComponent(requete)}`)
        .then((r) => !annule && setRes(r))
        .catch(() => !annule && setRes(null))
        .finally(() => !annule && setCharge(false));
    }, 300);
    return () => {
      annule = true;
      clearTimeout(minuteur);
    };
  }, [q]);

  const aller = (f: () => void) => {
    f();
    setOuvert(false);
  };
  const vide = res && !res.souvenirs.length && !res.historique.length && !res.transcriptions.length && !res.documents.length && !res.afaire.length;

  return (
    <>
      <button
        onClick={() => setOuvert(true)}
        title={t("Rechercher partout (Ctrl+Maj+F)")}
        aria-label={t("Rechercher partout")}
        className="grid size-9 place-items-center rounded-md border border-ligne text-doux transition-colors hover:border-hud hover:text-hud"
      >
        <Search className="size-4" />
      </button>
      {ouvert && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-fond/70 p-4 pt-[12vh] backdrop-blur-sm" onMouseDown={() => setOuvert(false)}>
          <div
            role="dialog"
            aria-label={t("Rechercher partout")}
            onMouseDown={(e) => e.stopPropagation()}
            className="flex max-h-[72vh] w-[min(640px,100%)] flex-col overflow-hidden rounded-xl border border-ligne-forte bg-surface-2 shadow-glow"
          >
            <div className="flex items-center gap-2 border-b border-ligne px-3">
              {charge ? <Loader2 className="size-4 animate-spin text-hud" /> : <Search className="size-4 text-hud" />}
              <input
                ref={champ}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("Chercher dans tes souvenirs, conversations, transcriptions, documents…")}
                className="h-12 min-w-0 flex-1 bg-transparent text-sm outline-none"
              />
              <button onClick={() => setOuvert(false)} title={t("Fermer")} className="text-doux hover:text-texte">
                <X className="size-4" />
              </button>
            </div>
            <div className="min-h-0 overflow-y-auto">
              {!res && <p className="p-4 text-center text-[13px] text-doux">{t("Tape au moins deux lettres. Wesley cherche par le sens : d'autres mots que ceux d'origine marchent aussi.")}</p>}
              {vide && <p className="p-4 text-center text-[13px] text-doux">{t("Rien trouvé.")}</p>}
              {res && res.souvenirs.length > 0 && (
                <Section titre={t("Souvenirs")} icone={<Brain />}>
                  {res.souvenirs.map((x) => (
                    <Ligne key={x.fid || x.fait} onClick={() => aller(() => maj({ vue: "memoire" }))} haut={x.fait} bas={x.categorie} />
                  ))}
                </Section>
              )}
              {res && res.transcriptions.length > 0 && (
                <Section titre={t("Transcriptions")} icone={<AudioLines />}>
                  {res.transcriptions.map((x, i) => (
                    <Ligne
                      key={`${x.id}-${i}`}
                      onClick={() =>
                        aller(() => {
                          ouvrirTranscription(x.id);
                          maj({ vue: "transcription" });
                        })
                      }
                      haut={x.texte}
                      bas={[x.titre, x.date ? new Date(x.date * 1000).toLocaleDateString() : "", x.heure, x.locuteur, x.appareil].filter(Boolean).join(" · ")}
                    />
                  ))}
                </Section>
              )}
              {res && res.documents.length > 0 && (
                <Section titre={t("Documents")} icone={<FileText />}>
                  {res.documents.map((x, i) => (
                    <Ligne
                      key={`${x.fichier}-${x.page}-${i}`}
                      onClick={() => aller(() => maj({ vue: "memoire" }))}
                      haut={x.texte}
                      bas={nomFichier(x.fichier) + (x.page ? ` · ${t("page {n}", { n: x.page })}` : "")}
                    />
                  ))}
                </Section>
              )}
              {res && res.afaire.length > 0 && (
                <Section titre={t("À faire")} icone={<ListChecks />}>
                  {res.afaire.map((x) => (
                    <Ligne key={x.id} onClick={() => aller(() => maj({ vue: "afaire" }))} haut={x.titre} bas={x.echeance || undefined} />
                  ))}
                </Section>
              )}
              {res && res.historique.length > 0 && (
                <Section titre={t("Conversations passées")} icone={<History />}>
                  {res.historique.map((x, i) => (
                    <Ligne key={`${x.jour}-${i}`} onClick={() => aller(() => maj({ vue: "historique" }))} haut={x.texte} bas={x.jour} />
                  ))}
                </Section>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
