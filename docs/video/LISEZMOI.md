# Vidéo de démo

`demo.html` reproduit l'interface de Jarvis (mêmes couleurs, icônes, réacteur et statuts que `interface/`) et joue
un scénario minuté. `window.render(t)` dessine l'image à l'instant `t` : la vidéo est donc identique à chaque rendu.

```bash
cd docs/video
npm install                      # puppeteer-core + ffmpeg (utilise le Chrome installé)
npm run apercu -- 6.8 21.9 35.7  # captures PNG à ces instants, pour vérifier
npm run video                    # jarvis-demo.mp4, 1920x1080, 30 i/s (~2 min)
LANGUE=en npm run video          # version anglaise (interface, phrases et sous-titres en anglais)
```

Pour le README (`docs/demo.webp` et `docs/demo.mp4` en français, `docs/demo-en.*` en anglais) :

```bash
ffmpeg -i jarvis-demo.mp4 -vf "fps=10,scale=800:-1:flags=lanczos" -c:v libwebp -q:v 50 -compression_level 6 -loop 0 ../demo.webp
ffmpeg -i jarvis-demo.mp4 -vf scale=1280:-2 -c:v libx264 -preset slow -crf 25 -pix_fmt yuv420p -movflags +faststart ../demo.mp4
```

Le scénario (phrases, outils, minutage) est dans le tableau `SC` de `demo.html`. Le chemin de Chrome est dans `rendu.mjs`.
