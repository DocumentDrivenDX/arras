// SPDX-License-Identifier: MIT OR Apache-2.0
import { createHash } from "node:crypto";
import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import { extname, relative, resolve, sep } from "node:path";

const uiRoot = resolve(import.meta.dirname, "..");
const output = resolve(uiRoot, "../src/arras/ui/static");
const project = await readFile(resolve(uiRoot, "../pyproject.toml"), "utf8");
const runtimeVersion = /^version\s*=\s*"([^"]+)"/m.exec(project)?.[1];
if (!runtimeVersion) throw new Error("pyproject.toml lacks the release-cohort version");
const lock = JSON.parse(await readFile(resolve(uiRoot, "package-lock.json"), "utf8"));
const schema = lock.packages["node_modules/@documentdrivendx/umf-schema-browser"];
if (!schema?.version || !schema?.integrity)
  throw new Error("package-lock lacks pinned schema-browser integrity");
const mime: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};
const files: Record<string, { sha256: string; size: number; mime: string }> = {};
async function walk(dir: string): Promise<void> {
  for (const item of await readdir(dir, { withFileTypes: true })) {
    const full = resolve(dir, item.name);
    if (item.isDirectory()) await walk(full);
    else if (item.isFile()) {
      const path = relative(output, full).split(sep).join("/");
      if (path === "asset-manifest.json") continue;
      const type = mime[extname(path).toLowerCase()];
      if (!type) throw new Error(`unsupported runtime asset MIME: ${path}`);
      const body = await readFile(full);
      files[path] = {
        sha256: createHash("sha256").update(body).digest("hex"),
        size: body.length,
        mime: type,
      };
    }
  }
}
await walk(output);
if (!files["index.html"] && !files["embed.html"]) throw new Error("compiled page entry is missing");
const html = files["embed.html"] ? "embed.html" : "index.html";
const manifest = {
  format: "arras.ui.assets",
  version: 1,
  kind: "page",
  package: { name: "@documentdrivendx/arras-ui", version: runtimeVersion },
  contracts: { console: 2, operate: 2, schema: 1, browser: 1 },
  schema_browser: {
    name: "@documentdrivendx/umf-schema-browser",
    version: schema.version,
    integrity: schema.integrity,
  },
  entry: { html },
  files,
};
await writeFile(resolve(output, "asset-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
const st = await stat(resolve(output, html));
if (!st.isFile()) throw new Error("compiled page entry is not a file");
