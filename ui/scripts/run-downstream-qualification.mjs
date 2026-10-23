// SPDX-License-Identifier: MIT OR Apache-2.0
// Build and run both downstream routes from the same wheel-carried npm tarball/catalog cohort.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmodSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ui = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(ui, "..");
const wheel = resolve(process.argv[2] ?? join(repo, "dist/arras-0.6.0-py3-none-any.whl"));
for (const arg of process.argv.slice(3))
  assert.ok(
    ["--update-baselines", "--update-canonical-baselines", "--narrow-only"].includes(arg),
    `unknown argument ${arg}`,
  );
const updateBaselines = process.argv.includes("--update-baselines");
const updateCanonicalBaselines = process.argv.includes("--update-canonical-baselines");
const narrowOnly = process.argv.includes("--narrow-only");
assert.ok(existsSync(wheel), `missing wheel: ${wheel}; run uv build first`);
const temp = mkdtempSync(join(tmpdir(), "arras-downstream-qualification-"));
const venv = join(temp, "venv");
const extracted = join(temp, "wheel");
const hostRoot = join(temp, "host");
const hostDist = join(hostRoot, "dist");
const controlsDist = join(hostRoot, "controls-dist");
const modules = join(hostRoot, "node_modules");
const themePackageSource = join(repo, "tests/downstream/theme-package");
const themePackage = join(hostRoot, "theme-package");
mkdirSync(extracted, { recursive: true });
mkdirSync(hostRoot, { recursive: true });
execFileSync("python3", [
  "-c",
  "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])",
  wheel,
  extracted,
]);
const pyRoot = join(extracted, "arras");
const catalog = JSON.parse(readFileSync(join(pyRoot, "public-api.json"), "utf8"));
const tarballPath = join(
  pyRoot,
  "ui/npm",
  readdirSync(join(pyRoot, "ui/npm")).find((name) => name.endsWith(".tgz")),
);
const tarTemp = join(temp, "tarball");
mkdirSync(tarTemp);
execFileSync("tar", ["-xzf", tarballPath, "-C", tarTemp, "--strip-components=1"]);
const pkg = JSON.parse(readFileSync(join(tarTemp, "package.json"), "utf8"));
assert.equal(catalog.distribution.npm.version_source, "pyproject.toml");
assert.equal(pkg.name, catalog.distribution.npm.name);
const metadataFile = readdirSync(extracted).find((name) => name.endsWith(".dist-info"));
const wheelMetadata = readFileSync(join(extracted, metadataFile, "METADATA"), "utf8");
assert.match(
  wheelMetadata,
  new RegExp(`^Version: ${pkg.version}$`, "m"),
  "npm artifact and wheel must share the exact version cohort",
);
writeFileSync(
  join(hostRoot, "package.json"),
  JSON.stringify(
    { name: "arras-downstream-host", version: "1.0.0", private: true, type: "module" },
    null,
    2,
  ),
);
const npmConfig = {
  ...process.env,
  npm_config_userconfig: "/dev/null",
  npm_config_registry: "https://registry.npmjs.org/",
};
execFileSync(
  "npm",
  [
    "install",
    "--ignore-scripts",
    "--no-audit",
    "--no-fund",
    "--package-lock=false",
    tarballPath,
    "react@19.3.0",
    "react-dom@19.3.0",
    "@types/react@19.3.0",
    "@types/react-dom@19.3.0",
    "typescript@6.0.3",
    "@types/node@26.6.4",
    "vite@8.3.2",
    "@vitejs/plugin-react@6.1.1",
    "@playwright/test@1.63.0",
    "@axe-core/playwright@4.13.0",
  ],
  { cwd: hostRoot, env: npmConfig, stdio: "inherit" },
);
cpSync(themePackageSource, themePackage, { recursive: true });
execFileSync(
  process.execPath,
  [join(modules, "typescript/bin/tsc"), "-p", join(themePackage, "tsconfig.json")],
  { cwd: themePackage },
);
const themePackOutput = execFileSync("npm", ["pack", "--silent", "--pack-destination", temp], {
  cwd: themePackage,
  encoding: "utf8",
});
const themeTarball = join(temp, themePackOutput.trim().split("\n").at(-1));
const themeTarTemp = join(temp, "theme-tarball");
mkdirSync(themeTarTemp);
execFileSync("tar", ["-xzf", themeTarball, "-C", themeTarTemp, "--strip-components=1"]);
const themePkg = JSON.parse(readFileSync(join(themeTarTemp, "package.json"), "utf8"));
assert.equal(themePkg.name, "@arras-fixtures/neutral-theme");
assert.deepEqual(Object.keys(themePkg.peerDependencies).sort(), [
  "@documentdrivendx/arras-ui",
  "react",
]);
assert.equal(themePkg.peerDependencies["@documentdrivendx/arras-ui"], pkg.version);
assert.ok(
  existsSync(join(themeTarTemp, "dist/index.js")) &&
    existsSync(join(themeTarTemp, "dist/index.d.ts")),
);
execFileSync("uv", ["venv", venv], { cwd: temp });
const python = join(venv, "bin/python");
execFileSync("uv", ["pip", "install", "--python", python, `${wheel}[devhost]`], { cwd: temp });
const npmScope = join(modules, "@documentdrivendx");
const arrasPackageDir = join(npmScope, "arras-ui");
execFileSync(
  "npm",
  ["install", "--ignore-scripts", "--no-audit", "--no-fund", "--package-lock=false", themeTarball],
  { cwd: hostRoot, env: npmConfig, stdio: "inherit" },
);
const qualifyBin = join(arrasPackageDir, pkg.bin["arras-ui-qualify"]);
assert.ok(
  existsSync(qualifyBin),
  "wheel-carried npm artifact is missing its declared qualification bin",
);
const themeScope = join(modules, "@arras-fixtures");
const themeRequire = createRequire(join(themeScope, "neutral-theme", "package.json"));
const hostRequire = createRequire(join(hostRoot, "host.html"));
assert.equal(
  realpathSync(themeRequire.resolve("react")),
  realpathSync(hostRequire.resolve("react")),
  "the packed theme and Arras host must resolve one React installation",
);
assert.equal(
  realpathSync(themeRequire.resolve("@documentdrivendx/arras-ui/package.json")),
  realpathSync(join(npmScope, "arras-ui", "package.json")),
  "the theme must resolve the wheel-carried Arras package from the same host node_modules",
);
const regularFiles = (root, directory = root) =>
  readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isSymbolicLink())
      throw new Error(`installed schema-browser asset is a symlink: ${path}`);
    if (entry.isDirectory()) return regularFiles(root, path);
    if (!entry.isFile())
      throw new Error(`installed schema-browser asset is not a regular file: ${path}`);
    return [relative(root, path).split("\\").join("/")];
  });
const assertSameFileTree = (expectedRoot, actualRoot, reason) => {
  const expectedFiles = regularFiles(expectedRoot).sort();
  const actualFiles = regularFiles(actualRoot).sort();
  assert.deepEqual(actualFiles, expectedFiles, `${reason}: file inventory differs`);
  for (const name of expectedFiles)
    assert.deepEqual(
      readFileSync(join(actualRoot, name)),
      readFileSync(join(expectedRoot, name)),
      `${reason}: ${name} bytes differ`,
    );
};
for (const name of ["host.html", "host.tsx", "controls.html", "controls.tsx", "host-frame.css"])
  cpSync(join(ui, "downstream", name), join(hostRoot, name));
cpSync(join(hostRoot, "host.html"), join(hostRoot, "index.html"));
cpSync(join(themeTarTemp, "src/theme.css"), join(hostRoot, "theme.css"));
cpSync(join(themeTarTemp, "src/favicon.svg"), join(hostRoot, "favicon.svg"));
cpSync(join(ui, "downstream/vite.config.ts"), join(hostRoot, "vite.config.ts"));
writeFileSync(
  join(hostRoot, "tsconfig.json"),
  JSON.stringify({
    compilerOptions: {
      jsx: "react-jsx",
      target: "ES2022",
      module: "ESNext",
      moduleResolution: "Bundler",
      lib: ["ESNext", "DOM"],
      types: ["vite/client", "node"],
      skipLibCheck: true,
    },
  }),
);
execFileSync(
  process.execPath,
  [join(modules, "typescript/bin/tsc"), "--noEmit", "-p", join(hostRoot, "tsconfig.json")],
  { cwd: hostRoot, stdio: "inherit" },
);
execFileSync(
  process.execPath,
  [join(modules, "vite/bin/vite.js"), "build", "--config", join(hostRoot, "vite.config.ts")],
  { cwd: hostRoot, env: { ...process.env, ARRAS_DOWNSTREAM_ROOT: hostRoot }, stdio: "inherit" },
);
const schemaBrowserAssetIndex = hostRequire.resolve(
  "@documentdrivendx/umf-schema-browser/assets/index.html",
);
const schemaBrowserRoot = dirname(dirname(schemaBrowserAssetIndex));
const schemaBrowserPackage = JSON.parse(
  readFileSync(join(schemaBrowserRoot, "package.json"), "utf8"),
);
assert.equal(
  schemaBrowserPackage.version,
  pkg.dependencies["@documentdrivendx/umf-schema-browser"],
  "host schema-browser assets must come from Arras's exact installed dependency pin",
);
const builtSchemaBrowserAssets = join(hostDist, "umf-explorer");
const installedSchemaBrowserAssets = join(schemaBrowserRoot, "assets");
const packedSchemaBrowserAssets = join(arrasPackageDir, "support/acceptance/dist/umf-explorer");
assertSameFileTree(
  installedSchemaBrowserAssets,
  builtSchemaBrowserAssets,
  "compiled host schema-browser assets differ from the installed dependency",
);
assertSameFileTree(
  packedSchemaBrowserAssets,
  builtSchemaBrowserAssets,
  "compiled host schema-browser assets differ from the wheel-carried public assets",
);
cpSync(hostDist, controlsDist, { recursive: true });
cpSync(join(hostDist, "controls.html"), join(controlsDist, "index.html"));
const themeDir = join(temp, "theme");
execFileSync(
  "uv",
  [
    "run",
    "python",
    join(repo, "tests/downstream/theme/build_manifest.py"),
    themeDir,
    "--ui-version",
    pkg.version,
    "--package-dir",
    themeTarTemp,
  ],
  { cwd: repo },
);
const py = spawn(
  python,
  [
    join(repo, "tests/downstream/serve_prebuilt.py"),
    "--static",
    join(pyRoot, "ui/static"),
    "--theme",
    join(themeDir, "theme-manifest.json"),
    "--port",
    "8765",
  ],
  { cwd: temp, stdio: "inherit" },
);
const brandedDevhostPath = join(hostRoot, "branded_devhost.py");
writeFileSync(
  brandedDevhostPath,
  `import sys
from arras.devhost import main
from arras.branding import Brand
from arras.distribution import DistributionConfig

main(
    ["--port", sys.argv[1], "--ui", sys.argv[2]],
    distribution=DistributionConfig(
        brand=Brand(name="Neutral Host", title="Neutral Host Console", logo="theme")
    ),
)
`,
);
const brandedDevhost = (port, directory) =>
  spawn(python, [brandedDevhostPath, String(port), directory], {
    cwd: temp,
    env: { ...process.env, PYTHONPATH: "", PYTHONNOUSERSITE: "1" },
    stdio: "inherit",
  });
const mainHost = brandedDevhost(8766, hostDist);
const schemaHost = brandedDevhost(8777, hostDist);
const checkerHost = brandedDevhost(8768, controlsDist);
async function ready(url, process) {
  for (let i = 0; i < 80; i++) {
    if (process.exitCode !== null)
      throw new Error(`fixture server exited before ready (${process.exitCode})`);
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error(`fixture server did not become ready: ${url}`);
}
try {
  await ready("http://127.0.0.1:8765/", py);
  await ready("http://127.0.0.1:8766/", mainHost);
  await ready("http://127.0.0.1:8777/", schemaHost);
  await ready("http://127.0.0.1:8768/", checkerHost);
  const help = execFileSync(process.execPath, [qualifyBin, "--help"], { encoding: "utf8" });
  assert.match(help, /--baselines <dir>/);
  let invalidArgsExit = 0;
  try {
    execFileSync(process.execPath, [qualifyBin, "http://127.0.0.1/", "--bogus"]);
  } catch (error) {
    invalidArgsExit = error.status;
  }
  assert.equal(invalidArgsExit, 2, "packed CLI must reject unknown arguments with exit 2");
  for (const args of [
    ["http://127.0.0.1/", "--console", "--console"],
    ["http://127.0.0.1/", "--output", "one", "--output", "two"],
    ["https://probe-user:probe-password@example.invalid/"],
  ]) {
    let result;
    try {
      execFileSync(process.execPath, [qualifyBin, ...args], { encoding: "utf8" });
      throw new Error("invalid packed CLI arguments unexpectedly succeeded");
    } catch (error) {
      result = error;
    }
    assert.equal(result.status, 2, "packed CLI must reject malformed arguments with exit 2");
    assert.ok(
      !String(result.stderr).includes("probe-user") &&
        !String(result.stderr).includes("probe-password"),
      "CLI diagnostics must not echo URL credentials",
    );
  }
  const outputDir = join(repo, "tests/downstream/evidence", process.platform);
  const baselines = join(repo, "tests/downstream/baselines", process.platform);
  const receipts = [];
  const run = (url, ...flags) => {
    const args = [qualifyBin, url, ...flags, "--output", outputDir, "--baselines", baselines];
    if (updateBaselines) args.push("--update-baselines");
    const output = execFileSync(process.execPath, args, { cwd: hostRoot, encoding: "utf8" });
    assert.ok(
      !output.includes("token=sentinel"),
      "success receipt/stdout must omit URL query values",
    );
    const receiptLine = output.trim().split("\n").at(-1);
    receipts.push(JSON.parse(receiptLine));
  };
  run("http://127.0.0.1:8765/?token=sentinel");
  run("http://127.0.0.1:8765/", "--console");
  run("http://127.0.0.1:8768/", "--host-build");
  run("http://127.0.0.1:8768/", "--host-build", "--console");

  if (narrowOnly) {
    process.stdout.write(
      `Narrow downstream qualification passed: ${receipts.length} routes, ${process.platform}.\n`,
    );
  } else {
    const evidenceRoot = join(repo, "tests/downstream/evidence", process.platform);
    mkdirSync(evidenceRoot, { recursive: true });
    const rawReportPath = join(temp, "playwright-raw.json");
    const reportPath = join(evidenceRoot, "playwright-summary-neutral-theme.json");
    const snapshotPolicy = updateCanonicalBaselines ? "all" : "none";
    const acceptanceConfig = `import { createAcceptanceConfig } from "@documentdrivendx/arras-ui/testkit";
export default {
  ...createAcceptanceConfig({
    baseURL: "http://127.0.0.1:8766",
    schemaBaseURL: "http://127.0.0.1:8777",
    outputDir: ${JSON.stringify(join(temp, "playwright-results"))},
    themeId: "neutral-theme",
    expectedBrand: { name: "Neutral Host", title: "Neutral Host Console", logo: "theme" },
    expectedSurface: { light: "rgb(248, 250, 252)", dark: "rgb(2, 6, 23)" },
    ...(process.platform === "darwin" ? { baselineDir: ${JSON.stringify(join(repo, "tests/downstream/baselines/darwin/neutral-theme"))} } : {}),
  }),
  updateSnapshots: ${JSON.stringify(snapshotPolicy)},
  reporter: [["json", { outputFile: ${JSON.stringify(rawReportPath)} }]],
};
`;
    writeFileSync(join(hostRoot, "playwright.config.mjs"), acceptanceConfig);
    let fullSuiteExit = 0;
    try {
      execFileSync(
        process.execPath,
        [
          join(modules, "@playwright/test/cli.js"),
          "test",
          "--config",
          join(hostRoot, "playwright.config.mjs"),
        ],
        { cwd: hostRoot, env: process.env, stdio: "inherit" },
      );
    } catch (error) {
      fullSuiteExit = error.status ?? 1;
    }
    assert.ok(
      existsSync(rawReportPath),
      "full canonical Playwright suite must retain its JSON report",
    );
    const playReport = JSON.parse(readFileSync(rawReportPath, "utf8"));
    const projectCounts = new Map();
    const countReportTests = (suite) => {
      for (const spec of suite.specs ?? [])
        for (const test of spec.tests ?? []) {
          const name = test.projectName;
          const counts = projectCounts.get(name) ?? {
            name,
            expected: 0,
            discovered: 0,
            passed: 0,
            failed: 0,
            skipped: 0,
          };
          counts.expected += 1;
          counts.discovered += 1;
          const result = test.results?.at(-1);
          if (result?.status === "passed") counts.passed += 1;
          else if (result?.status === "skipped") counts.skipped += 1;
          else counts.failed += 1;
          projectCounts.set(name, counts);
        }
      for (const child of suite.suites ?? []) countReportTests(child);
    };
    for (const suite of playReport.suites ?? []) countReportTests(suite);
    const canonical = JSON.parse(
      readFileSync(join(arrasPackageDir, "support/acceptance/resources.json"), "utf8"),
    );
    const expectedProjects =
      process.platform === "darwin"
        ? ["chromium", "schema-admin", "browser", "visual"]
        : ["chromium", "schema-admin", "browser"];
    const fullCounts = expectedProjects.map((name) => {
      const counts = projectCounts.get(name) ?? {
        name,
        expected: 0,
        discovered: 0,
        passed: 0,
        failed: 0,
        skipped: 0,
      };
      assert.equal(
        counts.discovered,
        canonical.expectedCounts[name],
        `canonical ${name} test count differs`,
      );
      return counts;
    });
    if (
      process.platform === "darwin" &&
      fullCounts.find((item) => item.name === "visual")?.failed
    ) {
      const reviewRoot = join(evidenceRoot, "neutral-theme-review");
      mkdirSync(reviewRoot, { recursive: true });
      const images = [];
      const collect = (directory) => {
        for (const entry of readdirSync(directory, { withFileTypes: true })) {
          const path = join(directory, entry.name);
          if (entry.isDirectory()) collect(path);
          else if (entry.isFile() && /(?:actual|expected|diff)\.png$/.test(entry.name))
            images.push(path);
        }
      };
      collect(join(temp, "playwright-results"));
      images.sort();
      for (const [index, source] of images.entries())
        cpSync(source, join(reviewRoot, `visual-${String(index + 1).padStart(3, "0")}.png`));
      writeFileSync(
        join(reviewRoot, "review-index.json"),
        `${JSON.stringify({ files: images.length, names: images.map((path) => path.split("/").at(-1)) }, null, 2)}\n`,
      );
    }
    for (const counts of fullCounts) {
      assert.equal(counts.failed, 0, `canonical ${counts.name} project has failures`);
      assert.equal(counts.skipped, 0, `canonical ${counts.name} project has unexpected skips`);
    }
    assert.equal(fullSuiteExit, 0, "full canonical Playwright suite must pass");

    const probeOptions = {
      baseURL: "http://127.0.0.1:8766",
      schemaBaseURL: "http://127.0.0.1:8777",
      outputDir: join(temp, "negative-output"),
      themeId: "negative-control",
      ...(process.platform === "darwin"
        ? { baselineDir: join(repo, "tests/downstream/baselines/darwin/neutral-theme") }
        : {}),
    };
    const runFactoryProbe = (body) => {
      const source = `import { createAcceptanceConfig } from "@documentdrivendx/arras-ui/testkit";\n${body}\n`;
      return execFileSync(process.execPath, ["--input-type=module", "-e", source], {
        cwd: hostRoot,
        encoding: "utf8",
      });
    };
    const acceptanceResource = join(arrasPackageDir, "support/acceptance/e2e/a11y.spec.ts");
    const resourceBytes = readFileSync(acceptanceResource);
    let missingResource = false;
    const missingPath = `${acceptanceResource}.missing`;
    try {
      rmSync(missingPath, { force: true });
      cpSync(acceptanceResource, missingPath);
      rmSync(acceptanceResource);
      try {
        runFactoryProbe(`createAcceptanceConfig(${JSON.stringify(probeOptions)});`);
      } catch {
        missingResource = true;
      }
    } finally {
      if (existsSync(missingPath)) cpSync(missingPath, acceptanceResource);
      rmSync(missingPath, { force: true });
    }
    assert.ok(missingResource, "packed testkit must refuse a missing canonical resource");
    writeFileSync(acceptanceResource, Buffer.concat([resourceBytes, Buffer.from("\n// tamper\n")]));
    let tamperedResource = false;
    try {
      try {
        runFactoryProbe(`createAcceptanceConfig(${JSON.stringify(probeOptions)});`);
      } catch {
        tamperedResource = true;
      }
    } finally {
      writeFileSync(acceptanceResource, resourceBytes);
    }
    assert.ok(tamperedResource, "packed testkit must refuse a changed canonical resource");
    let invalidOptions = false;
    try {
      runFactoryProbe(
        `let refused = false; try { createAcceptanceConfig({ ...${JSON.stringify(probeOptions)}, baseURL: "https://probe-user:probe-password@example.invalid/?token=sentinel" }); } catch (error) { if (String(error).includes("probe-user") || String(error).includes("sentinel")) process.exit(2); refused = true; } if (!refused) process.exit(1);`,
      );
      invalidOptions = true;
    } catch {
      invalidOptions = false;
    }
    assert.ok(
      invalidOptions,
      "packed testkit must refuse unsafe options without echoing credentials",
    );
    const controlledDir = join(hostRoot, "controlled-failure");
    mkdirSync(controlledDir, { recursive: true });
    const controlledReport = join(controlledDir, "canonical-brand-failure.json");
    writeFileSync(
      join(controlledDir, "controlled-failure.spec.mjs"),
      `import { expect, test } from "@playwright/test";\ntest("controlled failing acceptance assertion", async ({ page }) => { await page.goto("http://127.0.0.1:8766/"); await expect(page.getByRole("heading", { name: "intentionally absent" })).toBeVisible(); });\n`,
    );
    writeFileSync(
      join(controlledDir, "playwright.config.mjs"),
      `import { createAcceptanceConfig } from "@documentdrivendx/arras-ui/testkit";
const config = createAcceptanceConfig({
  baseURL: "http://127.0.0.1:8766",
  schemaBaseURL: "http://127.0.0.1:8777",
  outputDir: ${JSON.stringify(join(controlledDir, "playwright-results"))},
  themeId: "controlled-failure",
  expectedBrand: { name: "Intentionally incorrect", title: "Intentionally incorrect Console" },
  expectedSurface: { light: "rgb(248, 250, 252)", dark: "rgb(2, 6, 23)" },
  baselineDir: ${JSON.stringify(join(repo, "tests/downstream/baselines/darwin/neutral-theme"))},
});
config.reporter = [["json", { outputFile: ${JSON.stringify(controlledReport)} }]];
export default config;
`,
    );
    let controlledFailureExit = 0;
    try {
      execFileSync(
        process.execPath,
        [
          join(modules, "@playwright/test/cli.js"),
          "test",
          "--config",
          join(controlledDir, "playwright.config.mjs"),
          "--grep",
          "served page carries the brand meta tag the app reads",
        ],
        { cwd: hostRoot, stdio: "ignore" },
      );
    } catch (error) {
      controlledFailureExit = error.status ?? 1;
    }
    assert.equal(
      controlledFailureExit,
      1,
      "a canonical public-factory assertion must fail the runner",
    );
    assert.ok(existsSync(controlledReport), "controlled failure must retain its JSON report");
    const controlledResult = JSON.parse(readFileSync(controlledReport, "utf8"));
    const failedCanonicalBrandAssertions = [];
    const findCanonicalBrandFailure = (suite) => {
      for (const spec of suite.specs ?? []) {
        if (
          !spec.file?.endsWith("brand.spec.ts") ||
          spec.title !== "the served page carries the brand meta tag the app reads"
        )
          continue;
        for (const test of spec.tests ?? []) {
          if (test.results?.at(-1)?.status === "failed") failedCanonicalBrandAssertions.push(test);
        }
      }
      for (const child of suite.suites ?? []) findCanonicalBrandFailure(child);
    };
    for (const suite of controlledResult.suites ?? []) findCanonicalBrandFailure(suite);
    assert.ok(
      failedCanonicalBrandAssertions.length > 0,
      "the controlled failure must execute and fail the canonical brand assertion",
    );
    writeFileSync(
      join(evidenceRoot, "controlled-brand-negative-neutral-theme.json"),
      `${JSON.stringify(
        {
          schema: "arras.ui.canonical-brand-negative.v1",
          file: "brand.spec.ts",
          title: "the served page carries the brand meta tag the app reads",
          project: failedCanonicalBrandAssertions[0].projectName,
          status: "failed",
        },
        null,
        2,
      )}\n`,
    );
    const failureOutput = join(temp, "failure-receipt");
    let failedQualification;
    try {
      execFileSync(
        process.execPath,
        [qualifyBin, "http://127.0.0.1:1/?token=sentinel", "--output", failureOutput],
        {
          encoding: "utf8",
        },
      );
      throw new Error("unreachable qualification URL unexpectedly succeeded");
    } catch (error) {
      failedQualification = error;
    }
    assert.equal(failedQualification.status, 1, "browser failures must exit 1");
    assert.ok(
      !String(failedQualification.stderr).includes("token=sentinel"),
      "failure diagnostics must omit query values",
    );
    const failedReceiptName = readdirSync(failureOutput).find((name) =>
      name.endsWith("-failure.json"),
    );
    assert.ok(failedReceiptName, "failed browser qualification must retain a JSON receipt");
    const failureReceipt = readFileSync(join(failureOutput, failedReceiptName), "utf8");
    assert.equal(JSON.parse(failureReceipt).status, "failed");
    assert.ok(!failureReceipt.includes("token=sentinel"), "failure receipt must omit query values");
    const sha256 = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
    const nodeVersion = process.version;
    const npmVersion = execFileSync("npm", ["--version"], { encoding: "utf8" }).trim();
    const pythonVersion = execFileSync(python, ["--version"], { encoding: "utf8" }).trim();
    const installedVersion = (name) =>
      JSON.parse(readFileSync(join(modules, name, "package.json"), "utf8")).version;
    const themeArchive = readFileSync(themeTarball);
    const acceptanceResourcesSource = join(arrasPackageDir, "support/acceptance/resources.json");
    const acceptanceResourcesPath = join(evidenceRoot, "acceptance-resources-neutral-theme.json");
    cpSync(acceptanceResourcesSource, acceptanceResourcesPath);
    const canonicalInventoryPath = join(evidenceRoot, "acceptance-inventory-neutral-theme.json");
    writeFileSync(
      canonicalInventoryPath,
      `${JSON.stringify(
        {
          schema: "arras.ui.canonical-acceptance-inventory.v1",
          specs: canonical.specs,
          expectedCounts: canonical.expectedCounts,
        },
        null,
        2,
      )}\n`,
    );
    const suiteSummary = {
      schema: "arras.ui.canonical-playwright-summary.v1",
      status: "passed",
      platform: process.platform,
      projects: fullCounts,
      expectedTestCount: fullCounts.reduce((sum, item) => sum + item.expected, 0),
      unexpectedSkips: 0,
    };
    writeFileSync(reportPath, `${JSON.stringify(suiteSummary, null, 2)}\n`);
    for (const sidecar of [acceptanceResourcesPath, canonicalInventoryPath, reportPath])
      JSON.parse(readFileSync(sidecar, "utf8"));
    const expectedTestCount = fullCounts.reduce((sum, item) => sum + item.expected, 0);
    const acceptanceSuite = {
      schema: "arras.ui.portable-acceptance.v1",
      status: "passed",
      themeId: "neutral-theme",
      projects: fullCounts,
      canonical: {
        specCount: canonical.specs.length,
        expectedTestCount,
        sourceExpectedCounts: canonical.expectedCounts,
        inventoryPath: "acceptance-inventory-neutral-theme.json",
        inventorySha256: sha256(canonicalInventoryPath),
        resourcesPath: "acceptance-resources-neutral-theme.json",
        resourcesSha256: sha256(acceptanceResourcesPath),
      },
      playwright: {
        reportPath: "playwright-summary-neutral-theme.json",
        sha256: sha256(reportPath),
      },
      visual:
        process.platform === "darwin"
          ? updateCanonicalBaselines
            ? {
                status: "updated-unreviewed",
                updatedScreenshots: fullCounts.find((item) => item.name === "visual")?.passed ?? 0,
              }
            : {
                status: "compared",
                comparedScreenshots: fullCounts.find((item) => item.name === "visual")?.passed ?? 0,
              }
          : { status: "skipped-non-Darwin" },
      negativeControls: {
        missingResource: "refused",
        tamperedResource: "refused",
        invalidOptions: "refused",
        controlledFailure: "exit-1",
      },
      cohort: {
        wheelSha256: sha256(wheel),
        npmSha256: sha256(tarballPath),
        themeSha256: createHash("sha256").update(themeArchive).digest("hex"),
        runnerSha256: sha256(qualifyBin),
      },
    };
    const report = {
      schema: "arras.ui.downstream-qualification.v1",
      cohort: {
        wheel: { file: wheel.split("/").at(-1), sha256: sha256(wheel), version: pkg.version },
        npm: {
          file: tarballPath.split("/").at(-1),
          sha256: sha256(tarballPath),
          version: pkg.version,
        },
        theme: {
          name: themePkg.name,
          version: themePkg.version,
          sha256: createHash("sha256").update(themeArchive).digest("hex"),
        },
        runner: { sha256: sha256(qualifyBin) },
      },
      acceptance_suite: acceptanceSuite,
      runtime: {
        python: pythonVersion,
        node: nodeVersion,
        npm: npmVersion,
        browser: receipts[0].browser,
        packages: {
          react: installedVersion("react"),
          reactDom: installedVersion("react-dom"),
          typescript: installedVersion("typescript"),
          vite: installedVersion("vite"),
          playwright: installedVersion("@playwright/test"),
          axePlaywright: installedVersion("@axe-core/playwright"),
        },
        platform: process.platform,
        javascriptDependencies:
          "npm-installed from the public registry into a temporary consumer; Arras and theme installed from exact cohort tarballs",
      },
      routes: receipts,
    };
    writeFileSync(
      join(outputDir, `qualification-${process.platform}.json`),
      `${JSON.stringify(report, null, 2)}\n`,
    );
    process.stdout.write(
      `Downstream qualification passed: wheel ${pkg.version}, ${process.platform}, prebuilt and packed host routes.\n`,
    );
  }
} catch (error) {
  const privateRoot = join(tmpdir(), "arras-downstream-failed-runs");
  const attempt = join(
    privateRoot,
    `${new Date().toISOString().replaceAll(":", "-")}-${process.pid}`,
  );
  try {
    mkdirSync(privateRoot, { recursive: true, mode: 0o700 });
    mkdirSync(attempt, { recursive: true, mode: 0o700 });
    chmodSync(privateRoot, 0o700);
    chmodSync(attempt, 0o700);
    for (const name of ["playwright-raw.json", "playwright-results"]) {
      const source = join(temp, name);
      if (existsSync(source))
        cpSync(source, join(attempt, name), { recursive: true, errorOnExist: true });
    }
    writeFileSync(join(attempt, "failure.txt"), `${error?.stack ?? error}\n`, { mode: 0o600 });
    process.stderr.write(`Private failed-run artifacts retained at ${attempt}\n`);
  } catch (preserveError) {
    process.stderr.write(`Could not preserve private failed-run artifacts: ${preserveError}\n`);
  }
  throw error;
} finally {
  py.kill("SIGTERM");
  mainHost.kill("SIGTERM");
  schemaHost.kill("SIGTERM");
  checkerHost.kill("SIGTERM");
  rmSync(temp, { recursive: true, force: true });
}
