// SPDX-License-Identifier: MIT OR Apache-2.0
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Route } from "../route";
import { ArrasApp } from "../shell";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { type FakeApi, json, seedCatalog, stage } from "./fake";
import { qc, renderConsole } from "./render";

let api: FakeApi;
let routes: Route[];
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
  routes = [];
  api.on((r) => {
    if (!r.path.endsWith("/graphql/catalog") || !r.body.query.includes("_search")) return undefined;
    return json(200, {
      data: {
        _search: {
          hits: [
            {
              type: "Solution",
              key: "sol-1",
              label: "Lumen alert correlation",
              excerpt: [
                { text: "…uses ", mark: false },
                { text: "Lumen", mark: true },
              ],
            },
          ],
          notSearched: [{ type: "UseCase", reason: "no_capability" }],
          truncated: false,
        },
      },
    });
  });
});

async function console_(user: ReturnType<typeof userEvent.setup>) {
  renderConsole({
    route: { module: "catalog", area: "model" },
    onRoute: (r) => routes.push(r),
  });
  await screen.findByRole("tab", { name: /model/i });
  void user;
}
const field = () => screen.getByRole("combobox");
const open = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.keyboard("/");
  return screen.findByRole("dialog", { name: "Command palette" });
};
const searches = () =>
  api.posts(/\/graphql\/catalog$/).filter((r) => r.body.query.includes("_search"));

describe("the command palette (OPR-19)", () => {
  it("opens on / and on Ctrl+K and Cmd+K, closes on Escape and gives focus back", async () => {
    const user = userEvent.setup();
    await console_(user);
    const tab = screen.getByRole("tab", { name: /entities/i });
    tab.focus();
    await open(user);
    expect(field()).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(tab).toHaveFocus();
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.keyboard("{Meta>}k{/Meta}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("does not open on / while typing in a field, but Ctrl+K works from one", async () => {
    const user = userEvent.setup();
    await console_(user);
    const input = document.createElement("input");
    document.body.append(input);
    input.focus();
    await user.keyboard("/");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(input).toHaveValue("/");
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(input).toHaveFocus();
    input.remove();
  });

  it("leaves a / that a control already handled (a Data row's filter key) alone", async () => {
    const user = userEvent.setup();
    await console_(user);
    const btn = document.createElement("button");
    btn.addEventListener("keydown", (e) => e.preventDefault());
    document.body.append(btn);
    btn.focus();
    await user.keyboard("/");
    expect(screen.queryByRole("dialog")).toBeNull();
    btn.remove();
  });

  it("with no text shows the commands only, reads no entity, and says nothing of search failing", async () => {
    const user = userEvent.setup();
    await console_(user);
    const dialog = await open(user);
    expect(within(dialog).getByText("Searching in")).toHaveTextContent("catalog");
    expect(within(dialog).getByRole("group", { name: "Commands" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("group", { name: "Entities" })).toBeNull();
    expect(within(dialog).getAllByRole("option").length).toBeGreaterThanOrEqual(6);
    expect(searches()).toHaveLength(0);
  });

  it("finds an entity, shows <Type> · <title> (<key>) with its excerpt, and Enter opens it in Data", async () => {
    const user = userEvent.setup();
    await console_(user);
    await open(user);
    await user.type(field(), "lumen");
    const option = await screen.findByRole("option", {
      name: /Solution · Lumen alert correlation \(sol-1\)/,
    });
    expect(within(option).getByText("Lumen").tagName).toBe("MARK");
    expect(screen.getByRole("group", { name: "Entities" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("UseCase not searched");
    expect(field()).toHaveAttribute("aria-activedescendant", option.id);
    await user.keyboard("{Enter}");
    expect(routes.at(-1)).toEqual({
      module: "catalog",
      area: "entities",
      type: "catalog.Solution",
      key: "sol-1",
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Shift+Enter opens the entity in Graph and Alt+Enter its History", async () => {
    const user = userEvent.setup();
    await console_(user);
    await open(user);
    await user.type(field(), "lumen");
    await screen.findByRole("option", { name: /Lumen alert correlation/ });
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    expect(routes.at(-1)).toMatchObject({ area: "graph", type: "catalog.Solution", key: "sol-1" });
    await open(user);
    await user.type(field(), "lumen");
    await screen.findByRole("option", { name: /Lumen alert correlation/ });
    await user.keyboard("{Alt>}{Enter}{/Alt}");
    expect(routes.at(-1)).toMatchObject({
      area: "changes",
      type: "catalog.Solution",
      key: "sol-1",
    });
  });

  it("moves with the arrow keys, Home and End, and opens an action's form with Enter", async () => {
    const user = userEvent.setup();
    await console_(user);
    await open(user);
    await user.type(field(), "coverage");
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(2));
    const options = screen.getAllByRole("option");
    // Only the action matches "coverage" among the commands; the entity comes first.
    expect(options.map((o) => o.getAttribute("aria-label"))).toEqual([
      expect.stringContaining("Solution · Lumen"),
      expect.stringContaining("Action · catalog.CorrectSolution"),
    ]);
    expect(field()).toHaveAttribute("aria-activedescendant", options[0]?.id);
    await user.keyboard("{ArrowDown}");
    expect(field()).toHaveAttribute("aria-activedescendant", options[1]?.id);
    await user.keyboard("{ArrowDown}");
    expect(field()).toHaveAttribute("aria-activedescendant", options[0]?.id); // wraps
    await user.keyboard("{End}");
    expect(field()).toHaveAttribute("aria-activedescendant", options[1]?.id);
    await user.keyboard("{Home}{ArrowUp}{Enter}");
    expect(routes.at(-1)).toEqual({
      module: "catalog",
      area: "actions",
      action: "catalog.CorrectSolution",
    });
  });

  it("opens a type's Data list and an area from the commands", async () => {
    const user = userEvent.setup();
    await console_(user);
    await open(user);
    await user.type(field(), "usecase");
    await user.click(await screen.findByRole("option", { name: /Type · UseCase/ }));
    expect(routes.at(-1)).toEqual({ module: "catalog", area: "entities", type: "catalog.UseCase" });
    await open(user);
    await user.type(field(), "query");
    await user.keyboard("{Enter}");
    expect(routes.at(-1)).toEqual({ module: "catalog", area: "query" });
  });

  it("keeps focus in the dialog: Tab cycles and Shift+Tab goes back", async () => {
    const user = userEvent.setup();
    await console_(user);
    const dialog = await open(user);
    const close = within(dialog).getByRole("button", { name: "Close" });
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab();
    expect(field()).toHaveFocus();
    await user.tab({ shift: true });
    expect(close).toHaveFocus();
    await user.click(close);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says a failed search is modest and keeps the commands working", async () => {
    api.on((r) =>
      r.path.endsWith("/graphql/catalog") && r.body.query.includes("_search")
        ? json(200, {
            data: null,
            errors: [{ message: "echo", extensions: { code: "UNAVAILABLE" } }],
          })
        : undefined,
    );
    const user = userEvent.setup();
    await console_(user);
    await open(user);
    await user.type(field(), "model");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("unavailable"));
    expect(screen.getByRole("status")).toHaveTextContent("Commands still work.");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("option", { name: /Area · Model/ })).toBeInTheDocument();
  });

  it("hides the entity group and says so when no type of the module is searchable", async () => {
    for (const t of api.modules[0]?.entityTypes ?? [])
      for (const c of Object.values(t.capabilities)) c.search = "none";
    const user = userEvent.setup();
    await console_(user);
    await open(user);
    await user.type(field(), "lumen");
    expect(screen.getByRole("status")).toHaveTextContent("not available for this module");
    await new Promise((r) => setTimeout(r, 350));
    expect(searches()).toHaveLength(0);
  });

  it("hides Changes while it is hidden", async () => {
    api.on((r) =>
      r.path.endsWith("/audit/changes")
        ? json(501, { error: { type: "Unsupported", message: "no" } })
        : undefined,
    );
    const user = userEvent.setup();
    await console_(user);
    await waitFor(() => expect(api.posts(/audit\/changes$/).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.queryByRole("tab", { name: /changes/i })).toBeNull());
    await open(user);
    await user.type(field(), "changes");
    expect(screen.queryByRole("option", { name: /Area · Changes/ })).toBeNull();
  });

  it("puts the typed text in no address, console output or history entry", async () => {
    const spy = vi.spyOn(console, "error");
    const user = userEvent.setup();
    await console_(user);
    await open(user);
    fireEvent.change(field(), { target: { value: "needle words" } });
    await screen.findByRole("option", { name: /Lumen/ });
    await user.keyboard("{Escape}");
    expect(window.location.href).not.toContain("needle");
    expect(`${JSON.stringify(window.history.state)}`).not.toContain("needle");
    expect(JSON.stringify(routes)).not.toContain("needle");
    expect(spy.mock.calls.flat().join(" ")).not.toContain("needle");
    for (const r of api.log) expect(r.url).not.toContain("needle");
    const search = searches()[0];
    expect(search?.method).toBe("POST");
    expect(search?.body.variables).toMatchObject({ text: "needle words" });
    await open(user);
    expect(field()).toHaveValue(""); // nothing was kept
    spy.mockRestore();
  });
});

describe("the command palette in Explore (SD-013, Keyboard)", () => {
  let fake: BrowserFake;
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    window.location.hash = "#/explore/catalog";
    fake = stageBrowser();
    fake.mods = fake.mods.slice(0, 1);
  });
  const app = () => render(<ArrasApp queryClient={qc()} />);
  const ready = async (user: ReturnType<typeof userEvent.setup>) => {
    app();
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    await screen.findByRole("textbox", { name: /Search/ });
    await user.keyboard("{Control>}k{/Control}");
    return screen.findByRole("dialog", { name: "Command palette" });
  };
  const options = () => screen.getAllByRole("option").map((o) => o.getAttribute("aria-label"));

  it("opens on Ctrl+K in Explore, lists the module's types as commands and the operator's Open in Operate, and no Operate area or action", async () => {
    const user = userEvent.setup();
    await ready(user);
    const names = options();
    expect(names.filter((n) => n?.startsWith("Type · "))).toHaveLength(3);
    expect(names).toContain("Mode · Open in Operate");
    expect(names.some((n) => n?.startsWith("Area · ") || n?.startsWith("Action · "))).toBe(false);
    expect(screen.getByText(/Enter opens · Esc closes/)).toBeInTheDocument();
    expect(screen.queryByText(/Graph|History/)).toBeNull();
  });

  it("an entity result opens the entity's page", async () => {
    const user = userEvent.setup();
    await ready(user);
    await user.keyboard("Lumen");
    const hit = await screen.findByRole("option", { name: /^Solution · Lumen alert correlation/ });
    expect(hit).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Shift+Enter and Alt+Enter on an entity do nothing: Graph and History are Operate's", async () => {
    const user = userEvent.setup();
    await ready(user);
    await user.keyboard("Lumen");
    await screen.findByRole("option", { name: /^Solution · Lumen/ });
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.keyboard("{Alt>}{Enter}{/Alt}");
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/explore/catalog");
  });

  it("a type command opens that type's list", async () => {
    const user = userEvent.setup();
    await ready(user);
    await user.keyboard("use case");
    await user.click(await screen.findByRole("option", { name: /^Type · / }));
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/UseCase"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Open in Operate moves to Operate with the page that was open", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    app();
    await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" });
    await screen.findByRole("group", { name: "Mode" });
    await user.keyboard("{Control>}k{/Control}");
    await user.keyboard("open in operate");
    await user.click(await screen.findByRole("option", { name: "Mode · Open in Operate" }));
    expect(await screen.findByTestId("console-header")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.Solution/sol-1");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("for carol, who is not an operator, there is no Open in Operate and no word of Operate", async () => {
    fake.viewerModes = ["user"];
    const user = userEvent.setup();
    app();
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    await waitFor(() => expect(fake.requests.some((r) => r.path.endsWith("/viewer"))).toBe(true));
    await screen.findByRole("textbox", { name: /Search/ });
    await user.keyboard("{Control>}k{/Control}");
    const dialog = await screen.findByRole("dialog", { name: "Command palette" });
    expect(options().filter((n) => n?.startsWith("Type · "))).toHaveLength(3);
    expect(screen.queryByRole("option", { name: /Open in Operate/ })).toBeNull();
    await user.keyboard("operate");
    expect(screen.queryByRole("option", { name: /Operate/ })).toBeNull();
    expect(dialog.textContent).not.toMatch(/operate/i);
  });

  it("Escape closes it and gives the focus back to the search box", async () => {
    const user = userEvent.setup();
    app();
    const box = await screen.findByRole("textbox", { name: /Search/ });
    await user.click(box);
    await user.keyboard("{Control>}k{/Control}");
    await screen.findByRole("dialog", { name: "Command palette" });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(box).toHaveFocus();
  });
});
