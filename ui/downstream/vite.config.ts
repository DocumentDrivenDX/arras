// SPDX-License-Identifier: MIT OR Apache-2.0
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { resolve } from "node:path";

const root = process.env.ARRAS_DOWNSTREAM_ROOT;
export default defineConfig({
  root,
  base: "./",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: { input: [resolve(root ?? ".", "index.html"), resolve(root ?? ".", "controls.html")] },
  },
});
