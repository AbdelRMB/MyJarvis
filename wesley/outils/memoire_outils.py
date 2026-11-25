from . import outil
from .. import memoire


@outil
def memoriser(fait: str, categorie: str = "general"):
    """Enregistre durablement un fait sur l'utilisateur (identité, goûts, projets, habitudes, contacts, préférences). À utiliser dès que tu apprends quelque chose d'utile.
    fait: le fait, en une phrase
    categorie: identite | preference | projet | contact | habitude | general | consigne (= comment l'utilisateur veut que tu te comportes ou répondes : « réponds en une phrase », « tutoie-moi »…)"""
    return memoire.ajouter(fait, categorie)


@outil
def retenir_lecon(lecon: str):
    """Enregistre une leçon de méthode pour faire mieux la prochaine fois : ce qui a marché après un échec, ou une correction de l'utilisateur sur ta façon de faire. Pas pour les faits sur l'utilisateur (memoriser).
    lecon: la leçon, en une phrase concrète et réutilisable (quand / quoi faire / quoi éviter)"""
    return memoire.ajouter(lecon, "lecon")


@outil
def oublier(texte: str):
    """Supprime de la mémoire les faits contenant ce texte.
    texte: texte à rechercher dans les faits à supprimer"""
    return memoire.supprimer(texte)


@outil
def chercher_memoire(requete: str):
    """Cherche dans la mémoire et dans l'historique des conversations passées.
    requete: mots-clés"""
    return memoire.chercher(requete)


@outil
def chercher_partout(requete: str):
    """Cherche en une fois dans TOUT ce que Wesley sait : souvenirs, conversations passées, transcriptions (cours, réunions… de tous tes appareils), documents indexés (PDF, Word…) et liste À faire. À utiliser quand on ne sait pas où est l'information (« où on a parlé de … ? », « qu'est-ce que je sais sur … ? ») ; sinon l'outil spécialisé suffit.
    requete: le sujet, en quelques mots (par le sens : d'autres mots que ceux de la source marchent aussi)"""
    from .. import recherche
    return recherche.en_texte(recherche.chercher_partout(requete), requete)


@outil
def lister_souvenirs(categorie: str = ""):
    """Liste tous les souvenirs sur l'utilisateur avec leur identifiant (pour en modifier ou en supprimer un précisément).
    categorie: (optionnel) identite | preference | projet | contact | habitude | general | lecon"""
    faits = [f for f in memoire._charger() if not categorie or f.get("categorie") == categorie]
    return "\n".join(f"[{(f.get('fid') or '')[:8]}] ({f.get('categorie', 'general')}) {f['fait']}" for f in faits) or "Mémoire vide."


@outil
def modifier_souvenir(souvenir: str, nouveau_texte: str, categorie: str = ""):
    """Corrige un souvenir existant (au lieu de le supprimer puis d'en recréer un). Utilise-le dès qu'une info de ta mémoire est fausse ou a changé.
    souvenir: identifiant entre crochets (via lister_souvenirs) ou un morceau du texte actuel du souvenir
    nouveau_texte: le texte corrigé, complet
    categorie: (optionnel) nouvelle catégorie"""
    faits = memoire._charger()
    cle = souvenir.strip("[] ").lower()
    trouves = [f for f in faits if (f.get("fid") or "").startswith(cle)] or [f for f in faits if cle in f["fait"].lower()]
    if not trouves:
        return "Aucun souvenir ne correspond. Utilise lister_souvenirs pour trouver le bon."
    if len(trouves) > 1:
        return "Plusieurs souvenirs correspondent, précise avec l'identifiant :\n" + "\n".join(
            f"[{(f.get('fid') or '')[:8]}] {f['fait']}" for f in trouves[:15])
    f = trouves[0]
    memoire.modifier(f["fid"], nouveau_texte, categorie or None)
    return f"Souvenir corrigé : « {f['fait']} » → « {nouveau_texte} »"


@outil
def historique_jours(nombre: int = 14):
    """Liste les derniers jours où l'utilisateur a parlé à Wesley (sur tous ses appareils), avec le nombre d'échanges.
    nombre: combien de jours (défaut 14)"""
    jours = memoire.fichiers_par_jour()
    lignes = []
    for jour in sorted(jours, reverse=True)[:max(1, min(int(nombre), 120))]:
        n = sum(len(f.read_text(encoding="utf-8").splitlines()) for f in jours[jour])
        pcs = sorted({f.stem.split("__")[1] for f in jours[jour] if "__" in f.stem})
        lignes.append(f"{jour} : {n} lignes ({', '.join(pcs) or 'cet appareil'})")
    return "\n".join(lignes) or "Aucun historique."


@outil
def historique_lire(jour: str, appareil: str = ""):
    """Relit la conversation complète d'un jour (tous appareils fusionnés, dans l'ordre). Pour retrouver ce qui a été dit ou fait.
    jour: date au format AAAA-MM-JJ (voir historique_jours)
    appareil: (optionnel) ne garder qu'un appareil"""
    fichiers = memoire.fichiers_par_jour().get(jour.strip())
    if not fichiers:
        return f"Pas d'historique le {jour}."
    lignes = [l for _, pc, l in memoire.lignes_du_jour(fichiers) if not appareil or appareil.lower() in pc.lower()]
    texte = "\n".join(lignes)
    return texte[-15000:] if len(texte) > 15000 else (texte or "Rien pour cet appareil ce jour-là.")


@outil
def apprendre_prononciation(mot: str, prononciation: str):
    """Corrige la façon dont ta voix prononce un mot (« ne dis pas X, on dit Y », « tu prononces mal Kyutai »). Écris la prononciation comme elle se lit en français.
    mot: le mot tel qu'il s'écrit (ex : Kyutai)
    prononciation: comment le dire, écrit phonétiquement en français (ex : kyou-taï)"""
    from .. import prononciation as p
    p.apprendre(mot, prononciation)
    return f"Noté : je dirai « {prononciation} » pour « {mot} »."


@outil
def confirmer_memoire(proposition: str, accepter: bool):
    """Applique la réponse de l'utilisateur à une « mémoire à vérifier » (un souvenir qui semble périmé ou contredit) : accepter=true met la mémoire à jour, false la garde telle quelle.
    proposition: identifiant entre crochets de la proposition
    accepter: true si l'utilisateur confirme le changement, false sinon"""
    from .. import consolidation
    return consolidation.repondre(proposition.strip("[] "), bool(accepter))


@outil
def ranger_memoire():
    """Range la mémoire maintenant : fusionne les souvenirs en double, repère ceux qui se contredisent (à confirmer avec l'utilisateur) et résume la semaine passée. Fait automatiquement chaque jour ; à utiliser quand l'utilisateur le demande."""
    from .. import consolidation
    r = consolidation.consolider(forcer=True)
    parties = [f"{r.get('fusions', 0)} doublon(s) fusionné(s)", f"{r.get('contradictions', 0)} souvenir(s) à vérifier"]
    if r.get("semaine"):
        parties.append("résumé de la semaine passée ajouté")
    return "Mémoire rangée : " + ", ".join(parties) + "."
