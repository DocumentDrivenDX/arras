// SPDX-License-Identifier: MIT OR Apache-2.0
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { commandsFor } from "../lib/paletteCommands";
import { GROUP_TITLES, SHORTCUTS } from "../lib/shortcuts";
import {
  AREA_LABELS,
  duplicateLabels,
  FORBIDDEN_WORDS,
  forbiddenIn,
  LABELS,
} from "../lib/vocabulary";
import { AREAS } from "../route";
import { catalog } from "./fake";

describe("the vocabulary (SD-013)", () => {
  it("names every area, in the order of the tabs", () => {
    expect(AREAS.map((a) => AREA_LABELS[a])).toEqual([
      "Model",
      "Graph",
      "Entities",
      "Actions",
      "Changes",
      "Query",
    ]);
  });

  it("uses one label for one meaning: the label-to-meaning map is injective", () => {
    expect(duplicateLabels(LABELS)).toEqual([]);
  });

  it("the injectivity check fails on a planted duplicate, whatever its case", () => {
    expect(duplicateLabels({ ...LABELS, "area.audit": "Changes" })).toEqual(["changes"]);
    expect(duplicateLabels({ ...LABELS, "word.thing": "entity TYPE" })).toEqual(["entity type"]);
  });

  it("says node, edge or vertex in no label", () => {
    for (const label of Object.values(LABELS)) expect(forbiddenIn(label)).toEqual([]);
    for (const label of Object.values(GROUP_TITLES)) expect(forbiddenIn(label)).toEqual([]);
    for (const s of SHORTCUTS) expect(forbiddenIn(s.label)).toEqual([]);
  });

  it("the forbidden-word check really finds the words, as whole words only", () => {
    for (const w of FORBIDDEN_WORDS) expect(forbiddenIn(`Open the ${w} page`)).toEqual([w]);
    expect(forbiddenIn("Node")).toEqual(["node"]);
    expect(forbiddenIn("Open the nodes and edges")).toEqual(["nodes", "edges"]);
    expect(forbiddenIn("Knowledge, decoders and acknowledge")).toEqual([]);
  });

  it("the palette's area commands read the same labels", () => {
    const areas = commandsFor(catalog(), true).filter((c) => c.kind === "area");
    expect(areas.map((c) => c.label)).toEqual(AREAS.map((a) => AREA_LABELS[a]));
  });
});

// Files whose words are the drawing's internal vocabulary, not text a person reads (paths under src/).
const CANVAS_INTERNALS = new Set<string>([]);
const SCANNED = ["areas", "console", "browser", "shell"];
const TEXT_ATTRS = new Set(["aria-label", "ariaLabel", "title", "placeholder", "alt", "label"]);
const TEXT_KINDS = new Set([
  ts.SyntaxKind.JsxText,
  ts.SyntaxKind.StringLiteral,
  ts.SyntaxKind.NoSubstitutionTemplateLiteral,
  ts.SyntaxKind.TemplateHead,
  ts.SyntaxKind.TemplateMiddle,
  ts.SyntaxKind.TemplateTail,
]);

/** Whether a literal is shown to a person: JSX text, or the value of a text-bearing attribute or property. */
function shownToPeople(node: ts.Node): boolean {
  if (node.kind === ts.SyntaxKind.JsxText) return true;
  for (let n: ts.Node | undefined = node.parent; n; n = n.parent) {
    if (ts.isJsxAttribute(n) || ts.isPropertyAssignment(n)) return TEXT_ATTRS.has(n.name.getText());
    if (ts.isJsxExpression(n) && (ts.isJsxElement(n.parent) || ts.isJsxFragment(n.parent)))
      return true;
    if (ts.isJsxElement(n) || ts.isStatement(n) || ts.isArrowFunction(n)) return false;
  }
  return false;
}

function wordsIn(file: string, text: string): string[] {
  const kind = file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  const hits: string[] = [];
  const visit = (node: ts.Node): void => {
    if (TEXT_KINDS.has(node.kind) && shownToPeople(node)) {
      const shown = node.getText(sf);
      const found = forbiddenIn(shown);
      if (found.length > 0)
        hits.push(`${file}: ${found.join(", ")} in ${shown.trim().slice(0, 60)}`);
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return hits;
}

function sourcesUnder(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    if (e.isDirectory()) return sourcesUnder(p);
    return /\.tsx?$/.test(e.name) ? [p] : [];
  });
}

describe("no user-visible string or aria-label says node, edge or vertex", () => {
  it("every shown string under areas, console, browser and shell is clean", () => {
    const root = join(import.meta.dirname, "..");
    const files = SCANNED.flatMap((d) => sourcesUnder(join(root, d))).filter(
      (f) => !CANVAS_INTERNALS.has(relative(root, f)),
    );
    expect(files.length).toBeGreaterThan(20);
    expect(files.flatMap((f) => wordsIn(relative(root, f), readFileSync(f, "utf8")))).toEqual([]);
  });

  it("negative control: a planted word is found in an aria-label, a title, JSX text and a template", () => {
    expect(wordsIn("a.tsx", '<input aria-label="Filter nodes" />')).toHaveLength(1);
    expect(wordsIn("a.tsx", '<div title="Open edge">x</div>')).toHaveLength(1);
    expect(wordsIn("a.tsx", "<p>Pick a vertex</p>")).toHaveLength(1);
    expect(wordsIn("a.tsx", `<g aria-label={\`Move between ${"$"}{n} nodes\`} />`)).toHaveLength(1);
    expect(wordsIn("a.tsx", 'const x = { ariaLabel: "Move between nodes" };')).toHaveLength(1);
    expect(wordsIn("a.tsx", '<p>{"3 nodes"}</p>')).toHaveLength(1);
    expect(wordsIn("a.tsx", '<p>{x ? "Open edge" : ""}</p>')).toHaveLength(1);
    expect(wordsIn("a.tsx", `<p>{\`${"$"}{n} edges\`}</p>`)).toHaveLength(1);
    expect(wordsIn("a.tsx", '<><b>{"a vertex"}</b></>')).toHaveLength(1);
    expect(wordsIn("a.tsx", '<p>{x ? "Open entity" : ""}</p>')).toEqual([]);
    expect(wordsIn("a.tsx", '<input aria-label="Filter entities" />')).toEqual([]);
  });
});
