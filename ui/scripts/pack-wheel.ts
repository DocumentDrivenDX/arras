// SPDX-License-Identifier: MIT OR Apache-2.0
// Packs the library build (`npm run build:lib`) as the npm tarball the Python wheel carries
// (ADR-027): src/arras/ui/npm/documentdrivendx-arras-ui-<version>.tgz, with the version of pyproject.toml, so
// the package a host installs is the one its pinned wheel was built with. The release also publishes
// it, as `@documentdrivendx/arras-ui`, to the public npm registry, so that name and the registry are set
// here and the source keeps `arras-ui`.
//
//   node scripts/pack-wheel.ts        # after `npm run build:lib`
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { packedManifest } from "./pack-manifest.ts";

const UI = fileURLToPath(new URL("..", import.meta.url));
const ROOT = join(UI, "..");
const DIST = join(UI, "dist-lib");
const OUT = join(ROOT, "src", "arras", "ui", "npm");
const STAGE = join(UI, ".pack", "package");
const REGISTRY = "https://registry.npmjs.org/";
const REPOSITORY = "git+https://github.com/DocumentDrivenDX/arras.git";

const version = /^version\s*=\s*"([^"]+)"/m.exec(
  readFileSync(join(ROOT, "pyproject.toml"), "utf8"),
)?.[1];
if (!version) throw new Error("pyproject.toml has no version");
if (!existsSync(join(DIST, "index.js"))) throw new Error("run `npm run build:lib` first");

const source = JSON.parse(readFileSync(join(UI, "package.json"), "utf8"));
rmSync(join(UI, ".pack"), { recursive: true, force: true });
mkdirSync(STAGE, { recursive: true });
cpSync(DIST, join(STAGE, "dist"), { recursive: true });
rmSync(join(STAGE, "dist", "styles.js"), { force: true }); // the stylesheet's entry stub
for (const file of ["LICENSE.md", "LICENSE-MIT", "LICENSE-APACHE", "README.md"]) {
  cpSync(join(UI, file), join(STAGE, file));
}
writeFileSync(
  join(STAGE, "package.json"),
  `${JSON.stringify(packedManifest(source, version, REGISTRY, REPOSITORY), null, 2)}\n`,
);
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
execFileSync("npm", ["pack", "--pack-destination", OUT, "--ignore-scripts"], {
  cwd: STAGE,
  stdio: "inherit",
});
