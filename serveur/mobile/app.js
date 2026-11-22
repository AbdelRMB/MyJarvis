/* Wesley mobile : télécommande de tes ordinateurs (même compte).
 * - Connexion : la clé est dérivée du mot de passe SUR le téléphone (scrypt, mêmes réglages que Wesley) ; le mot de
 *   passe n'est jamais envoyé.
 * - Chaque demande est chiffrée (AES-GCM, clé du compte) puis relayée par le serveur au Wesley de l'appareil choisi,
 *   qui l'exécute et renvoie la réponse chiffrée. Le serveur ne peut ni lire ni fabriquer une demande.
 */
"use strict";
const CLE_APPLI = window.WESLEY_CLE_APPLI || "";
const STOCKAGE = "wesley-mobile";
const DEPOT = "AbdelRMB/Wesley";
const $ = (id) => document.getElementById(id);

// ---------- langue ----------
const EN = {
  "Pilote ton Wesley depuis ton téléphone.": "Control your Wesley from your phone.",
  "Adresse e-mail": "Email address", "Mot de passe": "Password", "Se connecter": "Sign in",
  "Ton mot de passe ne quitte pas ce téléphone : il sert à chiffrer tes demandes, que seuls tes ordinateurs peuvent lire.":
    "Your password never leaves this phone: it encrypts your requests, which only your computers can read.",
  "Demande quelque chose…": "Ask something…", "Sur quel appareil ?": "On which device?", "Fermer": "Close",
  "Réglages": "Settings", "Réponses à voix haute": "Spoken replies", "Langue": "Language",
  "Effacer l'historique": "Clear history", "Se déconnecter": "Sign out", "Connexion…": "Signing in…",
  "E-mail ou mot de passe incorrect.": "Wrong email or password.", "en ligne": "online", "hors ligne": "offline",
  "occupé": "busy", "refuse les ordres": "refuses orders", "Aucun ordinateur connecté à ton compte.": "No computer signed in to your account.",
  "Choisis un appareil": "Pick a device", "{nom} est hors ligne (éteint ou Wesley fermé).": "{nom} is offline (off or Wesley closed).",
  "Envoi à {nom}…": "Sending to {nom}…", "{nom} travaille…": "{nom} is working…", "{nom} n'a pas répondu.": "{nom} didn't answer.",
  "Session expirée : reconnecte-toi.": "Session expired: sign in again.", "Mettre à jour vers {v}": "Update to {v}",
  "Mise à jour de {nom} lancée : il redémarre tout seul.": "{nom} update started: it restarts by itself.",
  "Que veux-tu que je fasse sur <b>{nom}</b> ?": "What should I do on <b>{nom}</b>?", "Connecté : {email}": "Signed in: {email}",
  "Effacer l'historique de ce téléphone ?": "Clear this phone's history?", "Te déconnecter de Wesley sur ce téléphone ?": "Sign out of Wesley on this phone?",
  "La reconnaissance vocale n'est pas disponible dans ce navigateur.": "Speech recognition isn't available in this browser.",
  "Je t'écoute…": "Listening…", "À faire": "To do", "Tickets": "Tickets", "Nouvelle tâche…": "New task…",
  "Touche une tâche pour la passer à l'étape suivante. Même ordinateur éteint, tu peux écrire « ajoute du pain à ma liste ».":
    "Tap a task to move it to the next step. Even with your computer off, you can type “add bread to my list”.",
  "en cours": "in progress", "fait": "done", "à faire": "to do", "Rien de prévu.": "Nothing planned.",
  "Ajouté à ta liste : {t}": "Added to your list: {t}", "Bug": "Bug", "Amélioration": "Improvement", "Idée": "Idea", "Question": "Question",
  "Titre": "Title", "Détails…": "Details…", "Envoyer au développeur": "Send to the developer", "Ticket envoyé.": "Ticket sent.",
  "Aucun ticket.": "No tickets.", "ouvert": "open", "résolu": "resolved", "fermé": "closed", "Réponse : ": "Reply: ",
  "Supprimer cette tâche ?": "Delete this task?", "version {v} — trop ancienne pour la mise à jour à distance": "version {v} — too old for remote update",
};
let langue = lire().langue || ((navigator.language || "fr").startsWith("en") ? "en" : "fr");
const t = (s, v = {}) => Object.entries(v).reduce((r, [k, x]) => r.replaceAll(`{${k}}`, x), langue === "en" ? EN[s] ?? s : s);
function traduire() {
  document.documentElement.lang = langue;
  document.querySelectorAll("[data-t]").forEach((e) => (e.textContent = t(e.dataset.t)));
  document.querySelectorAll("[data-ph]").forEach((e) => (e.placeholder = t(e.dataset.ph)));
  $("btn-langue-1").textContent = langue === "fr" ? "English" : "Français";
}

// ---------- état local ----------
function lire() { try { return JSON.parse(localStorage.getItem(STOCKAGE)) || {}; } catch { return {}; } }
function ecrire(p) { const e = { ...lire(), ...p }; localStorage.setItem(STOCKAGE, JSON.stringify(e)); return e; }
const b64 = (u8) => btoa(String.fromCharCode(...u8));
const deb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
function nomAppareil() {
  const ua = navigator.userAgent;
  return /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android" : "Téléphone";
}

// ---------- API ----------
async function api(methode, chemin, corps) {
  const e = lire();
  const r = await fetch("/v1" + chemin, {
    method: methode,
    headers: { "Content-Type": "application/json", "X-Wesley-Appli": CLE_APPLI, ...(e.jeton ? { Authorization: `Bearer ${e.jeton}` } : {}) },
    body: corps ? JSON.stringify(corps) : undefined,
  });
  if (r.status === 401 && chemin !== "/connexion") { deconnexionLocale(t("Session expirée : reconnecte-toi.")); throw new Error("401"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || `Erreur ${r.status}`);
  return d;
}

// ---------- chiffrement ----------
let cleAes = null;
async function cle() {
  if (!cleAes) cleAes = await crypto.subtle.importKey("raw", deb64(lire().cle), "AES-GCM", false, ["encrypt", "decrypt"]);
  return cleAes;
}
async function chiffrer(obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const c = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: new TextEncoder().encode("wesley-ordre") },
    await cle(), new TextEncoder().encode(JSON.stringify(obj))));
  const tout = new Uint8Array(12 + c.length); tout.set(iv); tout.set(c, 12);
  return b64(tout);
}
async function dechiffrer(blob) {
  const brut = deb64(blob);
  const p = await crypto.subtle.decrypt({ name: "AES-GCM", iv: brut.slice(0, 12), additionalData: new TextEncoder().encode("wesley-ordre") },
    await cle(), brut.slice(12));
  return JSON.parse(new TextDecoder().decode(p));
}

// ---------- connexion ----------
const enc = new TextEncoder();
async function deriver(mdp, email) {
  const maitre = await scrypt.scrypt(enc.encode(mdp), enc.encode("wesley-compte:" + email), 32768, 8, 1, 64);
  return { auth: Array.from(maitre.slice(0, 32), (x) => x.toString(16).padStart(2, "0")).join(""), cle: maitre.slice(32) };
}
async function essayer(email, auth) {
  const r = await fetch("/v1/connexion", { method: "POST", headers: { "Content-Type": "application/json", "X-Wesley-Appli": CLE_APPLI },
    body: JSON.stringify({ email, cle_auth: auth, appareil: nomAppareil() }) });
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) return null;
  if (!r.ok) throw new Error(d.detail || `Erreur ${r.status}`);
  return d;
}
async function connexion(ev) {
  ev.preventDefault();
  const email = $("email").value.trim().toLowerCase(), mdp = $("mdp").value;
  $("btn-connexion").disabled = true; $("btn-connexion").textContent = t("Connexion…"); $("erreur-connexion").textContent = "";
  try {
    await new Promise((r) => setTimeout(r, 30));   // laisse l'écran se mettre à jour (le calcul prend ~1 s)
    const cles = await deriver(mdp, email);
    const r = await essayer(email, cles.auth);
    if (!r) throw new Error("401");
    ecrire({ jeton: r.jeton, email: r.email, prenom: r.prenom, cle: b64(cles.cle) });
    cleAes = null; $("mdp").value = "";
    demarrer();
  } catch (e) {
    $("erreur-connexion").textContent = e.message === "401" ? t("E-mail ou mot de passe incorrect.") : e.message;
  } finally {
    $("btn-connexion").disabled = false; $("btn-connexion").textContent = t("Se connecter");
  }
}
function deconnexionLocale(message) {
  const e = lire();
  localStorage.setItem(STOCKAGE, JSON.stringify({ langue: e.langue, voix: e.voix, email: e.email }));
  cleAes = null;
  $("ecran-app").hidden = true; $("ecran-connexion").hidden = false; fermerFeuilles();
  if (e.email) $("email").value = e.email;
  $("erreur-connexion").textContent = message || "";
}

// ---------- appareils ----------
let appareils = [], derniere = "";
async function chargerAppareils() {
  try {
    appareils = (await api("GET", "/appareils")).filter((a) => !a.moi && a.plateforme !== "telephone");
  } catch { return; }
  const e = lire();
  let choisi = appareils.find((a) => a.id === e.appareil);
  if (!choisi || (!choisi.en_ligne && appareils.some((a) => a.en_ligne))) choisi = appareils.find((a) => a.en_ligne) || choisi || appareils[0];
  if (choisi) ecrire({ appareil: choisi.id });
  $("appareil-nom").textContent = choisi ? `${choisi.nom} · ${choisi.en_ligne ? t("en ligne") : t("hors ligne")}` : t("Choisis un appareil");
  dessinerListe();
  if (!$("fil").children.length || $("fil").querySelector(".vide")) dessinerFil();
}
function appareilChoisi() { return appareils.find((a) => a.id === lire().appareil); }
const plusRecent = (a, b) => { const x = a.split(".").map(Number), y = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); return false; };
function dessinerListe() {
  const l = $("liste-appareils"); l.innerHTML = "";
  if (!appareils.length) { l.innerHTML = `<p class="petit">${t("Aucun ordinateur connecté à ton compte.")}</p>`; return; }
  for (const a of appareils) {
    const b = document.createElement("button");
    b.className = "option-appareil" + (a.id === lire().appareil ? " choisi" : "");
    const etat = a.en_ligne ? (a.occupe ? t("occupé") : t("en ligne")) : t("hors ligne");
    b.innerHTML = `<span class="pastille ${a.en_ligne ? "on" : ""}"></span><span><b></b><small></small></span>`;
    b.querySelector("b").textContent = a.nom;
    b.querySelector("small").textContent = `${etat}${a.version ? " · v" + a.version : ""}${a.en_ligne && !a.accepte ? " · " + t("refuse les ordres") : ""}`;
    b.onclick = () => { ecrire({ appareil: a.id }); fermerFeuilles(); chargerAppareils(); dessinerFil(); };
    if (derniere && a.en_ligne && a.accepte && a.version && plusRecent(derniere, a.version)) {
      const m = document.createElement("span"); m.className = "maj";
      if (plusRecent("1.4.0", a.version)) { m.textContent = t("version {v} — trop ancienne pour la mise à jour à distance", { v: a.version }); m.style.opacity = ".6"; }
      else {
        m.textContent = t("Mettre à jour vers {v}", { v: derniere });
        m.onclick = (ev) => { ev.stopPropagation(); mettreAJour(a); };
      }
      b.appendChild(m);
    }
    l.appendChild(b);
  }
}
async function verifierDerniereVersion() {
  try {
    const r = await fetch(`https://api.github.com/repos/${DEPOT}/releases/latest`);
    if (r.ok) derniere = (await r.json()).tag_name.replace(/^v/, "");
  } catch { /* hors ligne */ }
}

// ---------- ordres ----------
async function envoyerOrdre(a, contenu) {
  const ordre = { ...contenu, nonce: crypto.randomUUID(), ts: Date.now() / 1000, de: nomAppareil(), vers: a.id };
  const { id } = await api("POST", "/ordres", { vers: a.id, blob: await chiffrer(ordre) });
  etat(t("{nom} travaille…", { nom: a.nom }));
  const debut = Date.now(); let recu = false;
  while (Date.now() - debut < 600000) {
    const r = await api("GET", `/ordres/${id}/attendre`);
    recu = recu || r.recu;
    if (r.pret) return dechiffrer(r.blob);
    if (!recu && Date.now() - debut > 60000) break;
  }
  throw new Error(t("{nom} n'a pas répondu.", { nom: a.nom }));
}
async function demander(texte) {
  // « ajoute du pain à ma liste » : directement dans la liste À faire du compte, même ordinateur éteint
  const m = texte.match(/^(?:ajoute|rajoute|mets|note|add|put)\s+(.+?)\s+(?:à|a|dans|sur|to|on)\s+(?:ma|la|my|the)\s+(?:liste|todo|to-do|list|liste (?:à|a) faire)\s*[.!]?$/i);
  if (m) {
    ajouter("moi", texte, "Wesley");
    try { await ajouterTache(m[1]); ajouter("wesley", t("Ajouté à ta liste : {t}", { t: m[1] }), "Wesley"); }
    catch (e) { if (e.message !== "401") ajouter("wesley", e.message, "Wesley", true); }
    return;
  }
  const a = appareilChoisi();
  if (!a) return;
  if (!a.en_ligne) { ajouter("wesley", t("{nom} est hors ligne (éteint ou Wesley fermé).", { nom: a.nom }), a.nom, true); return; }
  ajouter("moi", texte, a.nom);
  $("reacteur").classList.add("actif");
  const att = document.createElement("div"); att.className = "attente"; att.innerHTML = `<span class="points"><span></span><span></span><span></span></span>`;
  $("fil").appendChild(att); defiler();
  etat(t("Envoi à {nom}…", { nom: a.nom }));
  try {
    const r = await envoyerOrdre(a, { type: "demande", texte });
    ajouter("wesley", r.resultat || "OK", a.nom, !r.ok);
    parler(r.resultat);
  } catch (e) {
    if (e.message !== "401") ajouter("wesley", e.message, a.nom, true);
  } finally {
    att.remove(); etat(""); $("reacteur").classList.remove("actif");
  }
}
async function mettreAJour(a) {
  fermerFeuilles();
  try {
    const r = await envoyerOrdre(a, { type: "mettre_a_jour" });
    ajouter("wesley", r.resultat || t("Mise à jour de {nom} lancée : il redémarre tout seul.", { nom: a.nom }), a.nom, !r.ok);
  } catch (e) { ajouter("wesley", e.message, a.nom, true); } finally { etat(""); }
}

// ---------- fil de discussion ----------
function historique() { return lire().historique || []; }
function ajouter(qui, texte, appareil, erreur = false) {
  const h = [...historique(), { qui, texte, appareil, ts: Date.now(), erreur }].slice(-100);
  ecrire({ historique: h });
  bulle(h[h.length - 1]);
}
function bulle(m) {
  $("fil").querySelector(".vide")?.remove();
  const d = document.createElement("div");
  d.className = `bulle ${m.qui}${m.erreur ? " erreur" : ""}`;
  d.textContent = m.texte;
  const meta = document.createElement("div"); meta.className = "meta";
  meta.textContent = `${m.appareil || ""} · ${new Date(m.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  d.appendChild(meta);
  $("fil").appendChild(d); defiler();
}
function dessinerFil() {
  $("fil").innerHTML = "";
  const h = historique();
  if (!h.length) {
    const a = appareilChoisi();
    $("fil").innerHTML = `<div class="vide">${t("Que veux-tu que je fasse sur <b>{nom}</b> ?", { nom: a ? a.nom.replace(/[<>&]/g, "") : "…" })}</div>`;
  }
  h.forEach(bulle);
}
const defiler = () => requestAnimationFrame(() => ($("fil").scrollTop = $("fil").scrollHeight));
const etat = (s) => ($("etat").textContent = s);

// ---------- voix ----------
function parler(texte) {
  if (!lire().voix || !texte || !window.speechSynthesis) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(texte);
  u.lang = langue === "en" ? "en-GB" : "fr-FR";
  speechSynthesis.speak(u);
}
let reco = null;
function micro() {
  const R = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!R) { etat(t("La reconnaissance vocale n'est pas disponible dans ce navigateur.")); return; }
  if (reco) { reco.stop(); return; }
  reco = new R(); reco.lang = langue === "en" ? "en-US" : "fr-FR"; reco.interimResults = true;
  $("btn-micro").classList.add("ecoute"); etat(t("Je t'écoute…"));
  let final = "";
  reco.onresult = (e) => { final = Array.from(e.results).map((r) => r[0].transcript).join(""); $("demande").value = final; };
  reco.onend = () => {
    reco = null; $("btn-micro").classList.remove("ecoute"); etat("");
    if (final.trim()) { $("demande").value = ""; demander(final.trim()); }
  };
  reco.start();
}

// ---------- liste À faire (document « afaire » du compte, le même que sur les ordinateurs) ----------
const ETAPES = ["a_faire", "en_cours", "fait"];
const LIB = { a_faire: "à faire", en_cours: "en cours", fait: "fait" };
let taches = [];
const maintenant = () => new Date().toISOString().slice(0, 19);
async function chargerTaches() { taches = (await api("GET", "/documents/afaire")).contenu || []; return taches; }
async function sauverTaches(modif) {
  await chargerTaches();   // part de la dernière version (un ordinateur a pu la changer)
  modif(taches);
  await api("PUT", "/documents/afaire", { contenu: taches });
  dessinerTaches();
}
function ajouterTache(titre) {
  return sauverTaches((l) => l.push({ id: crypto.randomUUID().replace(/-/g, "").slice(0, 8), titre: titre.trim(), note: "", echeance: "",
    rappel: "", priorite: "normale", statut: "a_faire", cree: maintenant(), modifie: maintenant(), fait_le: "" }));
}
function dessinerTaches() {
  const l = $("liste-afaire"); l.innerHTML = "";
  if (!taches.length) { l.innerHTML = `<p class="petit">${t("Rien de prévu.")}</p>`; return; }
  for (const s of ETAPES) {
    const items = taches.filter((x) => x.statut === s);
    if (!items.length) continue;
    const h = document.createElement("div"); h.className = "colonne-titre"; h.textContent = `${t(LIB[s])} · ${items.length}`; l.appendChild(h);
    for (const x of items) {
      const b = document.createElement("button"); b.className = `tache ${x.statut}`;
      b.innerHTML = `<span class="rond"></span><span><span class="t"></span><small></small></span><span class="suppr">×</span>`;
      b.querySelector(".t").textContent = x.titre;
      b.querySelector("small").textContent = [x.echeance && "⏰ " + x.echeance.replace("T", " "), x.rappel && "🔔 " + x.rappel.replace("T", " ")].filter(Boolean).join(" · ");
      b.onclick = (ev) => {
        if (ev.target.classList.contains("suppr")) {
          if (confirm(t("Supprimer cette tâche ?"))) sauverTaches((li) => li.splice(li.findIndex((y) => y.id === x.id), 1)).catch(() => {});
          return;
        }
        const suivant = ETAPES[(ETAPES.indexOf(x.statut) + 1) % 3];
        sauverTaches((li) => { const y = li.find((z) => z.id === x.id); if (y) { y.statut = suivant; y.modifie = maintenant(); y.fait_le = suivant === "fait" ? maintenant() : ""; } }).catch(() => {});
      };
      l.appendChild(b);
    }
  }
}

// ---------- tickets ----------
async function dessinerTickets() {
  const l = $("liste-tickets"); l.innerHTML = "";
  let liste = [];
  try { liste = await api("GET", "/tickets"); } catch { return; }
  if (!liste.length) { l.innerHTML = `<p class="petit">${t("Aucun ticket.")}</p>`; return; }
  const STATUTS = { ouvert: "ouvert", en_cours: "en cours", resolu: "résolu", ferme: "fermé" };
  for (const x of liste) {
    const d = document.createElement("div"); d.className = "ticket";
    d.innerHTML = `<span class="statut ${x.statut}"></span><b></b><br><small></small>`;
    d.querySelector(".statut").textContent = t(STATUTS[x.statut] || x.statut);
    d.querySelector("b").textContent = `#${x.id} ${x.titre}`;
    d.querySelector("small").textContent = new Date(x.cree * 1000).toLocaleDateString();
    if (x.reponse) { const r = document.createElement("div"); r.className = "reponse"; r.textContent = t("Réponse : ") + x.reponse; d.appendChild(r); }
    l.appendChild(d);
  }
}
async function envoyerTicket(ev) {
  ev.preventDefault();
  const titre = $("ticket-titre").value.trim();
  if (titre.length < 3) return;
  try {
    await api("POST", "/tickets", { genre: $("ticket-genre").value, titre, description: $("ticket-description").value.trim(),
      version: "mobile", plateforme: "telephone", appareil: nomAppareil() });
    $("ticket-titre").value = ""; $("ticket-description").value = "";
    etat(t("Ticket envoyé.")); dessinerTickets();
  } catch (e) { if (e.message !== "401") alert(e.message); }
}

// ---------- feuilles ----------
function ouvrir(id) { $(id).hidden = false; }
function fermerFeuilles() { document.querySelectorAll(".feuille").forEach((f) => (f.hidden = true)); }

// ---------- démarrage ----------
let presence = null;
function demarrer() {
  $("ecran-connexion").hidden = true; $("ecran-app").hidden = false;
  $("compte-info").textContent = t("Connecté : {email}", { email: lire().email || "" });
  $("opt-voix").checked = lire().voix !== false; ecrire({ voix: lire().voix !== false });
  dessinerFil(); chargerAppareils(); verifierDerniereVersion().then(dessinerListe);
  const signaler = () => api("POST", "/appareils/presence", { nom: nomAppareil(), plateforme: "telephone", version: "mobile",
    occupe: false, accepte: false, mode: "libre" }).catch(() => {});
  signaler(); clearInterval(presence);
  presence = setInterval(() => { if (!document.hidden) { signaler(); chargerAppareils(); } }, 20000);
}
function init() {
  traduire();
  $("form-connexion").onsubmit = connexion;
  $("btn-langue-1").onclick = () => { langue = langue === "fr" ? "en" : "fr"; ecrire({ langue }); traduire(); };
  $("form-demande").onsubmit = (e) => { e.preventDefault(); const v = $("demande").value.trim(); if (v) { $("demande").value = ""; demander(v); } };
  $("btn-micro").onclick = micro;
  $("choix-appareil").onclick = () => { dessinerListe(); ouvrir("feuille-appareils"); };
  $("btn-afaire").onclick = () => { ouvrir("feuille-afaire"); dessinerTaches(); chargerTaches().then(dessinerTaches).catch(() => {}); };
  $("btn-tickets").onclick = () => { ouvrir("feuille-tickets"); dessinerTickets(); };
  $("form-afaire").onsubmit = (e) => { e.preventDefault(); const v = $("afaire-titre").value.trim(); if (v) { $("afaire-titre").value = ""; ajouterTache(v).catch(() => {}); } };
  $("form-ticket").onsubmit = envoyerTicket;
  $("btn-reglages").onclick = () => { $("opt-langue").value = langue; ouvrir("feuille-reglages"); };
  $("opt-voix").onchange = (e) => ecrire({ voix: e.target.checked });
  $("opt-langue").onchange = (e) => { langue = e.target.value; ecrire({ langue }); traduire(); dessinerFil(); };
  $("btn-effacer").onclick = () => { if (confirm(t("Effacer l'historique de ce téléphone ?"))) { ecrire({ historique: [] }); dessinerFil(); fermerFeuilles(); } };
  $("btn-deconnexion").onclick = async () => {
    if (!confirm(t("Te déconnecter de Wesley sur ce téléphone ?"))) return;
    await api("POST", "/deconnexion").catch(() => {});
    deconnexionLocale();
  };
  document.querySelectorAll(".feuille").forEach((f) => (f.onclick = (e) => (e.target === f || e.target.dataset.ferme !== undefined) && fermerFeuilles()));
  document.addEventListener("visibilitychange", () => { if (!document.hidden && lire().jeton) chargerAppareils(); });
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  if (lire().jeton && lire().cle) demarrer(); else deconnexionLocale();
}
init();
