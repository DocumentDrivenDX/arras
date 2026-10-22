// SPDX-License-Identifier: MIT OR Apache-2.0
/**
 * The route audit (FR-74, SD-013): every screen and state of both modes has an address, and the
 * address round-trips in its own grammar, restores on a fresh load and sets the document title.
 * The table below is the single list; `ui/README.md` carries the same table.
 *
 * | Mode   | Screen and state            | Address                                                                              | Document title                                                    |
 * | ------ | --------------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
 * | Explore | Chooser                     | `#/explore`                                                                           | `Arras`                                                         |
 * | Explore | Module entry                | `#/explore/catalog`                                                                   | `Product catalog · Arras`                                       |
 * | Explore | Type list                   | `#/explore/catalog/UseCase`                                                           | `Use cases · Product catalog · Arras`                           |
 * | Explore | Type list with position     | `#/explore/catalog/UseCase?after=uc-1`                                                | `Use cases · Product catalog · Arras`                           |
 * | Explore | Entity                      | `#/explore/catalog/Solution/sol-1`                                                    | `Lumen alert correlation (S-017) · Solutions · Product catalog · Arras` |
 * | Explore | Entity with History         | `#/explore/catalog/Solution/sol-1/history`                                            | `Lumen alert correlation (S-017) · Solutions · Product catalog · Arras` |
 * | Operate  | Model                       | `#/operate/catalog/model`                                                              | `Model · catalog · Arras`                                       |
 * | Operate  | Model with a selected type  | `#/operate/catalog/model/catalog.Solution`                                             | `catalog.Solution · Model · catalog · Arras`                    |
 * | Operate  | Model UMF view              | `#/operate/catalog/model?view=umf`                                                     | `Model · catalog · Arras`                                       |
 * | Operate  | Entities type               | `#/operate/catalog/entities/catalog.Solution`                                          | `catalog.Solution · Entities · catalog · Arras`                 |
 * | Operate  | Entities with an entity     | `#/operate/catalog/entities/catalog.Solution/sol-1`                                    | `sol-1 · Entities · catalog · Arras`                            |
 * | Operate  | Entities with a filter      | `#/operate/catalog/entities/catalog.Solution?f.code=sol-1`                             | `catalog.Solution · Entities · catalog · Arras`                 |
 * | Operate  | Entities with a page start  | `#/operate/catalog/entities/catalog.Solution?after=sol-1`                              | `catalog.Solution · Entities · catalog · Arras`                 |
 * | Operate  | Entities with a sort        | `#/operate/catalog/entities/catalog.Solution?sort=name%3Adesc`                           | `catalog.Solution · Entities · catalog · Arras`                 |
 * | Operate  | Graph with a selection      | `#/operate/catalog/graph/catalog.Solution/sol-1`                                       | `sol-1 · Graph · catalog · Arras`                               |
 * | Operate  | Actions                     | `#/operate/catalog/actions`                                                            | `Actions · catalog · Arras`                                     |
 * | Operate  | Actions with a prefill      | `#/operate/catalog/actions/catalog.CorrectSolution?in.solution=sol-1`                  | `catalog.CorrectSolution · Actions · catalog · Arras`           |
 * | Operate  | Changes                     | `#/operate/catalog/changes`                                                            | `Changes · catalog · Arras`                                     |
 * | Operate  | Changes with an entity      | `#/operate/catalog/changes/catalog.Solution/sol-1`                                     | `sol-1 · Changes · catalog · Arras`                             |
 * | Operate  | Changes with action, since, until | `#/operate/catalog/changes?action=catalog.CorrectSolution&since=2026-01-01T00%3A00%3A00Z&until=2026-02-01T00%3A00%3A00Z` | `catalog.CorrectSolution · Changes · catalog · Arras` |
 * | Operate  | Changes with a group        | `#/operate/catalog/changes?group=g-1`                                                  | `Changes · catalog · Arras`                                     |
 * | Operate  | Changes, the import loads   | `#/operate/catalog/changes?view=loads`                                                 | `Changes · catalog · Arras`                                     |
 * | Operate  | Query                       | `#/operate/catalog/query`                                                              | `Query · catalog · Arras`                                       |
 *
 * Search text, a Query statement, a typed value and a person are in no address: the parsers have no
 * field for them. The legacy area ids `schema`, `data` and `audit` are read and rewritten to
 * `model`, `entities` and `changes`.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { MetaData } from "../api/types";
import {
  type ExploreLocation,
  formatExplore,
  parseExplore,
  sameLocation,
} from "../browser/location";
import { resolveLocation } from "../browser/resolve";
import { browseTitle } from "../browser/useBrowserTitle";
import { titleFor } from "../console/useDocumentTitle";
import { type Area, canonicalHash, formatHash, parseHash, type Route } from "../route";
import { modules } from "./browserFake";

const BRAND = "Arras";
const SINCE = "2026-01-01T00:00:00Z";
const UNTIL = "2026-02-01T00:00:00Z";

interface ExploreRow {
  mode: "explore";
  state: string;
  hash: string;
  loc: ExploreLocation;
  title: string;
}
interface OperateRow {
  mode: "operate";
  state: string;
  hash: string;
  route: Route;
  title: string;
}
type Row = ExploreRow | OperateRow;

const SOLUTION = "Lumen alert correlation (S-017) · Solutions · Product catalog · Arras";
const USE_CASES = "Use cases · Product catalog · Arras";
const A = "#/operate/catalog";
const catalog = { module: "catalog" } as const;
const solution = { ...catalog, type: "catalog.Solution" } as const;

const explore = (state: string, hash: string, loc: ExploreLocation, title: string): ExploreRow => ({
  mode: "explore",
  state,
  hash,
  loc,
  title,
});
const operate = (state: string, path: string, route: Route, title: string): OperateRow => ({
  mode: "operate",
  state,
  hash: `${A}/${path}`,
  route,
  title,
});

/** Every addressable screen and state of both modes: its address, what it parses to, its title. */
const ROWS: Row[] = [
  explore("Chooser", "#/explore", {}, BRAND),
  explore("Module entry", "#/explore/catalog", { module: "catalog" }, `Product catalog · ${BRAND}`),
  explore(
    "Type list",
    "#/explore/catalog/UseCase",
    { module: "catalog", type: "UseCase" },
    USE_CASES,
  ),
  explore(
    "Type list with position",
    "#/explore/catalog/UseCase?after=uc-1",
    { module: "catalog", type: "UseCase", after: "uc-1" },
    USE_CASES,
  ),
  explore(
    "Entity",
    "#/explore/catalog/Solution/sol-1",
    { module: "catalog", type: "Solution", key: "sol-1" },
    SOLUTION,
  ),
  explore(
    "Entity with History",
    "#/explore/catalog/Solution/sol-1/history",
    { module: "catalog", type: "Solution", key: "sol-1", history: true },
    SOLUTION,
  ),
  operate("Model", "model", { ...catalog, area: "model" }, `Model · catalog · ${BRAND}`),
  operate(
    "Model with a selected type",
    "model/catalog.Solution",
    { ...solution, area: "model" },
    `catalog.Solution · Model · catalog · ${BRAND}`,
  ),
  operate(
    "Model UMF view",
    "model?view=umf",
    { ...catalog, area: "model", view: "umf" },
    `Model · catalog · ${BRAND}`,
  ),
  operate(
    "Entities type",
    "entities/catalog.Solution",
    { ...solution, area: "entities" },
    `catalog.Solution · Entities · catalog · ${BRAND}`,
  ),
  operate(
    "Entities with an entity",
    "entities/catalog.Solution/sol-1",
    { ...solution, area: "entities", key: "sol-1" },
    `sol-1 · Entities · catalog · ${BRAND}`,
  ),
  operate(
    "Entities with a filter",
    "entities/catalog.Solution?f.code=sol-1",
    { ...solution, area: "entities", filter: { code: "sol-1" } },
    `catalog.Solution · Entities · catalog · ${BRAND}`,
  ),
  operate(
    "Entities with a page start",
    "entities/catalog.Solution?after=sol-1",
    { ...solution, area: "entities", after: "sol-1" },
    `catalog.Solution · Entities · catalog · ${BRAND}`,
  ),
  operate(
    "Entities with a sort",
    "entities/catalog.Solution?sort=name%3Adesc",
    { ...solution, area: "entities", sort: { column: "name", dir: "desc" } },
    `catalog.Solution · Entities · catalog · ${BRAND}`,
  ),
  operate(
    "Graph with a selection",
    "graph/catalog.Solution/sol-1",
    { ...solution, area: "graph", key: "sol-1" },
    `sol-1 · Graph · catalog · ${BRAND}`,
  ),
  operate("Actions", "actions", { ...catalog, area: "actions" }, `Actions · catalog · ${BRAND}`),
  operate(
    "Actions with a prefill",
    "actions/catalog.CorrectSolution?in.solution=sol-1",
    {
      ...catalog,
      area: "actions",
      action: "catalog.CorrectSolution",
      input: { solution: "sol-1" },
    },
    `catalog.CorrectSolution · Actions · catalog · ${BRAND}`,
  ),
  operate("Changes", "changes", { ...catalog, area: "changes" }, `Changes · catalog · ${BRAND}`),
  operate(
    "Changes with an entity",
    "changes/catalog.Solution/sol-1",
    { ...solution, area: "changes", key: "sol-1" },
    `sol-1 · Changes · catalog · ${BRAND}`,
  ),
  operate(
    "Changes with action, since, until",
    `changes?action=catalog.CorrectSolution&since=${encodeURIComponent(SINCE)}&until=${encodeURIComponent(UNTIL)}`,
    { ...catalog, area: "changes", action: "catalog.CorrectSolution", since: SINCE, until: UNTIL },
    `catalog.CorrectSolution · Changes · catalog · ${BRAND}`,
  ),
  operate(
    "Changes with a group",
    "changes?group=g-1",
    { ...catalog, area: "changes", group: "g-1" },
    `Changes · catalog · ${BRAND}`,
  ),
  operate(
    "Changes, the import loads",
    "changes?view=loads",
    { ...catalog, area: "changes", view: "loads" },
    `Changes · catalog · ${BRAND}`,
  ),
  operate("Query", "query", { ...catalog, area: "query" }, `Query · catalog · ${BRAND}`),
];

const EXPLORE_ROWS = ROWS.filter((r): r is ExploreRow => r.mode === "explore");
const OPERATE_ROWS = ROWS.filter((r): r is OperateRow => r.mode === "operate");

// The completeness guard. A key added to `Route` or `ExploreLocation` makes these literals fail to
// type-check until it is listed here, and the test below then needs a row that sets it.
const ROUTE_FIELDS: Record<keyof Route, true> = {
  module: true,
  area: true,
  type: true,
  key: true,
  action: true,
  group: true,
  input: true,
  view: true,
  filter: true,
  after: true,
  sort: true,
  since: true,
  until: true,
};
const BROWSE_FIELDS: Record<keyof ExploreLocation, true> = {
  module: true,
  type: true,
  key: true,
  history: true,
  after: true,
};

const used = (objects: object[]) =>
  new Set(objects.flatMap((o) => Object.keys(o).filter((k) => (o as never)[k] !== undefined)));

const meta: MetaData = { modules: modules(), status: [] };

describe("the route audit table", () => {
  it("lists at least 22 addressable states, each once", () => {
    expect(ROWS.length).toBeGreaterThanOrEqual(22);
    expect(new Set(ROWS.map((r) => r.hash)).size).toBe(ROWS.length);
  });

  it("has a row that sets every field of Route", () => {
    const covered = used(OPERATE_ROWS.map((r) => r.route));
    expect(Object.keys(ROUTE_FIELDS).filter((f) => !covered.has(f))).toEqual([]);
    expect([...covered].filter((f) => !(f in ROUTE_FIELDS))).toEqual([]);
  });

  it("has a row that sets every field of ExploreLocation", () => {
    const covered = used(EXPLORE_ROWS.map((r) => r.loc));
    expect(Object.keys(BROWSE_FIELDS).filter((f) => !covered.has(f))).toEqual([]);
    expect([...covered].filter((f) => !(f in BROWSE_FIELDS))).toEqual([]);
  });

  it("covers every area of the console", () => {
    const areas = new Set<Area>(OPERATE_ROWS.map((r) => r.route.area));
    expect([...areas].sort()).toEqual(
      ["actions", "changes", "entities", "graph", "model", "query"].sort(),
    );
  });

  it("is the table in this file's header, row for row", () => {
    const header = readFileSync(import.meta.filename, "utf8").split("*/")[0] ?? "";
    for (const r of ROWS) {
      expect(header, r.state).toContain(`\`${r.hash}\``);
      expect(header, r.state).toContain(`\`${r.title}\``);
    }
  });
});

describe("Explore addresses round-trip in browser/location.ts", () => {
  it.each(EXPLORE_ROWS.map((r) => [r.state, r] as const))("%s", (_s, r) => {
    expect(formatExplore(r.loc)).toBe(r.hash);
    const parsed = parseExplore(r.hash);
    expect(parsed).toEqual({ kind: "explore", loc: r.loc });
    expect(parseExplore(formatExplore(r.loc))).toEqual(parsed);
    if (parsed.kind === "explore") expect(sameLocation(parsed.loc, r.loc)).toBe(true);
    expect(formatExplore((parsed as { loc: ExploreLocation }).loc)).toBe(r.hash);
  });

  it("an entity key with reserved characters survives the round trip", () => {
    const loc = { module: "catalog", type: "Solution", key: "a/b?c#d e" };
    expect(parseExplore(formatExplore(loc))).toEqual({ kind: "explore", loc });
  });
});

describe("Operate addresses round-trip in route.ts", () => {
  it.each(OPERATE_ROWS.map((r) => [r.state, r] as const))("%s", (_s, r) => {
    expect(formatHash(r.route, "operate")).toBe(r.hash);
    expect(parseHash(r.hash, "operate")).toEqual(r.route);
    expect(parseHash(formatHash(r.route, "operate"), "operate")).toEqual(r.route);
    // as a bare console route, without the shell's prefix
    expect(parseHash(formatHash(r.route))).toEqual(r.route);
    expect(canonicalHash(r.hash, "operate")).toBeUndefined();
  });

  it("an entity key and a filter key with reserved characters survive the round trip", () => {
    const r: Route = {
      ...solution,
      area: "entities",
      filter: { "co&de": "a=b/c" },
      after: "k #1",
    };
    expect(parseHash(formatHash(r, "operate"), "operate")).toEqual(r);
  });
});

describe("the legacy area ids are rewritten", () => {
  const aliased = (r: OperateRow, from: Area, old: string) =>
    r.route.area === from ? [r.hash.replace(`/${from}`, `/${old}`)] : [];
  const cases = OPERATE_ROWS.flatMap((r) => [
    ...aliased(r, "model", "schema").map((h) => [h, r] as const),
    ...aliased(r, "entities", "data").map((h) => [h, r] as const),
    ...aliased(r, "changes", "audit").map((h) => [h, r] as const),
  ]);

  it("includes an alias of every aliased area", () => {
    expect(new Set(cases.map(([h]) => h.split("?")[0]?.split("/")[3]))).toEqual(
      new Set(["schema", "data", "audit"]),
    );
  });

  it.each(cases)("%s reads as its row and is rewritten to %#", (old, r) => {
    expect(parseHash(old, "operate")).toEqual(r.route);
    expect(canonicalHash(old, "operate")).toBe(r.hash);
  });
});

describe("the document title", () => {
  it.each(OPERATE_ROWS.map((r) => [r.state, r] as const))("Operate: %s", (_s, r) => {
    expect(titleFor(r.route, r.route.area, BRAND)).toBe(r.title);
  });

  it.each(EXPLORE_ROWS.map((r) => [r.state, r] as const))("Explore: %s", (_s, r) => {
    const parsed = parseExplore(r.hash);
    const resolved = resolveLocation(meta, parsed);
    const state = { status: "ready", entity: { code: "S-017", name: "Lumen alert correlation" } };
    expect(browseTitle(BRAND, meta, resolved, state as never)).toBe(r.title);
  });

  it("Explore: a loading entity is the type, module and brand, never its key", () => {
    const resolved = resolveLocation(meta, parseExplore("#/explore/catalog/Solution/sol-1"));
    const title = browseTitle(BRAND, meta, resolved, { status: "loading" });
    expect(title).toBe("Solutions · Product catalog · Arras");
  });

  it.each(["#/explore/nowhere", "#/explore/catalog/Nothing", "#/explore/catalog/Solution/a/nope"])(
    "Explore: %s, which names nothing, is the brand alone",
    (hash) => {
      const resolved = resolveLocation(meta, parseExplore(hash));
      expect(browseTitle(BRAND, meta, resolved, { status: "na" })).toBe(BRAND);
    },
  );

  it("carries a renamed brand last in both modes", () => {
    expect(titleFor({ ...catalog, area: "query" }, "query", "Example")).toBe(
      "Query · catalog · Example",
    );
    const resolved = resolveLocation(meta, parseExplore("#/explore/catalog"));
    expect(browseTitle("Example", meta, resolved, { status: "loading" })).toBe(
      "Product catalog · Example",
    );
  });
});

describe("what no address can carry", () => {
  const SECRET = "needle-text";
  const ALIEN = ["q", "search", "sql", "statement", "value", "person", "user", "as"];

  it("Operate: a search, a statement, a value or a person in the query string is dropped", () => {
    for (const r of OPERATE_ROWS) {
      const extra = ALIEN.map((n) => `${n}=${SECRET}`).join("&");
      const hash = r.hash.includes("?") ? `${r.hash}&${extra}` : `${r.hash}?${extra}`;
      const parsed = parseHash(hash, "operate");
      expect(parsed, r.state).toEqual(r.route);
      expect(JSON.stringify(parsed)).not.toContain(SECRET);
      expect(formatHash(parsed, "operate")).not.toContain(SECRET);
    }
  });

  it("Operate: a Query address is the area alone, whatever follows it", () => {
    const parsed = parseHash(`${A}/query?sql=select%201&q=x`, "operate");
    expect(parsed).toEqual({ ...catalog, area: "query" });
    expect(formatHash(parsed, "operate")).toBe(`${A}/query`);
  });

  it("Operate: only the in.<name> prefill of an action reaches its route, and only as a string", () => {
    const parsed = parseHash(
      `${A}/actions/catalog.CorrectSolution?summary=typed&in.solution=sol-1`,
      "operate",
    );
    expect(parsed.input).toEqual({ solution: "sol-1" });
  });

  it("Explore: any query other than a lone after=<key> on a type list does not parse", () => {
    for (const hash of [
      "#/explore/catalog?q=text",
      "#/explore/catalog/UseCase?q=text",
      "#/explore/catalog/UseCase?after=uc-1&q=text",
      "#/explore/catalog/UseCase/uc-1?after=uc-2",
      "#/explore/catalog/UseCase?person=carol",
      "#/explore/catalog/UseCase?after=",
    ])
      expect(parseExplore(hash), hash).toEqual({ kind: "invalid" });
  });

  it("Explore: no field of the location is text, a statement, a typed value or a person", () => {
    expect(Object.keys(BROWSE_FIELDS).sort()).toEqual([
      "after",
      "history",
      "key",
      "module",
      "type",
    ]);
  });
});
