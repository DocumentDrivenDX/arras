// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AREA_LABELS } from "../lib/vocabulary";
import type { Area } from "../route";
import { type FakeApi, seedCatalog, stage, wire } from "./fake";
import { renderConsole } from "./render";

// Navigation in the console (FEAT-010, CONTRACT-010 D): every navigation pushes a history entry, Back
// and Forward restore the console, and the open entity, the graph selection, the audit entity and the
// action prefill are read from the fragment.
let api: FakeApi;
const ORIGINAL_TITLE = document.title;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
  document.title = ORIGINAL_TITLE;
});
afterEach(() => {
  window.location.hash = "";
});

const hash = () => window.location.hash;
const depth = () => window.history.length;
const selected = (name: string) => screen.getByRole("tab", { name, selected: true }) as HTMLElement;
const selectedArea = (area: Area) =>
  within(screen.getByRole("tablist", { name: "Areas" })).getByRole("tab", {
    name: AREA_LABELS[area],
    selected: true,
  });
const back = async () => {
  act(() => window.history.back());
};

describe("history: a navigation adds an entry and Back restores the console", () => {
  it("an area change, then Back and Forward", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/model";
    renderConsole({ hashRouting: true });
    await screen.findByTestId("schema");
    const before = depth();
    await user.click(screen.getByRole("tab", { name: "Graph" }));
    expect(depth()).toBe(before + 1);
    expect(hash()).toBe("#/catalog/graph");
    await back();
    await waitFor(() => expect(selectedArea("model")).toBeInTheDocument());
    expect(hash()).toBe("#/catalog/model");
    act(() => window.history.forward());
    await waitFor(() => expect(selectedArea("graph")).toBeInTheDocument());
  });

  it("the area keys navigate too, and a module change", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/model";
    renderConsole({ hashRouting: true });
    await screen.findByTestId("schema");
    const before = depth();
    await user.keyboard("3");
    await waitFor(() => expect(selectedArea("entities")).toBeInTheDocument());
    expect(depth()).toBe(before + 1);
  });

  it("the module with no route is opened by a replacement: it adds no entry", async () => {
    window.history.replaceState(null, "", "/#/");
    const before = depth();
    renderConsole({ hashRouting: true });
    await screen.findByTestId("schema");
    expect(hash()).toBe("#/catalog/model");
    expect(depth()).toBe(before);
  });

  it("the Data area names its default type, by replacement, so the address is the screen", async () => {
    window.location.hash = "#/catalog/entities";
    const before = depth();
    renderConsole({ hashRouting: true });
    await screen.findByRole("tab", { name: "UseCase", selected: true });
    expect(hash()).toBe("#/catalog/entities/catalog.UseCase");
    expect(depth()).toBe(before);
  });

  it("a type tab and an opened entity are entries; Back closes the entity, Forward opens it", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/entities/catalog.UseCase";
    renderConsole({ hashRouting: true });
    await screen.findByText("uc-1");
    const before = depth();
    await user.click(screen.getByRole("tab", { name: "Solution" }));
    expect(hash()).toBe("#/catalog/entities/catalog.Solution");
    await user.click(await screen.findByText("sol-1"));
    await screen.findByTestId("entity-panel");
    expect(hash()).toBe("#/catalog/entities/catalog.Solution/sol-1");
    expect(depth()).toBe(before + 2);
    await back();
    await waitFor(() => expect(screen.queryByTestId("entity-panel")).toBeNull());
    expect(hash()).toBe("#/catalog/entities/catalog.Solution");
    act(() => window.history.forward());
    await screen.findByTestId("entity-panel");
    await back();
    await waitFor(() => expect(hash()).toBe("#/catalog/entities/catalog.Solution"));
    await back();
    await waitFor(() => expect(hash()).toBe("#/catalog/entities/catalog.UseCase"));
    await waitFor(() => expect(selected("UseCase")).toBeInTheDocument());
  });

  it("closing the entity panel is a navigation too", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/entities/catalog.Solution/sol-1";
    renderConsole({ hashRouting: true });
    await screen.findByTestId("entity-panel");
    const before = depth();
    await user.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() => expect(screen.queryByTestId("entity-panel")).toBeNull());
    expect(hash()).toBe("#/catalog/entities/catalog.Solution");
    expect(depth()).toBe(before + 1);
  });

  it("History from an entity opens that entity's audit view, an entry Back leaves", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/entities/catalog.Solution/sol-1";
    renderConsole({ hashRouting: true });
    await screen.findByTestId("entity-panel");
    await user.click(await screen.findByRole("button", { name: "History" }));
    await waitFor(() => expect(hash()).toBe("#/catalog/changes/catalog.Solution/sol-1"));
    await back();
    await screen.findByTestId("entity-panel");
    expect(hash()).toBe("#/catalog/entities/catalog.Solution/sol-1");
  });

  it("selecting a node in the graph is an entry carrying the node", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/graph";
    renderConsole({ hashRouting: true });
    await user.click(await screen.findByRole("button", { name: /Solution Pipeline extractor/ }));
    await screen.findByTestId("entity-panel");
    expect(hash()).toBe("#/catalog/graph/catalog.Solution/sol-1");
    await back();
    await waitFor(() => expect(screen.queryByTestId("entity-panel")).toBeNull());
  });

  it("the Graph action of an entity opens the graph on that entity", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/entities/catalog.Solution/sol-1";
    renderConsole({ hashRouting: true });
    await screen.findByTestId("entity-panel");
    await user.click(await screen.findByRole("button", { name: /graph/i }));
    await waitFor(() => expect(hash()).toBe("#/catalog/graph/catalog.Solution/sol-1"));
    await screen.findByTestId("entity-panel");
  });
});

describe("hydration: a refresh or a shared link restores the view", () => {
  it("an address with an earlier area id is rewritten once, in place, to the current one", async () => {
    const replace = vi.spyOn(window.history, "replaceState");
    const push = vi.spyOn(window.history, "pushState");
    window.location.hash = "#/catalog/audit/catalog.Solution/sol-1";
    const before = depth();
    renderConsole({ hashRouting: true });
    await waitFor(() => expect(selectedArea("changes")).toBeInTheDocument());
    expect(hash()).toBe("#/catalog/changes/catalog.Solution/sol-1");
    expect(replace.mock.calls.filter(([, , url]) => url === hash())).toHaveLength(1);
    expect(push).not.toHaveBeenCalled();
    expect(depth()).toBe(before);
    replace.mockRestore();
    push.mockRestore();
  });

  it("an entity in Data", async () => {
    window.location.hash = "#/catalog/entities/catalog.Solution/sol-1";
    renderConsole({ hashRouting: true });
    const panel = await screen.findByTestId("entity-panel");
    await waitFor(() => expect(panel).toHaveTextContent("sol-1"));
    expect(selected("Solution")).toBeInTheDocument();
  });

  it("an entity in the graph", async () => {
    window.location.hash = "#/catalog/graph/catalog.Solution/sol-1";
    renderConsole({ hashRouting: true });
    const panel = await screen.findByTestId("entity-panel");
    await waitFor(() => expect(panel).toHaveTextContent("sol-1"));
  });

  it("an entity's audit history", async () => {
    window.location.hash = "#/catalog/changes/catalog.Solution/sol-1";
    renderConsole({ hashRouting: true });
    await waitFor(() => expect(selectedArea("changes")).toBeInTheDocument());
    await waitFor(() =>
      expect(
        api.posts(/\/changes$/).some((r) => r.body.key === "sol-1" && r.body.module === "catalog"),
      ).toBe(true),
    );
  });

  it("an action with its ref inputs prefilled from keys", async () => {
    window.location.hash = "#/catalog/actions/catalog.CorrectSolution?in.solution=sol-1";
    renderConsole({ hashRouting: true });
    await screen.findByRole("tab", { name: "Actions", selected: true });
    await waitFor(() => expect(screen.getByDisplayValue("sol-1")).toBeInTheDocument());
  });

  it("a prefill that is not a ref input holding a key fills nothing and opens no entity", async () => {
    window.location.hash =
      "#/catalog/actions/catalog.CorrectSolution?in.level=partial&in.nothing=x&in.solution=%07";
    renderConsole({ hashRouting: true });
    await screen.findByRole("tab", { name: "Actions", selected: true });
    const level = await screen.findByLabelText(/^level/);
    expect(level).toHaveValue("");
    expect(screen.getByLabelText(/^solution/)).toHaveValue("");
    expect(screen.queryByRole("navigation", { name: "Entity context" })).toBeNull();
  });

  it("an odd key survives the round trip through the fragment", async () => {
    window.location.hash = `#/catalog/entities/catalog.Solution/${encodeURIComponent("a/b c?#é")}`;
    renderConsole({ hashRouting: true });
    await screen.findByTestId("entity-panel");
    expect(hash()).toBe("#/catalog/entities/catalog.Solution/a%2Fb%20c%3F%23%C3%A9");
  });

  it("a malformed fragment falls back to the module's area", async () => {
    window.location.hash = "#/catalog/entities/catalog.Solution/%E0%A4%A/x/y";
    renderConsole({ hashRouting: true });
    await screen.findByRole("tab", { name: "Entities", selected: true });
    expect(screen.queryByTestId("entity-panel")).toBeNull();
  });
});

describe("the page title", () => {
  it("names the entity, area and module, and is the page's own again on unmount", async () => {
    document.title = "Host page";
    window.location.hash = "#/catalog/entities/catalog.Solution/sol-1";
    const { unmount } = renderConsole({ hashRouting: true });
    await screen.findByTestId("entity-panel");
    expect(document.title).toBe("sol-1 · Entities · catalog · Arras");
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Query" }));
    await waitFor(() => expect(document.title).toBe("Query · catalog · Arras"));
    unmount();
    expect(document.title).toBe("Host page");
  });
});

describe("a host that owns the location", () => {
  it("takes every change through onRoute and shows the route it is given", async () => {
    const user = userEvent.setup();
    const seen: { hash: string; replace: boolean }[] = [];
    const { formatHash } = await import("../route");
    renderConsole({
      route: { module: "catalog", area: "model" },
      onRoute: (r, o) => seen.push({ hash: formatHash(r), replace: o.replace }),
    });
    await screen.findByTestId("schema");
    await user.click(screen.getByRole("tab", { name: "Graph" }));
    expect(seen).toEqual([{ hash: "#/catalog/graph", replace: false }]);
    expect(window.location.hash).toBe("");
  });
});

describe("keys on the area tablist (WAI-ARIA tabs)", () => {
  it("roving tabindex, Left and Right wrap, Home and End jump", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/model";
    renderConsole({ hashRouting: true });
    await screen.findByTestId("schema");
    const tabs = () => screen.getAllByRole("tab").filter((t) => t.closest('[aria-label="Areas"]'));
    expect(tabs().map((t) => t.tabIndex)).toEqual(tabs().map((_, i) => (i === 0 ? 0 : -1)));
    tabs()[0]?.focus();
    await user.keyboard("{ArrowRight}");
    expect(tabs()[1]).toHaveFocus();
    expect(tabs()[1]).toHaveAttribute("aria-selected", "true");
    expect(tabs()[1]?.tabIndex).toBe(0);
    expect(tabs()[0]?.tabIndex).toBe(-1);
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(tabs().at(-1)).toHaveFocus();
    expect(tabs().at(-1)).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}");
    expect(tabs()[0]).toHaveFocus();
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(tabs().at(-1)).toHaveFocus();
  });

  it("the type tablist of Data answers the same keys", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/entities/catalog.UseCase";
    renderConsole({ hashRouting: true });
    await screen.findByText("uc-1");
    screen.getByRole("tab", { name: "UseCase" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Solution" })).toHaveFocus();
    await waitFor(() => expect(hash()).toBe("#/catalog/entities/catalog.Solution"));
  });
});

describe("an address that names nothing is one not-found page (FR-74)", () => {
  const open = (path: string) => {
    window.location.hash = `#/operate/catalog/${path}`;
    return renderConsole({ hashRouting: true, hashPrefix: "operate" });
  };
  const empty = () =>
    api.on((r) =>
      r.method === "POST" && r.path.endsWith("/audit/changes")
        ? { status: 200, body: wire.page([], null) }
        : undefined,
    );

  const causes: [string, string, () => void][] = [
    ["a type the module does not declare, in Model", "model/catalog.Nothing", () => undefined],
    [
      "a type the module does not declare, in Entities",
      "entities/catalog.Nothing",
      () => undefined,
    ],
    [
      "an entity that cannot be read, in Entities",
      "entities/catalog.Solution/nope",
      () => undefined,
    ],
    ["an entity that cannot be read, in Graph", "graph/catalog.Solution/nope", () => undefined],
    ["an entity that cannot be read, in Changes", "changes/catalog.Solution/nope", () => undefined],
    ["an action the module does not declare", "actions/catalog.Nothing", () => undefined],
    ["a group with no changes", "changes?group=g-none", empty],
  ];

  it.each(causes)("%s shows the notice that links to Model", async (_cause, path, prepare) => {
    const user = userEvent.setup();
    prepare();
    open(path);
    const notice = await screen.findByTestId("not-found");
    expect(notice).toHaveTextContent("Not found. There is nothing at this address");
    const link = within(notice).getByRole("link", { name: "Go to Model of catalog" });
    expect(link).toHaveAttribute("href", "#/operate/catalog/model");
    await user.click(link);
    await screen.findByTestId("schema");
    expect(hash()).toBe("#/operate/catalog/model");
  });

  it("is the same page for every cause, so it never says which", async () => {
    const texts: (string | null)[] = [];
    for (const [, path, prepare] of causes) {
      prepare();
      const { unmount } = open(path);
      texts.push((await screen.findByTestId("not-found")).textContent);
      unmount();
    }
    expect(new Set(texts).size).toBe(1);
  });

  it("a declared type, a readable entity, a declared action and a group with changes are found", async () => {
    open("entities/catalog.Solution/sol-1");
    await screen.findByTestId("entity-panel");
    expect(screen.queryByTestId("not-found")).toBeNull();
  });

  it("a group reached by submitting the receipt form is not replaced by the notice", async () => {
    const user = userEvent.setup();
    empty();
    open("changes");
    await user.click(await screen.findByRole("tab", { name: "Receipt by group" }));
    await user.type(screen.getByLabelText("Group id"), "g-none");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(hash()).toBe("#/operate/catalog/changes?group=g-none"));
    expect(screen.queryByTestId("not-found")).toBeNull();
  });
});

describe("a page's address and its title (FR-74)", () => {
  it("names the place with the Area label from the vocabulary, for each kind of page", async () => {
    window.location.hash = "#/operate/catalog/entities/catalog.Solution";
    renderConsole({ hashRouting: true, hashPrefix: "operate" });
    await screen.findByTestId("data-table-pane");
    expect(document.title).toBe("catalog.Solution · Entities · catalog · Arras");
    act(() => {
      window.location.hash = "#/operate/catalog/actions/catalog.CorrectSolution";
    });
    await waitFor(() =>
      expect(document.title).toBe("catalog.CorrectSolution · Actions · catalog · Arras"),
    );
    act(() => {
      window.location.hash = "#/operate/catalog/model/catalog.Solution";
    });
    await waitFor(() => expect(document.title).toBe("catalog.Solution · Model · catalog · Arras"));
  });

  it("selecting a type in Model pushes and Back returns to the model", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/model";
    renderConsole({ hashRouting: true, hashPrefix: "operate" });
    await screen.findByTestId("schema");
    const before = depth();
    await user.click(screen.getByRole("button", { name: "Select catalog.Solution" }));
    expect(hash()).toBe("#/operate/catalog/model/catalog.Solution");
    expect(depth()).toBe(before + 1);
    expect(screen.getByTestId("type-catalog.Solution")).toHaveAttribute("aria-current", "true");
    await back();
    await waitFor(() => expect(hash()).toBe("#/operate/catalog/model"));
    expect(screen.getByTestId("type-catalog.Solution")).not.toHaveAttribute("aria-current");
  });

  it("opening the UMF source pushes and leaving it pushes", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/model/catalog.Solution";
    renderConsole({ hashRouting: true, hashPrefix: "operate" });
    await screen.findByTestId("schema");
    const before = depth();
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    expect(hash()).toBe("#/operate/catalog/model/catalog.Solution?view=umf");
    await user.click(screen.getByRole("button", { name: "Live registry" }));
    expect(hash()).toBe("#/operate/catalog/model/catalog.Solution");
    expect(depth()).toBe(before + 2);
  });
});
