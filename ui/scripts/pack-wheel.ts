// SPDX-License-Identifier: MIT OR Apache-2.0
// Packs the library build (`npm run build:lib`) as the npm tarball the Python wheel carries
// (ADR-027): src/arras/ui/npm/documentdrivendx-arras-ui-<version>.tgz, with the version of pyproject.toml, so
// the package a host installs is the one its pinned wheel was built with. The release also publishes
// it, as `@documentdrivendx/arras-ui`, to the public npm registry, so that name and the registry are set
// here and the source keeps `arras-ui`.
//
//   node scripts/pack-wheel.ts        # after `npm run build:lib`
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CANONICAL_SPECS, CANONICAL_TEST_COUNTS } from "../src/testkit/inventory.ts";
import { assertNoAliasedResources, verifyAcceptanceInventory } from "./acceptance-inventory.ts";
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
for (const file of [
  "LICENSE.md",
  "LICENSE-MIT",
  "LICENSE-APACHE",
  "README.md",
  "support/qualify-downstream-theme.mjs",
  "support/QUALIFICATION.md",
]) {
  cpSync(join(UI, file), join(STAGE, file));
}
const acceptanceFiles = [
  ...CANONICAL_SPECS.map((name) => `e2e/${name}`),
  "e2e/acceptance.ts",
  "e2e/gb-fixtures.ts",
  "e2e/shots.mjs",
  "scripts/umf-schema-browser.ts",
  "src/test/defined.ts",
  "src/test/scheme.vectors.json",
  "src/lib/vocabulary.ts",
  "src/arras/conformance/module.umf.json",
  "examples/catalog/catalog.umf.json",
  "examples/catalog/seed.json",
];
const acceptanceRoot = join(STAGE, "support", "acceptance");
const inventory: Record<string, string> = {};
const packagedPath = (source: string) => {
  if (source.startsWith("src/arras/")) return join(STAGE, "support", source);
  if (source.startsWith("examples/")) return join(STAGE, "support", source);
  return join(acceptanceRoot, source);
};
for (const source of acceptanceFiles) {
  const from =
    source.startsWith("src/arras/") || source.startsWith("examples/")
      ? join(ROOT, source)
      : join(UI, source);
  if (!existsSync(from)) throw new Error(`acceptance resource is missing: ${source}`);
  const target = packagedPath(source);
  mkdirSync(dirname(target), { recursive: true });
  cpSync(from, target);
  inventory[target.replace(`${STAGE}/support/`, "").split("\\").join("/")] = createHash("sha256")
    .update(readFileSync(from))
    .digest("hex");
}
const staticAssets = join(ROOT, "src", "arras", "ui", "static", "umf-explorer");
if (!existsSync(staticAssets))
  throw new Error("build the wheel UI assets before packing the acceptance kit");
const assetFiles: string[] = [];
const walk = (dir: string, prefix = "") => {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const relative = prefix ? `${prefix}/${name}` : name;
    if (statSync(path).isDirectory()) walk(path, relative);
    else assetFiles.push(relative);
  }
};
walk(staticAssets);
for (const name of assetFiles.sort()) {
  const from = join(staticAssets, name);
  const target = join(acceptanceRoot, "dist", "umf-explorer", name);
  mkdirSync(dirname(target), { recursive: true });
  cpSync(from, target);
  inventory[`acceptance/dist/umf-explorer/${name}`] = createHash("sha256")
    .update(readFileSync(from))
    .digest("hex");
}
const listing = JSON.parse(
  execFileSync(
    process.execPath,
    [
      join(UI, "node_modules", "@playwright", "test", "cli.js"),
      "test",
      "--config",
      "scripts/playwright-inventory.config.ts",
      "--list",
      "--reporter=json",
    ],
    { cwd: UI, encoding: "utf8" },
  ),
) as { suites: Array<Record<string, unknown>> };
const discoveredCounts: Record<string, number> = {};
const countTests = (suite: Record<string, unknown>) => {
  for (const spec of (suite.specs as Array<Record<string, unknown>> | undefined) ?? [])
    for (const test of (spec.tests as Array<Record<string, unknown>> | undefined) ?? []) {
      const project = test.projectName;
      if (typeof project !== "string") throw new Error("Playwright discovery omitted project name");
      discoveredCounts[project] = (discoveredCounts[project] ?? 0) + 1;
    }
  for (const child of (suite.suites as Array<Record<string, unknown>> | undefined) ?? [])
    countTests(child);
};
for (const suite of listing.suites) countTests(suite);
for (const [project, expected] of Object.entries(CANONICAL_TEST_COUNTS)) {
  const actual = discoveredCounts[project];
  if (expected !== actual)
    throw new Error(`Playwright canonical ${project} discovery count differs`);
}
if (
  !discoveredCounts.chromium ||
  !discoveredCounts["schema-admin"] ||
  !discoveredCounts.browser ||
  !discoveredCounts.visual
)
  throw new Error("Playwright canonical project discovery is incomplete");
const expectedCounts = { ...CANONICAL_TEST_COUNTS };
writeFileSync(
  join(acceptanceRoot, "resources.json"),
  `${JSON.stringify(
    { version: 1, specs: CANONICAL_SPECS, expectedCounts, files: inventory },
    null,
    2,
  )}\n`,
);
const publicCatalog = JSON.parse(readFileSync(join(ROOT, "src/arras/public-api.json"), "utf8"));
const resourceBytes = readFileSync(join(acceptanceRoot, "resources.json"));
const resourceContract = publicCatalog.resources?.ui_acceptance;
const expectedResourceContract = {
  manifest_path: "support/acceptance/resources.json",
  manifest_sha256: createHash("sha256").update(resourceBytes).digest("hex"),
  version: 1,
  specs: CANONICAL_SPECS,
  expected_counts: expectedCounts,
  file_count: Object.keys(inventory).length,
};
if (JSON.stringify(resourceContract) !== JSON.stringify(expectedResourceContract))
  throw new Error("packed acceptance resource manifest differs from the public catalog");
const resourceRoot = join(STAGE, "support");
const inventoryProblems = verifyAcceptanceInventory(
  resourceRoot,
  { version: 1, specs: [...CANONICAL_SPECS], expectedCounts, files: inventory },
  UI,
);
if (inventoryProblems.length) throw new Error(inventoryProblems.join("\n"));
assertNoAliasedResources(resourceRoot);
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
