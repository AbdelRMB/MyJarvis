# Versions de Jarvis

Chaque section `## x.y.z` devient la description de la mise à jour affichée dans l'appli
(écran **Mises à jour**). Écris pour l'utilisateur : ce qui change pour lui, pas le détail du code.

## 1.1.1
- **Connexion beaucoup plus rapide** : la création de compte et la connexion pouvaient rester bloquées plusieurs minutes sur certaines box Internet (IPv6 défaillant). Jarvis passe maintenant directement par la bonne connexion, et l'écran n'attend plus la première synchronisation.
- **Moins d'attente au démarrage sur Mac** : le trousseau n'est plus relu à chaque échange avec le serveur.
- **Pas de doublon d'historique** quand la même ancienne mémoire est trouvée à deux endroits sur un appareil.
- **Bouton « Actualiser » dans l'écran Mémoire** : récupère tout de suite ce que tes autres appareils ont appris, sans attendre la synchronisation automatique.
- **Autorisations demandées une seule fois** (Mac) : l'appli est maintenant signée avec un certificat Apple, donc macOS garde le micro, l'écran, l'accessibilité et l'accès aux fichiers d'une mise à jour à l'autre. Au premier lancement, Jarvis les demande une fois (tu acceptes ou non) et ne redemande plus. Après cette mise à jour, il faudra les accorder une dernière fois.
- **Trousseau : plus de mot de passe à répétition** (Mac) : Jarvis ne lit ses identifiants qu'une fois par lancement et ne réécrit que ce qui a changé. Avec la signature stable, « Toujours autoriser » suffit une fois pour toutes.
- **Nouvel onglet Réglages › Autorisations** : voir chaque accès, l'accorder, le retirer ou ouvrir le bon réglage du système.
- **Jarvis ne bloque plus l'arrêt de l'ordinateur** : à l'extinction, au redémarrage ou à la déconnexion (Windows et Mac), il se ferme tout de suite au lieu de se cacher.
- **Mises à jour sans jeton GitHub** : le projet est maintenant public (github.com/AbdelRMB/MyJarvis), plus rien à configurer pour recevoir les nouvelles versions.

## 1.1.0
- **Comptes Jarvis** : crée ton compte (e-mail + mot de passe) ou connecte-toi au lancement. Ta mémoire, ton historique, tes connecteurs et tes réglages sont dans ton compte et te suivent sur tous tes appareils, PC ou Mac. Chaque personne a son propre Jarvis.
- **Secrets chiffrés** : ta clé API Claude et les mots de passe des connecteurs sont chiffrés avec ton mot de passe avant l'envoi. Le serveur ne peut pas les lire, et ils sont réinstallés automatiquement quand tu te connectes sur un nouvel appareil.
- **Ta mémoire actuelle est récupérée** : à la première connexion sur un appareil, Jarvis envoie dans ton compte tout ce qu'il savait déjà (ancienne version, OneDrive), sans doublon. Bouton « Envoyer la mémoire de cet appareil » dans Réglages › Application pour le refaire.
- **Plus besoin d'OneDrive** : la synchronisation passe par ton serveur Jarvis (toutes les 2 minutes, et ça marche hors ligne : les changements partent dès que le réseau revient).
- Réglages › Application › « Mon compte » : synchroniser, se déconnecter.

## 1.0.4
- **Mises à jour intégrées** : écran « Mises à jour » pour voir les nouvelles versions, lire ce qu'elles contiennent et installer la dernière ou une version précise, sans désinstaller. Raccourci « Mettre à jour Jarvis » dans la recherche (menu Démarrer / Spotlight).
- **Démarrage discret** : à l'allumage de l'ordinateur, Jarvis tourne en fond sans charger son interface ; elle s'ouvre seulement quand tu l'appelles. Plus d'annonce « Tous les systèmes sont opérationnels ».
- **Mémoire partagée** : bouton « Envoyer la mémoire de ce PC » (Réglages › Application) pour verser dans OneDrive ce qu'un PC savait avant, sans rien écraser. Le OneDrive personnel est utilisé en priorité sur tous les appareils.
- **Mac** : lancement automatique à l'ouverture de session activé d'office ; connecteurs MCP inclus dans l'appli.

## 1.0.3
- Version de départ (Windows et macOS).
