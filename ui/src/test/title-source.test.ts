// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { titleFor } from "../console/useDocumentTitle";
import { joinTitle, moduleTitle } from "../lib/documentTitle";
import { catalog } from "./fake";

// One title source (SD-013 FR-72): both modes join the same parts by `joinTitle` and name the module
// by its view title and an entity by its title-template name.
describe("the document title source", () => {
  it("joinTitle drops empty parts and puts the brand last", () => {
    expect(joinTitle(["a", undefined, "", "c"], "Atlas")).toBe("a · c · Atlas");
    expect(joinTitle([], "Atlas")).toBe("Atlas");
  });

  it("moduleTitle is the view's title, else the name", () => {
    expect(moduleTitle({ name: "catalog" })).toBe("catalog");
    expect(moduleTitle({ name: "catalog", view: { title: "Tools Catalog" } })).toBe(
      "Tools Catalog",
    );
  });

  it("Operate's title names the module by its view title and the entity by its template name", () => {
    const module = { ...catalog(), view: { title: "Tools Catalog", description: null } };
    const route = {
      module: "catalog",
      area: "entities",
      type: "catalog.Solution",
      key: "s-1",
    } as const;
    expect(titleFor(route, "entities", "Atlas", { module, entityName: "Alert grouping" })).toBe(
      "Alert grouping · Entities · Tools Catalog · Atlas",
    );
    // before the entity is read, the key stands for its name
    expect(titleFor(route, "entities", "Atlas", { module })).toBe(
      "s-1 · Entities · Tools Catalog · Atlas",
    );
    // without a context it is the route alone
    expect(titleFor(route, "entities", "Atlas")).toBe("s-1 · Entities · catalog · Atlas");
  });

  it("an entity name is the subject only on the area the route is about", () => {
    const route = {
      module: "catalog",
      area: "changes",
      type: "catalog.Solution",
      key: "s-1",
    } as const;
    expect(titleFor(route, "model", "Atlas", { entityName: "Alert grouping" })).toBe(
      "Model · catalog · Atlas",
    );
  });
});
