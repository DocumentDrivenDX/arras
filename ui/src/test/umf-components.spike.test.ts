// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  type ComponentModel,
  renderPropertyTable,
  renderRecordMap,
} from "@documentdrivendx/umf-schema-browser";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo } from "../api/types";
import { defined } from "./defined";
import { catalog } from "./fake";

// A spike, not product code: UMF's reusable components (`renderPropertyTable`, `renderRecordMap`,
// package 1.1.2) fed the console's own module, to show what replacing the Schema area's type cards
// and relationship diagram (SchemaBrowser.tsx, Diagram.tsx) would keep and lose. The console does
// not use them yet (docs/intake/umf-explorer-embedding-request.md lists what is missing). These
// assertions record the gaps: when one fails, the gap may be closed and adoption worth revisiting.
// Re-run against 1.1.2: closed are the light-only paper (now `--umf-paper` / `color-scheme`), the
// edge number sharing the badge class (now `umf-map-number`) and one annotation line per record
// (now one line each). Open: endpoints in another module, multiplicity as data, the property
// table's caption and columns, and tone colours a host can set (see the assertions).
const COMPONENTS_CSS = readFileSync(
  resolve(
    __dirname,
    "../../node_modules/@documentdrivendx/umf-schema-browser/assets/components.css",
  ),
  "utf8",
);
vi.unmock("@documentdrivendx/umf-schema-browser");

/** The console's module as the component's model: records by type name, one edge per endpoint pair. */
function model(m: ModuleInfo): ComponentModel {
  return {
    records: m.entityTypes.map((t) => ({
      id: t.name,
      label: t.name.split(".").pop(),
      properties: t.properties.length,
    })),
    edges: m.relationships.flatMap((r) =>
      r.source.flatMap((s) =>
        r.target.map((t) => ({
          id: `${r.name}:${s}>${t}`,
          source: s,
          target: t,
          label: `${r.name} · ${r.sourceMultiplicity} → ${r.targetMultiplicity}`,
          directed: true,
        })),
      ),
    ),
  };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("spike: UMF's record map in place of the console's diagram", () => {
  it("draws the module's types as keyboard-reachable records and its relationships with their multiplicities (in the label)", () => {
    const root = document.createElement("div");
    document.body.append(root);
    const opened: string[] = [];
    renderRecordMap(root, model(catalog()), {
      onNavigate: (id, kind) => opened.push(`${kind}:${id}`),
    });
    const records = root.querySelectorAll('svg a[aria-label^="Inspect record"]');
    expect(records).toHaveLength(2);
    expect(defined(records[0], "records[0]").getAttribute("tabindex")).toBe("0");
    defined(records[0], "records[0]").dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
    expect(opened).toEqual(["record:catalog.UseCase"]);
    expect(
      defined(root.querySelector(".map-relationships"), 'root.querySelector(".map-relationships")')
        .textContent,
    ).toContain("addresses · 0..* → 0..*");
  });

  it("gap: an endpoint in another module is not drawn (the console draws a dashed stub naming the module)", () => {
    const m = catalog({
      relationships: [
        {
          name: "ownedBy",
          source: ["catalog.Solution"],
          target: ["vendors.Vendor"],
          sourceMultiplicity: "0..*",
          targetMultiplicity: "1",
          lifecycle: "independent",
          inverse: null,
        },
      ],
    });
    const root = document.createElement("div");
    document.body.append(root);
    renderRecordMap(root, model(m));
    expect(root.querySelectorAll('svg a[aria-label^="Inspect relationship"]')).toHaveLength(0);
    expect(root.textContent).toContain("1 relationships have endpoints outside this record model");
    expect(root.textContent).not.toContain("vendors");
  });

  it("closed in 1.1.2: the paper is the host's --umf-paper, the edge number has its own class, each annotation has a line", () => {
    const root = document.createElement("div");
    document.body.append(root);
    const two = {
      "catalog.UseCase": [
        { badge: "memory · mutable", tone: "positive" as const },
        { badge: "memory_replica · read-only", tone: "neutral" as const },
      ],
    };
    renderRecordMap(root, model(catalog()), { annotations: two });
    expect(
      defined(root.querySelector("svg rect"), 'root.querySelector("svg rect")').getAttribute(
        "fill",
      ),
    ).toBe("var(--umf-paper,var(--paper,#fffdf7))");
    expect(
      defined(
        root.querySelector("text.umf-map-number"),
        'root.querySelector("text.umf-map-number")',
      ).textContent,
    ).toBe("1");
    expect(root.querySelector("text.umf-annotation:not([data-tone])")).toBeNull();
    // Two annotation lines: the node is 78 + 2 x 16 high and the count sits below the last line.
    const useCase = defined(
      root.querySelector('svg a[aria-label^="Inspect record UseCase"]'),
      "root.querySelector('svg a[aria-label^=\"Inspect record UseCase\"]')",
    );
    expect(
      defined(useCase.querySelector("rect"), 'useCase.querySelector("rect")').getAttribute(
        "height",
      ),
    ).toBe("110");
    const notes = Array.from(useCase.querySelectorAll("text.umf-annotation"), (t) =>
      Number(t.getAttribute("y")),
    );
    const count = Number(
      defined(
        useCase.querySelector("text.map-count"),
        'useCase.querySelector("text.map-count")',
      ).getAttribute("y"),
    );
    expect(Math.max(...notes)).toBeLessThan(count - 12);
  });

  it("gap: tone colours are not tokens: SVG badges are all --umf-ink, HTML badges fixed light pills", () => {
    // In the record map every tone is painted in ink (the state is the badge's text) ...
    expect(COMPONENTS_CSS).toContain(
      ".umf-record-map-view svg .umf-annotation{fill:var(--umf-ink,var(--ink,#203c35))}",
    );
    // ... and the legend's badges keep fixed light backgrounds in both schemes, with no --umf-* token.
    expect(COMPONENTS_CSS).toContain(
      '.umf-annotation[data-tone="positive"]{background:#e2f5e9;color:#185e35}',
    );
    expect(COMPONENTS_CSS).not.toMatch(/--umf-(positive|warning|negative|info|tone)/);
    // Change states, by contrast, are tokens with light/dark fallbacks.
    expect(COMPONENTS_CSS).toContain("var(--umf-created,light-dark(#185e35,#83d9a7))");
  });
});

describe("spike: UMF's property table in place of the console's property chips", () => {
  it("renders one row per property with the value as text, under a fixed caption", () => {
    const t = defined(catalog().entityTypes[0], "catalog().entityTypes[0]");
    const root = document.createElement("div");
    document.body.append(root);
    renderPropertyTable(
      root,
      Object.fromEntries(
        t.properties.map((p) => [
          p.name,
          `${p.type}, ${p.required ? "required" : "optional"}, ${p.cardinality}`,
        ]),
      ),
      {
        annotations: { code: [{ badge: "key", tone: "info" }] },
      },
    );
    const rows = root.querySelectorAll("tr");
    expect(rows).toHaveLength(3);
    expect(
      defined(
        defined(rows[0], "rows[0]").querySelector("th"),
        'defined(rows[0], "rows[0]").querySelector("th")',
      ).getAttribute("scope"),
    ).toBe("row");
    expect(defined(rows[0], "rows[0]").textContent).toBe("codekeystring, required, one");
    // Gap: the caption cannot name the type, so several tables on one page read alike.
    expect(
      defined(root.querySelector("caption"), 'root.querySelector("caption")').textContent,
    ).toBe("Declared properties");
  });
});
