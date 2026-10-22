// SPDX-License-Identifier: MIT OR Apache-2.0
// Every example module can be edited in place: each property but the key has a declared action
// that edits it (`editPlan`), alone or, for properties that only change together, in a form.
import { describe, expect, it } from "vitest";
import { editPlan } from "../kit";
import { exampleModule } from "./catalogModule";

describe.each(["catalog", "northwind", "pizza"])("the %s example", (name) => {
  const module = exampleModule(name);
  it.each(module.entityTypes.map((t) => [t.name, t] as const))(
    "%s: every property but the key is editable",
    (_n, type) => {
      const without = type.properties
        .map((p) => p.name)
        .filter((p) => p !== type.key && !editPlan(module, type, p));
      expect(without).toEqual([]);
    },
  );
});
