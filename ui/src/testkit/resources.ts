// SPDX-License-Identifier: MIT OR Apache-2.0
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join, relative, resolve } from "node:path";
import { CANONICAL_SPECS, CANONICAL_TEST_COUNTS } from "./inventory";

interface ResourceManifest {
  version: 1;
  specs: string[];
  expectedCounts: Record<string, number>;
  files: Record<string, string>;
}

function walk(root: string, current = root): string[] {
  return readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    const path = join(current, entry.name);
    if (entry.isSymbolicLink()) throw new Error("packed acceptance resources cannot be symlinks");
    if (entry.isDirectory()) return walk(root, path);
    if (!entry.isFile()) throw new Error("packed acceptance resources must be regular files");
    return [relative(root, path).split("\\").join("/")];
  });
}

export function verifyPackedAcceptanceResources(supportRoot: string): void {
  const root = join(supportRoot, "acceptance", "resources.json");
  const manifest = JSON.parse(readFileSync(root, "utf8")) as ResourceManifest;
  if (
    manifest.version !== 1 ||
    JSON.stringify(manifest.specs) !== JSON.stringify(CANONICAL_SPECS) ||
    !manifest.expectedCounts ||
    JSON.stringify(manifest.expectedCounts) !== JSON.stringify(CANONICAL_TEST_COUNTS) ||
    !manifest.files ||
    typeof manifest.files !== "object" ||
    Array.isArray(manifest.files)
  ) {
    throw new Error("packed acceptance resource manifest is invalid");
  }
  const listed = Object.keys(manifest.files).sort();
  const requiredSpecs = CANONICAL_SPECS.map((name) => `acceptance/e2e/${name}`).sort();
  if (requiredSpecs.some((path) => !listed.includes(path)))
    throw new Error("packed acceptance resource manifest omits a canonical spec");
  const actual = walk(supportRoot)
    .filter((path) => /^(acceptance|examples|src)\//.test(path))
    .filter((path) => path !== "acceptance/resources.json")
    .sort();
  if (JSON.stringify(listed) !== JSON.stringify(actual))
    throw new Error("packed acceptance resource inventory differs");
  const inodeToPath = new Map<string, string>();
  for (const path of actual) {
    const absolute = join(supportRoot, path);
    const stat = lstatSync(absolute);
    const inode = `${stat.dev}:${stat.ino}`;
    if (inodeToPath.has(inode)) throw new Error("packed acceptance resources alias a file");
    inodeToPath.set(inode, path);
    const digest = createHash("sha256").update(readFileSync(absolute)).digest("hex");
    if (manifest.files[path] !== digest)
      throw new Error(`packed acceptance resource digest differs: ${path}`);
  }
}

function supportDigest(root: string): string {
  const files = walk(root).map((path) => ({
    path,
    sha256: createHash("sha256")
      .update(readFileSync(join(root, path)))
      .digest("hex"),
  }));
  return createHash("sha256").update(JSON.stringify(files)).digest("hex");
}

function verifyMaterializedSupport(source: string, target: string): void {
  const expected = walk(source)
    .filter((path) => /^(acceptance|examples|src)\//.test(path))
    .sort();
  const actual = walk(target)
    .filter((path) => /^(acceptance|examples|src)\//.test(path))
    .sort();
  if (JSON.stringify(expected) !== JSON.stringify(actual))
    throw new Error("materialized acceptance resources differ from the verified package");
  for (const path of expected) {
    const expectedDigest = createHash("sha256")
      .update(readFileSync(join(source, path)))
      .digest("hex");
    const actualDigest = createHash("sha256")
      .update(readFileSync(join(target, path)))
      .digest("hex");
    if (expectedDigest !== actualDigest)
      throw new Error("materialized acceptance resource digest differs from the verified package");
  }
}

function teardownSource(root: string, identitySha256: string): string {
  return `import { readFileSync, rmSync } from "node:fs";\nexport default async () => { const marker = JSON.parse(readFileSync(${JSON.stringify(join(root, ".arras-acceptance-owner.json"))}, "utf8")); if (marker.identitySha256 === ${JSON.stringify(identitySha256)}) rmSync(${JSON.stringify(root)}, { recursive: true, force: true }); };\n`;
}

export function materializePackedAcceptanceSuite(
  supportRoot: string,
  consumerRoot: string,
  profileIdentity: string,
): {
  testDir: string;
  globalTeardown: string;
} {
  const hostRoot = resolve(consumerRoot);
  if (hostRoot.split(/[\\/]/).includes("node_modules"))
    throw new Error("acceptance suite must be materialized from a consumer project directory");
  const supportSha256 = supportDigest(supportRoot);
  const identitySha256 = createHash("sha256")
    .update(JSON.stringify({ hostRoot, profileIdentity, supportSha256 }))
    .digest("hex");
  const root = join(hostRoot, `.arras-acceptance-${identitySha256.slice(0, 24)}`);
  const marker = join(root, ".arras-acceptance-owner.json");
  const verifyExisting = () => {
    const stat = lstatSync(root);
    if (!stat.isDirectory() || stat.isSymbolicLink())
      throw new Error("acceptance materialization path is not an owned directory");
    const markerStat = lstatSync(marker);
    if (!markerStat.isFile() || markerStat.isSymbolicLink())
      throw new Error("acceptance materialization ownership marker is invalid");
    const data = JSON.parse(readFileSync(marker, "utf8")) as {
      identitySha256?: string;
      supportSha256?: string;
    };
    if (data.identitySha256 !== identitySha256 || data.supportSha256 !== supportSha256)
      throw new Error("acceptance materialization ownership marker differs");
    const teardownPath = join(root, "cleanup.mjs");
    const teardownStat = lstatSync(teardownPath);
    if (!teardownStat.isFile() || teardownStat.isSymbolicLink())
      throw new Error("acceptance materialization cleanup script is invalid");
    if (readFileSync(teardownPath, "utf8") !== teardownSource(root, identitySha256))
      throw new Error("acceptance materialization cleanup script differs");
    verifyMaterializedSupport(supportRoot, root);
  };
  if (existsSync(root)) {
    verifyExisting();
    return { testDir: join(root, "acceptance/e2e"), globalTeardown: join(root, "cleanup.mjs") };
  }
  const staging = mkdtempSync(join(hostRoot, ".arras-acceptance-stage-"));
  try {
    for (const directory of ["acceptance", "examples", "src"])
      cpSync(join(supportRoot, directory), join(staging, directory), { recursive: true });
    writeFileSync(marker.replace(root, staging), JSON.stringify({ identitySha256, supportSha256 }));
    const globalTeardown = join(staging, "cleanup.mjs");
    writeFileSync(globalTeardown, teardownSource(root, identitySha256));
    try {
      renameSync(staging, root);
    } catch (error) {
      if (!existsSync(root)) throw error;
      rmSync(staging, { recursive: true, force: true });
      verifyExisting();
    }
    return { testDir: join(root, "acceptance/e2e"), globalTeardown: join(root, "cleanup.mjs") };
  } catch (error) {
    rmSync(staging, { recursive: true, force: true });
    throw error;
  }
}
