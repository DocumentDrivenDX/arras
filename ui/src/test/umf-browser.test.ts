// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BackendStatus } from "../api/types";
import {
  annotationsFor,
  CATEGORIES,
  definitionKey,
  describeSelection,
  documentIds,
  entryId,
  hostTheme,
  relationshipKey,
  schemeOf,
  THEME_TOKENS,
  toEntries,
  typeForSelection,
} from "../areas/umfBrowser";
import { defined } from "./defined";
import { catalog } from "./fake";

const vectors: unknown = JSON.parse(
  readFileSync(resolve(__dirname, "scheme.vectors.json"), "utf8"),
);

// The pure half of the UMF source view: what the console hands UMF's schema browser and how it
// reads what comes back (host contract 1.1 of @documentdrivendx/umf-schema-browser).
const REGISTERED = readFileSync(
  resolve(__dirname, "../../../src/arras/conformance/module.umf.json"),
  "utf8",
);
const entry = (id = "arras:catalog", text = REGISTERED) => ({
  id,
  title: id.slice("arras:".length),
  category: "domain",
  path: "catalog.umf.json",
  text,
  format: "json" as const,
});
const UP: BackendStatus[] = [
  { backend: "memory", available: true, reason: null, position: null, lag: null },
  { backend: "memory_replica", available: true, reason: null, position: null, lag: null },
];

describe("the catalog as the package's entries", () => {
  it("keeps the fields the package reads, in the console's one category", () => {
    const entries = toEntries({
      version: 1,
      entries: [
        {
          id: "arras:a",
          title: "a",
          category: "domain",
          path: "a.umf.yaml",
          text: "x: 1",
          format: "yaml",
          description: "d",
          schemaFormat: "umf",
        },
        {
          id: "arras:b",
          title: "b",
          category: "other",
          path: "b.json",
          text: "{}",
          format: "json",
          description: "n",
          schemaFormat: "json-schema",
        },
      ],
    });
    expect(entries).toEqual([
      {
        id: "arras:a",
        title: "a",
        category: "domain",
        path: "a.umf.yaml",
        text: "x: 1",
        format: "yaml",
        description: "d",
        schemaFormat: "umf",
      },
      {
        id: "arras:b",
        title: "b",
        category: "domain",
        path: "b.json",
        text: "{}",
        format: "json",
        description: "n",
        schemaFormat: "json-schema",
      },
    ]);
    expect(CATEGORIES).toEqual([{ id: "domain", label: "Registered modules" }]);
    expect(entryId("a&b")).toBe("arras:a&b");
  });

  it("reads record and relationship ids from a JSON document, and nothing from YAML or broken text", () => {
    const ids = documentIds([
      entry(),
      { ...entry("arras:y"), format: "yaml", text: "modules: []" },
      entry("arras:z", "{not json"),
    ]);
    expect([...defined(ids.records.get("catalog"), 'ids.records.get("catalog")')]).toEqual([
      "UseCase",
      "Solution",
    ]);
    expect([
      ...defined(ids.relationships.get("catalog"), 'ids.relationships.get("catalog")'),
    ]).toEqual([["addresses", "solution-addresses"]]);
    expect(ids.records.size).toBe(1);
  });
});

describe("selection keys and the type a selection names", () => {
  const m = catalog();
  it("spells keys as the contract does", () => {
    expect(definitionKey("catalog", "UseCase")).toBe('["catalog","UseCase"]');
    expect(relationshipKey("catalog", "solution-addresses")).toBe(
      '["relationship","catalog","solution-addresses"]',
    );
  });

  it("maps a record of the module's own entry to its entity type, by name", () => {
    expect(
      typeForSelection(
        { schema: "arras:catalog", definition: definitionKey("catalog", "UseCase") },
        m,
      ),
    ).toBe("catalog.UseCase");
    expect(
      typeForSelection(
        { schema: "arras:catalog", definition: definitionKey("catalog", "Solution") },
        m,
      ),
    ).toBe("catalog.Solution");
  });

  it("maps nothing else: a field, an unknown record, another entry, a relationship, the entry, bad keys", () => {
    const no = [
      { schema: "arras:catalog", definition: definitionKey("catalog", "UseCase.code") },
      { schema: "arras:catalog", definition: definitionKey("catalog", "Nope") },
      { schema: "arras:other", definition: definitionKey("catalog", "UseCase") },
      { schema: "arras:catalog", definition: definitionKey("other", "UseCase") },
      { schema: "arras:catalog", relationship: relationshipKey("catalog", "solution-addresses") },
      { schema: "arras:catalog" },
      { schema: "arras:catalog", definition: "UseCase" },
      { schema: "arras:catalog", definition: "[1,2]" },
      { schema: "arras:catalog", definition: '["catalog","UseCase","x"]' },
    ];
    for (const s of no) expect(typeForSelection(s, m), JSON.stringify(s)).toBeUndefined();
    expect(typeForSelection(null, m)).toBeUndefined();
    expect(
      typeForSelection(
        { schema: "arras:catalog", definition: definitionKey("catalog", "UseCase") },
        undefined,
      ),
    ).toBeUndefined();
  });

  it("describes a selection for the console's line", () => {
    const entries = [entry()];
    expect(describeSelection({ schema: "arras:catalog" }, entries)).toEqual({
      schema: "catalog",
    });
    expect(
      describeSelection(
        { schema: "arras:catalog", definition: definitionKey("catalog", "UseCase") },
        entries,
      ),
    ).toEqual({ schema: "catalog", item: "UseCase" });
    expect(
      describeSelection(
        { schema: "arras:catalog", relationship: relationshipKey("catalog", "r1") },
        entries,
      ),
    ).toEqual({ schema: "catalog", item: "relationship r1" });
    expect(describeSelection({ schema: "arras:x", definition: "odd" }, entries)).toEqual({
      schema: "arras:x",
      item: "odd",
    });
  });
});

describe("annotations from the live registry", () => {
  const m = catalog();
  const useCase = definitionKey("catalog", "UseCase");
  const rel = relationshipKey("catalog", "solution-addresses");

  it("on the entry, each entity record (one per backend) and the relationship", () => {
    const a = annotationsFor([m], UP, [entry()]);
    expect(Object.keys(a).sort()).toEqual(
      ["arras:catalog", definitionKey("catalog", "Solution"), useCase, rel].sort(),
    );
    expect(a["arras:catalog"]).toEqual([
      {
        badge: "record: memory",
        tone: "positive",
        tooltip:
          "memory is the system of record: it serves LATEST reads and holds the module's document",
      },
      {
        badge: "replica: memory_replica",
        tone: "neutral",
        tooltip: "memory_replica serves BULK reads from a replica",
      },
    ]);
    expect(a[useCase]).toEqual([
      {
        badge: "memory · mutable",
        tone: "positive",
        tooltip:
          "memory (record store): mutable, applies this type's actions; latency interactive; filter columns: code, name; counts",
      },
      {
        badge: "memory_replica · read-only",
        tone: "neutral",
        tooltip:
          "memory_replica (replica): read-only replica; latency batch; filter columns: code, name; counts",
      },
    ]);
    expect(a[rel]).toEqual([
      {
        badge: "follows: memory, memory_replica",
        tone: "info",
        tooltip: "Backends whose capabilities follow addresses from catalog.Solution",
      },
    ]);
  });

  it("an unavailable backend: the capabilities it no longer reports become 'unavailable', a warning", () => {
    const down = catalog();
    for (const t of down.entityTypes) delete t.capabilities.memory_replica;
    const status = [
      defined(UP[0], "UP[0]"),
      { ...defined(UP[1], "UP[1]"), available: false, reason: "unreachable" },
    ];
    const a = annotationsFor([down], status, [entry()]);
    expect(defined(a["arras:catalog"], 'a["arras:catalog"]').map((x) => [x.badge, x.tone])).toEqual(
      [
        ["record: memory", "positive"],
        ["replica: memory_replica", "neutral"],
        ["memory_replica · unavailable", "warning"],
      ],
    );
    expect(defined(a[useCase], "a[useCase]").map((x) => [x.badge, x.tone])).toEqual([
      ["memory · mutable", "positive"],
      ["memory_replica · unavailable", "warning"],
    ]);
    expect(
      defined(defined(a[useCase], "a[useCase]")[1], 'defined(a[useCase], "a[useCase]")[1]').tooltip,
    ).toBe(
      "memory_replica (replica): unavailable now (unreachable), so it reports no capabilities",
    );
    expect(defined(defined(a[rel], "a[rel]")[0], 'defined(a[rel], "a[rel]")[0]').badge).toBe(
      "follows: memory",
    );
  });

  it("a backend that reports nothing for a type while available: 'not served'; nothing followed: a warning", () => {
    const odd = catalog();
    delete defined(odd.entityTypes[0], "odd.entityTypes[0]").capabilities.memory_replica;
    for (const t of odd.entityTypes)
      for (const c of Object.values(t.capabilities)) c.relationships = [];
    const a = annotationsFor([odd], UP, [entry()]);
    expect(defined(a[useCase], "a[useCase]")[1]).toEqual({
      badge: "memory_replica · not served",
      tone: "warning",
      tooltip: "memory_replica (replica): reports no capabilities for this type",
    });
    expect(a[rel]).toEqual([
      {
        badge: "not followed",
        tone: "warning",
        tooltip: "No available backend reports addresses among its capabilities",
      },
    ]);
  });

  it("a read-only record store is neutral, its tooltip says read-only; the tones do not depend on the scheme", () => {
    const ro = catalog();
    for (const t of ro.entityTypes)
      defined(t.capabilities.memory, "t.capabilities.memory").mutable = false;
    const a = annotationsFor([ro], UP, [entry()]);
    expect(defined(a[useCase], "a[useCase]").map((x) => [x.badge, x.tone])).toEqual([
      ["memory · read-only", "neutral"],
      ["memory_replica · read-only", "neutral"],
    ]);
    expect(
      defined(defined(a[useCase], "a[useCase]")[0], 'defined(a[useCase], "a[useCase]")[0]').tooltip,
    ).toMatch(/^memory \(record store\): read-only; /);
    // No scheme parameter: package 1.1.2's tones pass in dark too (e2e/umf-explorer.spec.ts).
    expect(annotationsFor.length).toBe(3);
  });

  it("only for modules in the catalog, and only for records the document declares", () => {
    expect(annotationsFor([m], UP, [])).toEqual({});
    expect(annotationsFor([{ ...m, name: "other" }], UP, [entry()])).toEqual({});
    const a = annotationsFor([m], UP, [
      entry("arras:catalog", '{"modules":[{"id":"catalog","elements":[]}]}'),
    ]);
    expect(Object.keys(a)).toEqual(["arras:catalog"]);
  });
});

describe("the theme from the console's tokens", () => {
  afterEach(() => {
    document.documentElement.removeAttribute("style");
    vi.unstubAllGlobals();
  });

  it("maps each token the contract accepts, with the console's scheme", () => {
    document.documentElement.style.setProperty("--surface", "#ffffff");
    document.documentElement.style.setProperty("--fg", "#151a23");
    document.documentElement.style.setProperty("--umf-muted", "#4a5365");
    document.documentElement.style.setProperty("--line", "#d5d9e1");
    document.documentElement.style.setProperty("--accent", "#1f4fd8");
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: q === "(prefers-color-scheme: dark)",
      media: q,
    }));
    const t = hostTheme();
    expect(t.theme).toBe("dark");
    expect(t.themeVariables).toMatchObject({
      "--paper": "#ffffff",
      "--ink": "#151a23",
      "--muted": "#4a5365",
      "--line": "#d5d9e1",
      "--accent": "#1f4fd8",
    });
    expect(Object.keys(THEME_TOKENS)).toEqual([
      "--paper",
      "--ink",
      "--muted",
      "--line",
      "--accent",
    ]);
  });

  it("reads the tokens from the console's root, not the page's, so a host's own tokens of those names are ignored", () => {
    document.documentElement.style.setProperty("--accent", "#ff0000");
    document.documentElement.style.setProperty("--surface", "#000000");
    const root = document.createElement("div");
    root.className = "arras-root";
    root.style.setProperty("--accent", "#1f4fd8");
    root.style.setProperty("--surface", "#ffffff");
    const inner = document.createElement("div");
    root.append(inner);
    document.body.append(root);
    try {
      expect(hostTheme(inner).themeVariables).toMatchObject({
        "--accent": "#1f4fd8",
        "--paper": "#ffffff",
      });
      expect(hostTheme(document).themeVariables).toMatchObject({ "--accent": "#1f4fd8" });
    } finally {
      root.remove();
    }
  });

  it("takes the nearest ancestor's inline color-scheme before the console's own computed one", () => {
    const outer = document.createElement("div");
    outer.style.colorScheme = "dark";
    const root = document.createElement("div");
    root.className = "arras-root";
    const rule = document.createElement("style"); // what the console's own tokens set where the host says nothing
    rule.textContent = ".arras-root { color-scheme: light }";
    document.head.append(rule);
    const inner = document.createElement("div");
    root.append(inner);
    outer.append(root);
    document.body.append(outer);
    try {
      expect(schemeOf(inner)).toBe("dark");
      outer.setAttribute("data-appearance", "light"); // an explicit appearance still comes first
      expect(schemeOf(inner)).toBe("light");
    } finally {
      rule.remove();
      outer.remove();
    }
  });

  it("reads an inline color-scheme as the scheme only when it is one scheme, light or dark, alone or with `only` (the stylesheet's table, scheme.vectors.json)", () => {
    for (const { style, os, want } of vectors as {
      style: string;
      os: "light" | "dark";
      want: "light" | "dark";
    }[]) {
      vi.stubGlobal("matchMedia", (q: string) => ({
        matches: q === "(prefers-color-scheme: dark)" && os === "dark",
      }));
      const host = document.createElement("div");
      host.setAttribute("style", style);
      const inner = document.createElement("div");
      host.append(inner);
      document.body.append(host);
      try {
        expect(schemeOf(inner), `${style} with the system ${os}`).toBe(want);
      } finally {
        host.remove();
      }
    }
  });

  it("is light, with no variables, where nothing is set and matchMedia is missing", () => {
    vi.stubGlobal("matchMedia", undefined);
    const t = hostTheme();
    expect(t.theme).toBe("light");
    expect(Object.keys(t.themeVariables).filter((k) => k !== "--umf-font")).toEqual([]);
  });
});
