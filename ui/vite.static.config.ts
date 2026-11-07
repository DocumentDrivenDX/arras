// SPDX-License-Identifier: MIT OR Apache-2.0
import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { scopeCss } from "./scripts/scope-css.ts";

// The static read-only host (ADR-031, CONTRACT-012): the Graph Browser over files, in dist-static, with
// relative asset URLs so any static file host and any path prefix works. `npm run build:static`; then
// `npm run stage:static -- OUT MODULE.umf.json GRAPH.graph.json` puts a module and its graph beside it.
export default defineConfig({
  css: { postcss: { plugins: [scopeCss()] } },
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: resolve(import.meta.dirname, "dist-static"),
    emptyOutDir: true,
    rollupOptions: { input: { index: resolve(import.meta.dirname, "static.html") } },
  },
});
