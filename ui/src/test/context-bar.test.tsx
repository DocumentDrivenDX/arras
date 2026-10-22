// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { actionHref, entityHref } from "../route";
import { crossLinks } from "../shell/links";
import { type FakeApi, json, seedCatalog, stage, wire } from "./fake";
import { renderConsole } from "./render";

// The entity context bar (FEAT-010 OPR-18): where you are, with links to the entity's other views.
let api: FakeApi;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
  api.on((r) =>
    r.method === "POST" && r.path.endsWith("/audit/changes")
      ? json(200, wire.page([wire.change()], null))
      : undefined,
  );
});

const bar = () => screen.findByRole("navigation", { name: "Entity context" });
const open = async (hash: string) => {
  window.location.hash = hash;
  renderConsole({ hashRouting: true });
  return await bar();
};

describe("the entity context bar", () => {
  it("names the entity and links to its Entities, Graph, History and Actions views", async () => {
    const nav = await open("#/catalog/entities/catalog.Solution/sol-1");
    expect(within(nav).getByTestId("entity-context-name")).toHaveTextContent("Solution · sol-1");
    const link = (name: string) => within(nav).getByRole("link", { name });
    expect(link("Entities of Solution sol-1")).toHaveAttribute(
      "href",
      entityHref("catalog", "entities", "catalog.Solution", "sol-1"),
    );
    expect(link("Graph of Solution sol-1")).toHaveAttribute(
      "href",
      entityHref("catalog", "graph", "catalog.Solution", "sol-1"),
    );
    await waitFor(() =>
      expect(link("History of Solution sol-1")).toHaveAttribute(
        "href",
        entityHref("catalog", "changes", "catalog.Solution", "sol-1"),
      ),
    );
    expect(link("Actions of Solution sol-1")).toHaveAttribute(
      "href",
      actionHref("catalog", "catalog.CorrectSolution", { solution: "sol-1" }),
    );
    // The current area's link is marked, and only it.
    expect(link("Entities of Solution sol-1")).toHaveAttribute("aria-current", "page");
    expect(link("Graph of Solution sol-1")).not.toHaveAttribute("aria-current");
  });

  it("shows the entity's readable name when it is known", async () => {
    const nav = await open("#/catalog/entities/catalog.Solution/sol-1");
    await waitFor(() =>
      expect(within(nav).getByTestId("entity-context-name")).toHaveTextContent(
        "Pipeline extractor",
      ),
    );
  });

  it("a link follows the route: History opens the entity's changes, with the bar still there", async () => {
    const user = userEvent.setup();
    const nav = await open("#/catalog/entities/catalog.Solution/sol-1");
    await user.click(await within(nav).findByRole("link", { name: "History of Solution sol-1" }));
    expect(window.location.hash).toBe("#/catalog/changes/catalog.Solution/sol-1");
    await screen.findByTestId("history-chip");
    const again = await bar();
    expect(within(again).getByRole("link", { name: "History of Solution sol-1" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("is shown for a graph selection", async () => {
    const nav = await open("#/catalog/graph/catalog.Solution/sol-1");
    expect(within(nav).getByRole("link", { name: "Graph of Solution sol-1" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("is shown for an action prefilled with an entity, and marks Actions current", async () => {
    const nav = await open("#/catalog/actions/catalog.CorrectSolution?in.solution=sol-1");
    expect(within(nav).getByTestId("entity-context-name")).toHaveTextContent("Solution · sol-1");
    const actions = within(nav).getByRole("link", { name: "Actions of Solution sol-1" });
    expect(actions).toHaveAttribute("aria-current", "page");
    expect(actions).toHaveAttribute(
      "href",
      actionHref("catalog", "catalog.CorrectSolution", { solution: "sol-1" }),
    );
  });

  it("copies only the prefill that fits the action into its Actions link", async () => {
    const nav = await open(
      "#/catalog/actions/catalog.CorrectSolution?in.solution=sol-1&in.level=partial&in.nothing=x",
    );
    expect(within(nav).getByRole("link", { name: "Actions of Solution sol-1" })).toHaveAttribute(
      "href",
      actionHref("catalog", "catalog.CorrectSolution", { solution: "sol-1" }),
    );
  });

  it("builds its links under the console's own prefix, and none where the host owns the location", async () => {
    window.location.hash = "#/operate/catalog/entities/catalog.Solution/sol-1";
    const { unmount } = renderConsole({ hashRouting: true, hashPrefix: "operate" });
    const nav = await bar();
    expect(within(nav).getByRole("link", { name: "Graph of Solution sol-1" })).toHaveAttribute(
      "href",
      entityHref("catalog", "graph", "catalog.Solution", "sol-1", "operate"),
    );
    unmount();
    const route = {
      module: "catalog",
      area: "entities" as const,
      type: "catalog.Solution",
      key: "sol-1",
    };
    const seen: unknown[] = [];
    const user = userEvent.setup();
    renderConsole({ route, onRoute: (r) => seen.push(r) });
    const hosted = await bar();
    expect(within(hosted).queryByRole("link", { name: /^Graph of / })).toBeNull();
    await user.click(within(hosted).getByRole("button", { name: "Graph of Solution sol-1" }));
    expect(seen).toEqual([
      { module: "catalog", area: "graph", type: "catalog.Solution", key: "sol-1" },
    ]);
  });

  it("clear returns to the area's list", async () => {
    const user = userEvent.setup();
    const nav = await open("#/catalog/entities/catalog.Solution/sol-1");
    await user.click(within(nav).getByRole("button", { name: /^Clear Solution sol-1/ }));
    expect(window.location.hash).toBe("#/catalog/entities/catalog.Solution");
    await waitFor(() => expect(screen.queryByTestId("entity-context")).toBeNull());
  });

  it("renders nothing when no entity is in context", async () => {
    window.location.hash = "#/catalog/entities/catalog.Solution";
    renderConsole({ hashRouting: true });
    await screen.findByRole("tab", { name: "Entities", selected: true });
    expect(screen.queryByRole("navigation", { name: "Entity context" })).toBeNull();
  });
});

describe("View in Explore on the context bar (FR-71)", () => {
  const toExplore = crossLinks({
    hash: true,
    openOperate: () => {},
    openExplore: () => {},
  }).toExplore;

  it("is an anchor to the entity's Explore page, and to its History from Changes, for an operator", async () => {
    window.location.hash = "#/catalog/entities/catalog.Solution/sol-1";
    renderConsole({ hashRouting: true, links: { toExplore } });
    const nav = await bar();
    expect(within(nav).getByRole("link", { name: /View in Explore/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/Solution/sol-1",
    );
  });

  it("opens the entity's History page when the console shows its Changes", async () => {
    window.location.hash = "#/catalog/changes/catalog.Solution/sol-1";
    renderConsole({ hashRouting: true, links: { toExplore } });
    const nav = await bar();
    expect(within(nav).getByRole("link", { name: /View in Explore/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/Solution/sol-1/history",
    );
  });

  it("is absent when the shell hands the console no link", async () => {
    const nav = await open("#/catalog/entities/catalog.Solution/sol-1");
    expect(within(nav).queryByText(/Explore/)).toBeNull();
  });
});
