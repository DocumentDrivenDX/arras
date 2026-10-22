// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GraphArea } from "../areas/GraphArea";
import { assembleGraph, layoutLanes } from "../lib/graph";
import { defined } from "./defined";
import { attribution, catalog, type FakeApi, seedCatalog, stage } from "./fake";
import { renderConsole, renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});

const nodes = () => screen.getAllByTestId("node");
const byStatus = (s: string) => nodes().filter((n) => n.getAttribute("data-status") === s);

describe("Graph (typed lanes, relationships as edges)", () => {
  it("draws one lane per type and an edge per distinct relationship instance", async () => {
    renderPart(<GraphArea module="catalog" />);
    await waitFor(() => expect(screen.getAllByTestId("node")).toHaveLength(4));
    const lanes = screen.getAllByTestId("lane");
    expect(lanes).toHaveLength(2);
    expect(lanes[0]).toHaveTextContent("USECASE");
    expect(lanes[1]).toHaveTextContent("SOLUTION");
    // sol-1 addresses uc-1 (seen from both sides) and is addressed by uc-2 and uc-3: three edges, no duplicates.
    const edges = screen.getAllByTestId("edge");
    expect(edges).toHaveLength(3);
    expect(edges.every((e) => e.getAttribute("data-rel") === "addresses")).toBe(true);
    // The freshness chip names the backend, position and consistency.
    const fresh = screen.getByTestId("freshness");
    expect(fresh).toHaveTextContent("LATEST");
    expect(fresh).toHaveTextContent("record: memory");
    expect(fresh).toHaveTextContent("position fake:3");
  });

  it("reads one list per type with limit 100 and selects only keys, a label and relationship refs", async () => {
    renderPart(<GraphArea module="catalog" />);
    await waitFor(() => expect(screen.getAllByTestId("node").length).toBeGreaterThan(0));
    const lists = api.posts(/graphql\/catalog$/).filter((r) => /List\(/.test(r.body.query));
    expect(lists).toHaveLength(2);
    for (const r of lists) {
      expect(r.body.variables.limit).toBe(100);
      expect(r.body.query).not.toContain("target {");
      expect(r.body.query).toMatch(/items \{ key name \w+ \{ module type key \} \}/);
    }
  });

  it("selecting a node opens the entity panel with its actions; Enter selects from the keyboard", async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    renderPart(<GraphArea module="catalog" onAction={onAction} />);
    const node = await screen.findByRole("button", { name: /Solution Pipeline extractor/ });
    await user.click(node);
    const panel = await screen.findByTestId("entity-panel");
    expect(await within(panel).findByTestId("prop-name")).toHaveTextContent("Pipeline extractor");
    expect(node).toHaveAttribute("aria-pressed", "true");
    await user.click(within(panel).getByRole("button", { name: /CorrectSolution/ }));
    expect(onAction).toHaveBeenCalledWith("catalog.CorrectSolution", { solution: "sol-1" });
    // keyboard: arrow to the neighbouring lane, Enter opens it
    node.focus();
    await user.keyboard("{ArrowLeft}");
    expect(document.activeElement?.getAttribute("data-node-id")).toMatch(/^catalog\.UseCase:uc-/);
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByTestId("entity-panel")).toHaveTextContent("UseCase"));
  });

  it("hover lights a node's edges and fades the rest", async () => {
    const user = userEvent.setup();
    renderPart(<GraphArea module="catalog" />);
    const uc2 = await screen.findByRole("button", { name: /UseCase Use case 2/ });
    await user.hover(uc2);
    const lit = screen.getAllByTestId("edge").filter((e) => e.getAttribute("opacity") === "1");
    expect(lit).toHaveLength(1);
    const uc3 = screen.getByRole("button", { name: /UseCase Use case 3/ });
    expect(uc3.closest('[data-testid="node"]')).toHaveAttribute("opacity", "0.28");
  });

  it("a text filter dims the nodes that do not match, and a type chip hides a lane", async () => {
    const user = userEvent.setup();
    renderPart(<GraphArea module="catalog" />);
    await screen.findAllByTestId("node");
    await user.type(screen.getByLabelText("Filter entities"), "extractor");
    expect(
      screen.getAllByTestId("node").filter((n) => n.getAttribute("data-dimmed") === "true"),
    ).toHaveLength(3);
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("1 match");
    await user.clear(screen.getByLabelText("Filter entities"));
    const overview = screen.getByTestId("overview");
    await user.click(within(overview).getByRole("button", { name: /UseCase/ }));
    expect(screen.getAllByTestId("node")).toHaveLength(1);
    expect(screen.queryAllByTestId("edge")).toHaveLength(0);
    // the relationship toggle hides edges
    await user.click(within(overview).getByRole("button", { name: /UseCase/ }));
    await user.click(within(overview).getByRole("button", { name: /addresses/ }));
    expect(screen.queryAllByTestId("edge")).toHaveLength(0);
  });

  it("says how much is shown when the read is cut off", async () => {
    api.rows["catalog.UseCase"] = Array.from({ length: 130 }, (_, i) => ({
      key: `uc-${String(i).padStart(3, "0")}`,
      type: "catalog.UseCase",
      name: `Case ${i}`,
      addressedBy: [],
      ...attribution(),
    }));
    renderPart(<GraphArea module="catalog" />);
    const note = await screen.findByTestId("truncation");
    // 100 read of the use cases (a next page exists) and one solution
    expect(note).toHaveTextContent("Showing 101 of 101+ entities");
    expect(screen.getAllByTestId("node")).toHaveLength(101);
  });

  it("caps the nodes drawn at 150, connected entities first", () => {
    const m = catalog();
    const ucs = Array.from({ length: 100 }, (_, i) => ({
      key: `u${i}`,
      name: `U${i}`,
      addressedBy: [],
    }));
    const sols = Array.from({ length: 100 }, (_, i) => ({
      key: `s${i}`,
      name: `S${i}`,
      addresses: i === 99 ? [{ module: "catalog", type: "catalog.UseCase", key: "u99" }] : [],
    }));
    const g = assembleGraph(m, [
      {
        type: defined(m.entityTypes[0], "m.entityTypes[0]"),
        read: { items: ucs, truncated: false, freshness: null },
      },
      {
        type: defined(m.entityTypes[1], "m.entityTypes[1]"),
        read: { items: sols, truncated: false, freshness: null },
      },
    ]);
    expect(g.loaded).toBe(200);
    expect(g.shown).toBe(150);
    expect(g.nodes.some((n) => n.id === "catalog.Solution:s99")).toBe(true); // connected ones are kept
    expect(g.nodes.some((n) => n.id === "catalog.UseCase:u99")).toBe(true);
    expect(g.edges).toHaveLength(1);
  });

  it("draws an end in another module as a stub node in its own lane", async () => {
    api.rows["catalog.Solution"] = [
      {
        key: "sol-1",
        type: "catalog.Solution",
        name: "Pipeline extractor",
        addresses: [{ module: "billing", type: "billing.Invoice", key: "inv-9" }],
        ...attribution(),
      },
    ];
    api.rows["catalog.UseCase"] = [];
    api.modules = [
      {
        ...catalog(),
        relationships: [
          {
            ...defined(catalog().relationships[0], "catalog().relationships[0]"),
            target: ["billing.Invoice"],
          },
        ],
      },
    ];
    renderPart(<GraphArea module="catalog" />);
    const stub = await screen.findByRole("button", { name: /Invoice inv-9/ });
    expect(stub).toHaveAttribute("aria-label", expect.stringContaining("not loaded"));
    expect(screen.getAllByTestId("lane").some((l) => l.textContent?.includes("↗"))).toBe(true);
    expect(screen.getAllByTestId("edge")).toHaveLength(1);
  });

  it("outlines the entities a change touched, with a banner that can be dismissed", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    renderPart(
      <GraphArea
        module="catalog"
        changed={{ label: "group g-4", ids: ["catalog.Solution:sol-1"] }}
        onDismissChanged={onDismiss}
      />,
    );
    await screen.findAllByTestId("node");
    expect(screen.getByTestId("changed-banner")).toHaveTextContent("Changed by group g-4");
    expect(nodes().filter((n) => n.getAttribute("data-changed") === "true")).toHaveLength(1);
    expect(byStatus("plain")).toHaveLength(4);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it("has an empty state and an error state", async () => {
    api.rows["catalog.UseCase"] = [];
    api.rows["catalog.Solution"] = [];
    const a = renderPart(<GraphArea module="catalog" />);
    expect(await screen.findByText("No entities yet")).toBeInTheDocument();
    a.unmount();
    api.on((r) =>
      /List\(/.test(r.body?.query ?? "") && /solutionList/.test(r.body.query)
        ? { status: 200, body: { data: null, errors: [{ message: "boom" }] } }
        : undefined,
    );
    api.rows["catalog.UseCase"] = [
      { key: "uc-1", type: "catalog.UseCase", name: "One", addressedBy: [], ...attribution() },
    ];
    renderPart(<GraphArea module="catalog" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not read Solution");
    expect(screen.getAllByTestId("node")).toHaveLength(1);
  });
});

describe("Graph in the console", () => {
  it("is the second area, reachable by the key 2, and puts the selected entity in the fragment, not in any request URL", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/model";
    renderConsole({ hashRouting: true });
    await screen.findByTestId("schema");
    await user.keyboard("2");
    expect(await screen.findByTestId("graph-area")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/catalog/graph");
    await user.click(await screen.findByRole("button", { name: /Solution Pipeline extractor/ }));
    await screen.findByTestId("entity-panel");
    expect(window.location.hash).toBe("#/catalog/graph/catalog.Solution/sol-1");
    expect(api.log.every((r) => !r.url.includes("sol-1"))).toBe(true);
  });
});

describe("layout", () => {
  it("is deterministic and keeps linked nodes level", () => {
    const ns = [
      { id: "a1", type: "A", label: "x" },
      { id: "a2", type: "A", label: "y" },
      { id: "b1", type: "B", label: "z" },
      { id: "b2", type: "B", label: "w" },
    ];
    const es = [
      { from: "a1", to: "b2" },
      { from: "a2", to: "b1" },
    ];
    const lanes = [
      { id: "A", title: "A", foreign: false },
      { id: "B", title: "B", foreign: false },
    ];
    const o = { nodeW: 100, rowH: 20, width: 500, headerH: 10, padX: 5, maxGap: 100 };
    const l1 = layoutLanes(ns, es, lanes, o);
    const l2 = layoutLanes([...ns].reverse(), es, lanes, o);
    const flat = (l: typeof l1) => [...l.pos.entries()].sort((x, y) => x[0].localeCompare(y[0]));
    expect(flat(l1)).toEqual(flat(l2));
    expect(defined(l1.pos.get("a1"), "l1.pos.get(a1)").y).toBe(
      defined(l1.pos.get("b2"), "l1.pos.get(b2)").y,
    );
    expect(defined(l1.pos.get("a2"), "l1.pos.get(a2)").y).toBe(
      defined(l1.pos.get("b1"), "l1.pos.get(b1)").y,
    );
  });
});
