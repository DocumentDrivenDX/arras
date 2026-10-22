// SPDX-License-Identifier: MIT OR Apache-2.0
// The kit's derivations (SD-013, Business rules 1 to 3), on the example catalog and on hand-made
// modules: which declared actions are an edit, a link, a retire or a create plan, which are claimed,
// and which remain entity actions. Pure functions; no rendering.
import { describe, expect, it } from "vitest";
import type { ActionInfo, Effect, InputSpec, ModuleInfo } from "../api/types";
import {
  changedIds,
  claimsOf,
  createdKey,
  createPlan,
  createPlans,
  editPlan,
  entityActions,
  entityActionsOf,
  groupLinks,
  planTakes,
  propertyActions,
  retirePlan,
  retirePlans,
  splitActions,
  updateOf,
} from "../kit";
import { actions, create, link, m, ref, text, update } from "./actionFixtures";
import { modules } from "./browserFake";
import { exampleCatalog } from "./catalogModule";
import { defined } from "./defined";
import { catalog, decl, receipt } from "./fake";

const cat = exampleCatalog();
const names = (list: { action: ActionInfo }[]) =>
  list.map((x) => x.action.name.replace("catalog.", ""));
const typeOf = (module: ModuleInfo, name: string) =>
  defined(module.entityTypes.find((t) => t.name === name));
const withActions = (list: ActionInfo[]): ModuleInfo => ({ ...cat, actions: list });
const declared = (name: string) => defined(cat.actions.find((a) => a.name === `catalog.${name}`));

describe("createPlan (Rule 2)", () => {
  it("AddSolution creates a solution and links it to the use case it is for", () => {
    const p = defined(createPlan(cat, "catalog.Solution"));
    expect(p.action).toBe("catalog.AddSolution");
    expect(p.key).toEqual({ input: "code" });
    expect(p.inputs.map((i) => i.name)).toEqual([
      "code",
      "name",
      "deliveryMode",
      "summary",
      "workflow",
      "prompt",
      "audience",
      "launchUrl",
      "useCase",
    ]);
    expect(p.refInputs).toEqual(["useCase"]);
  });

  it("AssertCoverage creates a coverage assertion linked at two ref inputs", () => {
    const p = defined(createPlan(cat, "catalog.CoverageAssertion"));
    expect(p.action).toBe("catalog.AssertCoverage");
    expect(p.type).toBe("CoverageAssertion");
    expect(p.refInputs).toEqual(["product", "useCase"]);
  });

  it("AddUseCase is a create with no link at all", () => {
    const p = defined(createPlan(cat, "UseCase"));
    expect(p.action).toBe("catalog.AddUseCase");
    expect(p.refInputs).toEqual([]);
  });

  it("a generated key is a plan whose form does not ask for the key", () => {
    const base = declared("AddUseCase");
    const generated = (key: unknown): ActionInfo => ({
      ...base,
      name: "catalog.NewUseCase",
      effects: base.effects.map((e) => ({ ...e, key })),
    });
    for (const key of [{ kind: "uuid" }, { generate: "uuid" }])
      expect(createPlan(withActions([generated(key)]), "catalog.UseCase")?.key).toEqual({
        generated: true,
      });
  });

  it("several creates of one type are ordered by fewest inputs, then name", () => {
    const small: ActionInfo = {
      ...declared("AddUseCase"),
      name: "catalog.QuickUseCase",
      inputSpecs: [text("code"), text("name")],
    };
    const same: ActionInfo = { ...small, name: "catalog.AnotherUseCase" };
    const plans = createPlans(
      withActions([declared("AddUseCase"), small, same]),
      "catalog.UseCase",
    );
    expect(plans.map((p) => p.action)).toEqual([
      "catalog.AnotherUseCase",
      "catalog.QuickUseCase",
      "catalog.AddUseCase",
    ]);
  });

  it("a type no action creates has none, and neither has a type the module lacks", () => {
    expect(
      createPlan(withActions([declared("UpdateSolution")]), "catalog.Solution"),
    ).toBeUndefined();
    expect(createPlan(cat, "catalog.Nothing")).toBeUndefined();
  });

  it("an action that updates as well as creates is not a plan (negative)", () => {
    const add = declared("AddSolution");
    const both: ActionInfo = {
      ...add,
      name: "catalog.AddAndTouch",
      effects: [...add.effects, ...declared("UpdateSolution").effects],
    };
    expect(createPlan(withActions([both]), "catalog.Solution")).toBeUndefined();
  });

  it("other shapes are not plans: a second create, a link with no created end, a non-ref end, a literal key", () => {
    const add = declared("AddSolution");
    const [first, linkEffect] = add.effects;
    const one = defined(first);
    const two = defined(linkEffect);
    const plan = (effects: ActionInfo["effects"], inputs = add.inputSpecs) =>
      createPlan(withActions([{ ...add, effects, inputSpecs: inputs }]), "catalog.Solution");
    expect(plan([one, two])).toBeDefined();
    expect(plan([one, one])).toBeUndefined();
    expect(plan([one, { ...two, source: { name: "useCase" } }])).toBeUndefined();
    expect(plan([one, { ...two, target: { name: "name" } }])).toBeUndefined();
    expect(plan([{ ...one, key: { literal: "x" } }, two])).toBeUndefined();
    expect(plan([{ ...one, key: { name: "missing" } }, two])).toBeUndefined();
    expect(plan([])).toBeUndefined();
    // the created alias is on both ends
    expect(plan([one, { ...two, target: { alias: "new" } }])).toBeUndefined();
    // the link's other end is another alias
    expect(plan([one, { ...two, target: { alias: "other" } }])?.refInputs).toEqual([]);
  });
});

describe("createdKey (Rule 2: the entity a create made)", () => {
  const plan = defined(createPlan(cat, "catalog.Solution"));
  const made = (key: string): Effect => ({
    kind: "create",
    ref: { type: "catalog.Solution", key },
    properties: {},
  });
  const done = (...keys: string[]) =>
    receipt({ refs: keys.map((key) => ({ type: "catalog.Solution", key, version: 1 })) });

  it("is the validated create key when the receipt confirms it", () => {
    expect(createdKey(plan, [made("s-1")], done("s-1"))).toBe("s-1");
  });

  it("is the validated key even where the receipt touched other entities of the type", () => {
    expect(createdKey(plan, [made("s-2")], done("s-1", "s-2"))).toBe("s-2");
  });

  it("falls back to the receipt's one ref of the type where it does not carry the validated key", () => {
    expect(createdKey(plan, [made("generated")], done("s-9"))).toBe("s-9");
    expect(createdKey(plan, [], done("s-9"))).toBe("s-9");
  });

  it("names nothing where the receipt has none or several of the type and none is the validated key", () => {
    expect(createdKey(plan, [made("s-1")], receipt({ refs: [] }))).toBeUndefined();
    expect(createdKey(plan, [made("s-1")], done("s-8", "s-9"))).toBeUndefined();
  });

  it("ignores a ref of another type", () => {
    const other = receipt({ refs: [{ type: "catalog.UseCase", key: "uc-1", version: 1 }] });
    expect(createdKey(plan, [made("uc-1")], other)).toBeUndefined();
  });
});

describe("retirePlan (Rule 3)", () => {
  it("RetireSolution, RetireCoverage and RetireFinding delete their type by a ref input", () => {
    expect(retirePlan(cat, "catalog.Solution")).toEqual({
      action: "catalog.RetireSolution",
      keyInput: "solution",
    });
    expect(retirePlan(cat, "catalog.CoverageAssertion")).toEqual({
      action: "catalog.RetireCoverage",
      keyInput: "coverageAssertion",
    });
    expect(retirePlan(cat, "Finding")?.action).toBe("catalog.RetireFinding");
  });

  it("a type with no deleting action has no Retire", () => {
    for (const t of ["UseCase", "Product", "ProductVersion", "Nothing"])
      expect(retirePlan(cat, `catalog.${t}`), t).toBeUndefined();
  });

  it("needs the key to be a ref input and every other input to be optional", () => {
    const retire = declared("RetireSolution");
    const needy: ActionInfo = {
      ...retire,
      name: "catalog.RetireWithReason",
      inputSpecs: [...retire.inputSpecs, text("reason")],
    };
    const optional: ActionInfo = {
      ...retire,
      name: "catalog.RetireWithNote",
      inputSpecs: [...retire.inputSpecs, text("note", "optional")],
    };
    expect(retirePlans(withActions([needy]), "catalog.Solution")).toEqual([]);
    expect(retirePlans(withActions([optional, retire]), "catalog.Solution")).toHaveLength(2);
    const scalarKey: ActionInfo = { ...retire, inputSpecs: [text("solution")] };
    expect(retirePlan(withActions([scalarKey]), "catalog.Solution")).toBeUndefined();
    const withLink: ActionInfo = { ...retire, effects: [...retire.effects, ...retire.effects] };
    expect(retirePlan(withActions([withLink]), "catalog.Solution")).toBeUndefined();
  });
});

describe("claims (Rule 1)", () => {
  it("an action is claimed by the first plan it qualifies for: edit, link, retire, create", () => {
    const c = claimsOf(cat, "catalog.Solution");
    expect(c.get("catalog.UpdateSolution")).toBe("edit");
    expect(c.get("catalog.CorrectSolution")).toBe("edit");
    expect(c.get("catalog.AddressUseCase")).toBe("link");
    expect(c.get("catalog.UnaddressUseCase")).toBe("link");
    expect(c.get("catalog.SetSolutionProvider")).toBe("link");
    expect(c.get("catalog.RetireSolution")).toBe("retire");
    expect(c.get("catalog.AddSolution")).toBe("create");
    expect(c.has("catalog.RenameUseCase")).toBe(false);
  });

  it("a link action is claimed from either end of the relationship", () => {
    expect(claimsOf(cat, "catalog.UseCase").get("catalog.AddressUseCase")).toBe("link");
    expect(claimsOf(cat, "catalog.UseCase").get("catalog.ApplyFindingTo")).toBe("link");
  });

  it("entityActionsOf is the unclaimed actions that take the type", () => {
    expect(names(entityActionsOf(cat, "catalog.Solution"))).toEqual([]);
    expect(names(entityActionsOf(cat, "catalog.Finding"))).toEqual([]);
    expect(names(entityActionsOf(cat, "catalog.CoverageAssertion"))).toEqual([]);
    // creating a solution or a coverage assertion from a use case or a product is no plan of those
    expect(names(entityActionsOf(cat, "catalog.UseCase"))).toEqual([
      "AddSolution",
      "AssertCoverage",
    ]);
    expect(names(entityActionsOf(cat, "catalog.Product"))).toEqual([
      "AddFinding",
      "AddProductVersion",
      "AssertCoverage",
    ]);
  });

  it("claimed means qualifies, not wins: a loser of the ranking is offered nowhere", () => {
    const coarse = update("CorrectLevel", "Solution", { coverageLevel: "lvl", name: "n" });
    const rename = update("RenameLevel", "Solution", { coverageLevel: "lvl" });
    const mod = catalog({ actions: [coarse, rename] });
    expect(editPlan(mod, typeOf(mod, "catalog.Solution"), "coverageLevel")?.action).toBe(
      "catalog.RenameLevel",
    );
    // both are claimed by editPlan, so neither is an entity action; the loser is not offered
    expect(names(entityActionsOf(mod, "catalog.Solution"))).toEqual([]);
    expect(names(entityActions(mod, "catalog.Solution"))).toEqual(["RenameLevel", "CorrectLevel"]);
  });

  it("an update of a property the type does not have is no edit, so it is an entity action", () => {
    const stray = update("Stray", "Solution", { nonesuch: "x" });
    const mod = catalog({ actions: [stray] });
    expect(names(entityActionsOf(mod, "catalog.Solution"))).toEqual(["Stray"]);
  });

  it("an update needing another required input is no edit plan, so it is an entity action", () => {
    const needy = update("Reclassify", "Solution", { coverageLevel: "lvl" }, [text("reason")]);
    const mod = catalog({ actions: [needy] });
    expect(names(entityActionsOf(mod, "catalog.Solution"))).toEqual(["Reclassify"]);
  });

  it("an action whose inputs or effects the generic form cannot ask or summarise is not offered (Rule 4)", () => {
    const askableAction = update("Reclassify", "Solution", { coverageLevel: "lvl" }, [text("why")]);
    const odd = (a: ActionInfo, name: string): ActionInfo => ({ ...a, name: `catalog.${name}` });
    const strange: InputSpec = {
      name: "blob",
      type: "x",
      kind: "graph" as never,
      cardinality: "one",
    };
    const manyUnknown: InputSpec = { ...text("tags"), cardinality: "several" as never };
    const badInput = odd(
      { ...askableAction, inputSpecs: [...askableAction.inputSpecs, strange] },
      "BadInput",
    );
    const badCardinality = odd(
      { ...askableAction, inputSpecs: [...askableAction.inputSpecs, manyUnknown] },
      "BadCardinality",
    );
    const badEffect = odd(
      {
        ...askableAction,
        effects: [...askableAction.effects, decl({ op: "merge", ref_type: "Solution" })],
      },
      "BadEffect",
    );
    const mod = catalog({ actions: [askableAction, badInput, badCardinality, badEffect] });
    expect(names(entityActions(mod, "catalog.Solution"))).toContain("BadInput");
    expect(names(entityActionsOf(mod, "catalog.Solution"))).toEqual(["Reclassify"]);
  });

  it("record, list and boolean inputs and every one of the five effects are askable", () => {
    const rich: ActionInfo = {
      name: "catalog.Rich",
      description: "",
      inputSpecs: [
        ref("target", "Solution"),
        { name: "rec", type: "Address", kind: "record", cardinality: "optional" },
        { name: "keys", type: "UseCase", kind: "ref", cardinality: "many" },
        { name: "flag", type: "boolean", kind: "scalar", cardinality: "optional" },
      ],
      preconditions: [],
      effects: ["create", "update", "delete", "link", "unlink"].map((op) =>
        decl({ op, ref_type: "Solution" }),
      ),
    };
    const mod = catalog({ actions: [rich] });
    expect(names(entityActionsOf(mod, "catalog.Solution"))).toEqual(["Rich"]);
  });
});

describe("editPlan and groupLinks on the browser fixture and the catalog", () => {
  const browser = defined(modules()[0]);
  const type = typeOf(browser, "catalog.Solution");

  it("prefers the action that changes the fewest properties", () => {
    expect(editPlan(browser, type, "name")?.action).toBe("catalog.RenameSolution");
    expect(editPlan(browser, type, "summary")?.action).toBe("catalog.CorrectSolution");
    expect(editPlan(browser, type, "code")).toBeUndefined(); // the key
    expect(editPlan(browser, type, "tags")).toBeUndefined(); // a list
  });

  it("plans a form for properties an action can only change together, and inline for the rest", () => {
    const caveat = editPlan(browser, type, "caveat");
    expect(caveat?.form).toBe(true);
    expect(caveat?.action).toBe("catalog.SetCaveatAndCost");
    expect(caveat?.fields.map((f) => f.property)).toEqual(["caveat", "cost"]);
    expect(editPlan(browser, type, "audience")?.form).toBe(false);
  });

  it("on the catalog, a lone required property is inline and several that change together are a form", () => {
    expect(editPlan(cat, typeOf(cat, "catalog.UseCase"), "name")?.form).toBe(false);
    const solution = defined(editPlan(cat, typeOf(cat, "catalog.Solution"), "name"));
    expect(solution.action).toBe("catalog.UpdateSolution");
    expect(solution.fields.map((f) => f.property)).toEqual(["name", "deliveryMode"]);
    expect(solution.form).toBe(true);
    const finding = typeOf(cat, "catalog.Finding");
    const plan = defined(editPlan(cat, finding, "status"));
    expect(plan.action).toBe("catalog.UpdateFinding");
    expect(plan.form).toBe(true);
    expect(plan.fields.map((f) => f.property)).toEqual(["statement", "kind", "status"]);
  });

  it("finds the add and remove actions of a relationship, as seen from either end", () => {
    const own = defined(groupLinks(browser, "catalog.Solution", "addresses"));
    expect(own.forward).toBe(true);
    expect(own.otherTypes).toEqual(["catalog.UseCase"]);
    expect(own.add).toEqual({
      action: "catalog.AddressUseCase",
      pageInput: "solution",
      otherInput: "useCase",
      otherType: "catalog.UseCase",
    });
    expect(own.remove?.action).toBe("catalog.UnaddressUseCase");
    const inverse = defined(groupLinks(browser, "catalog.UseCase", "addressedBy"));
    expect(inverse.forward).toBe(false);
    expect(inverse.otherTypes).toEqual(["catalog.Solution"]);
    expect(inverse.add).toEqual({
      action: "catalog.AddressUseCase",
      pageInput: "useCase",
      otherInput: "solution",
      otherType: "catalog.Solution",
    });
  });

  it("records the type each action's other input takes, for a relationship with two target types", () => {
    const wide: ModuleInfo = {
      ...browser,
      relationships: browser.relationships.map((r) =>
        r.name === "addresses" ? { ...r, target: ["catalog.UseCase", "catalog.Product"] } : r,
      ),
    };
    const plans = defined(groupLinks(wide, "catalog.Solution", "addresses"));
    expect(plans.otherTypes).toEqual(["catalog.UseCase", "catalog.Product"]);
    const add = defined(plans.add);
    expect(planTakes(add, "catalog.UseCase")).toBe(true);
    expect(planTakes(add, "catalog.Product")).toBe(false);
    expect(planTakes(defined(plans.remove), "catalog.Product")).toBe(false);
  });

  it("compares qualified names: a same-named type of another module is not the one the input takes", () => {
    const add = defined(defined(groupLinks(browser, "catalog.Solution", "addresses")).add);
    expect(planTakes(add, "catalog.UseCase")).toBe(true);
    expect(planTakes(add, "other.UseCase")).toBe(false);
  });

  it("offers only what the module declares: an add with no remove, and nothing for the rest", () => {
    const provider = defined(groupLinks(browser, "catalog.Solution", "providedBy"));
    expect(provider.add?.action).toBe("catalog.SetSolutionProvider");
    expect(provider.remove).toBeUndefined();
    expect(groupLinks(browser, "catalog.Solution", "notedIn")).toBeUndefined();
    expect(groupLinks(browser, "catalog.Solution", "nothing")).toBeUndefined();
    expect(groupLinks(browser, "catalog.Product", "addresses")).toBeUndefined();
  });
});

describe("changedIds", () => {
  it("collects the entities a change touched from the effects and the receipt", () => {
    const refOf = (type: string, key: string) => ({ type, key });
    const got = changedIds(
      catalog(),
      [
        { kind: "update", ref: refOf("Solution", "sol-1"), set: {}, unset: [] },
        {
          kind: "link",
          relationship: "addresses",
          source: refOf("Solution", "sol-1"),
          target: refOf("UseCase", "uc-1"),
        },
        { kind: "create", ref: { type: "Solution", key: "", generated: true }, properties: {} },
      ],
      receipt({ refs: [{ type: "catalog.Solution", key: "sol-9", version: 1 }] }),
    );
    expect(got.sort()).toEqual([
      "catalog.Solution:sol-1",
      "catalog.Solution:sol-9",
      "catalog.UseCase:uc-1",
    ]);
  });
});

describe("updateOf", () => {
  it("reads an update of the type keyed by a ref input, and the inputs that supply its properties", () => {
    const u = defined(updateOf(defined(actions[1]), "catalog.Solution"), "update");
    expect(u.keyInput.name).toBe("target");
    expect(Object.keys(u.properties)).toEqual(["name", "coverageLevel", "summary"]);
    expect(u.width).toBe(3);
  });
  it("is nothing for a creation, a link, or an update of another type", () => {
    expect(updateOf(defined(actions[0]), "catalog.Solution")).toBeUndefined();
    expect(updateOf(link, "catalog.Solution")).toBeUndefined();
    expect(updateOf(defined(actions[5]), "catalog.Solution")).toBeUndefined();
  });
  it("is nothing when the key is not a ref input", () => {
    const a = update("X", "Solution", { name: "name" });
    a.inputSpecs = a.inputSpecs.map((s) => (s.name === "target" ? text("target") : s));
    expect(updateOf(a, "catalog.Solution")).toBeUndefined();
  });
});

describe("entityActions: relevance ranking (Rule 1a)", () => {
  const order = (type: string) => names(entityActions(m, type));
  // A name that starts like a correction (`Correct...`) carries no rank; ties go by name.
  it("puts updates first: alone before together, then fewest properties, then by name", () => {
    expect(order("catalog.Solution")).toEqual([
      "Archive", // one property, alone
      "RenameSolution", // one property, alone; after Archive by name
      "CorrectSolution", // three properties, together
      "LinkSolution", // takes the entity but is no update
    ]);
  });
  it("a Correct... name does not outrank an equally narrow update", () => {
    const mod = catalog({
      actions: [
        update("CorrectName", "Solution", { name: "name" }),
        update("Archive", "Solution", { coverageLevel: "lvl" }),
      ],
    });
    expect(names(entityActions(mod, "catalog.Solution"))).toEqual(["Archive", "CorrectName"]);
  });
  it("an update that changes a property alone ranks before one that needs more", () => {
    const wide = update("Everything", "Solution", { name: "a", coverageLevel: "b" });
    const optional: ActionInfo = {
      ...wide,
      inputSpecs: wide.inputSpecs.map(
        (s): InputSpec => (s.kind === "ref" ? s : { ...s, cardinality: "optional" }),
      ),
    };
    const narrow = update("Narrow", "Solution", { name: "a" }, [text("reason")]);
    const mod = catalog({ actions: [wide, narrow, { ...optional, name: "catalog.Loose" }] });
    expect(names(entityActions(mod, "catalog.Solution"))).toEqual([
      "Loose",
      "Narrow",
      "Everything",
    ]);
  });
  it("lists only actions that take the type as a ref input", () => {
    expect(order("catalog.UseCase")).toEqual(["RenameUseCase", "LinkSolution"]);
    expect(order("catalog.Missing")).toEqual([]);
  });
  it("derives from the declared effects, not from names", () => {
    const odd = catalog({ actions: [update("Frobnicate", "Solution", { name: "name" })] });
    expect(entityActions(odd, "catalog.Solution")[0]?.updates).toBe(true);
  });
  it("splits the bar's primary actions (updates, at most three) from the menu's", () => {
    const { primary, rest } = splitActions(entityActions(m, "catalog.Solution"));
    expect(primary.map((x) => x.action.name)).toEqual([
      "catalog.Archive",
      "catalog.RenameSolution",
      "catalog.CorrectSolution",
    ]);
    expect(rest.map((x) => x.action.name)).toEqual(["catalog.LinkSolution"]);
    const four = catalog({
      actions: ["A", "B", "C", "D"].map((n) => update(n, "Solution", { name: "n" })),
    });
    expect(splitActions(entityActions(four, "catalog.Solution")).rest).toHaveLength(1);
  });
});

describe("propertyActions: property to action", () => {
  it("chooses, per property, the update that changes it alone, then the fewest properties, then the first by name", () => {
    const p = propertyActions(m, "catalog.Solution");
    expect(p.name).toEqual({ action: "catalog.RenameSolution", keyInput: "target", input: "name" });
    expect(p.coverageLevel?.action).toBe("catalog.Archive");
    expect(p.summary?.action).toBe("catalog.CorrectSolution"); // only an action of several properties
    expect(p.summary?.input).toBe("s");
  });
  it("offers an action that needs other required inputs: it opens an ordinary form", () => {
    const needy = catalog({
      actions: [update("Reclassify", "Solution", { coverageLevel: "lvl" }, [text("reason")])],
    });
    expect(propertyActions(needy, "catalog.Solution").coverageLevel?.input).toBe("lvl");
  });
  it("ignores a non-update action and properties no update sets", () => {
    const only = catalog({ actions: [create("AddSolution", "Solution"), link] });
    expect(propertyActions(only, "catalog.Solution")).toEqual({});
    expect(propertyActions(m, "catalog.Solution").code).toBeUndefined();
  });
  it("reads a property set by something other than an input as none", () => {
    const a = update("Stamp", "Solution", { name: "name" });
    const e = defined(a.effects[0]);
    e.properties = { name: { literal: "x" } };
    expect(propertyActions(catalog({ actions: [a] }), "catalog.Solution")).toEqual({});
  });
});

// A reference input and a record input are not text: they are not edit values.
describe("inputs that are not text", () => {
  it("a ref input is never a property's value", () => {
    const a = update("Odd", "Solution", { name: "name" });
    a.inputSpecs = a.inputSpecs.map((s) => (s.name === "name" ? ref("name", "Product") : s));
    const mod = catalog({ actions: [a] });
    expect(editPlan(mod, typeOf(mod, "catalog.Solution"), "name")).toBeUndefined();
    expect(decl({}).op).toBe("update");
  });
});
