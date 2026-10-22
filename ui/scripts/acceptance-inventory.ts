// SPDX-License-Identifier: MIT OR Apache-2.0
import { createHash } from "node:crypto";
import { lstatSync, readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { CANONICAL_SPECS } from "../src/testkit/inventory.ts";

export interface AcceptanceInventory {
  version: 1;
  specs: string[];
  expectedCounts?: Record<string, number>;
  files: Record<string, string>;
}

function walk(root: string, current = root): string[] {
  return readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    const path = join(current, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`acceptance resources cannot be symlinks: ${path}`);
    if (entry.isDirectory()) return walk(root, path);
    if (!entry.isFile()) throw new Error(`acceptance resource must be a regular file: ${path}`);
    return [relative(root, path).split("\\").join("/")];
  });
}

function missingCanonicalSpecs(listed: string[]): string[] {
  return CANONICAL_SPECS.filter((name) => !listed.includes(`acceptance/e2e/${name}`));
}

function digestProblems(
  root: string,
  manifest: AcceptanceInventory,
  listed: string[],
  actual: string[],
  sourceRoot?: string,
): string[] {
  const errors: string[] = [];
  for (const path of listed.filter((name) => actual.includes(name))) {
    const bytes = readFileSync(join(root, path));
    const digest = createHash("sha256").update(bytes).digest("hex");
    if (manifest.files[path] !== digest) errors.push(`acceptance resource digest differs: ${path}`);
    if (!sourceRoot || !path.startsWith("acceptance/e2e/")) continue;
    const sourceName = path.slice("acceptance/".length);
    const source = join(sourceRoot, sourceName);
    try {
      const sourceDigest = createHash("sha256").update(readFileSync(source)).digest("hex");
      if (sourceDigest !== digest) errors.push(`packed canonical spec/helper drift: ${path}`);
    } catch {
      errors.push(`canonical source spec/helper is missing: ${sourceName}`);
    }
  }
  return errors;
}

export function verifyAcceptanceInventory(
  root: string,
  manifest: AcceptanceInventory,
  sourceRoot?: string,
): string[] {
  const errors: string[] = [];
  if (manifest.version !== 1) errors.push("unsupported acceptance resource manifest version");
  if (JSON.stringify(manifest.specs) !== JSON.stringify(CANONICAL_SPECS))
    errors.push("canonical acceptance spec inventory differs");
  const listed = Object.keys(manifest.files).sort();
  errors.push(
    ...missingCanonicalSpecs(listed).map(
      (name) => `canonical acceptance spec is missing from the manifest: ${name}`,
    ),
  );
  const actual = walk(root)
    .filter(
      (path) => /^(acceptance|examples|src)\//.test(path) && path !== "acceptance/resources.json",
    )
    .sort();
  for (const path of listed.filter((name) => !actual.includes(name)))
    errors.push(`listed acceptance resource is missing: ${path}`);
  for (const path of actual.filter((name) => !listed.includes(name)))
    errors.push(`unlisted acceptance resource: ${path}`);
  errors.push(...digestProblems(root, manifest, listed, actual, sourceRoot));
  return errors;
}

export function hashAcceptanceFiles(root: string): Record<string, string> {
  return Object.fromEntries(
    walk(root)
      .filter(
        (path) => /^(acceptance|examples|src)\//.test(path) && path !== "acceptance/resources.json",
      )
      .sort()
      .map((path) => [
        path,
        createHash("sha256")
          .update(readFileSync(join(root, path)))
          .digest("hex"),
      ]),
  );
}

export function assertNoAliasedResources(root: string): void {
  const inodeToPath = new Map<string, string>();
  for (const path of walk(root)) {
    const stat = lstatSync(join(root, path));
    const inode = `${stat.dev}:${stat.ino}`;
    const previous = inodeToPath.get(inode);
    if (previous) throw new Error(`acceptance resources alias the same file: ${previous}, ${path}`);
    inodeToPath.set(inode, path);
  }
}
