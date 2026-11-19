# Versions de Jarvis

Chaque section `## x.y.z` devient la description de la mise à jour affichée dans l'appli
(écran **Mises à jour**). Écris pour l'utilisateur : ce qui change pour lui, pas le détail du code.

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
