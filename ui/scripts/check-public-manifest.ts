// SPDX-License-Identifier: MIT OR Apache-2.0
// Check the inert public API catalog against the package manifest and what npm consumers import.
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";
import { packedManifest } from "./pack-manifest.ts";

type Inventory = Record<string, string[]>;
type Peer = { version: string; optional: boolean };
type PublicCatalog = {
  distribution: {
    npm: {
      exports: Record<string, Record<string, string>>;
      peer_dependencies: Record<string, Peer>;
    };
  };
  ui: {
    npm_runtime_exports: Inventory;
    npm_type_exports: Inventory;
    npm_style_exports: string[];
    role_tokens: string[];
    root_class: string;
  };
};

const UI = resolve(import.meta.dirname, "..");
const ROOT = resolve(UI, "..");
const DIST = resolve(UI, "dist-lib");
const ENTRY_FILES: Record<string, { runtime: string; types: string }> = {
  ".": { runtime: "index", types: "index" },
  "./browser": { runtime: "browser", types: "browser/index" },
  "./shell": { runtime: "shell", types: "shell/index" },
  "./testkit": { runtime: "testkit", types: "testkit/index" },
  "./testkit/host": { runtime: "testkit/host", types: "testkit/host" },
};

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export function parityErrors(
  expected: Record<string, unknown>,
  actual: Record<string, unknown>,
): string[] {
  const errors: string[] = [];
  for (const key of new Set([...Object.keys(expected), ...Object.keys(actual)])) {
    if (stable(expected[key]) !== stable(actual[key])) {
      errors.push(`${key}: expected ${stable(expected[key])}, received ${stable(actual[key])}`);
    }
  }
  return errors;
}

function moduleExports(file: string): { runtime: string[]; types: string[] } {
  const program = ts.createProgram([file], {
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    skipLibCheck: true,
  });
  const source = program.getSourceFile(file);
  if (!source) throw new Error(`TypeScript could not load ${file}`);
  const checker = program.getTypeChecker();
  const module = checker.getSymbolAtLocation(source);
  if (!module) throw new Error(`No module symbol in ${file}`);
  const exports = checker.getExportsOfModule(module);
  const names = (mask: ts.SymbolFlags) =>
    exports
      .filter((symbol) => {
        const resolved =
          symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
        return (resolved.flags & mask) !== 0;
      })
      .map((symbol) => symbol.getName())
      .sort();
  return { runtime: names(ts.SymbolFlags.Value), types: names(ts.SymbolFlags.Type) };
}

async function runtimeExports(): Promise<Inventory> {
  const result: Inventory = {};
  for (const [subpath, entries] of Object.entries(ENTRY_FILES)) {
    const module = await import(pathToFileURL(resolve(DIST, `${entries.runtime}.js`)).href);
    result[subpath] = Object.keys(module).sort();
  }
  return result;
}

function typeExports(): Inventory {
  const result: Inventory = {};
  for (const [subpath, entries] of Object.entries(ENTRY_FILES)) {
    const declaration = resolve(DIST, "types", `${entries.types}.d.ts`);
    result[subpath] = moduleExports(declaration).types;
  }
  return result;
}

function catalogExports(
  packedExports: Record<string, unknown>,
): Record<string, Record<string, string>> {
  return Object.fromEntries(
    Object.entries(packedExports).map(([subpath, target]) => {
      if (typeof target === "string") {
        const kind = subpath === "./styles.css" ? "style" : "metadata";
        return [subpath, { [kind]: target.replace(/^\.\//, "") }];
      }
      const entry = target as { import?: string; types?: string };
      return [
        subpath,
        {
          ...(entry.import ? { runtime: entry.import.replace(/^\.\//, "") } : {}),
          ...(entry.types ? { types: entry.types.replace(/^\.\//, "") } : {}),
        },
      ];
    }),
  );
}

function catalogPeers(packed: ReturnType<typeof packedManifest>): Record<string, Peer> {
  return Object.fromEntries(
    Object.entries(packed.peerDependencies).map(([name, version]) => [
      name,
      {
        version: version ?? "",
        optional: packed.peerDependenciesMeta[name]?.optional === true,
      },
    ]),
  );
}

function styleTokens(css: string): string[] {
  return [
    ...new Set(
      [...css.matchAll(/var\(\s*(--arras-[\w-]+)/g)].flatMap((match) =>
        match[1] ? [match[1]] : [],
      ),
    ),
  ].sort();
}

function inventorySets(inventory: Inventory): Inventory {
  return Object.fromEntries(
    Object.entries(inventory).map(([key, names]) => [key, [...names].sort()]),
  );
}

export async function checkPublicManifest(catalog: PublicCatalog): Promise<string[]> {
  const source = JSON.parse(readFileSync(resolve(UI, "package.json"), "utf8"));
  const version = /^version\s*=\s*"([^"]+)"/m.exec(
    readFileSync(resolve(ROOT, "pyproject.toml"), "utf8"),
  )?.[1];
  if (!version) throw new Error("pyproject.toml has no version");
  const packed = packedManifest(
    source,
    version,
    "https://registry.npmjs.org/",
    "git+https://github.com/DocumentDrivenDX/arras.git",
  );
  const missingBuildFiles = [
    ...Object.values(ENTRY_FILES).flatMap((entries) => [
      resolve(DIST, `${entries.runtime}.js`),
      resolve(DIST, "types", `${entries.types}.d.ts`),
    ]),
    resolve(DIST, "styles.css"),
  ].filter((file) => !existsSync(file));
  if (missingBuildFiles.length) {
    throw new Error(`run \`npm run build:lib\` first; missing ${missingBuildFiles.join(", ")}`);
  }
  const runtime = await runtimeExports();
  const types = typeExports();
  const sourceCss = readFileSync(resolve(UI, "src/styles.css"), "utf8");
  const builtCss = readFileSync(resolve(DIST, "styles.css"), "utf8");
  const rootSelector = new RegExp(
    `${catalog.ui.root_class.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{`,
  );
  const emittedRootTokens = styleTokens(builtCss);
  const hasScopedRoot = rootSelector.test(builtCss);
  const errors = [
    ...parityErrors(catalog.distribution.npm.exports, catalogExports(packed.exports)),
    ...parityErrors(catalog.distribution.npm.peer_dependencies, catalogPeers(packed)),
    ...parityErrors(inventorySets(catalog.ui.npm_runtime_exports), inventorySets(runtime)),
    ...parityErrors(inventorySets(catalog.ui.npm_type_exports), inventorySets(types)),
    ...parityErrors(
      { style_exports: catalog.ui.npm_style_exports },
      {
        style_exports: Object.keys(packed.exports)
          .filter((key) => key === "./styles.css")
          .sort(),
      },
    ),
    ...parityErrors(
      { role_tokens: [...catalog.ui.role_tokens].sort() },
      { role_tokens: styleTokens(sourceCss) },
    ),
    ...parityErrors(
      { emitted_role_tokens: [...catalog.ui.role_tokens].sort() },
      { emitted_role_tokens: emittedRootTokens },
    ),
  ];
  if (!hasScopedRoot)
    errors.push(
      `dist-lib/styles.css does not contain the catalog root selector ${catalog.ui.root_class}`,
    );
  return errors;
}

export async function checkNegativeControls(catalog: PublicCatalog): Promise<string[]> {
  const controls: Array<[string, (candidate: PublicCatalog) => void]> = [
    ["removed runtime symbol", (candidate) => candidate.ui.npm_runtime_exports["."]?.pop()],
    [
      "extra runtime symbol",
      (candidate) => candidate.ui.npm_runtime_exports["."]?.push("__unexpectedRuntime"),
    ],
    ["removed type symbol", (candidate) => candidate.ui.npm_type_exports["."]?.pop()],
    [
      "extra type symbol",
      (candidate) => candidate.ui.npm_type_exports["."]?.push("__unexpectedType"),
    ],
    ["removed npm subpath", (candidate) => delete candidate.distribution.npm.exports["./browser"]],
    [
      "extra npm subpath",
      (candidate) =>
        (candidate.distribution.npm.exports["./internal"] = {
          runtime: "dist/internal.js",
          types: "dist/types/internal.d.ts",
        }),
    ],
    ["removed peer", (candidate) => delete candidate.distribution.npm.peer_dependencies.react],
    [
      "extra peer",
      (candidate) =>
        (candidate.distribution.npm.peer_dependencies["__unexpected-peer"] = {
          version: "*",
          optional: false,
        }),
    ],
    [
      "wrong peer range",
      (candidate) => {
        const peer = candidate.distribution.npm.peer_dependencies.react;
        if (peer) peer.version = "0.0.0";
      },
    ],
    ["removed role token", (candidate) => candidate.ui.role_tokens.pop()],
    ["extra role token", (candidate) => candidate.ui.role_tokens.push("--arras-internal-token")],
    ["wrong root class", (candidate) => (candidate.ui.root_class = ".arras-internal-root")],
  ];
  const failures: string[] = [];
  for (const [name, mutate] of controls) {
    const candidate = structuredClone(catalog);
    mutate(candidate);
    if ((await checkPublicManifest(candidate)).length === 0) failures.push(name);
  }
  return failures;
}

if (import.meta.main) {
  const catalog = JSON.parse(
    readFileSync(resolve(ROOT, "src/arras/public-api.json"), "utf8"),
  ) as PublicCatalog;
  const errors = await checkPublicManifest(catalog);
  const failedControls = await checkNegativeControls(catalog);
  if (errors.length || failedControls.length) {
    if (errors.length) {
      process.stderr.write(
        `Public API manifest parity failed:\n${errors.map((error) => `- ${error}`).join("\n")}\n`,
      );
    }
    if (failedControls.length) {
      process.stderr.write(
        `Public API mutation controls were not detected: ${failedControls.join(", ")}`,
      );
    }
    process.exitCode = 1;
  } else {
    process.stdout.write(
      "Public API manifest matches npm exports, emitted runtime and type exports, peers, and scoped role tokens.\n",
    );
    process.stdout.write(`${11 - failedControls.length} mutation controls passed.\n`);
  }
}
