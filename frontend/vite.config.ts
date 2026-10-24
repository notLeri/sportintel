import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [
    // Плагин должен идти до react(); routeTree.gen.ts коммитится (FE-T0.8 §22).
    tanstackRouter({
      target: "react",
      routesDirectory: "./src/app/routes",
      generatedRouteTree: "./src/app/routeTree.gen.ts",
      autoCodeSplitting: false,
    }),
    react(),
    tailwindcss(),
  ],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  // Тот же origin для SPA и API: cookie сессии работают без CORS (FE-T0.7 §3).
  server: { proxy: { "/api": backend, "/auth": backend } },
  // hidden: карты строятся для Sentry, но ссылок на них в бандле нет (FE-T0.13 §15).
  build: { sourcemap: "hidden" },
});
