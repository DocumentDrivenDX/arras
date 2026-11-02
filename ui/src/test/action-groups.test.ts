// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { defaultAction, relevantTo } from "../areas/actionRelevance";
import {
  contextOf,
  groupActions,
  matchesFilter,
  OTHER_GROUP,
  targetType,
} from "../lib/actionGroups";
import { createFormFocus, requestInputFocus, takeInputFocus } from "../lib/formFocus";
import { planRefLabels, readRefLabels, titleSelection } from "../lib/relLabels";
import { actions, link, m } from "./actionFixtures";
import { defined } from "./defined";
import { catalog } from "./fake";

describe("actionGroups", () => {
  it("names the type an action is about from its effects", () => {
    expect(targetType(m, defined(actions[0]))).toBe("Solution");
    expect(targetType(m, defined(actions[5]))).toBe("UseCase");
    expect(targetType(m, link)).toBe("Solution"); // a link: its relationship's source
    expect(targetType(m, defined(actions[6]))).toBeUndefined();
  });
  it("groups by type in the module's order, the rest under Other, last", () => {
    const g = groupActions(m);
    expect(g.map((x) => x.title)).toEqual(["UseCase", "Solution", OTHER_GROUP]);
    expect(g[1]?.actions.map((a) => a.name)).toEqual([
      "catalog.AddSolution",
      "catalog.CorrectSolution",
      "catalog.Archive",
      "catalog.RenameSolution",
      "catalog.LinkSolution",
    ]);
    expect(g[2]?.actions.map((a) => a.name)).toEqual(["catalog.Ping"]);
  });
  it("filters on name and description, ignoring case, and drops empty groups", () => {
    expect(matchesFilter(defined(actions[6]), "PING")).toBe(true);
    expect(matchesFilter(defined(actions[6]), "sends")).toBe(true);
    expect(matchesFilter(defined(actions[6]), "zzz")).toBe(false);
    expect(groupActions(m, "rename").map((x) => x.title)).toEqual(["UseCase", "Solution"]);
    expect(groupActions(m, "nothing like it")).toEqual([]);
  });
  it("finds the entity in context from the prefilled ref input", () => {
    expect(contextOf(m, "catalog.RenameSolution", { target: "sol-1" })).toEqual({
      type: "Solution",
      key: "sol-1",
    });
    expect(contextOf(m, "catalog.RenameSolution", undefined)).toBeUndefined();
    expect(contextOf(m, "catalog.Nope", { target: "x" })).toBeUndefined();
  });
  it("opens the action asked for, else the first relevant to the entity, else the first declared", () => {
    const ctx = { type: "Solution", key: "sol-1" };
    expect(relevantTo(m, ctx)[0]?.name).toBe("catalog.Archive");
    expect(defaultAction(m, "catalog.Ping", ctx)).toBe("catalog.Ping");
    expect(defaultAction(m, "catalog.Gone", ctx)).toBe("catalog.Archive");
    expect(defaultAction(m, undefined, ctx)).toBe("catalog.Archive");
    expect(defaultAction(m, undefined, undefined)).toBe("catalog.AddSolution");
    expect(defaultAction(catalog({ actions: [] }), undefined, undefined)).toBeUndefined();
  });
});

describe("formFocus", () => {
  it("hands a request over once, to its own action, before it lapses", () => {
    const scope = createFormFocus();
    requestInputFocus(scope, "a.X", "level", 1000);
    expect(takeInputFocus(scope, "a.Y", 1001)).toBeUndefined();
    expect(takeInputFocus(scope, "a.X", 1001)).toBe("level");
    expect(takeInputFocus(scope, "a.X", 1002)).toBeUndefined();
    requestInputFocus(scope, "a.X", "level", 1000);
    expect(takeInputFocus(scope, "a.X", 60_000)).toBeUndefined();
  });
});

describe("relLabels", () => {
  const solution = defined(m.entityTypes.find((t) => t.name === "catalog.Solution"));
  const r = (key: string, type = "catalog.UseCase", module = "catalog") => ({ module, type, key });
  /** The module with its use case titled by this template. */
  const titled = (title: string) => ({
    ...m,
    entityTypes: m.entityTypes.map((t) =>
      t.name === "catalog.UseCase" && t.view ? { ...t, view: { ...t.view, title } } : t,
    ),
  });
  it("selects the placeholders of the resolved view's title, else the key, and nothing without a view", () => {
    expect(titleSelection(solution)).toEqual(["name"]);
    expect(titleSelection({ ...solution, view: undefined })).toBeUndefined();
    const keyed = { ...solution, view: { ...defined(solution.view), title: "Solution" } };
    expect(titleSelection(keyed)).toEqual(["key"]);
    const three = titled("{name} ({code}) {workArea}");
    expect(titleSelection(defined(three.entityTypes[0]))).toEqual(["name", "code", "workArea"]);
  });
  it("plans aliased by-key reads, of one module, with no `target`", () => {
    const [plan, ...more] = planRefLabels(m, [
      r("uc-1"),
      r("uc-1"),
      r("x", "billing.Invoice", "billing"),
    ]);
    expect(more).toEqual([]);
    expect(defined(plan).variables).toEqual({ k0: "uc-1" });
    expect(defined(plan).query).toBe("query($k0: String!) { t0: useCase(key: $k0) { name } }");
  });
  it("chunks at 20 targets and reads at most 60", () => {
    const many = Array.from({ length: 70 }, (_, i) => r(`uc-${i}`));
    const plans = planRefLabels(m, many);
    expect(plans.map((p) => p.refs.length)).toEqual([20, 20, 20]);
    for (const p of plans) expect(p.query.length).toBeLessThan(2000);
  });
  it("holds floor(50 / (1 + placeholders)) targets a request, never past 20", () => {
    const many = Array.from({ length: 40 }, (_, i) => r(`uc-${i}`));
    const counts = (title: string) => planRefLabels(titled(title), many).map((p) => p.refs.length);
    expect(counts("{name}")).toEqual([20, 20]);
    expect(counts("{name} {code}")).toEqual([16, 16, 8]);
    expect(counts("{name} {code} {workArea}")).toEqual([12, 12, 12, 4]);
  });
  it("reads each title as the template over the row; an absent, null or key-only one has none", () => {
    const [plan] = planRefLabels(titled("{name}[ ({code})]"), [r("a"), r("b"), r("c"), r("d")]);
    expect(
      readRefLabels(defined(plan), {
        t0: { name: "Alpha", code: "A1" },
        t1: null,
        t2: { name: "  ", code: "" },
        t3: { name: "Delta", code: "" },
      }),
    ).toEqual({ "catalog.UseCase:a": "Alpha (A1)", "catalog.UseCase:d": "Delta" });
    expect(readRefLabels(defined(plan), null)).toEqual({});
  });
});
