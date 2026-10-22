// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { tabTarget } from "../components/Tabs";
import { titleFor } from "../console/useDocumentTitle";
import {
  AREA_ALIASES,
  actionHref,
  canonicalHash,
  entityHref,
  formatHash,
  groupHref,
  parseHash,
  type Route,
  sameRoute,
} from "../route";

const roundTrip = (r: Route, prefix?: string) => parseHash(formatHash(r, prefix), prefix);

describe("the console route grammar (CONTRACT-010 D)", () => {
  it("writes each area's address", () => {
    expect(formatHash({ module: "catalog", area: "model" })).toBe("#/catalog/model");
    expect(formatHash({ module: "catalog", area: "query" })).toBe("#/catalog/query");
    expect(formatHash({ module: "catalog", area: "entities", type: "catalog.Product" })).toBe(
      "#/catalog/entities/catalog.Product",
    );
    expect(
      formatHash(
        { module: "catalog", area: "entities", type: "catalog.Product", key: "lumen" },
        "operate",
      ),
    ).toBe("#/operate/catalog/entities/catalog.Product/lumen");
    expect(
      formatHash({ module: "catalog", area: "graph", type: "catalog.Product", key: "lumen" }),
    ).toBe("#/catalog/graph/catalog.Product/lumen");
    expect(
      formatHash({ module: "catalog", area: "changes", type: "catalog.Product", key: "lumen" }),
    ).toBe("#/catalog/changes/catalog.Product/lumen");
    expect(formatHash({ module: "catalog", area: "actions", action: "catalog.Approve" })).toBe(
      "#/catalog/actions/catalog.Approve",
    );
  });

  it("round-trips every shape, with and without a prefix", () => {
    const routes: Route[] = [
      { module: "catalog", area: "model" },
      { module: "catalog", area: "entities" },
      { module: "catalog", area: "entities", type: "catalog.UseCase" },
      { module: "catalog", area: "entities", type: "catalog.UseCase", key: "uc-1" },
      { module: "catalog", area: "graph", type: "catalog.UseCase", key: "uc-1" },
      { module: "catalog", area: "changes", type: "catalog.UseCase", key: "uc-1" },
      { module: "catalog", area: "actions" },
      { module: "catalog", area: "actions", action: "catalog.Approve" },
      {
        module: "catalog",
        area: "actions",
        action: "catalog.Approve",
        input: { solution: "sol-1", "use case": "a&b=c" },
      },
    ];
    for (const r of routes) {
      for (const prefix of [undefined, "operate"]) {
        const back = roundTrip(r, prefix);
        expect(formatHash(back, prefix)).toBe(formatHash(r, prefix));
        expect(back).toMatchObject(r);
      }
    }
  });

  it("percent-encodes every segment and reads odd keys back", () => {
    const key = "a/b c?#é%&=+";
    const hash = formatHash({ module: "m o", area: "entities", type: "t/y", key });
    expect(hash).toBe(`#/m%20o/entities/t%2Fy/${encodeURIComponent(key)}`);
    expect(hash.split("/")).toHaveLength(5);
    expect(parseHash(hash)).toEqual({ module: "m o", area: "entities", type: "t/y", key });
    // the query separator in a key is encoded, so it never starts a query
    expect(parseHash(formatHash({ module: "m", area: "actions", action: "a?b" }))).toMatchObject({
      action: "a?b",
    });
  });

  it("writes prefill as ?in.<input>=<key> inside the fragment, for actions only", () => {
    const route: Route = {
      module: "catalog",
      area: "actions",
      action: "catalog.CorrectSolution",
      input: { solution: "sol-1", level: "a b" },
    };
    expect(formatHash(route, "operate")).toBe(
      "#/operate/catalog/actions/catalog.CorrectSolution?in.solution=sol-1&in.level=a%20b",
    );
    expect(formatHash({ ...route, area: "entities" })).not.toContain("?");
    expect(formatHash({ ...route, action: undefined })).not.toContain("?");
    expect(
      parseHash("#/catalog/actions/catalog.Approve?in.solution=sol-1&x=1&in.=n&in.k=%E0%A4%A&bad"),
    ).toEqual({
      module: "catalog",
      area: "actions",
      action: "catalog.Approve",
      input: { solution: "sol-1" },
    });
    expect(parseHash("#/catalog/actions/catalog.Approve?x=1").input).toBeUndefined();
    expect(parseHash("#/catalog/actions/a?in.__proto__=x").input).toEqual(
      Object.fromEntries([["__proto__", "x"]]),
    );
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });

  it("falls back to the module's area for a fragment that does not fit", () => {
    const area = (a: Route["area"]) => ({ module: "catalog", area: a });
    expect(parseHash("#/catalog/bogus/x")).toEqual(area("model"));
    expect(parseHash("#/catalog")).toEqual(area("model"));
    expect(parseHash("#/catalog/entities/a/b/c")).toEqual(area("entities"));
    expect(parseHash("#/catalog/entities//k")).toEqual(area("entities"));
    expect(parseHash("#/catalog/entities/t/%E0%A4%A")).toEqual(area("entities"));
    expect(parseHash("#/catalog/graph/t")).toEqual(area("graph"));
    expect(parseHash("#/catalog/graph")).toEqual(area("graph"));
    expect(parseHash("#/catalog/changes/t/k/extra")).toEqual(area("changes"));
    expect(parseHash("#/catalog/actions/a/b")).toEqual(area("actions"));
    expect(parseHash("#/catalog/model/anything/else")).toEqual(area("model"));
  });

  it("falls back to no module when the module does not parse, and ignores a trailing slash", () => {
    expect(parseHash("")).toEqual({ area: "model" });
    expect(parseHash("#/")).toEqual({ area: "model" });
    expect(parseHash("#//entities")).toEqual({ area: "model" });
    expect(parseHash("#/%E0%A4%A/entities")).toEqual({ area: "model" });
    expect(parseHash("#/operate", "operate")).toEqual({ area: "model" });
    expect(parseHash("#/operate/catalog/entities/", "operate")).toEqual({
      module: "catalog",
      area: "entities",
    });
    expect(parseHash("#/catalog/entities/t/", undefined)).toMatchObject({ type: "t" });
  });

  it("reads the prefix only when the first segment is it", () => {
    expect(parseHash("#/operate/catalog/entities/catalog.P/k", "operate")).toEqual({
      module: "catalog",
      area: "entities",
      type: "catalog.P",
      key: "k",
    });
    expect(parseHash("#/catalog/model", "operate")).toEqual({ module: "catalog", area: "model" });
  });

  it("a key needs its type, and Graph and Audit need both, to be written", () => {
    expect(formatHash({ module: "m", area: "entities", key: "k" })).toBe("#/m/entities");
    expect(formatHash({ module: "m", area: "graph", type: "t" })).toBe("#/m/graph");
    expect(formatHash({ module: "m", area: "changes", key: "k" })).toBe("#/m/changes");
    expect(formatHash({ area: "model" })).toBe("#/");
    expect(formatHash({ area: "model" }, "operate")).toBe("#/operate");
  });

  it("a change group opens its receipt in Changes: changes?group=<id> round-trips", () => {
    const href = groupHref("catalog", "g 4", "operate");
    expect(href).toBe("#/operate/catalog/changes?group=g%204");
    expect(parseHash(href, "operate")).toEqual({
      module: "catalog",
      area: "changes",
      group: "g 4",
    });
    expect(formatHash({ module: "catalog", area: "changes", group: "g-4" })).toBe(
      "#/catalog/changes?group=g-4",
    );
    // An entity wins over a stray group, and an empty group is none.
    expect(
      formatHash({ module: "catalog", area: "changes", type: "t", key: "k", group: "g-4" }),
    ).toBe("#/catalog/changes/t/k");
    expect(parseHash("#/catalog/changes?group=")).toEqual({ module: "catalog", area: "changes" });
  });

  it("entityHref and actionHref build the addresses every link uses", () => {
    expect(entityHref("catalog", "entities", "catalog.Product", "lumen", "operate")).toBe(
      "#/operate/catalog/entities/catalog.Product/lumen",
    );
    expect(entityHref("catalog", "graph", "catalog.Product", "a b", "operate")).toBe(
      "#/operate/catalog/graph/catalog.Product/a%20b",
    );
    // No prefix is none: the address of a console that owns the whole fragment.
    expect(entityHref("catalog", "graph", "catalog.Product", "k")).toBe(
      "#/catalog/graph/catalog.Product/k",
    );
    expect(entityHref("catalog", "changes", "catalog.Product", "k", "ops")).toBe(
      "#/ops/catalog/changes/catalog.Product/k",
    );
    expect(actionHref("catalog", "catalog.Approve", undefined, "operate")).toBe(
      "#/operate/catalog/actions/catalog.Approve",
    );
    expect(actionHref("catalog", "catalog.Approve", { solution: "sol-1" }, "operate")).toBe(
      "#/operate/catalog/actions/catalog.Approve?in.solution=sol-1",
    );
    expect(
      parseHash(entityHref("catalog", "entities", "catalog.Product", "x/y", "operate"), "operate"),
    ).toEqual({
      module: "catalog",
      area: "entities",
      type: "catalog.Product",
      key: "x/y",
    });
  });

  it("two routes are the same when they write the same address", () => {
    expect(
      sameRoute({ module: "m", area: "model", by: undefined } as Route, {
        module: "m",
        area: "model",
      }),
    ).toBe(true);
    expect(
      sameRoute({ module: "m", area: "model", type: "t" }, { module: "m", area: "model" }),
    ).toBe(false);
    expect(
      sameRoute(
        { module: "m", area: "entities", type: "t" },
        { module: "m", area: "entities", type: "u" },
      ),
    ).toBe(false);
  });
});

describe("the Operate route grammar: aliases", () => {
  it("accepts schema, data and audit for model, entities and changes and writes the new ids", () => {
    expect(AREA_ALIASES).toEqual({ schema: "model", data: "entities", audit: "changes" });
    const alias = "#/operate/catalog/audit/catalog.Solution/sol-1";
    const route = parseHash(alias, "operate");
    expect(route).toEqual({
      module: "catalog",
      area: "changes",
      type: "catalog.Solution",
      key: "sol-1",
    });
    expect(formatHash(route, "operate")).toBe("#/operate/catalog/changes/catalog.Solution/sol-1");
    expect(formatHash(parseHash("#/operate/catalog/schema", "operate"), "operate")).toBe(
      "#/operate/catalog/model",
    );
    expect(
      formatHash(parseHash("#/operate/catalog/data/catalog.Solution/k", "operate"), "operate"),
    ).toBe("#/operate/catalog/entities/catalog.Solution/k");
    expect(parseHash("#/catalog/audit?group=g-1")).toEqual({
      module: "catalog",
      area: "changes",
      group: "g-1",
    });
  });

  it("canonicalHash gives the current form of an alias fragment, and nothing for any other", () => {
    expect(canonicalHash("#/operate/catalog/data/catalog.P/k", "operate")).toBe(
      "#/operate/catalog/entities/catalog.P/k",
    );
    expect(canonicalHash("#/catalog/schema")).toBe("#/catalog/model");
    expect(canonicalHash("#/operate/catalog/audit?group=g", "operate")).toBe(
      "#/operate/catalog/changes?group=g",
    );
    expect(canonicalHash("#/operate/catalog/model", "operate")).toBeUndefined();
    expect(canonicalHash("#/operate/catalog", "operate")).toBeUndefined();
  });

  it("the shell's earlier prefix #/admin is read as #/operate and written as #/operate", () => {
    expect(parseHash("#/admin/catalog/entities/catalog.P/k", "operate")).toEqual(
      parseHash("#/operate/catalog/entities/catalog.P/k", "operate"),
    );
    expect(canonicalHash("#/admin/catalog/entities/catalog.P/k", "operate")).toBe(
      "#/operate/catalog/entities/catalog.P/k",
    );
    expect(canonicalHash("#/admin/catalog/data/catalog.P/k", "operate")).toBe(
      "#/operate/catalog/entities/catalog.P/k",
    );
    expect(canonicalHash("#/admin/catalog/model")).toBeUndefined();
    // without a shell prefix `admin` is a module's name
    expect(parseHash("#/admin/model")).toEqual({ module: "admin", area: "model" });
  });

  it("an area id that is not an own alias (a prototype name) is not an area", () => {
    expect(parseHash("#/catalog/constructor/x")).toEqual({ module: "catalog", area: "model" });
    expect(parseHash("#/catalog/__proto__")).toEqual({ module: "catalog", area: "model" });
  });
});

describe("the Operate route grammar: every field round-trips", () => {
  const instant = "2026-10-12T14:30:00.000Z";
  const routes: Route[] = [
    { module: "catalog", area: "model", type: "catalog.Solution" },
    { module: "catalog", area: "model", view: "umf" },
    { module: "catalog", area: "model", type: "catalog.Solution", view: "umf" },
    { module: "catalog", area: "changes", view: "loads" },
    { module: "catalog", area: "entities", type: "catalog.Solution", filter: { id: "a&b c" } },
    {
      module: "catalog",
      area: "entities",
      type: "catalog.Solution",
      filter: { id: "sol-1", solution: "s=1&2" },
      after: "sol/9",
      sort: { column: "created at", dir: "desc" },
    },
    {
      module: "catalog",
      area: "entities",
      type: "catalog.Solution",
      sort: { column: "a:b", dir: "asc" },
    },
    { module: "catalog", area: "changes" },
    { module: "catalog", area: "changes", group: "g 4" },
    { module: "catalog", area: "changes", action: "catalog.Approve" },
    { module: "catalog", area: "changes", since: instant, until: "2026-10-13T00:00:00+02:00" },
    {
      module: "catalog",
      area: "changes",
      type: "catalog.Solution",
      key: "sol-1",
      action: "catalog.Retire",
      since: instant,
    },
    { module: "catalog", area: "graph", type: "catalog.Solution", key: "sol-1" },
    { module: "catalog", area: "actions", action: "catalog.Approve", input: { solution: "s 1" } },
    { module: "catalog", area: "query" },
  ];

  it("parses back what it formats, with and without a prefix", () => {
    for (const r of routes)
      for (const prefix of [undefined, "operate"]) {
        const hash = formatHash(r, prefix);
        expect(parseHash(hash, prefix)).toEqual(r);
        expect(formatHash(parseHash(hash, prefix), prefix)).toBe(hash);
      }
  });

  it("writes the grammar the design names", () => {
    expect(
      formatHash(
        {
          module: "catalog",
          area: "entities",
          type: "catalog.Solution",
          filter: { id: "a b" },
          after: "k 1",
          sort: { column: "name", dir: "desc" },
        },
        "operate",
      ),
    ).toBe("#/operate/catalog/entities/catalog.Solution?f.id=a%20b&after=k%201&sort=name%3Adesc");
    expect(
      formatHash({ module: "catalog", area: "model", type: "catalog.Solution", view: "umf" }),
    ).toBe("#/catalog/model/catalog.Solution?view=umf");
    expect(
      formatHash({
        module: "catalog",
        area: "changes",
        action: "catalog.Approve",
        since: "2026-10-12T14:30:00Z",
        until: "2026-10-13T14:30:00Z",
      }),
    ).toBe(
      "#/catalog/changes?action=catalog.Approve&since=2026-10-12T14%3A30%3A00Z&until=2026-10-13T14%3A30%3A00Z",
    );
  });

  it("writes a field only where its area reads it", () => {
    const all: Route = {
      module: "m",
      area: "graph",
      type: "t",
      key: "k",
      view: "umf",
      filter: { a: "b" },
      after: "x",
      sort: { column: "c", dir: "asc" },
      since: "2026-10-12T14:30:00Z",
      action: "a",
    };
    expect(formatHash(all)).toBe("#/m/graph/t/k");
    expect(formatHash({ ...all, area: "query" })).toBe("#/m/query");
    expect(formatHash({ ...all, area: "model" })).toBe("#/m/model/t?view=umf");
    // a page open on one entity carries no page start or sort; a table with no type carries no filter
    expect(formatHash({ ...all, area: "entities" })).toBe("#/m/entities/t/k?f.a=b");
    expect(formatHash({ ...all, area: "entities", type: undefined })).toBe("#/m/entities");
    // an entity's history carries no group
    expect(formatHash({ ...all, area: "changes", group: "g" })).toBe(
      "#/m/changes/t/k?action=a&since=2026-10-12T14%3A30%3A00Z",
    );
  });

  it("leaves out a value that does not fit its field rather than throwing", () => {
    const at = (rest: string) => parseHash(`#/catalog/${rest}`);
    expect(at("model?view=other")).toEqual({ module: "catalog", area: "model" });
    expect(at("model?view=umf")).toEqual({ module: "catalog", area: "model", view: "umf" });
    expect(at("changes?since=yesterday&until=2026-13-45T99:99:99Z&action=")).toEqual({
      module: "catalog",
      area: "changes",
    });
    expect(at("changes?since=2026-10-12")).toEqual({ module: "catalog", area: "changes" });
    expect(at("entities/t?sort=name&after=")).toEqual({
      module: "catalog",
      area: "entities",
      type: "t",
    });
    expect(at("entities/t?sort=name:sideways")).toEqual({
      module: "catalog",
      area: "entities",
      type: "t",
    });
    expect(at("entities/t?sort=:asc")).toEqual({ module: "catalog", area: "entities", type: "t" });
    expect(at("entities/t?f.=x&f.a=%E0%A4%A&after=%E0%A4%A&%E0%A4%A=1")).toEqual({
      module: "catalog",
      area: "entities",
      type: "t",
    });
    expect(at("entities/t?f.__proto__=x").filter).toEqual(Object.fromEntries([["__proto__", "x"]]));
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
    expect(() => at("changes?%&=&&?since")).not.toThrow();
  });

  it("a fragment that does not fit its area falls back to the area", () => {
    const area = (a: Route["area"]) => ({ module: "catalog", area: a });
    expect(parseHash("#/catalog/model/a/b")).toEqual(area("model"));
    expect(parseHash("#/catalog/changes/t")).toEqual(area("changes"));
    expect(parseHash("#/catalog/changes/t/k/x?action=a")).toEqual(area("changes"));
    expect(parseHash("#/catalog/entities/a/b/c?f.x=1")).toEqual(area("entities"));
    expect(parseHash("#/catalog/entities//k")).toEqual(area("entities"));
  });

  it("the parser accepts only what the writer emits", () => {
    // a view that the area's writer never emits is left out, and so is a field of another area
    expect(parseHash("#/catalog/model?view=loads")).toEqual({ module: "catalog", area: "model" });
    expect(parseHash("#/catalog/changes?view=umf")).toEqual({ module: "catalog", area: "changes" });
    expect(parseHash("#/catalog/changes?view=loads")).toEqual({
      module: "catalog",
      area: "changes",
      view: "loads",
    });
    expect(parseHash("#/catalog/query?view=umf&action=a&f.id=1&after=k")).toEqual({
      module: "catalog",
      area: "query",
    });
    expect(parseHash("#/catalog/actions/a?after=k&sort=x:asc&since=2026-01-01T00:00:00Z")).toEqual({
      module: "catalog",
      area: "actions",
      action: "a",
    });
    // the page start and the sort belong to the table, not to an open entity
    const e = formatHash({ module: "catalog", area: "entities", type: "t", key: "k", after: "a" });
    expect(parseHash(e)).toEqual({ module: "catalog", area: "entities", type: "t", key: "k" });
  });

  it("carries no person: by and the person's name are not representable", () => {
    const withBy = { module: "catalog", area: "changes", by: "alice", person: "bob" } as Route;
    expect(formatHash(withBy)).toBe("#/catalog/changes");
    expect(parseHash("#/catalog/changes?by=alice&person=bob&principal=x")).toEqual({
      module: "catalog",
      area: "changes",
    });
  });

  it("a query string carries only keys, column ids, sort directions, instants, action names and views", () => {
    const hash = formatHash({
      module: "catalog",
      area: "entities",
      type: "catalog.Solution",
      filter: { id: "sol-1" },
      after: "sol-0",
      sort: { column: "id", dir: "asc" },
    });
    const query = hash.slice(hash.indexOf("?") + 1);
    const names = query.split("&").map((p) => decodeURIComponent(p.split("=")[0] ?? ""));
    expect(names).toEqual(["f.id", "after", "sort"]);
    expect(Object.keys(parseHash(hash)).sort()).toEqual(
      ["after", "area", "filter", "module", "sort", "type"].sort(),
    );
  });

  it("groupHref writes changes?group=", () => {
    expect(groupHref("catalog", "g-4", "operate")).toBe("#/operate/catalog/changes?group=g-4");
    expect(entityHref("catalog", "changes", "catalog.P", "k", "operate")).toBe(
      "#/operate/catalog/changes/catalog.P/k",
    );
  });
});

describe("the page title", () => {
  it("is <entity, action or type> · <Area label> · <module> · Arras with the empty parts dropped", () => {
    expect(
      titleFor(
        { module: "catalog", area: "entities", type: "catalog.P", key: "lumen" },
        "entities",
      ),
    ).toBe("lumen · Entities · catalog · Arras");
    expect(titleFor({ module: "catalog", area: "entities", type: "catalog.P" }, "entities")).toBe(
      "catalog.P · Entities · catalog · Arras",
    );
    expect(
      titleFor({ module: "catalog", area: "actions", action: "catalog.Approve" }, "actions"),
    ).toBe("catalog.Approve · Actions · catalog · Arras");
    expect(
      titleFor({ module: "catalog", area: "changes", action: "catalog.Approve" }, "changes"),
    ).toBe("catalog.Approve · Changes · catalog · Arras");
    expect(titleFor({ module: "catalog", area: "model", type: "catalog.P" }, "model")).toBe(
      "catalog.P · Model · catalog · Arras",
    );
    expect(
      titleFor({ module: "catalog", area: "graph", type: "catalog.P", key: "k" }, "graph"),
    ).toBe("k · Graph · catalog · Arras");
    expect(titleFor({ module: "catalog", area: "query" }, "query")).toBe("Query · catalog · Arras");
    expect(titleFor({ area: "model" }, "model")).toBe("Arras");
  });

  it("names the area that is shown when the route's is not available", () => {
    expect(titleFor({ module: "catalog", area: "changes", type: "t", key: "k" }, "model")).toBe(
      "Model · catalog · Arras",
    );
  });
});

describe("tab keys (WAI-ARIA tabs)", () => {
  it("Left and Right wrap, Home and End jump, other keys do nothing", () => {
    expect(tabTarget("ArrowRight", 0, 3)).toBe(1);
    expect(tabTarget("ArrowRight", 2, 3)).toBe(0);
    expect(tabTarget("ArrowLeft", 0, 3)).toBe(2);
    expect(tabTarget("ArrowLeft", 2, 3)).toBe(1);
    expect(tabTarget("Home", 2, 3)).toBe(0);
    expect(tabTarget("End", 0, 3)).toBe(2);
    expect(tabTarget("ArrowDown", 0, 3)).toBeNull();
    expect(tabTarget("a", 0, 3)).toBeNull();
    expect(tabTarget("ArrowRight", 0, 0)).toBeNull();
  });
});
