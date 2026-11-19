from . import outil
from .. import memoire


@outil
def memoriser(fait: str, categorie: str = "general"):
    """Enregistre durablement un fait sur l'utilisateur (identité, goûts, projets, habitudes, contacts, préférences). À utiliser dès que tu apprends quelque chose d'utile.
    fait: le fait, en une phrase
    categorie: identite | preference | projet | contact | habitude | general"""
    return memoire.ajouter(fait, categorie)


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
def lister_souvenirs(categorie: str = ""):
    """Liste tous les souvenirs sur l'utilisateur avec leur identifiant (pour en modifier ou en supprimer un précisément).
    categorie: (optionnel) identite | preference | projet | contact | habitude | general"""
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
    """Liste les derniers jours où l'utilisateur a parlé à Jarvis (sur tous ses appareils), avec le nombre d'échanges.
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
