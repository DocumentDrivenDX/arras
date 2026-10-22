// SPDX-License-Identifier: MIT OR Apache-2.0
// The manifest of the packed library (`@documentdrivendx/arras-ui`), built from the source package.json:
// the dependencies it ships with, and the peers a host provides. Every peer the source declares is a
// peer of the package, because the build leaves it external (vite.lib.config.ts); React comes from the
// source's dependencies, where the standalone host keeps it.
export interface SourceManifest {
  name: string;
  description?: string;
  dependencies: Record<string, string>;
  peerDependencies?: Record<string, string>;
  peerDependenciesMeta?: Record<string, { optional?: boolean }>;
}

function entry(name: string, types: string) {
  return { types: `./dist/types/${types}.d.ts`, import: `./dist/${name}.js` };
}

export function packedManifest(
  source: SourceManifest,
  version: string,
  registry: string,
  repository: string,
) {
  return {
    name: `@documentdrivendx/${source.name}`,
    version,
    description: source.description,
    type: "module",
    license: "MIT OR Apache-2.0",
    repository: { type: "git", url: repository, directory: "ui" },
    publishConfig: { registry, access: "public" },
    sideEffects: ["**/*.css"],
    files: ["dist"],
    exports: {
      ".": entry("index", "index"),
      "./browser": entry("browser", "browser/index"),
      "./shell": entry("shell", "shell/index"),
      "./styles.css": "./dist/styles.css",
      "./package.json": "./package.json",
    },
    dependencies: {
      "@documentdrivendx/umf-schema-browser":
        source.dependencies["@documentdrivendx/umf-schema-browser"],
      "@tanstack/react-query": source.dependencies["@tanstack/react-query"],
    },
    peerDependencies: {
      react: source.dependencies.react,
      "react-dom": source.dependencies["react-dom"],
      ...source.peerDependencies,
    } as Record<string, string | undefined>,
    peerDependenciesMeta: { ...source.peerDependenciesMeta },
  };
}
