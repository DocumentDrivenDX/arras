// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { bareImports, undeclared } from "../../scripts/check-externals.ts";
import { packedManifest, type SourceManifest } from "../../scripts/pack-manifest.ts";

const source = JSON.parse(
  readFileSync(resolve(import.meta.dirname, "../../package.json"), "utf8"),
) as SourceManifest;
const packed = packedManifest(source, "1.2.3", "https://registry.example/", "git+https://x/y.git");

describe("the packed manifest", () => {
  it("is the scoped, openly licensed package, with no design-system package to install", () => {
    expect(packed.name).toBe("@documentdrivendx/arras-ui");
    expect(packed.license).toBe("MIT OR Apache-2.0");
    const all = { ...packed.dependencies, ...packed.peerDependencies };
    expect(Object.keys(all).sort()).toEqual(
      [
        "@databricks/appkit-ui",
        "@documentdrivendx/umf-schema-browser",
        "@tanstack/react-query",
        "react",
        "react-dom",
      ].sort(),
    );
  });

  it("carries every peer the source declares, with its optional marks, and React", () => {
    expect(packed.peerDependencies).toMatchObject(source.peerDependencies ?? {});
    expect(packed.peerDependencies.react).toBe(source.dependencies.react);
    expect(packed.peerDependencies["react-dom"]).toBe(source.dependencies["react-dom"]);
    expect(packed.peerDependenciesMeta).toEqual(source.peerDependenciesMeta);
  });

  it("declares every package the library build leaves external", () => {
    const declared = { ...packed.dependencies, ...packed.peerDependencies };
    for (const name of [
      "react",
      "react-dom",
      "@tanstack/react-query",
      "@documentdrivendx/umf-schema-browser",
      "@databricks/appkit-ui",
    ]) {
      expect(declared, name).toHaveProperty([name]);
    }
  });
});

describe("the external-import check", () => {
  it("reads bare packages, scoped and subpath, and skips relative and node: imports", () => {
    const text = [
      'import a from "react/jsx-runtime";',
      'import { b } from "@example/widgets/button";',
      'export { c } from "./chunk.js";',
      'import("@example/tokens");',
      'import d from "node:fs";',
    ].join("\n");
    const multiline =
      'import {\n  a,\n  b,\n} from "@tanstack/react-query";\nconst s = x ? "from" : "y";';
    expect(bareImports(multiline)).toEqual(["@tanstack/react-query"]);
    expect(bareImports(text).sort()).toEqual(["@example/tokens", "@example/widgets", "react"]);
  });

  it("flags an import the manifest does not declare", () => {
    const files = { "dist/index.js": 'import x from "left-pad";\nimport y from "react";' };
    expect(undeclared(files, packed)).toHaveLength(1);
    expect(undeclared({ "dist/index.js": 'import y from "react";' }, packed)).toEqual([]);
    const withoutPeers = { ...packed, peerDependencies: { react: "^19" } };
    expect(
      undeclared({ "dist/a.js": 'import "@databricks/appkit-ui";' }, withoutPeers),
    ).toHaveLength(1);
  });
});
