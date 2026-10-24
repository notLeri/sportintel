import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// Слои FSD (CONV §11): импорт только вниз; слайс — только через index.ts.
const LAYERS = [
  { type: "app", pattern: "src/app", mode: "folder" },
  { type: "pages", pattern: "src/pages/*", mode: "folder", capture: ["slice"] },
  { type: "features", pattern: "src/features/*", mode: "folder", capture: ["slice"] },
  { type: "entities", pattern: "src/entities/*", mode: "folder", capture: ["slice"] },
  { type: "shared", pattern: "src/shared/*", mode: "folder", capture: ["segment"] },
];

export default tseslint.config(
  { ignores: ["dist", "coverage", "src/shared/api/generated", "src/app/routeTree.gen.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh, boundaries },
    settings: {
      "boundaries/elements": LAYERS,
      "boundaries/include": ["src/**/*"],
      "import/resolver": { typescript: { alwaysTryTypes: true } },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-explicit-any": "error",
      "boundaries/element-types": [
        "error",
        {
          default: "disallow",
          rules: [
            { from: "app", allow: ["app", "pages", "features", "entities", "shared"] },
            {
              from: "pages",
              allow: ["features", "entities", "shared", ["pages", { slice: "${from.slice}" }]],
            },
            {
              from: "features",
              allow: ["entities", "shared", ["features", { slice: "${from.slice}" }]],
            },
            { from: "entities", allow: ["shared", ["entities", { slice: "${from.slice}" }]] },
            { from: "shared", allow: ["shared"] },
          ],
        },
      ],
      "boundaries/entry-point": [
        "error",
        {
          default: "disallow",
          rules: [
            { target: ["pages", "features", "entities"], allow: "index.ts" },
            { target: ["shared"], allow: "**" },
            { target: ["app"], allow: "**" },
          ],
        },
      ],
    },
  },
  {
    // shadcn экспортирует *Variants рядом с компонентом; файлы маршрутов TanStack — Route + компонент.
    files: ["src/shared/ui/**/*.tsx", "src/app/routes/**/*.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
  {
    files: ["*.config.{ts,js}", "tests/**/*.ts"],
    languageOptions: { globals: { ...globals.node } },
  },
);
