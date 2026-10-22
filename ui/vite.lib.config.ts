// SPDX-License-Identifier: MIT OR Apache-2.0
import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { scopeCss } from "./scripts/scope-css.ts";

// The library build (ADR-027): ESM for `arras-ui`, `arras-ui/browser` and `arras-ui/shell`, and the
// compiled stylesheet as `styles.css`, in dist/. Declarations come from tsconfig.build.json. The
// peers (React, TanStack Query, UMF's schema browser API) stay outside, so a host has one copy of each.
// `npm run build:lib`; scripts/pack-wheel.ts packs it for the wheel.
const external = [
  /^react($|\/)/,
  /^react-dom($|\/)/,
  /^@tanstack\/react-query($|\/)/,
  /^@documentdrivendx\/umf-schema-browser($|\/)/,
  /^@databricks\/appkit-ui($|\/)/,
];

export default defineConfig({
  css: { postcss: { plugins: [scopeCss()] } },
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist-lib",
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: {
      entry: {
        index: resolve(import.meta.dirname, "src/index.ts"),
        browser: resolve(import.meta.dirname, "src/browser/index.ts"),
        shell: resolve(import.meta.dirname, "src/shell/index.ts"),
        styles: resolve(import.meta.dirname, "src/styles-entry.ts"),
      },
      formats: ["es"],
      cssFileName: "styles",
    },
    rollupOptions: { external },
  },
});
