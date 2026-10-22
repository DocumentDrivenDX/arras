// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { MAX_SELECTIONS } from "../api/gql";
import type { Ref } from "../api/types";
import { findQualified, findType } from "../browser/meta";
import {
  type GroupPlan,
  groupsOf,
  MAX_TARGETS,
  pageQueries,
  pictureRefs,
  planLabels,
  readLabels,
  targetOf,
  wantedRefs,
} from "../browser/planner";
import { modules } from "./browserFake";
import { countSelections, parseQuery } from "./gqlmini";

const meta = { modules: modules(), status: [] };
const entry = (module: string, type: string) => {
  const e = findType(meta, module, type);
  if (!e) throw new Error(`no ${module}.${type}`);
  return e;
};
const solution = entry("catalog", "Solution");

const refs = (n: number, type = "catalog.UseCase", module = "catalog"): Ref[] =>
  Array.from({ length: n }, (_, i) => ({ module, type, key: `k-${i}` }));

describe("the node page's page request (SD-011, Node page requests)", () => {
  it("US-067-AC1: the page reads properties, attribution, freshness and relationship keys, never a target", () => {
    const [q, ...rest] = pageQueries(solution);
    expect(rest).toEqual([]);
    expect(q).toContain("solution(key: $key)");
    expect(q).toContain("addresses { module type key }");
    expect(q).toContain("freshness { backend asOf at consistency }");
    expect(q).toContain("createdBy");
    expect(q).not.toContain("target");
  });

  it("a type with more selections than the limit is split across requests, each inside 50", () => {
    const wide = structuredClone(solution);
    wide.view.fields = Array.from({ length: 70 }, (_, i) => ({
      property: `p${i}`,
      label: `P ${i}`,
      format: "text",
      hideWhenEmpty: false,
      tones: null,
    }));
    const queries = pageQueries(wide);
    expect(queries.length).toBeGreaterThan(1);
    for (const q of queries)
      expect(countSelections(parseQuery(q, { key: "k" }))).toBeLessThanOrEqual(MAX_SELECTIONS);
    const all = queries.join(" ");
    for (let i = 0; i < 70; i++) expect(all).toContain(`p${i} `);
    expect(all).toContain("providedBy { module type key }");
  });
});

describe("label requests (US-068)", () => {
  const targets = (n: number, type = "catalog.UseCase", module = "catalog") =>
    refs(n, type, module).map(targetOf);
  const entryOf = (q: string) => findQualified(meta, q);

  it("US-068-AC3: 45 targets of one type are three chunks of at most 20, each inside 50 selections", () => {
    const plans = planLabels(targets(45), entryOf);
    expect(plans.map((p) => p.targets.length)).toEqual([MAX_TARGETS, MAX_TARGETS, 5]);
    for (const p of plans) {
      expect(countSelections(parseQuery(p.query, p.variables))).toBeLessThanOrEqual(MAX_SELECTIONS);
      expect(Object.keys(p.variables)).toHaveLength(p.targets.length);
    }
  });

  it("a type whose title reads many properties makes smaller chunks, by selections", () => {
    const wide = structuredClone(modules());
    const t = wide[0]?.entityTypes.find((x) => x.name === "catalog.UseCase");
    if (!t?.view) throw new Error("no view");
    t.view.title = "{code} {name} {workArea} {description}";
    const m = { modules: wide, status: [] };
    const plans = planLabels(targets(20), (q) => findQualified(m, q));
    expect(plans.length).toBeGreaterThan(1);
    for (const p of plans)
      expect(countSelections(parseQuery(p.query, p.variables))).toBeLessThanOrEqual(MAX_SELECTIONS);
  });

  it("targets per request are floor(50 / (1 + placeholders)), never past MAX_TARGETS", () => {
    const withTitle = (title: string) => {
      const mods = structuredClone(modules());
      const t = mods[0]?.entityTypes.find((x) => x.name === "catalog.UseCase");
      if (!t?.view) throw new Error("no view");
      t.view.title = title;
      return { modules: mods, status: [] };
    };
    const counts = (title: string) => {
      const m = withTitle(title);
      return planLabels(targets(40), (q) => findQualified(m, q)).map((p) => p.targets.length);
    };
    expect(counts("{name}")).toEqual([20, 20]);
    expect(counts("{name} {code}")).toEqual([16, 16, 8]);
    expect(counts("{code} {name} {workArea}")).toEqual([12, 12, 12, 4]);
  });

  it("US-068-AC4: a related entity of another module is read on its own module's endpoint", () => {
    const plans = planLabels([...targets(2), ...targets(2, "other.Note", "other")], entryOf);
    expect(plans.map((p) => p.module)).toEqual(["catalog", "other"]);
    expect(plans[1]?.query).toContain("note(key: $k0)");
  });

  it("US-068-AC5: a target whose type the viewer cannot describe has no plan", () => {
    expect(planLabels(targets(2, "ghost.Thing", "ghost"), entryOf)).toEqual([]);
  });

  it("US-068-AC5, AC7: a null with no error is not available; a refusal is not available; cost or a backend is a retry", () => {
    const [plan] = planLabels(targets(4), entryOf);
    if (!plan) throw new Error("no plan");
    const answer = {
      data: { t0: { key: "k-0", name: "Zero" }, t1: null, t2: null, t3: null },
      errors: [
        { code: "COST_EXCEEDED", path: ["t2"] },
        { code: "REFUSED", path: ["t3"] },
      ],
    };
    const got = readLabels(plan, answer, (_t, row) => String(row.name));
    expect(got).toEqual({
      "catalog.UseCase:k-0": { state: "ok", title: "Zero" },
      "catalog.UseCase:k-1": { state: "na" },
      "catalog.UseCase:k-2": { state: "retry" },
      "catalog.UseCase:k-3": { state: "na" },
    });
    expect(
      readLabels(plan, { data: null, errors: [{ code: "UNAVAILABLE" }] }, () => "")[
        "catalog.UseCase:k-0"
      ],
    ).toEqual({ state: "retry" });
  });
});

describe("what a page asks labels for", () => {
  const group = (field: string, n: number): GroupPlan => ({
    field,
    label: field,
    hideWhenEmpty: false,
    order: 50,
    refs: refs(n, `catalog.${field}`),
  });

  it("US-068-AC3: the first 20 of each group, and the picture's, each once", () => {
    const groups = [group("A", 100), group("B", 3)];
    const wanted = wantedRefs(groups, {}, 40);
    expect(new Set(wanted.map((r) => `${r.type}:${r.key}`)).size).toBe(wanted.length);
    expect(wanted.filter((r) => r.type === "catalog.A")).toHaveLength(37); // 20 + the picture's round-robin
    expect(wanted.filter((r) => r.type === "catalog.B")).toHaveLength(3);
  });

  it("show more labels the next 20 of the keys already read", () => {
    const groups = [group("A", 100)];
    expect(wantedRefs(groups, { A: 40 }, 0)).toHaveLength(40);
    expect(wantedRefs(groups, { A: 120 }, 0)).toHaveLength(100);
  });

  it("US-069-AC3: the picture takes one key per group in turn, at most 40", () => {
    const groups = [group("A", 100), group("B", 100), group("C", 2)];
    const picked = pictureRefs(groups, 40);
    expect(picked).toHaveLength(40);
    expect(picked.filter((r) => r.type === "catalog.C")).toHaveLength(2);
    expect(picked.filter((r) => r.type === "catalog.A")).toHaveLength(19);
  });

  it("groups come from the view's relationship fields, with the keys the page read", () => {
    const entity = { addresses: refs(2), providedBy: refs(1, "catalog.Product"), junk: [1] };
    const groups = groupsOf(solution.view, entity);
    expect(groups.map((g) => [g.field, g.refs.length])).toEqual([
      ["addresses", 2],
      ["providedBy", 1],
      ["notedIn", 0],
    ]);
  });
});
