// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
  window.location.hash = "#/explore/catalog/Solution/sol-1";
});
afterEach(() => {
  window.location.hash = "";
});

type User = ReturnType<typeof userEvent.setup>;
const editMode = async (user: User) =>
  user.click(await screen.findByRole("button", { name: "Edit mode" }));
const menuButton = () => screen.findByRole("button", { name: "Entity menu" });

/** Edit mode on, the menu open, Retire chosen: the confirmation. */
async function openConfirmation(user: User) {
  renderBrowser({ canEdit: true });
  await editMode(user);
  await user.click(await menuButton());
  await user.click(await screen.findByRole("menuitem", { name: "Retire" }));
  return screen.findByRole("dialog");
}

describe("Retire on a node page (FR-68)", () => {
  it("offers the menu with Retire in edit mode where a declared action deletes the type", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(screen.queryByRole("button", { name: "Entity menu" })).toBeNull();
    await editMode(user);
    await user.click(await menuButton());
    const menu = await screen.findByRole("menu");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((i) => i.textContent),
    ).toEqual(["Retire"]);
  });

  it("offers no Retire where no declared action deletes the type", async () => {
    window.location.hash = "#/explore/catalog/UseCase/uc-1";
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    await screen.findByRole("heading", { level: 1, name: /Alert review/ });
    expect(screen.queryByRole("button", { name: "Entity menu" })).toBeNull();
  });

  it("has no menu when the host does not offer edits (carol)", async () => {
    renderBrowser({ canEdit: false });
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(screen.queryByRole("button", { name: "Entity menu" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
  });

  it("names what goes with the entity by group, says the key is spent and there is no undo", async () => {
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    const groups = within(dialog).getByTestId("retire-groups");
    expect(groups).toHaveTextContent("Addresses use cases (3)");
    expect(groups).toHaveTextContent("Provided by (1)");
    expect(groups).toHaveTextContent("Notes (1)");
    expect(dialog).toHaveTextContent("sol-1");
    expect(dialog).toHaveTextContent("cannot be used again");
    expect(dialog).toHaveTextContent("no undo");
    expect(fake.writes).toEqual([]);
  });

  it("shows the keys of the linked entities on the page when nothing is hidden, and the dialog only counts them", async () => {
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    // the control: these keys are on the page the viewer can read, so their absence below means something
    for (const key of ["uc-1", "uc-2", "uc-3", "p-1", "n-1"])
      expect(document.body.textContent, key).toContain(key);
    expect(dialog.textContent).not.toMatch(/uc-1|uc-2|uc-3|p-1|n-1/);
    const groups = within(dialog).getByTestId("retire-groups");
    expect(groups.querySelectorAll("li")).toHaveLength(3);
    expect(groups).toHaveTextContent("Addresses use cases (3)");
  });

  it("never names the key of an entity the viewer cannot read", async () => {
    fake.hidden.add("catalog.UseCase:uc-2");
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    expect(document.body.textContent).not.toContain("uc-2");
    for (const key of ["uc-1", "uc-3", "p-1", "n-1"])
      expect(document.body.textContent, key).toContain(key);
    expect(dialog.textContent).not.toMatch(/uc-1|uc-2|uc-3|p-1|n-1/);
    // the groups still count every link the page holds, and the same three groups are listed
    const groups = within(dialog).getByTestId("retire-groups");
    expect(groups.querySelectorAll("li")).toHaveLength(3);
    expect(groups).toHaveTextContent("Addresses use cases (3)");
  });

  it("validates, then invokes with the key, and replaces the entity's history entry with the type's list", async () => {
    const user = userEvent.setup();
    const before = window.history.length;
    const dialog = await openConfirmation(user);
    await user.click(within(dialog).getByRole("button", { name: "Retire" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(fake.writes.map((w) => `${w.verb} ${w.action}`)).toEqual([
      "validate RetireSolution",
      "invoke RetireSolution",
    ]);
    expect(fake.writes[1]?.inputs).toEqual({ solution: "sol-1" });
    expect(window.location.hash).toBe("#/explore/catalog/Solution");
    expect(window.history.length).toBe(before);
    expect(await screen.findByText(/Alert grouping/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Solutions", level: 2 })).toHaveFocus(),
    );
    expect(screen.queryByText(/Lumen alert correlation/)).toBeNull();
  });

  it("sends an optional input only when it is filled", async () => {
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    await user.type(within(dialog).getByRole("textbox", { name: /reason/ }), "duplicate");
    await user.click(within(dialog).getByRole("button", { name: "Retire" }));
    await waitFor(() => expect(fake.writes.at(-1)?.verb).toBe("invoke"));
    expect(fake.writes.at(-1)?.inputs).toEqual({ solution: "sol-1", reason: "duplicate" });
  });

  it("shows a refusal in the dialog and applies nothing", async () => {
    fake.invalid = "a solution in use cannot be retired";
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    await user.click(within(dialog).getByRole("button", { name: "Retire" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "a solution in use cannot be retired",
    );
    expect(fake.writes.map((w) => w.verb)).toEqual(["validate"]);
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows a notice on a revision conflict and never invokes without a new click", async () => {
    fake.validateConflict = true;
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    await user.click(within(dialog).getByRole("button", { name: "Retire" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/module changed/);
    const reason = within(dialog).getByRole("textbox", { name: /reason/ });
    await user.type(reason, "duplicate");
    await user.tab();
    await waitFor(() => expect(fake.writes.filter((w) => w.verb === "validate").length).toBe(2));
    expect(fake.writes.map((w) => w.verb)).not.toContain("invoke");
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
  });

  it("says the viewer cannot retire it when the backend refuses the invoke, and keeps the page", async () => {
    fake.invokeStatus = 403;
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    await user.click(within(dialog).getByRole("button", { name: "Retire" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("You can't change this.");
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
  });

  it("cancels with the button or Escape, writing nothing, and returns focus to the menu button", async () => {
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await menuButton()).toHaveFocus();
    await user.click(await menuButton());
    await user.click(await screen.findByRole("menuitem", { name: "Retire" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await menuButton()).toHaveFocus();
    expect(fake.writes).toEqual([]);
  });

  it("keeps Tab inside the confirmation", async () => {
    const user = userEvent.setup();
    const dialog = await openConfirmation(user);
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    cancel.focus();
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.tab({ shift: true });
    await user.tab({ shift: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});

describe("the entity menu's keys", () => {
  it("opens with ArrowDown onto the first item, Escape closes it and returns focus to the button", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    const button = await menuButton();
    expect(button).toHaveAttribute("aria-expanded", "false");
    button.focus();
    await user.keyboard("{ArrowDown}");
    const item = await screen.findByRole("menuitem", { name: "Retire" });
    expect(item).toHaveFocus();
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{ArrowDown}");
    expect(item).toHaveFocus(); // one item: the arrows wrap onto it
    await user.keyboard("{ArrowUp}{Home}{End}");
    expect(item).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(button).toHaveFocus();
  });

  it("Enter on Retire opens the confirmation", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    (await menuButton()).focus();
    await user.keyboard("{Enter}");
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("closes on a click elsewhere and disappears with edit mode", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    await user.click(await menuButton());
    await screen.findByRole("menu");
    await user.click(screen.getByRole("heading", { level: 1 }));
    expect(screen.queryByRole("menu")).toBeNull();
    await editMode(user);
    expect(screen.queryByRole("button", { name: "Entity menu" })).toBeNull();
  });
});
