// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { formatExplore, parseExplore, sameLocation } from "../browser/location";
import { moduleOf, resolveLocation } from "../browser/resolve";
import {
  canonicalMode,
  effectiveMode,
  exploreFor,
  exploreForRoute,
  hashKind,
  operateFor,
  operateHash,
  routeForExplore,
} from "../shell/modeRoute";
import { modules } from "./browserFake";

describe("the Explore location (ADR-024)", () => {
  it("US-071-AC1: a node's address is #/explore/<module>/<type>/<key> with each segment percent-encoded", () => {
    expect(formatExplore({ module: "catalog", type: "Solution", key: "sol-1" })).toBe(
      "#/explore/catalog/Solution/sol-1",
    );
    const odd = formatExplore({ module: "catalog", type: "Solution", key: "a/b c?#é" });
    expect(odd).toBe("#/explore/catalog/Solution/a%2Fb%20c%3F%23%C3%A9");
    expect(parseExplore(odd)).toEqual({
      kind: "explore",
      loc: { module: "catalog", type: "Solution", key: "a/b c?#é" },
    });
  });

  it("the entry and the chooser are shorter forms of the same grammar", () => {
    expect(formatExplore({})).toBe("#/explore");
    expect(formatExplore({ module: "catalog" })).toBe("#/explore/catalog");
    expect(parseExplore("#/explore")).toEqual({ kind: "explore", loc: {} });
    expect(parseExplore("#/explore/catalog")).toEqual({
      kind: "explore",
      loc: { module: "catalog" },
    });
  });

  it("a type's list is the same grammar without a key: it round-trips and a key needs its type", () => {
    const list = formatExplore({ module: "catalog", type: "Use case/s" });
    expect(list).toBe("#/explore/catalog/Use%20case%2Fs");
    expect(parseExplore(list)).toEqual({
      kind: "explore",
      loc: { module: "catalog", type: "Use case/s", key: undefined },
    });
    expect(formatExplore({ module: "catalog", type: "UseCase" })).toBe("#/explore/catalog/UseCase");
    expect(formatExplore({ type: "UseCase" })).toBe("#/explore");
    expect(parseExplore("#/explore/catalog/UseCase/")).toEqual({ kind: "invalid" });
  });

  it("US-071-AC3: a fragment that does not parse is invalid, and another route is not ours", () => {
    for (const bad of [
      "#/explore//x",
      "#/explore/a/b/c/d",
      "#/explore/%E0%A4%A",
      "#/explore/a/%zz",
    ])
      expect(parseExplore(bad)).toEqual({ kind: "invalid" });
    expect(parseExplore("#/operate/catalog")).toEqual({ kind: "other" });
    expect(parseExplore("")).toEqual({ kind: "other" });
  });
});

describe("list position and the History panel address", () => {
  const roundTrip = (loc: Record<string, unknown>) => {
    const parsed = parseExplore(formatExplore(loc));
    expect(parsed.kind).toBe("explore");
    return parsed.kind === "explore" ? parsed.loc : undefined;
  };

  it("every Explore state round-trips", () => {
    expect(formatExplore({ module: "catalog", type: "Solution", after: "k 1" })).toBe(
      "#/explore/catalog/Solution?after=k%201",
    );
    expect(
      formatExplore({ module: "catalog", type: "Solution", key: "a/b?c", history: true }),
    ).toBe("#/explore/catalog/Solution/a%2Fb%3Fc/history");
    expect(roundTrip({})).toEqual({});
    expect(roundTrip({ module: "catalog" })).toEqual({ module: "catalog" });
    expect(roundTrip({ module: "catalog", type: "Solution" })).toEqual({
      module: "catalog",
      type: "Solution",
    });
    expect(roundTrip({ module: "catalog", type: "Solution", after: "k9" })).toEqual({
      module: "catalog",
      type: "Solution",
      after: "k9",
    });
    expect(roundTrip({ module: "catalog", type: "Solution", key: "k" })).toEqual({
      module: "catalog",
      type: "Solution",
      key: "k",
    });
    expect(roundTrip({ module: "catalog", type: "Solution", key: "a/b?c", history: true })).toEqual(
      {
        module: "catalog",
        type: "Solution",
        key: "a/b?c",
        history: true,
      },
    );
  });

  it("hostile keys survive, including one literally named history", () => {
    for (const key of ["a/b", "q?x=1", "h#frag", "50%", "a b", "history", "after=1", "é"]) {
      const entity = { module: "m", type: "T", key };
      expect(roundTrip(entity)).toEqual(entity);
      expect(roundTrip({ ...entity, history: true })).toEqual({ ...entity, history: true });
      const list = { module: "m", type: "T", after: key };
      expect(roundTrip(list)).toEqual(list);
    }
    expect(parseExplore("#/explore/m/T/history")).toEqual({
      kind: "explore",
      loc: { module: "m", type: "T", key: "history" },
    });
    expect(formatExplore({ module: "m", type: "T", key: "history", history: true })).toBe(
      "#/explore/m/T/history/history",
    );
  });

  it("history needs a key and after needs a bare type list; anything else is invalid", () => {
    expect(formatExplore({ module: "m", type: "T", history: true })).toBe("#/explore/m/T");
    expect(formatExplore({ module: "m", type: "T", key: "k", after: "x" })).toBe("#/explore/m/T/k");
    for (const bad of [
      "#/explore/m/T/k/other",
      "#/explore/m/T/k/history/x",
      "#/explore/m/T/k?after=x",
      "#/explore/m/T/k/history?after=x",
      "#/explore/m?after=x",
      "#/explore?after=x",
      "#/explore/m/T?after=",
      "#/explore/m/T?before=x",
      "#/explore/m/T?after=x&y=1",
      "#/explore/m/T?",
      "#/explore/m/T//history",
      "#/explore/m/T/k//",
      "#/explore/m/T?after=%zz",
      "#/explore/m/T/k%/history",
    ])
      expect(parseExplore(bad), bad).toEqual({ kind: "invalid" });
  });

  it("sameLocation compares history and after", () => {
    const e = { module: "m", type: "T", key: "k" };
    expect(sameLocation(e, { ...e })).toBe(true);
    expect(sameLocation(e, { ...e, history: false })).toBe(true);
    expect(sameLocation(e, { ...e, history: true })).toBe(false);
    const l = { module: "m", type: "T" };
    expect(sameLocation({ ...l, after: "a" }, { ...l, after: "a" })).toBe(true);
    expect(sameLocation({ ...l, after: "a" }, { ...l, after: "b" })).toBe(false);
    expect(sameLocation({ ...l, after: "a" }, l)).toBe(false);
  });
});

describe("which page a location is", () => {
  const meta = {
    modules: modules().map((m) => ({ ...m, entityTypes: m.entityTypes })),
    status: [],
  };

  it("US-067-AC6: a missing or unreadable module, type or malformed location is one and the same page", () => {
    const na = { kind: "na" };
    expect(resolveLocation(meta, { kind: "invalid" })).toEqual(na);
    expect(resolveLocation(meta, { kind: "explore", loc: { module: "ghost" } })).toEqual(na);
    // a module that resolved is kept, so the page can lead back to its entry
    const ghostType = resolveLocation(meta, {
      kind: "explore",
      loc: { module: "catalog", type: "Ghost", key: "k" },
    });
    expect(ghostType).toMatchObject(na);
    expect(ghostType.kind === "na" && ghostType.module?.name).toBe("catalog");
  });

  it("a type with no key is the entry listing that type; an unknown type is not available", () => {
    expect(
      resolveLocation(meta, { kind: "explore", loc: { module: "catalog", type: "UseCase" } }),
    ).toMatchObject({ kind: "entry", type: "UseCase" });
    expect(
      resolveLocation(meta, { kind: "explore", loc: { module: "catalog", type: "Ghost" } }),
    ).toMatchObject({ kind: "na" });
  });

  it("a type and a key is a node; a module alone is its entry; several modules offer the chooser", () => {
    const node = resolveLocation(meta, {
      kind: "explore",
      loc: { module: "catalog", type: "Solution", key: "sol-1" },
    });
    expect(node).toMatchObject({ kind: "node", key: "sol-1", history: false });
    expect(moduleOf(node)?.name).toBe("catalog");
    expect(resolveLocation(meta, { kind: "explore", loc: { module: "catalog" } }).kind).toBe(
      "entry",
    );
    expect(resolveLocation(meta, { kind: "explore", loc: {} }).kind).toBe("chooser");
    expect(
      resolveLocation({ ...meta, modules: meta.modules.slice(0, 1) }, { kind: "other" }).kind,
    ).toBe("entry");
    expect(resolveLocation({ ...meta, modules: [] }, { kind: "other" }).kind).toBe("none");
  });
});

describe("the shell's hash grammar (ADR-025)", () => {
  const both = ["user", "admin"] as const;
  const input = (hash: string, over = {}) => ({
    hash,
    modes: both,
    defaultMode: undefined,
    remembered: undefined,
    ...over,
  });

  it("US-072-AC1: an operator opens in Explore unless the fragment or defaultMode says otherwise", () => {
    expect(effectiveMode(input(""))).toBe("user");
    expect(effectiveMode(input("", { defaultMode: "admin" }))).toBe("admin");
    expect(effectiveMode(input("#/explore/catalog", { defaultMode: "admin" }))).toBe("user");
    expect(effectiveMode(input("#/operate/catalog/entities/catalog.UseCase"))).toBe("admin");
    expect(hashKind("#/explore/catalog/UseCase")).toBe("explore");
    expect(effectiveMode(input("#/explore/catalog/UseCase", { defaultMode: "admin" }))).toBe(
      "user",
    );
  });

  it("a fragment's query is cut before its mode is read: a list position is still an Explore address", () => {
    expect(hashKind("#/explore?after=x")).toBe("explore");
    expect(hashKind("#/explore/catalog/UseCase?after=sol-9")).toBe("explore");
    expect(hashKind("#/operate?x=1")).toBe("operate");
    expect(hashKind("#?after=x")).toBe("none");
    expect(hashKind("#/catalog/model?x=1")).toBe("legacy");
    // what follows the query never classifies the address: a slash or a mode name inside it is data
    expect(hashKind("#/explore?next=/admin/catalog")).toBe("explore");
    expect(hashKind("#/operate?next=/browse/catalog")).toBe("operate");
    expect(hashKind("#/?after=x")).toBe("none");
    expect(hashKind("#?/browse")).toBe("none");
    expect(hashKind("#/catalog?/browse")).toBe("legacy");
    expect(effectiveMode(input("#/explore?after=x", { defaultMode: "admin" }))).toBe("user");
  });

  it("the earlier ids #/browse and #/admin are the same modes, and canonicalMode rewrites them once", () => {
    expect(hashKind("#/browse/catalog/UseCase")).toBe("explore");
    expect(hashKind("#/admin/catalog/model")).toBe("operate");
    expect(effectiveMode(input("#/admin/catalog/model"))).toBe("admin");
    expect(effectiveMode(input("#/browse/catalog", { defaultMode: "admin" }))).toBe("user");
    expect(canonicalMode("#/browse")).toBe("#/explore");
    expect(canonicalMode("#/browse/catalog/UseCase?after=x")).toBe(
      "#/explore/catalog/UseCase?after=x",
    );
    expect(canonicalMode("#/admin/catalog/entities/catalog.UseCase")).toBe(
      "#/operate/catalog/entities/catalog.UseCase",
    );
    expect(canonicalMode("#/admin?x=1")).toBe("#/operate?x=1");
    expect(canonicalMode("#/explore/catalog")).toBeUndefined();
    expect(canonicalMode("#/operate/catalog/model")).toBeUndefined();
    expect(canonicalMode("#/administer/catalog")).toBeUndefined();
    expect(canonicalMode("#/catalog/browse")).toBeUndefined();
    expect(parseExplore("#/browse/catalog/UseCase/uc-1")).toEqual(
      parseExplore("#/explore/catalog/UseCase/uc-1"),
    );
  });

  it("the console's earlier fragment form is an Operate route for an operator", () => {
    expect(hashKind("#/catalog/entities/catalog.UseCase")).toBe("legacy");
    expect(effectiveMode(input("#/catalog/entities/catalog.UseCase"))).toBe("admin");
    expect(operateHash("#/catalog/entities/catalog.UseCase")).toBe(
      "#/operate/catalog/entities/catalog.UseCase",
    );
    expect(operateHash("#/operate/catalog/model")).toBe("#/operate/catalog/model");
  });

  it("US-072-AC6: anyone who is not offered Operate is in Explore whatever the fragment says", () => {
    const user = { modes: ["user"] };
    for (const hash of ["#/operate/catalog/entities/x", "#/catalog/model", "", "#/explore"])
      expect(
        effectiveMode(input(hash, { ...user, defaultMode: "admin", remembered: "admin" })),
      ).toBe("user");
  });

  it("US-072-AC2: a node's module, type and key carry over to the console's Data area, the entity open", () => {
    expect(operateFor("#/explore/catalog/Solution/sol-1")).toBe(
      "#/operate/catalog/entities/catalog.Solution/sol-1",
    );
    expect(operateFor("#/explore/catalog/Solution/a%2Fb%20c")).toBe(
      "#/operate/catalog/entities/catalog.Solution/a%2Fb%20c",
    );
    expect(operateFor("#/explore/catalog/Solution")).toBe(
      "#/operate/catalog/entities/catalog.Solution",
    );
    expect(operateFor("#/explore/catalog")).toBe("#/operate/catalog/model");
    expect(operateFor("#/explore")).toBe("#/operate");
    expect(operateFor("#/explore/a/b/c/d")).toBe("#/operate");
  });

  it("an Operate or legacy-alias fragment stays as it is when Operate is asked for", () => {
    expect(operateFor("#/operate/catalog/graph/catalog.Solution/sol-1")).toBe(
      "#/operate/catalog/graph/catalog.Solution/sol-1",
    );
    expect(operateFor("#/catalog/entities/catalog.Solution")).toBe(
      "#/operate/catalog/entities/catalog.Solution",
    );
    expect(operateFor("")).toBe("#/operate");
  });

  it("Explore opens the entity the console shows, else its type's list, else the module", () => {
    expect(exploreFor("#/operate/catalog/entities/catalog.Solution/sol-1")).toBe(
      "#/explore/catalog/Solution/sol-1",
    );
    expect(exploreFor("#/operate/catalog/graph/catalog.Solution/sol-1")).toBe(
      "#/explore/catalog/Solution/sol-1",
    );
    expect(exploreFor("#/operate/catalog/changes/catalog.Solution/a%2Fb")).toBe(
      "#/explore/catalog/Solution/a%2Fb/history",
    );
    expect(exploreFor("#/operate/catalog/entities/catalog.Solution")).toBe(
      "#/explore/catalog/Solution",
    );
    expect(exploreFor("#/operate/catalog/model")).toBe("#/explore/catalog");
    expect(exploreFor("#/operate/catalog/actions/catalog.Approve?in.id=sol-1")).toBe(
      "#/explore/catalog",
    );
    expect(exploreFor("#/operate")).toBe("#/explore");
    expect(exploreFor("#/catalog/entities/catalog.Solution")).toBe("#/explore/catalog/Solution");
    expect(exploreFor("")).toBe("#/explore");
    expect(exploreFor("#/explore/catalog/Solution/sol-1")).toBe("#/explore/catalog/Solution/sol-1");
  });

  it("a console route and an Explore location convert both ways", () => {
    expect(routeForExplore({ module: "catalog", type: "Solution", key: "k" })).toEqual({
      module: "catalog",
      area: "entities",
      type: "catalog.Solution",
      key: "k",
    });
    expect(routeForExplore({})).toEqual({ area: "model" });
    expect(
      exploreForRoute({ module: "catalog", area: "entities", type: "other.Thing", key: "k" }),
    ).toEqual({ module: "catalog", type: "other.Thing", key: "k" });
    expect(exploreForRoute({ area: "model" })).toEqual({});
  });

  it("an entity's History is the console's Changes for it, and a list's position is Entities' page start", () => {
    const history = { module: "catalog", type: "Solution", key: "sol-1", history: true };
    const changes = {
      module: "catalog",
      area: "changes" as const,
      type: "catalog.Solution",
      key: "sol-1",
    };
    expect(routeForExplore(history)).toEqual(changes);
    expect(exploreForRoute(changes)).toEqual(history);
    const list = { module: "catalog", type: "Solution", after: "sol-9" };
    const entities = {
      module: "catalog",
      area: "entities" as const,
      type: "catalog.Solution",
      after: "sol-9",
    };
    expect(routeForExplore(list)).toEqual(entities);
    expect(exploreForRoute(entities)).toEqual(list);
    // a bare type has no position; an entity's page start belongs to the table, not to the entity
    expect(routeForExplore({ module: "catalog", type: "Solution" })).toEqual({
      module: "catalog",
      area: "entities",
      type: "catalog.Solution",
    });
    expect(exploreForRoute({ ...entities, key: "sol-1" })).toEqual({
      module: "catalog",
      type: "Solution",
      key: "sol-1",
    });
  });

  it("the switch carries a History address and a list position both ways", () => {
    expect(operateFor("#/explore/catalog/Solution/sol-1/history")).toBe(
      "#/operate/catalog/changes/catalog.Solution/sol-1",
    );
    expect(exploreFor("#/operate/catalog/changes/catalog.Solution/sol-1")).toBe(
      "#/explore/catalog/Solution/sol-1/history",
    );
    expect(operateFor("#/explore/catalog/Solution?after=sol-9")).toBe(
      "#/operate/catalog/entities/catalog.Solution?after=sol-9",
    );
    expect(exploreFor("#/operate/catalog/entities/catalog.Solution?after=sol-9")).toBe(
      "#/explore/catalog/Solution?after=sol-9",
    );
  });
});
