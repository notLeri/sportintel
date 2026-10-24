import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./tests/setup/vitest.setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
      // часы «устройства» совпадают с поясом профиля из фикстуры — плашка о расхождении не мешает
      env: { TZ: "America/Sao_Paulo" },
    },
  }),
);
