import { t } from "../lib/i18n";
import { Blocks, CalendarDays, Check, Copy, KeyRound, Server, GitBranch, Loader2, Mail, NotebookPen, Plug, Plus, Power, Trash2, X, Zap } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Badge, Bouton, Champ, EnTetePage, Vide } from "../components/ui";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { useOS } from "../lib/os";
import { toast } from "../stores/toasts";

type ChampDef = { nom: string; libelle: string; type: "text" | "secret" | "url" | "choix"; aide?: string; requis?: boolean; choix?: string[]; multiligne?: boolean };
const LIBELLES_CHOIX: Record<string, string> = {
  commande: "Commande locale (npx, uvx, python…)",
  url: "Adresse web (serveur distant)",
  confirmation: "Confirmation : il me demande avant de modifier quoi que ce soit (conseillé)",
  lecture: "Lecture seule : il peut seulement regarder",
  libre: "Libre : il agit sans demander",
  non: "Non : jamais de sudo",
  oui: "Oui : sudo sans mot de passe, avec ton accord à chaque fois",
};
type TypeConnecteur = { type: string; nom: string; description: string; icone: string; champs: ChampDef[]; aide: string; multiple: boolean };
type Installe = { type: string; actif: boolean; conf: Record<string, string>; secrets: Record<string, boolean>; erreur: string; outils: string[] };
type Donnees = { catalogue: TypeConnecteur[]; installes: Record<string, Installe> };

const ICONES: Record<string, ReactNode> = {
  server: <Server />,
  mail: <Mail />, calendar: <CalendarDays />, github: <GitBranch />, notebook: <NotebookPen />, blocks: <Blocks />,
};
const icone = (n: string) => ICONES[n] ?? <Plug />;

/* ---------- clé SSH : génération + guide d'installation sur le serveur ---------- */
function BlocCommande({ texte }: { texte: string }) {
  const [copie, setCopie] = useState(false);
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-md border border-ligne-forte bg-surface-2 p-3 pr-10 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-all">{texte}</pre>
      <button
        onClick={() => {
          navigator.clipboard.writeText(texte);
          setCopie(true);
          setTimeout(() => setCopie(false), 1500);
        }}
        className="absolute top-2 right-2 rounded p-1 text-doux hover:text-texte"
        aria-label={t("Copier")}
        title={t("Copier")}
      >
        {copie ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </div>
  );
}

type Droits = "aucun" | "limites" | "complets";
// Droits limités : chaque permission = commandes autorisées sans mot de passe (chemins trouvés sur le serveur).
const PERMISSIONS: { id: string; libelle: string; alerte?: string; regle: string }[] = [
  {
    id: "services",
    libelle: "Démarrer, arrêter, redémarrer des services (systemctl)",
    regle: 'p=$(command -v systemctl) && echo "$U ALL=(root) NOPASSWD: $p start *, $p stop *, $p restart *, $p reload *, $p status *"',
  },
  { id: "journaux", libelle: "Lire les journaux système (journalctl)", regle: 'p=$(command -v journalctl) && echo "$U ALL=(root) NOPASSWD: $p"' },
  {
    id: "web",
    libelle: "Serveur web : tester et recharger Apache / Nginx",
    regle:
      'p=$(command -v apache2ctl) && echo "$U ALL=(root) NOPASSWD: $p configtest, $p -t, $p -S, $p graceful"\n' +
      '  p=$(command -v nginx) && echo "$U ALL=(root) NOPASSWD: $p -t, $p -s reload"',
  },
  { id: "certbot", libelle: "Certificats HTTPS (certbot)", regle: 'p=$(command -v certbot) && echo "$U ALL=(root) NOPASSWD: $p renew, $p certificates"' },
  {
    id: "maj",
    libelle: "Mettre à jour le système (apt)",
    regle: 'p=$(command -v apt-get) && echo "$U ALL=(root) NOPASSWD: $p update, $p upgrade -y, $p autoremove -y"',
  },
  {
    id: "docker",
    libelle: "Gérer Docker",
    alerte: "Avec Docker, on peut obtenir tous les droits sur le serveur : autant que « Tous les droits ».",
    regle: 'p=$(command -v docker) && echo "$U ALL=(root) NOPASSWD: $p"',
  },
];

/** Bloc de commandes à coller sur le serveur (avec le compte habituel de l'utilisateur, qui a sudo). */
function scriptServeur(u: string, publique: string, droits: Droits, permis: string[], deuxFA: boolean): string {
  const f = `/etc/sudoers.d/wesley-${u}`;
  const l = [
    `# Wesley : préparation du serveur pour l'utilisateur ${u}`,
    `U=${u}; PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"`,
    `id -u "$U" >/dev/null 2>&1 || sudo adduser --disabled-password --gecos "" "$U"`,
    `H=$(getent passwd "$U" | cut -d: -f6); G=$(id -gn "$U")`,
    `sudo install -d -m 700 -o "$U" -g "$G" "$H/.ssh"`,
    `CLE='${publique}'`,
    `sudo grep -qxF "$CLE" "$H/.ssh/authorized_keys" 2>/dev/null || echo "$CLE" | sudo tee -a "$H/.ssh/authorized_keys" >/dev/null`,
    `sudo chown "$U:$G" "$H/.ssh/authorized_keys" && sudo chmod 600 "$H/.ssh/authorized_keys"`,
  ];
  if (droits === "aucun") l.push(`sudo rm -f ${f}`);
  else {
    if (droits === "complets") l.push(`echo "$U ALL=(ALL) NOPASSWD: ALL" | sudo tee ${f} >/dev/null`);
    else {
      const regles = PERMISSIONS.filter((p) => permis.includes(p.id)).map((p) => "  " + p.regle);
      l.push("{", ...(regles.length ? regles : ["  true"]), `} | sudo tee ${f} >/dev/null`);
    }
    l.push(
      `sudo chmod 440 ${f}`,
      `sudo visudo -cf ${f} >/dev/null || { echo "Règle sudo invalide : retirée."; sudo rm -f ${f}; }`,
    );
  }
  if (deuxFA)
    l.push(
      `if ! sudo grep -q "^Match User $U\\$" /etc/ssh/sshd_config; then`,
      `  sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.avant-wesley`,
      `  printf '\\nMatch User %s\\n    AuthenticationMethods publickey\\n' "$U" | sudo tee -a /etc/ssh/sshd_config >/dev/null`,
      `  if sudo sshd -t; then sudo systemctl reload ssh 2>/dev/null || sudo systemctl reload sshd`,
      `  else sudo cp /etc/ssh/sshd_config.avant-wesley /etc/ssh/sshd_config; echo "Config SSH refusée : remise comme avant."; fi`,
      `fi`,
    );
  l.push(`echo; echo "== Wesley : $U prêt =="; sudo -l -U "$U" 2>/dev/null | sed -n '/NOPASSWD/p' || true`);
  return l.join("\n");
}

function GuideCleSSH({
  cid,
  conf,
  cleEnregistree,
  onCle,
  onSudo,
}: {
  cid: string | null;
  conf: Record<string, string>;
  cleEnregistree: boolean;
  onCle: (privee: string) => void;
  onSudo: (oui: boolean) => void;
}) {
  const [publique, setPublique] = useState("");
  const [nouvelle, setNouvelle] = useState(false);
  const [enCours, setEnCours] = useState(false);

  const generer = async () => {
    if (cleEnregistree && !confirm(t("Une clé est déjà enregistrée. La remplacer par une nouvelle ? Il faudra ajouter la nouvelle sur le serveur.")))
      return;
    setEnCours(true);
    try {
      const r = await api<{ privee: string; publique: string }>("/api/ssh/generer-cle", { method: "POST" });
      onCle(r.privee);
      setPublique(r.publique);
      setNouvelle(true);
    } catch (e) {
      toast((e as Error).message, "erreur");
    } finally {
      setEnCours(false);
    }
  };
  const afficher = async () => {
    setEnCours(true);
    try {
      const r = await api<{ publique: string }>(`/api/ssh/cle-publique?cid=${encodeURIComponent(cid ?? "")}`);
      if (r.publique) setPublique(r.publique);
      else toast(t("Aucune clé enregistrée sur cet appareil."), "erreur");
    } catch (e) {
      toast((e as Error).message, "erreur");
    } finally {
      setEnCours(false);
    }
  };

  const hote = (conf.hote ?? "").trim();
  const utilisateur = (conf.utilisateur ?? "").trim();
  const port = (conf.port ?? "").trim();
  const [droits, setDroitsEtat] = useState<Droits>(conf.sudo === "oui" ? "complets" : "aucun");
  const [permis, setPermis] = useState<string[]>(["services", "journaux"]);
  const [deuxFA, setDeuxFA] = useState(false);
  const setDroits = (d: Droits) => {
    setDroitsEtat(d);
    onSudo(d !== "aucun"); // l'option « Droits administrateur » du connecteur suit ce choix
  };
  const nomValide = /^[a-z_][a-z0-9_-]{0,31}$/.test(utilisateur);
  const script = publique && nomValide ? scriptServeur(utilisateur, publique, droits, permis, deuxFA) : "";
  const connexion = hote ? `ssh ${port && port !== "22" ? `-p ${port} ` : ""}ton-compte@${hote}` : "";

  return (
    <div className="space-y-3 rounded-md border border-ligne-forte p-3">
      <div className="flex flex-wrap items-center gap-2">
        <KeyRound className="size-4 text-hud" />
        <span className="text-sm font-medium">{t("Clé SSH")}</span>
        <div className="ml-auto flex gap-2">
          {cid && cleEnregistree && !publique && (
            <Bouton taille="sm" variante="fantome" onClick={afficher} chargement={enCours}>
              {t("Voir la clé publique")}
            </Bouton>
          )}
          <Bouton taille="sm" onClick={generer} chargement={enCours} icone={<KeyRound className="size-3.5" />}>
            {t("Générer une clé")}
          </Bouton>
        </div>
      </div>
      {!publique && (
        <p className="text-[12px] text-tres-doux">
          {t("Wesley crée une clé rien que pour lui et te guide pour l'ajouter au serveur. Avec une clé, plus besoin de mot de passe ni de code d'authentification, et elle suit ton compte sur tous tes appareils.")}
        </p>
      )}
      {publique && (
        <ol className="list-decimal space-y-3 pl-5 text-[13px] leading-relaxed">
          {nouvelle && <li>{t("La clé privée est dans le formulaire ci-dessous (champ « Clé privée SSH »). Elle sera enregistrée quand tu cliqueras sur « Connecter ».")}</li>}
          <li className="space-y-2">
            <span className="block">{t("Choisis ce que Wesley pourra faire sur le serveur :")}</span>
            <div className="space-y-1.5 rounded-md border border-ligne p-2.5">
              {(
                [
                  ["aucun", "Aucun droit administrateur (pas de sudo)"],
                  ["limites", "Droits limités : seulement ce que je coche"],
                  ["complets", "Tous les droits (sudo complet, équivaut à root)"],
                ] as [Droits, string][]
              ).map(([v, l]) => (
                <label key={v} className="flex items-center gap-2">
                  <input type="radio" checked={droits === v} onChange={() => setDroits(v)} className="accent-hud" />
                  {t(l)}
                </label>
              ))}
              {droits === "limites" && (
                <div className="ml-6 space-y-1 border-l border-ligne pl-3">
                  {PERMISSIONS.map((p) => (
                    <label key={p.id} className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        className="mt-1 accent-hud"
                        checked={permis.includes(p.id)}
                        onChange={(e) => setPermis(e.target.checked ? [...permis, p.id] : permis.filter((x) => x !== p.id))}
                      />
                      <span>
                        {t(p.libelle)}
                        {p.alerte && <span className="block text-[12px] text-ambre">{t(p.alerte)}</span>}
                      </span>
                    </label>
                  ))}
                </div>
              )}
              {droits === "complets" && (
                <p className="ml-6 text-[12px] text-ambre">
                  {t("Wesley pourra tout faire sur le serveur. Chaque commande sudo te demandera quand même « Autoriser / Refuser ».")}
                </p>
              )}
              <label className="flex items-center gap-2 border-t border-ligne pt-1.5">
                <input type="checkbox" checked={deuxFA} onChange={(e) => setDeuxFA(e.target.checked)} className="accent-hud" />
                {t("Mon serveur demande un code d'authentification (2FA) : la clé de Wesley suffira")}
              </label>
            </div>
          </li>
          <li>
            {!nomValide ? (
              <span className="text-ambre">{t("Remplis d'abord le champ « Utilisateur » ci-dessous (par exemple wesley) : le bloc de commandes apparaîtra ici.")}</span>
            ) : (
              <>
                {connexion
                  ? t("Connecte-toi au serveur avec ton compte habituel ({connexion}), puis colle ce bloc en entier :", { connexion })
                  : t("Connecte-toi au serveur avec ton compte habituel, puis colle ce bloc en entier :")}
                <BlocCommande texte={script} />
                <span className="mt-1 block text-[12px] text-tres-doux">
                  {t("Il crée l'utilisateur {u} s'il n'existe pas, installe la clé, règle les droits et affiche une vérification à la fin. Tu peux le relancer après avoir changé tes choix.", { u: utilisateur })}
                </span>
              </>
            )}
          </li>
          <li>{t("Clique sur « Connecter », puis sur « Tester » sur la carte du serveur.")}</li>
        </ol>
      )}
    </div>
  );
}

/* ---------- formulaire ---------- */
function Editeur({
  def,
  cid,
  existant,
  idsExistants,
  onFermer,
  onFini,
}: {
  def: TypeConnecteur;
  cid: string | null;
  existant?: Installe;
  idsExistants: string[];
  onFermer: () => void;
  onFini: () => void;
}) {
  const os = useOS();
  const [conf, setConf] = useState<Record<string, string>>({ mode: "commande", ...(existant?.conf ?? {}) });
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [aVider, setAVider] = useState<string[]>([]);   // secrets à effacer (ex. phrase de l'ancienne clé)
  const [envoi, setEnvoi] = useState(false);
  const visible = (c: ChampDef) =>
    def.type !== "mcp" || (conf.mode === "url" ? !["commande", "env"].includes(c.nom) : !["url", "entete"].includes(c.nom));

  const enregistrer = async () => {
    // 1er compte d'un type : identifiant = le type (compatibilité) ; les suivants : type:nom-du-compte (unique)
    const base = (conf.compte || conf.email || conf.nom || "compte").toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 24);
    let id = cid ?? (idsExistants.includes(def.type) ? `${def.type}:${base}` : def.type);
    for (let n = 2; !cid && idsExistants.includes(id) && n < 99; n++) id = `${def.type}:${base}_${n}`;
    setEnvoi(true);
    try {
      const r = await api<Installe>(`/api/connecteurs/${encodeURIComponent(id)}`, {
        method: "POST",
        json: { type: def.type, conf, secrets: Object.fromEntries(Object.entries(secrets).filter(([k, v]) => v !== "" || aVider.includes(k))), actif: true },
      });
      if (r.erreur) toast(r.erreur, "erreur");
      else toast(`${def.nom} connecté — ${r.outils.length} outil(s) ajouté(s) à Wesley.`, "succes");
      onFini();
    } catch (e) {
      toast((e as Error).message, "erreur");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/50" onClick={onFermer}>
      <aside className="flex h-full w-[min(520px,100vw)] animate-entree flex-col border-l border-ligne-forte bg-surface" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center gap-3 border-b border-ligne px-5 py-4">
          <span className="text-hud [&>svg]:size-5">{icone(def.icone)}</span>
          <h2 className="titre-hud text-sm text-hud">{def.nom}</h2>
          <button onClick={onFermer} className="ml-auto text-doux hover:text-texte" aria-label={t("Fermer")}>
            <X className="size-5" />
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <p className="text-sm text-doux">{def.description}</p>
          {def.aide && <div className="rounded-md border border-hud/25 bg-hud/5 p-3 text-[13px] leading-relaxed whitespace-pre-wrap text-hud-clair">{def.aide}</div>}
          {def.type === "ssh" && (
            <GuideCleSSH
              cid={cid}
              conf={conf}
              cleEnregistree={!!existant?.secrets.cle_privee}
              onCle={(privee) => {
                // nouvelle clé sans phrase de passe : on efface celle d'une éventuelle ancienne clé
                setSecrets((s) => ({ ...s, cle_privee: privee, phrase_cle: "" }));
                setAVider((v) => [...v, "phrase_cle"]);
              }}
              onSudo={(oui) => setConf((c) => ({ ...c, sudo: oui ? "oui" : "non" }))}
            />
          )}
          {def.champs.filter(visible).map((c) => (
            <label key={c.nom} className="block">
              <span className="mb-1.5 block text-sm">
                {c.libelle}
                {c.requis === false && <span className="text-tres-doux">{t(" (facultatif)")}</span>}
              </span>
              {c.type === "choix" ? (
                <select
                  value={conf[c.nom] ?? c.choix?.[0]}
                  onChange={(e) => setConf({ ...conf, [c.nom]: e.target.value })}
                  className="h-10 w-full rounded-md border border-ligne-forte bg-surface-2 px-3 text-sm"
                >
                  {c.choix?.map((o) => (
                    <option key={o} value={o}>
                      {LIBELLES_CHOIX[o] ? t(LIBELLES_CHOIX[o]) : o}
                    </option>
                  ))}
                </select>
              ) : c.nom === "env" || c.multiligne ? (
                <textarea
                  rows={3}
                  value={secrets[c.nom] ?? ""}
                  onChange={(e) => setSecrets({ ...secrets, [c.nom]: e.target.value })}
                  placeholder={existant?.secrets[c.nom] ? "•••••• enregistré (laisse vide pour garder)" : c.nom === "env" ? "CLE_API=xxxx" : ""}
                  className="w-full rounded-md border border-ligne-forte bg-surface-2 p-3 font-mono text-sm outline-none focus:border-hud"
                />
              ) : c.type === "secret" ? (
                <Champ
                  type="password"
                  autoComplete="off"
                  value={secrets[c.nom] ?? ""}
                  onChange={(e) => setSecrets({ ...secrets, [c.nom]: e.target.value })}
                  placeholder={existant?.secrets[c.nom] ? "•••••• enregistré (laisse vide pour garder)" : ""}
                />
              ) : (
                <Champ value={conf[c.nom] ?? ""} onChange={(e) => setConf({ ...conf, [c.nom]: e.target.value })} />
              )}
              {c.aide && <span className="mt-1 block text-[12px] text-tres-doux">{c.aide}</span>}
            </label>
          ))}
          <p className="text-[12px] text-tres-doux">
            Les mots de passe et jetons sont rangés dans le {os.coffre}. Ils rejoignent aussi ton compte, chiffrés avec ton mot de passe : le serveur ne peut pas les lire.
          </p>
        </div>
        <footer className="flex gap-2 border-t border-ligne p-4">
          <Bouton variante="primaire" chargement={envoi} onClick={enregistrer} icone={<Check className="size-4" />}>
            {t("Connecter")}
          </Bouton>
          <Bouton variante="fantome" onClick={onFermer}>
            {t("Annuler")}
          </Bouton>
        </footer>
      </aside>
    </div>
  );
}

/* ---------- carte d'un connecteur installé ---------- */
function CarteInstalle({ cid, c, def, onModifier, onMaj }: { cid: string; c: Installe; def?: TypeConnecteur; onModifier: () => void; onMaj: () => void }) {
  const [test, setTest] = useState<{ ok: boolean; texte: string } | null>(null);
  const [enCours, setEnCours] = useState(false);
  const titre = [def?.nom, c.conf.compte || c.conf.email || c.conf.nom].filter(Boolean).join(" — ") || cid;
  const statut = !c.actif ? ["Désactivé", "doux"] : c.erreur ? [c.erreur.startsWith("Identifiants") ? "À configurer sur ce PC" : "Erreur", c.erreur.startsWith("Identifiants") ? "ambre" : "rouge"] : [`Actif · ${c.outils.length} outils`, "vert"];

  const tester = async () => {
    setEnCours(true);
    try {
      setTest({ ok: true, texte: (await api<{ message: string }>(`/api/connecteurs/${encodeURIComponent(cid)}/tester`, { method: "POST" })).message });
    } catch (e) {
      setTest({ ok: false, texte: (e as Error).message });
    } finally {
      setEnCours(false);
    }
  };
  const basculer = async () => {
    try {
      await api(`/api/connecteurs/${encodeURIComponent(cid)}`, { method: "POST", json: { type: c.type, conf: c.conf, secrets: {}, actif: !c.actif } });
      onMaj();
    } catch (e) {
      toast((e as Error).message, "erreur");
    }
  };
  const supprimer = async () => {
    if (!confirm(t("Déconnecter {titre} ? Ses identifiants seront effacés de ce PC.", { titre }))) return;
    await api(`/api/connecteurs/${encodeURIComponent(cid)}`, { method: "DELETE" });
    toast(`${titre} déconnecté.`);
    onMaj();
  };

  return (
    <article className="coins flex flex-col border border-ligne bg-surface/60 p-4">
      <div className="flex items-start gap-3">
        <span className={cx("grid size-10 flex-none place-items-center rounded-md border [&>svg]:size-5", c.actif && !c.erreur ? "border-hud/50 text-hud" : "border-ligne text-doux")}>
          {icone(def?.icone ?? "plug")}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{titre}</div>
          <div className="text-xs text-doux">{def?.nom}</div>
        </div>
        <Badge ton={statut[1] as "vert" | "ambre" | "rouge" | "doux"}>{statut[0]}</Badge>
      </div>
      {c.erreur && <p className={cx("mt-3 text-[13px]", c.erreur.startsWith("Identifiants") ? "text-ambre" : "text-rouge")}>{c.erreur}</p>}
      {c.outils.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {c.outils.slice(0, 8).map((o) => (
            <span key={o} className="rounded border border-ligne px-1.5 py-0.5 font-mono text-[11px] text-tres-doux">
              {o}
            </span>
          ))}
          {c.outils.length > 8 && <span className="text-[11px] text-tres-doux">+{c.outils.length - 8}</span>}
        </div>
      )}
      {test && <p className={cx("mt-3 text-[13px]", test.ok ? "text-vert" : "text-rouge")}>{test.ok ? "✓ " : "✗ "}{test.texte}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <Bouton taille="sm" onClick={tester} chargement={enCours} icone={<Zap className="size-3.5" />} disabled={!c.actif}>
          {t("Tester")}
        </Bouton>
        <Bouton taille="sm" variante="fantome" onClick={onModifier}>
          {t("Modifier")}
        </Bouton>
        <Bouton taille="sm" variante="fantome" onClick={basculer} icone={<Power className="size-3.5" />}>
          {c.actif ? "Désactiver" : "Activer"}
        </Bouton>
        <button onClick={supprimer} className="ml-auto rounded p-1.5 text-tres-doux hover:text-rouge" aria-label={t("Déconnecter")} title={t("Déconnecter")}>
          <Trash2 className="size-4" />
        </button>
      </div>
    </article>
  );
}

/* ---------- vue ---------- */
export function VueConnecteurs() {
  const [d, setD] = useState<Donnees | null>(null);
  const [edition, setEdition] = useState<{ def: TypeConnecteur; cid: string | null } | null>(null);
  const charger = () => api<Donnees>("/api/connecteurs").then(setD).catch((e) => toast(e.message, "erreur"));
  useEffect(() => {
    charger();
  }, []);

  if (!d)
    return (
      <div className="grid h-full place-items-center text-doux">
        <Loader2 className="size-6 animate-spin" />
      </div>
    );
  const installes = Object.entries(d.installes);
  const def = (t: string) => d.catalogue.find((c) => c.type === t);
  const dejaLa = (t: string) => installes.some(([, c]) => c.type === t);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <EnTetePage
        titre={t("Connecteurs")}
        sousTitre={t("Branche tes services : leurs outils s'ajoutent à Wesley. La liste est partagée entre tes PC ; les mots de passe restent sur chaque PC.")}
      />

      <h2 className="titre-hud mb-3 text-[11px] text-hud">{t("Connectés")}</h2>
      {installes.length === 0 ? (
        <div className="coins mb-8 border border-ligne bg-surface/40">
          <Vide icone={<Plug />} titre={t("Aucun service connecté")} texte={t("Choisis un service ci-dessous. Par exemple Gmail pour que Wesley lise et envoie tes mails.")} />
        </div>
      ) : (
        <div className="mb-8 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {installes.map(([cid, c]) => (
            <CarteInstalle key={cid} cid={cid} c={c} def={def(c.type)} onMaj={charger} onModifier={() => setEdition({ def: def(c.type)!, cid })} />
          ))}
        </div>
      )}

      <h2 className="titre-hud mb-3 text-[11px] text-hud">{t("Ajouter un service")}</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {d.catalogue.map((ty) => {
          const indispo = !ty.multiple && dejaLa(ty.type);
          return (
            <button
              key={ty.type}
              disabled={indispo}
              onClick={() => setEdition({ def: ty, cid: null })}
              className="group flex gap-3 rounded-md border border-ligne bg-surface/40 p-4 text-left transition-colors hover:border-hud/50 hover:bg-hud/5 disabled:opacity-40"
            >
              <span className="grid size-10 flex-none place-items-center rounded-md border border-ligne text-hud [&>svg]:size-5">{icone(ty.icone)}</span>
              <span className="min-w-0">
                <span className="flex items-center gap-2 font-medium">
                  {ty.nom}
                  {indispo ? <Badge ton="vert">{t("connecté")}</Badge> : <Plus className="size-4 text-tres-doux group-hover:text-hud" />}
                </span>
                <span className="mt-1 block text-[13px] leading-snug text-doux">{ty.description}</span>
              </span>
            </button>
          );
        })}
      </div>

      <p className="mt-8 max-w-3xl text-[13px] text-tres-doux">
        {t("Un service n'est pas dans la liste (Spotify, Slack, Home Assistant, Google Drive…) ? Utilise « Serveur MCP ». C'est un standard que des centaines d'outils proposent. Sur la page du serveur MCP, copie la commande ou l'adresse indiquée.")}
      </p>

      {edition && (
        <Editeur
          def={edition.def}
          cid={edition.cid}
          existant={edition.cid ? d.installes[edition.cid] : undefined}
          idsExistants={Object.keys(d.installes)}
          onFermer={() => setEdition(null)}
          onFini={() => {
            setEdition(null);
            charger();
          }}
        />
      )}
    </div>
  );
}
