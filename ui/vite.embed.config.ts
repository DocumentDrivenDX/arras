// SPDX-License-Identifier: MIT OR Apache-2.0
import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";
import { scopeCss } from "./scripts/scope-css.ts";
import { copyAssets } from "./scripts/umf-schema-browser.ts";

// The build the Python wheel ships (`arras.ui`, ADR-027): the shell without the sandbox toolbar, in
// src/arras/ui/static, with relative asset URLs so any path prefix works, and UMF's schema browser
// assets beside it. `npm run build:embed`; the wheel build runs it first (release.yml).
const OUT = resolve(import.meta.dirname, "../src/arras/ui/static");

function umfSchemaBrowser(): Plugin {
  return { name: "arras-umf-schema-browser", writeBundle: () => copyAssets(OUT) };
}

export default defineConfig({
  css: { postcss: { plugins: [scopeCss()] } },
  base: "./",
  plugins: [react(), tailwindcss(), umfSchemaBrowser()],
  build: {
    outDir: OUT,
    emptyOutDir: true,
    rollupOptions: { input: { index: resolve(import.meta.dirname, "embed.html") } },
  },
});
