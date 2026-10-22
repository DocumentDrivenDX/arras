// SPDX-License-Identifier: MIT OR Apache-2.0
// Declared actions as the meta read spells them, for the tests of the derivations and of the
// Actions area's grouping: updates, a creation, a link and an action with no effects.
import type { ActionInfo, InputSpec } from "../api/types";
import { catalog, decl } from "./fake";

export const ref = (name: string, type: string): InputSpec => ({
  name,
  type,
  kind: "ref",
  cardinality: "one",
});
export const text = (name: string, cardinality: InputSpec["cardinality"] = "one"): InputSpec => ({
  name,
  type: "string",
  kind: "scalar",
  cardinality,
});

export const update = (
  name: string,
  type: string,
  properties: Record<string, string>,
  inputs: InputSpec[] = [],
): ActionInfo => ({
  name: `catalog.${name}`,
  description: `${name} a ${type}`,
  inputSpecs: [ref("target", type), ...Object.values(properties).map((n) => text(n)), ...inputs],
  preconditions: [],
  effects: [
    decl({
      op: "update",
      ref_type: type,
      key: { name: "target" },
      properties: Object.fromEntries(Object.entries(properties).map(([p, i]) => [p, { name: i }])),
    }),
  ],
});

export const create = (name: string, type: string): ActionInfo => ({
  name: `catalog.${name}`,
  description: `${name}`,
  inputSpecs: [text("name")],
  preconditions: [],
  effects: [decl({ op: "create", type, properties: { name: { name: "name" } } })],
});

export const link: ActionInfo = {
  name: "catalog.LinkSolution",
  description: "Link a solution to a use case",
  inputSpecs: [ref("solution", "Solution"), ref("useCase", "UseCase")],
  preconditions: [],
  effects: [
    decl({
      op: "link",
      type: "addresses",
      source: { name: "solution" },
      target: { name: "useCase" },
    }),
  ],
};

export const actions: ActionInfo[] = [
  create("AddSolution", "Solution"),
  update("CorrectSolution", "Solution", { name: "n", coverageLevel: "lvl", summary: "s" }),
  update("Archive", "Solution", { coverageLevel: "lvl" }),
  update("RenameSolution", "Solution", { name: "name" }),
  link,
  update("RenameUseCase", "UseCase", { name: "name" }),
  {
    name: "catalog.Ping",
    description: "Sends a ping",
    inputSpecs: [],
    preconditions: [],
    effects: [],
  },
];
export const m = catalog({ actions });
