// SPDX-License-Identifier: MIT OR Apache-2.0
// UMF's schema browser, as the console depends on it: the public npm package
// `@documentdrivendx/umf-schema-browser` at an exact version (package.json), whose integrity the
// lockfile carries. This module states the pin's release facts and checks them; vite.config.ts
// copies the installed package's `assets/` with `copyAssets`, and the tests use the checks.
//
//   node scripts/umf-schema-browser.ts              # offline: the pin, the lockfile, the installed package
//   node scripts/umf-schema-browser.ts --download   # and the registry: integrity and the release digest
//   node scripts/umf-schema-browser.ts --dist dist  # and a build's copy of the assets, byte for byte
//
// To bump: `npm install @documentdrivendx/umf-schema-browser@<v> --save-exact`, set RELEASE below
// to the GitHub release's tarball digest, run this with --download, then the tests (ui/README.md).
import { createHash } from "node:crypto";
import { cpSync, existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

export const PACKAGE = "@documentdrivendx/umf-schema-browser";
/** The GitHub release of the pinned version: its tarball is byte-identical to the npm one. */
export const RELEASE = {
  version: "2.0.0",
  tag: "schema-browser-v2.0.0",
  tarball: "documentdrivendx-umf-schema-browser-2.0.0.tgz",
  sha256: "03e13341c79f29fe891fa6d97a3e504b36a483ba51c98b2e1bcb557b6036e8e1",
  bytes: 2_178_040,
} as const;
export const LICENSE_FILES = ["LICENSE-MIT", "LICENSE-APACHE", "THIRD_PARTY_NOTICES.md"] as const;

const UI = fileURLToPath(new URL("..", import.meta.url));
const consumerRequire = createRequire(join(process.cwd(), "package.json"));
export const PACKAGE_DIR = dirname(
  dirname(consumerRequire.resolve(`${PACKAGE}/assets/index.html`)),
);
/** The directory a host serves at `explorerBase`; the build copies it to dist/umf-explorer. */
export const ASSETS_DIR = join(PACKAGE_DIR, "assets");
/** Where `npm run build` puts the assets, under the build's output directory. */
export const DIST_SUBDIR = "umf-explorer";

interface JsonFile {
  version?: string;
  license?: string;
  dependencies?: Record<string, string>;
  packages?: Record<string, { version: string; resolved: string; integrity: string }>;
}
const json = (path: string): JsonFile => JSON.parse(readFileSync(path, "utf8"));

/** What package.json and package-lock.json pin. */
export function pin(uiDir = UI): {
  declared: string;
  locked: { version: string; resolved: string; integrity: string } | undefined;
} {
  const declared = String(json(join(uiDir, "package.json")).dependencies?.[PACKAGE] ?? "");
  const locked = json(join(uiDir, "package-lock.json")).packages?.[`node_modules/${PACKAGE}`];
  return { declared, locked };
}

/** Every regular file under `dir`, relative, sorted. */
export function files(dir: string): string[] {
  const out: string[] = [];
  const walk = (d: string) => {
    for (const name of readdirSync(d)) {
      const p = join(d, name);
      if (statSync(p).isDirectory()) walk(p);
      else out.push(relative(dir, p).split("\\").join("/"));
    }
  };
  walk(dir);
  return out.sort();
}

/** How `copy` differs from `original`, file by file and byte for byte; empty when identical. */
export function differences(original: string, copy: string): string[] {
  if (!existsSync(copy)) return [`${copy} is missing`];
  const a = files(original);
  const b = files(copy);
  const out = [
    ...a.filter((f) => !b.includes(f)).map((f) => `missing: ${f}`),
    ...b.filter((f) => !a.includes(f)).map((f) => `extra: ${f}`),
  ];
  for (const f of a.filter((x) => b.includes(x))) {
    if (!readFileSync(join(original, f)).equals(readFileSync(join(copy, f))))
      out.push(`differs: ${f}`);
  }
  return out;
}

/** The build step: the installed package's assets, unchanged, at `<outDir>/umf-explorer`. */
export function copyAssets(outDir: string): void {
  cpSync(ASSETS_DIR, join(outDir, DIST_SUBDIR), { recursive: true });
}

/** Offline: the pin is exact and equal everywhere, the lock is the registry's, the package is whole. */
export function checkInstalled(uiDir = UI, packageDir = PACKAGE_DIR): string[] {
  const problems: string[] = [];
  const { declared, locked } = pin(uiDir);
  if (declared !== RELEASE.version)
    problems.push(`package.json pins ${PACKAGE} "${declared}", not exactly "${RELEASE.version}"`);
  if (!locked) return [...problems, `package-lock.json has no ${PACKAGE}`];
  if (locked.version !== RELEASE.version)
    problems.push(`package-lock.json locks ${locked.version}`);
  const tail = PACKAGE.split("/")[1];
  const registryUrl = `https://registry.npmjs.org/${PACKAGE}/-/${tail}-${RELEASE.version}.tgz`;
  if (locked.resolved !== registryUrl)
    problems.push(`package-lock.json resolves ${locked.resolved}, not ${registryUrl}`);
  if (!/^sha512-[A-Za-z0-9+/]+=*$/.test(locked.integrity ?? ""))
    problems.push(`package-lock.json has no sha512 integrity`);
  if (!existsSync(join(packageDir, "package.json")))
    return [...problems, `${PACKAGE} is not installed (npm ci)`];
  const installed = json(join(packageDir, "package.json"));
  if (installed.version !== RELEASE.version)
    problems.push(`installed ${PACKAGE} is ${installed.version}`);
  if (installed.license !== "(MIT OR Apache-2.0)")
    problems.push(`installed licence is ${installed.license}`);
  for (const f of LICENSE_FILES)
    if (!existsSync(join(packageDir, f))) problems.push(`installed package lacks ${f}`);
  for (const f of ["index.html", "explorer.js", "explorer.css", "style.css"])
    if (!existsSync(join(packageDir, "assets", f)))
      problems.push(`installed package lacks assets/${f}`);
  return problems;
}

/** Online: the registry's integrity is the lockfile's, and the tarball is the release's bytes. */
export async function checkRegistry(
  uiDir = UI,
): Promise<{ problems: string[]; facts: Record<string, string | number> }> {
  const { locked } = pin(uiDir);
  const problems: string[] = [];
  const meta = (await (
    await fetch(`https://registry.npmjs.org/${PACKAGE}/${RELEASE.version}`)
  ).json()) as { dist: { integrity: string; tarball: string } };
  if (meta.dist.integrity !== locked?.integrity)
    problems.push(
      `registry integrity ${meta.dist.integrity} is not the lockfile's ${locked?.integrity}`,
    );
  const tarball = Buffer.from(await (await fetch(meta.dist.tarball)).arrayBuffer());
  const sha512 = `sha512-${createHash("sha512").update(tarball).digest("base64")}`;
  const sha256 = createHash("sha256").update(tarball).digest("hex");
  if (sha512 !== locked?.integrity)
    problems.push(`downloaded tarball is ${sha512}, the lockfile says ${locked?.integrity}`);
  if (sha256 !== RELEASE.sha256)
    problems.push(
      `downloaded tarball sha256 ${sha256} is not release ${RELEASE.tag}'s ${RELEASE.sha256}`,
    );
  if (tarball.length !== RELEASE.bytes)
    problems.push(`downloaded tarball is ${tarball.length} bytes, the release's ${RELEASE.bytes}`);
  return {
    problems,
    facts: { tarball: meta.dist.tarball, bytes: tarball.length, sha256, integrity: sha512 },
  };
}

if (import.meta.main) {
  const args = process.argv.slice(2);
  const problems = checkInstalled();
  process.stdout.write(
    `${PACKAGE}@${RELEASE.version}: pin, lockfile and installed package ${problems.length ? "differ" : "agree"}\n`,
  );
  if (args.includes("--download")) {
    const r = await checkRegistry();
    problems.push(...r.problems);
    process.stdout.write(`registry tarball: ${JSON.stringify(r.facts)}\n`);
  }
  const dist = args[args.indexOf("--dist") + 1];
  if (args.includes("--dist") && dist)
    problems.push(...differences(ASSETS_DIR, join(dist, DIST_SUBDIR)));
  for (const p of problems) process.stderr.write(`  ${p}\n`);
  process.exit(problems.length ? 1 : 0);
}
