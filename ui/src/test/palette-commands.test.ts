// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { checkText } from "../api/search";
import {
  type Command,
  commandsFor,
  primaryCommands,
  rankCommands,
  scoreCommand,
  searchServed,
} from "../lib/paletteCommands";
import { catalog } from "./fake";

const cmd = (label: string, detail = ""): Command => ({
  id: label,
  kind: "action",
  label,
  detail,
  route: { area: "actions" },
});

describe("palette commands", () => {
  it("lists the areas (Changes only when shown), then the types, then the declared actions", () => {
    const m = catalog();
    const ids = (audit: boolean) => commandsFor(m, audit).map((c) => c.id);
    expect(ids(true)).toEqual([
      "area:model",
      "area:graph",
      "area:entities",
      "area:actions",
      "area:changes",
      "area:query",
      "type:catalog.UseCase",
      "type:catalog.Solution",
      ...m.actions.map((a) => `action:${a.name}`),
    ]);
    expect(ids(false)).not.toContain("area:changes");
  });

  it("routes a type to its Entities list and an action to its form", () => {
    const all = commandsFor(catalog(), true);
    expect(all.find((c) => c.id === "type:catalog.Solution")?.route).toEqual({
      module: "catalog",
      area: "entities",
      type: "catalog.Solution",
    });
    expect(all.find((c) => c.id === "action:catalog.CorrectSolution")?.route).toEqual({
      module: "catalog",
      area: "actions",
      action: "catalog.CorrectSolution",
    });
  });

  it("an empty query shows the areas and a few types, never an action", () => {
    const shown = rankCommands(commandsFor(catalog(), true), "  ");
    expect(shown.map((c) => c.kind)).toEqual([
      "area",
      "area",
      "area",
      "area",
      "area",
      "area",
      "type",
      "type",
    ]);
    expect(primaryCommands(commandsFor(catalog(), false))).toHaveLength(5 + 2);
  });

  it("ranks a prefix before a word prefix before a substring, case-insensitively", () => {
    const all = [cmd("Preserve"), cmd("Reserve"), cmd("Correct Server"), cmd("Query")];
    expect(rankCommands(all, "SERVE").map((c) => c.label)).toEqual([
      "Correct Server",
      "Preserve",
      "Reserve",
    ]);
    expect(rankCommands(all, "res").map((c) => c.label)).toEqual(["Reserve", "Preserve"]);
  });

  it("matches every word, in the label or the description, the label counting for more", () => {
    const a = cmd("CorrectSolution", "Correct a solution's coverage level");
    const b = cmd("Coverage", "Something else");
    expect(scoreCommand(a, "coverage level")).toBeGreaterThan(0);
    expect(scoreCommand(a, "coverage nothing")).toBe(0);
    expect(rankCommands([a, b], "coverage").map((c) => c.label)).toEqual([
      "Coverage",
      "CorrectSolution",
    ]);
  });

  it("an action is found by its description", () => {
    const hits = rankCommands(commandsFor(catalog(), true), "coverage level");
    expect(hits.map((c) => c.id)).toEqual(["action:catalog.CorrectSolution"]);
  });

  it("equal scores keep the commands' own order", () => {
    expect(rankCommands([cmd("b1"), cmd("b2"), cmd("b0")], "b").map((c) => c.label)).toEqual([
      "b1",
      "b2",
      "b0",
    ]);
  });

  it("knows whether any type's backend serves text search", () => {
    expect(searchServed(catalog())).toBe(true);
    const none = catalog();
    for (const t of none.entityTypes)
      for (const c of Object.values(t.capabilities)) c.search = "none";
    expect(searchServed(none)).toBe(false);
  });
});

describe("the text rules (CONTRACT-010 C)", () => {
  it("accepts 2 to 200 characters and at most 6 words, collapsed", () => {
    expect(checkText("  lumen   alert ")).toEqual({ ok: true, text: "lumen alert" });
    expect(checkText("")).toEqual({ ok: false, reason: "empty" });
    expect(checkText("h")).toEqual({ ok: false, reason: "short" });
    expect(checkText("x".repeat(201))).toEqual({ ok: false, reason: "long" });
    expect(checkText("a b c d e f g")).toEqual({ ok: false, reason: "words" });
    expect(checkText("a b c d e f").ok).toBe(true);
  });
});
