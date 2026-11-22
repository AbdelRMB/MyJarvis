# Détecteur instantané « Hey Wesley » (facultatif)

Wesley reconnaît son nom de deux façons (voir `wesley/ecoute.py`) :

1. **Détecteur instantané openWakeWord** : il réagit dès « Hey Wesley », sans rien transcrire, pour ~2 % d'un cœur.
   Il n'est actif que si le fichier `eveil/hey_wesley.onnx` existe.
2. **Transcription Whisper** (toujours active) : chaque phrase entendue est transcrite en local. Si elle commence
   par « Wesley » (ou « Hé Wesley », « Ok Wesley »…), c'est pour lui. Ça suffit pour l'appeler, avec un petit
   temps d'analyse en plus.

openWakeWord ne fournit pas de modèle tout fait pour « Hey Wesley » : il faut l'entraîner une fois.

## Entraîner le modèle

1. Ouvrir le carnet officiel d'openWakeWord dans Google Colab (GPU gratuit) :
   https://github.com/dscripka/openWakeWord › `notebooks/automatic_model_training.ipynb`
2. Mot à détecter : `hey wesley` (le carnet fabrique lui-même des milliers d'exemples avec une voix de synthèse).
   Compter environ une heure.
3. Récupérer le fichier `.onnx` produit, le renommer `hey_wesley.onnx` et le placer dans ce dossier `eveil/`.
4. Le committer (il pèse environ 200 Ko) : `wesley.spec` et `wesley-mac.spec` l'ajoutent alors aux installateurs, et
   l'écoute de fond l'utilise automatiquement. La sensibilité se règle avec `seuil_eveil` (0,5 par défaut).
