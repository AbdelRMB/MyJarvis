import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// `npm run dev` : interface sur http://localhost:5173 branchée sur le serveur Python (port 7777)
// `npm run build` : compile dans wesley/static, servi directement par le serveur Python
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "../wesley/static", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:7777",
      "/ws": { target: "ws://127.0.0.1:7777", ws: true },
    },
  },
});
