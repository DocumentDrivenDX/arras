// SPDX-License-Identifier: MIT OR Apache-2.0
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

// The import graph of `src/`, shared by the tests that read it: where a specifier points, the edges of a
// source text, and what an entry reaches through them.
export const SRC = join(import.meta.dirname, "..");
export const UI = join(SRC, "..");

export const files = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    return e.isDirectory() ? files(p) : /\.tsx?$/.test(e.name) ? [p] : [];
  });

const IMPORT = /(?:from|import)\s*\(?\s*["']([^"']+)["']/g;

/**
 * The package's own name, as a package-style import spells a path into `src/`: `arras-ui` is the
 * entry, `arras-ui/browser` and `arras-ui/shell` its exports.
 */
const PACKAGE = "arras-ui";
const PACKAGE_EXPORTS: Record<string, string> = {
  "": "index",
  browser: "browser/index",
  shell: "shell/index",
};

/**
 * Where an import specifier points inside `src/`, or undefined for a third-party package. A relative
 * path is resolved against the importing file; an alias (`@/`, `~/`, `src/`), an absolute path and
 * the package's own name resolve to the same files, so none is a way around a rule.
 */
function resolveSpecifier(file: string, spec: string): string | undefined {
  if (spec.startsWith(".")) return resolve(dirname(file), spec);
  if (spec.startsWith("/")) return resolve(spec);
  const alias = /^(?:@|~|src)\/(.*)$/.exec(spec);
  if (alias) return resolve(SRC, alias[1] ?? "");
  if (spec === PACKAGE || spec.startsWith(`${PACKAGE}/`)) {
    const sub = spec.slice(PACKAGE.length + 1);
    return resolve(SRC, PACKAGE_EXPORTS[sub] ?? sub);
  }
  return undefined;
}

/** The imports of a source text that point inside `src/`, resolved to paths. */
export function edges(file: string, text: string): string[] {
  return [...text.matchAll(IMPORT)]
    .map((m) => resolveSpecifier(file, m[1] ?? ""))
    .filter((t): t is string => t !== undefined);
}

export const inside = (target: string, dir: string) =>
  target === dir || target.startsWith(`${dir}/`);

/** The text of the source file at exactly this path, or undefined where there is none. */
export type Load = (path: string) => string | undefined;

/** `load` as the disk: a missing file or a directory has no text. */
export const fromDisk: Load = (path) => {
  try {
    return readFileSync(path, "utf8");
  } catch {
    return undefined;
  }
};

const SUFFIXES = ["", ".ts", ".tsx", "/index.ts", "/index.tsx"];

/** The source module a resolved import path names, as TypeScript finds it, with its text. */
function moduleAt(target: string, load: Load): { path: string; text: string } | undefined {
  for (const suffix of SUFFIXES) {
    const path = target + suffix;
    const text = /\.tsx?$/.test(path) ? load(path) : undefined;
    if (text !== undefined) return { path, text };
  }
  return undefined;
}

/**
 * Every source module `entry` reaches through imports, itself included, however many modules apart
 * (a stylesheet, a package and a path that is no module are not followed).
 */
export function reachable(entry: string, load: Load = fromDisk): string[] {
  const seen = new Set<string>();
  const queue = [entry];
  for (let file = queue.pop(); file !== undefined; file = queue.pop()) {
    if (seen.has(file)) continue;
    seen.add(file);
    const text = load(file);
    if (text === undefined) continue;
    for (const target of edges(file, text)) {
      const next = moduleAt(target, load);
      if (next) queue.push(next.path);
    }
  }
  return [...seen];
}
