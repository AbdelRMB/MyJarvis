# Versions de Jarvis

Chaque section `## x.y.z` devient la description de la mise à jour affichée dans l'appli
(écran **Mises à jour**). Écris pour l'utilisateur : ce qui change pour lui, pas le détail du code.

## 1.2.1
- **Corrigé : « Invalid signature in thinking block »** (cerveau Claude). L'erreur survenait souvent quand la mémoire changeait en pleine conversation (synchronisation entre appareils). Jarvis ne relit maintenant ses souvenirs que si leur texte change, et l'API ignore les anciens blocs de réflexion au lieu de refuser la demande.
- **Le bouton STOP coupe vraiment** : l'action en cours (commande, script, souris, téléchargement…) est interrompue tout de suite et les programmes qu'elle a lancés sont fermés, au lieu d'aller jusqu'au bout. Pareil avec Échap, « Jarvis, stop » et Ctrl+Alt+S. / **STOP really stops**: the running action is interrupted immediately.

## 1.2.0
- **English version**: choose French or English (Settings › Interface, or on the first screen). Interface, Jarvis's replies, speech recognition, voice and announcements switch language. / **Version anglaise** : choisis français ou anglais ; interface, réponses, reconnaissance vocale, voix et annonces suivent.
- **Cerveau OpenAI** : en plus de Claude et Ollama, utilise ta clé API OpenAI (GPT). Le modèle se choisit parmi ceux de ta clé.
- **Local ou en ligne, au choix** : au premier lancement, garde tout sur cet ordinateur (rien n'est envoyé à un serveur) ou crée un compte pour retrouver ta mémoire partout. En local, un autre appareil sera un nouveau Jarvis qui ne te connaît pas ; tu peux passer en ligne plus tard et tout envoyer dans ton compte (mémoire, réglages, connecteurs, clés).
- **Journal des mises à jour** : l'écran Mises à jour liste toutes les versions publiées et leur contenu.
- **Connexion beaucoup plus rapide** : la création de compte et la connexion pouvaient rester bloquées plusieurs minutes sur certaines box Internet (IPv6 défaillant). Jarvis passe maintenant directement par la bonne connexion, et l'écran n'attend plus la première synchronisation.
- **Moins d'attente au démarrage sur Mac** : le trousseau n'est plus relu à chaque échange avec le serveur.
- **Pas de doublon d'historique** quand la même ancienne mémoire est trouvée à deux endroits sur un appareil.
- **Bouton « Actualiser » dans l'écran Mémoire** : récupère tout de suite ce que tes autres appareils ont appris, sans attendre la synchronisation automatique.
- **Autorisations demandées une seule fois** (Mac) : l'appli est maintenant signée avec un certificat Apple, donc macOS garde le micro, l'écran, l'accessibilité et l'accès aux fichiers d'une mise à jour à l'autre. Au premier lancement, Jarvis les demande une fois (tu acceptes ou non) et ne redemande plus. Après cette mise à jour, il faudra les accorder une dernière fois.
- **Automatisations** : dis à Jarvis « quand je reçois un mail de mon père, préviens-moi » (ou crée la règle dans le nouvel écran Automatisations). Dès qu'un mail correspondant arrive, il te le dit **à voix haute** et t'envoie une notification, même si tu ne lui as pas parlé depuis longtemps et que sa fenêtre est fermée. Il peut aussi agir sur le mail (« résume-le-moi »…). Les règles sont dans ton compte, donc sur tous tes appareils.
- **Plusieurs comptes par connecteur** : autant de Gmail, messageries, agendas, GitHub ou Notion que tu veux, chacun avec son nom (perso, travail…). Tu peux dire à Jarvis lequel utiliser.
- **Interface prête dès le démarrage** : elle se charge en arrière-plan, fenêtre cachée, pour que Jarvis puisse te parler à tout moment avec ta voix choisie.
- **La dernière action gagne, sur tous tes appareils** : chaque souvenir garde la date de sa dernière action (ajout, modification, utilisation par Jarvis, suppression). Supprimé sur un appareil, il disparaît partout ; mais si un autre appareil s'en sert ou le modifie après, il reste. Ça marche même si un appareil était hors ligne.
- **Corrigé** : un souvenir supprimé depuis l'écran Mémoire revenait à la synchronisation suivante.
- **Historique de ta mémoire** : bouton « Historique » dans l'écran Mémoire, avec tout ce qui est arrivé à chaque souvenir (quoi, quand, sur quel appareil), et un bouton pour restaurer un souvenir supprimé.
- **Modifier un souvenir** : icône crayon sur chaque souvenir.
- **Mémoire en temps réel sur tous tes appareils** : un souvenir ajouté, modifié ou supprimé sur un appareil apparaît sur les autres en environ 1 seconde (avant : jusqu'à 2 minutes). Jarvis en tient compte tout de suite, même en pleine conversation, et l'écran Mémoire se met à jour tout seul.
- **Confidentialité** : l'ancienne mémoire d'un appareil n'est versée automatiquement que dans le premier compte qui s'y connecte. Une autre personne qui se connecte ensuite sur le même ordinateur ne la récupère pas.
- **Whisper ne tourne plus à l'infini** : un modèle déjà téléchargé se charge directement depuis le disque, et toutes les connexions de Jarvis évitent l'IPv6 défaillant de certaines box.
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
