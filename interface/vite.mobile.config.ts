import { rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Wesley mobile (appli web pour téléphone) : réutilise les composants, le style et les traductions de l'interface
// de bureau (src/), compilée dans serveur/mobile, servie par le serveur de comptes sur /mobile/.
// `npm run build:mobile` ; en direct : `npm run dev:mobile` (http://localhost:5174/mobile/, branché sur le serveur
// de comptes indiqué par WESLEY_SERVEUR, par défaut le serveur officiel).
const sortie = fileURLToPath(new URL("../serveur/mobile", import.meta.url));

export default defineConfig(({ command }) => {
  if (command === "build") rmSync(`${sortie}/app`, { recursive: true, force: true }); // anciennes versions compilées
  return {
    root: "mobile",
    base: "/mobile/",
    publicDir: false, // icônes, manifeste, pages légales et service worker sont déjà dans serveur/mobile
    plugins: [react(), tailwindcss()],
    build: { outDir: sortie, emptyOutDir: false, assetsDir: "app", chunkSizeWarningLimit: 1500 },
    server: {
      port: 5174,
      proxy: {
        "/v1": { target: process.env.WESLEY_SERVEUR || "https://wesley.abdelrahimriche.com", changeOrigin: true },
        "/mobile/config.js": { target: process.env.WESLEY_SERVEUR || "https://wesley.abdelrahimriche.com", changeOrigin: true },
      },
    },
  };
});
