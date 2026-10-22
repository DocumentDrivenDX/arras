// SPDX-License-Identifier: MIT OR Apache-2.0
import { cpSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const root = process.env.ARRAS_DOWNSTREAM_ROOT;

function installedSchemaBrowserAssetsPlugin(): Plugin {
  return {
    name: "arras-downstream-schema-browser-assets",
    writeBundle(options) {
      const hostRoot = resolve(root ?? ".");
      const consumerRequire = createRequire(join(hostRoot, "package.json"));
      const assetIndex = consumerRequire.resolve(
        "@documentdrivendx/umf-schema-browser/assets/index.html",
      );
      const packageRoot = dirname(dirname(assetIndex));
      const arrasPackage = JSON.parse(
        readFileSync(consumerRequire.resolve("@documentdrivendx/arras-ui/package.json"), "utf8"),
      ) as { dependencies?: Record<string, string> };
      const schemaBrowserPackage = JSON.parse(
        readFileSync(join(packageRoot, "package.json"), "utf8"),
      ) as { version?: string };
      if (
        schemaBrowserPackage.version !==
        arrasPackage.dependencies?.["@documentdrivendx/umf-schema-browser"]
      ) {
        throw new Error("installed schema-browser version differs from packed Arras dependency");
      }
      cpSync(join(packageRoot, "assets"), join(options.dir ?? resolve(hostRoot, "dist"), "umf-explorer"), {
        recursive: true,
      });
    },
  };
}

export default defineConfig({
  root,
  base: "./",
  plugins: [react(), installedSchemaBrowserAssetsPlugin()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: { input: [resolve(root ?? ".", "index.html"), resolve(root ?? ".", "controls.html")] },
  },
});
