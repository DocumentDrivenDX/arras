// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo } from "../api/types";
import { claimsOf, entityActionsOf } from "../kit";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { exampleCatalog } from "./catalogModule";
import { renderBrowser } from "./render";

// Entity actions on a node page (FR-70): the menu lists Retire and each declared action no plan claims;
// each opens a dialog on the kit's form model. The catalog module is the example's, so the claimed-action
// rule runs on the real declarations; one action of a list and a record input is added to it.

const TAG = {
  name: "catalog.TagUseCase",
  description: "Tag a use case with labels and a settings object",
  inputSpecs: [
    { name: "useCase", type: "UseCase", kind: "ref", cardinality: "one" },
    { name: "tags", type: "string", kind: "scalar", cardinality: "many" },
    { name: "settings", type: "Settings", kind: "record", cardinality: "optional" },
  ],
  preconditions: [],
  effects: [],
} as ModuleInfo["actions"][number];

let fake: BrowserFake;
const catalog = () => fake.mods.find((m) => m.name === "catalog") as ModuleInfo;

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
  // The example's actions, and the types and relationships they name that the double does not draw.
  const example = exampleCatalog();
  const own = new Set(catalog().entityTypes.map((t) => t.name));
  const links = new Set(catalog().relationships.map((r) => r.name));
  catalog().actions = [...example.actions, TAG];
  catalog().entityTypes.push(...example.entityTypes.filter((t) => !own.has(t.name)));
  catalog().relationships.push(...example.relationships.filter((r) => !links.has(r.name)));
  window.location.hash = "#/explore/catalog/UseCase/uc-1";
});
afterEach(() => {
  window.location.hash = "";
});

type User = ReturnType<typeof userEvent.setup>;

async function openMenu(user: User, props: Parameters<typeof renderBrowser>[0] = {}) {
  renderBrowser({ canEdit: true, ...props });
  await user.click(await screen.findByRole("button", { name: "Edit mode" }));
  await user.click(await screen.findByRole("button", { name: "Entity menu" }));
  return screen.findByRole("menu");
}

const labels = (menu: HTMLElement) =>
  within(menu)
    .getAllByRole("menuitem")
    .map((i) => i.firstElementChild?.textContent ?? i.textContent);

async function openAction(user: User, name: string) {
  const menu = await openMenu(user);
  await user.click(within(menu).getByRole("menuitem", { name: new RegExp(`^${name}`) }));
  return screen.findByRole("dialog");
}

/** Pick an entity in a reference field's dropdown (the picker lists the type's entities once read). */
async function choose(user: User, dialog: HTMLElement, name: RegExp, label: string) {
  const box = await within(dialog).findByRole("combobox", { name });
  await within(box).findByRole("option", { name: label });
  await user.selectOptions(box, label);
}

describe("the entity menu lists the actions no plan claims (FR-70)", () => {
  it("offers AssertCoverage on a use case, with its description, and Retire only where one deletes the type", async () => {
    const menu = await openMenu(userEvent.setup());
    expect(labels(menu)).toEqual(["AddSolution", "AssertCoverage", "TagUseCase"]);
    expect(within(menu).getByRole("menuitem", { name: /AssertCoverage/ })).toHaveTextContent(
      /AssertCoverage.+\S/,
    );
    expect(within(menu).getByRole("menuitem", { name: /TagUseCase/ })).toHaveTextContent(
      "Tag a use case with labels and a settings object",
    );
    expect(within(menu).queryByRole("menuitem", { name: "Retire" })).toBeNull();
  });

  it("lists Retire alone on a solution: its Correct… update is claimed by the edit plan", async () => {
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    const menu = await openMenu(userEvent.setup());
    expect(labels(menu)).toEqual(["Retire"]);
    expect(catalog().actions.some((a) => a.name === "catalog.CorrectSolution")).toBe(true);
    expect(claimsOf(catalog(), "catalog.Solution").get("catalog.CorrectSolution")).toBe("edit");
  });

  it("offers nothing twice: every item is an action no plan claims, once", async () => {
    for (const hash of ["UseCase/uc-1", "Solution/sol-1", "Product/p-1"]) {
      window.location.hash = `#/explore/catalog/${hash}`;
      const type = `catalog.${hash.split("/")[0]}`;
      const claimed = claimsOf(catalog(), type);
      const expected = entityActionsOf(catalog(), type).map((a) => a.action.name.slice(8));
      const { unmount } = renderBrowser({ canEdit: true });
      const user = userEvent.setup();
      await user.click(await screen.findByRole("button", { name: "Edit mode" }));
      await user.click(await screen.findByRole("button", { name: "Entity menu" }));
      const shown = labels(await screen.findByRole("menu")).filter((l) => l !== "Retire");
      expect(shown).toEqual(expected);
      expect(new Set(shown).size).toBe(shown.length);
      for (const name of shown) expect(claimed.has(`catalog.${name}`)).toBe(false);
      unmount();
    }
  });

  it("has no menu for a viewer the host does not offer edits (carol)", async () => {
    renderBrowser({ canEdit: false });
    await screen.findByRole("heading", { level: 1, name: /Alert review/ });
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Entity menu" })).toBeNull();
  });

  it("moves with the arrow keys, opens an item with Enter and Escape returns focus to the button", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await user.click(await screen.findByRole("button", { name: "Edit mode" }));
    const button = await screen.findByRole("button", { name: "Entity menu" });
    button.focus();
    await user.keyboard("{ArrowDown}");
    const menu = await screen.findByRole("menu");
    const items = within(menu).getAllByRole("menuitem");
    expect(items[0]).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(items[1]).toHaveFocus();
    await user.keyboard("{End}");
    expect(items[2]).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(items[0]).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(button).toHaveFocus();
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("AssertCoverage");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(button).toHaveFocus();
  });
});

describe("an entity action's dialog", () => {
  it("prefills the page's entity, asks the other inputs, validates, summarises as text, applies and shows the receipt", async () => {
    fake.validateEffects = [
      {
        kind: "create",
        ref: { type: "catalog.CoverageAssertion", key: "cov-9", generated: false },
        properties: { level: "full" },
      },
      {
        kind: "link",
        relationship: "ofUseCase",
        source: { type: "catalog.CoverageAssertion", key: "cov-9", generated: false },
        target: { type: "catalog.UseCase", key: "uc-1", generated: false },
      },
    ];
    fake.nextReceipt = {
      refs: [
        { type: "catalog.CoverageAssertion", key: "cov-9", version: 1 },
        { type: "catalog.Product", key: "p-1", version: 3 },
      ],
      created: 1,
      linked: 2,
      updated: 0,
      group: "g-77",
    };
    const user = userEvent.setup();
    const dialog = await openAction(user, "AssertCoverage");
    // The page's use case is the entity; the others are asked for, the key field being the default.
    expect(within(dialog).queryByRole("textbox", { name: /useCase/ })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    const order = within(dialog)
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(order).toEqual(["Cancel", "Validate", "Apply"]);
    expect(within(dialog).getByRole("button", { name: "Apply" })).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), "cov-9");
    await user.type(within(dialog).getByRole("textbox", { name: /^level/ }), "full");
    await choose(user, dialog, /^product/, "Lumen");
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    const summary = await within(dialog).findByTestId("effects-summary");
    expect(summary).toHaveAttribute("data-status", "preview");
    expect(summary.querySelectorAll("[data-testid=effect-sentence]").length).toBe(2);
    expect(dialog.querySelector("svg[data-graph], canvas")).toBeNull();
    expect(fake.writes.every((w) => w.verb === "validate")).toBe(true);
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));
    const receipt = await within(dialog).findByTestId("receipt-summary");
    await waitFor(() => expect(receipt).toHaveFocus());
    expect(fake.writes.at(-1)).toMatchObject({ verb: "invoke", action: "AssertCoverage" });
    expect(fake.writes.filter((w) => w.verb === "invoke")).toHaveLength(1);
    expect(fake.writes[1]?.inputs).toEqual({
      code: "cov-9",
      level: "full",
      product: "p-1",
      useCase: "uc-1",
    });
    // A type the viewer cannot read is counted, never named or linked.
    expect(receipt.textContent).not.toContain("cov-9");
    expect(dialog).toHaveTextContent("1 more entity you cannot read was touched");
    const link = within(receipt).getByRole("link", { name: /Product p-1/ });
    expect(link).toHaveAttribute("href", "#/explore/catalog/Product/p-1");
    // No Operate link where the shell handed none.
    expect(within(dialog).queryByText(/in Operate/)).toBeNull();
    await user.click(link);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(window.location.hash).toBe("#/explore/catalog/Product/p-1");
  });

  it("counts a touched entity the viewer cannot read and never names its key, as History does", async () => {
    // Product p-1 is of a readable type but the viewer cannot read this entity.
    fake.rows["catalog.Product"]?.push({
      key: "p-2",
      props: { code: "p-2", name: "Orbit Notebook" },
      rels: {},
    });
    fake.hidden.add("catalog.Product:p-1");
    fake.nextReceipt = {
      refs: [
        { type: "catalog.UseCase", key: "uc-1", version: 2 },
        { type: "catalog.Product", key: "p-1", version: 3 },
      ],
      created: 0,
      linked: 0,
      updated: 2,
      group: "g-78",
    };
    const user = userEvent.setup();
    const dialog = await openAction(user, "AssertCoverage");
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), "cov-9");
    await user.type(within(dialog).getByRole("textbox", { name: /^level/ }), "full");
    await choose(user, dialog, /^product/, "Orbit Notebook");
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await user.click(await within(dialog).findByRole("button", { name: "Apply" }));
    const receipt = await within(dialog).findByTestId("receipt-summary");
    await within(dialog).findByText(/1 more entity you cannot read was touched/);
    expect(receipt.textContent).not.toContain("p-1");
    expect(within(receipt).getByRole("link", { name: /UseCase uc-1/ })).toBeInTheDocument();
  });

  it("names and links an entity the action created even where the label read answers not available", async () => {
    fake.hidden.add("catalog.Solution:s-new");
    fake.validateEffects = [
      { kind: "create", ref: { type: "catalog.Solution", key: "s-new" }, properties: {} },
    ];
    fake.nextReceipt = {
      refs: [{ type: "catalog.Solution", key: "s-new", version: 1 }],
      created: 1,
      linked: 0,
      updated: 0,
    };
    const user = userEvent.setup();
    const dialog = await openAction(user, "AddSolution");
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), "s-new");
    await user.type(within(dialog).getByRole("textbox", { name: /^name/ }), "New");
    await user.type(within(dialog).getByRole("textbox", { name: /^deliveryMode/ }), "Embedded");
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await user.click(await within(dialog).findByRole("button", { name: "Apply" }));
    const receipt = await within(dialog).findByTestId("receipt-summary");
    expect(within(receipt).getByRole("link", { name: /Solution s-new/ })).toBeInTheDocument();
    expect(within(dialog).queryByText(/you cannot read/)).toBeNull();
  });

  it("reads the page again after an apply and returns focus to the menu button on Close", async () => {
    const user = userEvent.setup();
    const dialog = await openAction(user, "AddSolution");
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), "s-new");
    await user.type(within(dialog).getByRole("textbox", { name: /^name/ }), "New");
    await user.type(within(dialog).getByRole("textbox", { name: /^deliveryMode/ }), "Embedded");
    const reads = fake.moduleQueries("catalog").length;
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await user.click(await within(dialog).findByRole("button", { name: "Apply" }));
    await within(dialog).findByTestId("receipt-summary");
    await waitFor(() => expect(fake.moduleQueries("catalog").length).toBeGreaterThan(reads));
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Entity menu" })).toHaveFocus();
  });

  it("sends a list one value per line and a record as JSON", async () => {
    const user = userEvent.setup();
    const dialog = await openAction(user, "TagUseCase");
    await user.type(within(dialog).getByRole("textbox", { name: /^tags/ }), "a{Enter}b");
    const settings = within(dialog).getByRole("textbox", { name: /^settings/ });
    await user.click(settings);
    await user.paste('{"depth": 2}');
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await user.click(await within(dialog).findByRole("button", { name: "Apply" }));
    await within(dialog).findByTestId("receipt-summary");
    expect(fake.writes.at(-1)?.inputs).toEqual({
      useCase: "uc-1",
      tags: ["a", "b"],
      settings: { depth: 2 },
    });
  });

  it("shows a refusal inline, applies nothing and keeps the inputs", async () => {
    fake.invalid = "that product does not cover use cases";
    const user = userEvent.setup();
    const dialog = await openAction(user, "AssertCoverage");
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), "cov-1");
    await user.type(within(dialog).getByRole("textbox", { name: /^level/ }), "full");
    await choose(user, dialog, /^product/, "Lumen");
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "that product does not cover use cases",
    );
    expect(within(dialog).getByRole("button", { name: "Apply" })).toBeDisabled();
    expect(within(dialog).getByRole("textbox", { name: /^code/ })).toHaveValue("cov-1");
    expect(fake.writes.every((w) => w.verb === "validate")).toBe(true);
  });

  it("keeps the values on a 401 and offers Sign in again where the host can", async () => {
    const onUnauthorized = vi.fn();
    const user = userEvent.setup();
    const menu = await openMenu(user, { onUnauthorized });
    await user.click(within(menu).getByRole("menuitem", { name: /^AssertCoverage/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), "cov-1");
    await user.type(within(dialog).getByRole("textbox", { name: /^level/ }), "full");
    await choose(user, dialog, /^product/, "Lumen");
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await within(dialog).findByTestId("effects-summary");
    fake.invokeStatus = 401;
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));
    const again = await within(dialog).findByRole("button", { name: "Sign in again" });
    expect(within(dialog).getByRole("textbox", { name: /^code/ })).toHaveValue("cov-1");
    onUnauthorized.mockClear();
    await user.click(again);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("cancels with Cancel, applying nothing, and offers no batch", async () => {
    const user = userEvent.setup();
    const dialog = await openAction(user, "AssertCoverage");
    expect(within(dialog).queryByText(/batch/i)).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Entity menu" })).toHaveFocus();
    expect(fake.writes).toEqual([]);
  });

  it("links the group's receipt in Operate where the shell handed the link", async () => {
    fake.nextReceipt = { refs: [], group: "g-12" };
    const go = vi.fn();
    const toOperate = vi.fn(() => ({ href: "#/operate/catalog/changes/g-12", go }));
    const user = userEvent.setup();
    const menu = await openMenu(user, { links: { toOperate } });
    await user.click(within(menu).getByRole("menuitem", { name: /^AssertCoverage/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), "c");
    await user.type(within(dialog).getByRole("textbox", { name: /^level/ }), "full");
    await choose(user, dialog, /^product/, "Lumen");
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await user.click(await within(dialog).findByRole("button", { name: "Apply" }));
    const link = await within(dialog).findByRole("link", { name: /in Operate/ });
    expect(link).toHaveAttribute("href", "#/operate/catalog/changes/g-12");
    expect(toOperate).toHaveBeenCalledWith({ group: { module: "catalog", id: "g-12" } });
  });
});
