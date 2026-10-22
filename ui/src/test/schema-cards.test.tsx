// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EntityTypeInfo } from "../api/types";
import { SchemaBrowser } from "../areas/SchemaBrowser";
import { NavProvider } from "../components/NavLink";
import { actionsFor, capabilityLine } from "../lib/typeSummary";
import { crossLinks } from "../shell/links";
import { catalog, stage } from "./fake";
import { renderPart } from "./render";

beforeEach(() => {
  window.location.hash = "";
  stage();
});

describe("capabilityLine", () => {
  const t = (capabilities: EntityTypeInfo["capabilities"]): EntityTypeInfo => ({
    name: "m.T",
    key: "id",
    properties: [],
    capabilities,
  });

  it("says where the record is held, what serves bulk reads, search and counts, once", () => {
    const line = capabilityLine(
      t({
        truss: { mutable: true, count: true, search: "substring" },
        ashlar: { mutable: false, count: true, search: "none" },
      }),
      "truss",
    );
    expect(line).toBe(
      "Record store: truss · Bulk reads: ashlar · Text search: truss · Counts: every backend",
    );
  });

  it("says so when there is no search, and names the record backend when none is mutable", () => {
    expect(capabilityLine(t({ a: {}, b: {} }), "b")).toBe(
      "Record store: b · Bulk reads: a · No text search",
    );
    expect(capabilityLine(t({}), "b")).toBe("");
  });

  it("finds the actions that take or write a type", () => {
    const m = catalog();
    expect(actionsFor(m, "catalog.Solution").map((a) => a.name)).toEqual([
      "catalog.CorrectSolution",
    ]);
    expect(actionsFor(m, "catalog.UseCase").map((a) => a.name)).not.toContain(
      "catalog.CorrectSolution",
    );
  });
});

describe("Schema type cards", () => {
  it("show one capability line and keep the per-backend detail in a collapsed Details", async () => {
    renderPart(<SchemaBrowser module="catalog" />);
    const card = await screen.findByTestId("type-catalog.Solution");
    expect(within(card).getAllByTestId("type-summary")).toHaveLength(1);
    expect(within(card).getByTestId("type-summary")).toHaveTextContent(
      "Record store: memory · Bulk reads: memory_replica",
    );
    const details = within(card).getByTestId("type-details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(within(details).getByText("Details")).toBeInTheDocument();
    expect(within(details).getAllByText(/filter columns:/)).toHaveLength(2);
  });

  it("link to Entities, Graph, Actions (when the type has actions) and Query, each with the type's name", async () => {
    const user = userEvent.setup();
    const open = { data: vi.fn(), graph: vi.fn(), actions: vi.fn(), query: vi.fn() };
    renderPart(
      <SchemaBrowser
        module="catalog"
        onOpenData={open.data}
        onShowGraph={open.graph}
        onOpenActions={open.actions}
        onOpenQuery={open.query}
      />,
    );
    const card = await screen.findByTestId("type-catalog.Solution");
    await user.click(within(card).getByRole("button", { name: "Entities of Solution" }));
    await user.click(within(card).getByRole("button", { name: "Graph of Solution" }));
    await user.click(within(card).getByRole("button", { name: "Actions of Solution" }));
    await user.click(within(card).getByRole("button", { name: "Query Solution" }));
    expect(open.data).toHaveBeenCalledWith("catalog.Solution");
    expect(open.graph).toHaveBeenCalledWith("catalog.Solution");
    expect(open.actions).toHaveBeenCalledWith("catalog.Solution", "catalog.CorrectSolution");
    expect(open.query).toHaveBeenCalledWith("catalog.Solution");
    // the first action that takes or writes a type is the one the Actions link names
    const other = screen.getByTestId("type-catalog.UseCase");
    await user.click(within(other).getByRole("button", { name: "Actions of UseCase" }));
    expect(open.actions).toHaveBeenLastCalledWith("catalog.UseCase", "catalog.Typed");
  });

  it("show no link whose callback is not given", async () => {
    renderPart(<SchemaBrowser module="catalog" onOpenQuery={vi.fn()} />);
    const card = await screen.findByTestId("type-catalog.Solution");
    expect(within(card).getAllByRole("button")).toHaveLength(1);
  });
});

describe("View in Explore on type cards (FR-71)", () => {
  const toExplore = crossLinks({
    hash: true,
    openOperate: () => {},
    openExplore: () => {},
  }).toExplore;

  it("each card links to the type's Explore list for an operator, even with no other link", async () => {
    renderPart(
      <NavProvider go={() => {}} auditShown toExplore={toExplore}>
        <SchemaBrowser module="catalog" />
      </NavProvider>,
    );
    const card = await screen.findByTestId("type-catalog.Solution");
    expect(within(card).getByRole("link", { name: /View in Explore/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/Solution",
    );
  });

  it("draws none without the shell's primitive", async () => {
    renderPart(<SchemaBrowser module="catalog" onOpenQuery={vi.fn()} />);
    const card = await screen.findByTestId("type-catalog.Solution");
    expect(within(card).queryByText(/Explore/)).toBeNull();
  });
});
