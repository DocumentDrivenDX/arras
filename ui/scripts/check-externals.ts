// SPDX-License-Identifier: MIT OR Apache-2.0
// Fails if the built library imports a package its packed manifest declares neither as a dependency nor
// as a peer (a host installing the tarball would not get it). Run on a build's output:
//
//   node scripts/check-externals.ts dist-lib
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { packedManifest, type SourceManifest } from "./pack-manifest.ts";

// A static import or re-export (from the start of a line, so a string that mentions "from" is not
// one), a bare `import "x"`, or a dynamic `import("x")`.
const SPECIFIER =
  /^(?:import|export)\b[^"'`;]*?\bfrom\s*["']([^"'\n]+)["']|^import\s*["']([^"'\n]+)["']|\bimport\(\s*["']([^"'\n]+)["']\s*\)/gm;

const packageOf = (spec: string) =>
  spec
    .split("/")
    .slice(0, spec.startsWith("@") ? 2 : 1)
    .join("/");

/** The bare packages a JavaScript text imports: relative and node: specifiers are not packages. */
export function bareImports(text: string): string[] {
  const found = new Set<string>();
  for (const m of text.matchAll(SPECIFIER)) {
    const spec = m[1] ?? m[2] ?? m[3] ?? "";
    if (!/^(\.|\/|node:)/.test(spec)) found.add(packageOf(spec));
  }
  return [...found];
}

function jsFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name);
    if (e.isDirectory()) return jsFiles(path);
    return e.name.endsWith(".js") ? [path] : [];
  });
}

/** One line per import of a package the manifest does not declare. */
export function undeclared(
  files: Record<string, string>,
  manifest: { dependencies?: object; peerDependencies?: object },
): string[] {
  const declared = new Set([
    ...Object.keys(manifest.dependencies ?? {}),
    ...Object.keys(manifest.peerDependencies ?? {}),
  ]);
  return Object.entries(files).flatMap(([file, text]) =>
    bareImports(text)
      .filter((p) => !declared.has(p))
      .map((p) => `${file} imports ${p}, which the packed manifest does not declare`),
  );
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dist = process.argv[2];
  if (!dist) throw new Error("name the library build to check");
  const source = JSON.parse(
    readFileSync(new URL("../package.json", import.meta.url), "utf8"),
  ) as SourceManifest;
  const files = Object.fromEntries(jsFiles(dist).map((f) => [f, readFileSync(f, "utf8")]));
  const bad = undeclared(files, packedManifest(source, "0.0.0", "", ""));
  if (bad.length) {
    process.stderr.write(`${bad.join("\n")}\n`);
    process.exit(1);
  }
}
