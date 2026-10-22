// SPDX-License-Identifier: MIT OR Apache-2.0
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";
import { scopeCss } from "./scripts/scope-css.ts";
import { ASSETS_DIR, copyAssets, DIST_SUBDIR } from "./scripts/umf-schema-browser.ts";

// UMF's schema browser: the npm package `@documentdrivendx/umf-schema-browser`, pinned exactly in
// package.json (scripts/umf-schema-browser.ts checks the pin). Its API (index.js) is bundled with
// the console; its static `assets/` directory, which the browser's iframe loads, is copied from
// node_modules to dist/umf-explorer byte for byte (never through the bundler) and served there by
// `npm run dev`.
const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
};
// The policy the dev host gives the console's page and these assets (src/arras/devhost.py): UMF's
// strict profile plus `frame-ancestors 'self'` (ui/README.md, "UMF source"). `npm run dev` sets it
// on the assets only: Vite's own page needs inline scripts for hot reload.
export const CSP =
  "default-src 'none'; base-uri 'none'; script-src 'self'; style-src 'self'; img-src 'self'; frame-src 'self' about:; connect-src 'self'; frame-ancestors 'self'";

function umfSchemaBrowser(): Plugin {
  return {
    name: "arras-umf-schema-browser",
    writeBundle(options) {
      copyAssets(options.dir ?? resolve("dist"));
    },
    configureServer(server) {
      server.middlewares.use(`/${DIST_SUBDIR}`, (req, res, next) => {
        const name = (req.url ?? "/").split(/[?#]/)[0]?.replace(/^\/+/, "") || "index.html";
        const file = resolve(ASSETS_DIR, name);
        if (!file.startsWith(ASSETS_DIR + sep) || !existsSync(file) || !statSync(file).isFile())
          return next();
        const ext = name.slice(name.lastIndexOf("."));
        res.setHeader("content-type", TYPES[ext] ?? "application/octet-stream");
        res.setHeader("content-security-policy", CSP);
        res.setHeader("x-content-type-options", "nosniff");
        res.end(readFileSync(file));
      });
    },
  };
}

// Development: `npm run dev` proxies /api to the dev host (uv run --extra devhost python -m arras.devhost).
export default defineConfig({
  css: { postcss: { plugins: [scopeCss()] } },
  plugins: [react(), tailwindcss(), umfSchemaBrowser()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000" } },
  },
});
