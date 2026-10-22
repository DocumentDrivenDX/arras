// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { RemoveLink } from "../browser/LinkControls";
import { LinkDialog } from "../browser/LinkDialog";
import { type TypeEntry, typesOf } from "../browser/meta";
import { groupLinks } from "../kit";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { defined } from "./defined";
import { renderBrowser, renderPart } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
});
afterEach(() => {
  window.location.hash = "";
});

const open = (hash: string) => {
  window.location.hash = hash;
  return renderBrowser({ canEdit: true });
};
const group = async (name: RegExp) =>
  (await screen.findByRole("heading", { level: 3, name })).closest("section") as HTMLElement;
type User = ReturnType<typeof userEvent.setup>;
const unlock = async (user: User) =>
  user.click(await screen.findByRole("button", { name: "Edit mode" }));

describe("removing a link in place", () => {
  it("shows no add or remove control until edit mode is on, and none where nothing is declared", async () => {
    const user = userEvent.setup();
    open("#/explore/catalog/Solution/sol-1");
    const addresses = await group(/Addresses use cases/);
    await within(addresses).findByRole("link", { name: /Alert review/ });
    expect(screen.queryByRole("button", { name: /^Add to / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Remove link to / })).toBeNull();
    await unlock(user);
    expect(
      within(addresses).getByRole("button", { name: "Add to Addresses use cases" }),
    ).toBeVisible();
    expect(within(addresses).getAllByRole("button", { name: /^Remove link to / })).toHaveLength(3);
    const provided = await group(/Provided by/);
    expect(within(provided).getByRole("button", { name: "Add to Provided by" })).toBeVisible();
    expect(within(provided).queryByRole("button", { name: /^Remove link to / })).toBeNull();
    // a relationship the module declares no action for has no control, even while editing
    expect(within(await group(/Notes/)).queryByRole("button")).toBeNull();
  });

  it("asks once, then validates and invokes the unlink action with both keys, and the member goes", async () => {
    const user = userEvent.setup();
    open("#/explore/catalog/Solution/sol-1");
    await unlock(user);
    const addresses = await group(/Addresses use cases/);
    await user.click(
      await within(addresses).findByRole("button", { name: "Remove link to Alert review" }),
    );
    expect(within(addresses).getByText("Remove the link to Alert review?")).toBeVisible();
    expect(fake.writes).toEqual([]);
    await user.click(within(addresses).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(within(addresses).queryByRole("link", { name: /Alert review/ })).toBeNull(),
    );
    expect(fake.writes.map((w) => `${w.verb} ${w.action}`)).toEqual([
      "validate UnaddressUseCase",
      "invoke UnaddressUseCase",
    ]);
    expect(fake.writes[1]?.inputs).toEqual({ solution: "sol-1", useCase: "uc-1" });
    expect(within(addresses).getAllByRole("link")).toHaveLength(2);
  });

  it("keeps the link when the question is cancelled", async () => {
    const user = userEvent.setup();
    open("#/explore/catalog/Solution/sol-1");
    await unlock(user);
    const addresses = await group(/Addresses use cases/);
    await user.click(
      await within(addresses).findByRole("button", { name: "Remove link to Alert review" }),
    );
    await user.click(within(addresses).getByRole("button", { name: "Cancel" }));
    expect(within(addresses).getByRole("link", { name: /Alert review/ })).toBeVisible();
    expect(fake.writes).toEqual([]);
  });

  it("moves focus to Remove when the question opens, and back to the icon on Cancel", async () => {
    const user = userEvent.setup();
    open("#/explore/catalog/Solution/sol-1");
    await unlock(user);
    const addresses = await group(/Addresses use cases/);
    await user.click(
      await within(addresses).findByRole("button", { name: "Remove link to Alert review" }),
    );
    expect(within(addresses).getByRole("button", { name: "Remove" })).toHaveFocus();
    await user.click(within(addresses).getByRole("button", { name: "Cancel" }));
    expect(
      within(addresses).getByRole("button", { name: "Remove link to Alert review" }),
    ).toHaveFocus();
  });

  it("says why when the change is refused and keeps the link", async () => {
    const user = userEvent.setup();
    fake.invalid = "a solution must address something";
    open("#/explore/catalog/Solution/sol-1");
    await unlock(user);
    const addresses = await group(/Addresses use cases/);
    await user.click(
      await within(addresses).findByRole("button", { name: "Remove link to Alert review" }),
    );
    await user.click(within(addresses).getByRole("button", { name: "Remove" }));
    expect(await within(addresses).findByRole("alert")).toHaveTextContent(
      "a solution must address something",
    );
    expect(fake.writes.map((w) => w.verb)).toEqual(["validate"]);
    expect(within(addresses).getByRole("link", { name: /Alert review/ })).toBeVisible();
  });
});

describe("adding a link in place", () => {
  const openAdd = async (user: User, hash: string, group_: RegExp, label: string) => {
    open(hash);
    await unlock(user);
    await user.click(await within(await group(group_)).findByRole("button", { name: label }));
    return screen.findByRole("dialog");
  };
  const choices = (dialog: HTMLElement) =>
    within(dialog).getByRole("combobox", { name: /^Choose / });
  const labelsOf = (select: HTMLElement) =>
    within(select)
      .getAllByRole("option")
      .filter((o) => (o as HTMLOptionElement).value !== "")
      .map((o) => o.textContent);

  it("lists every choice at once in a dropdown, without typing, and shows what is already linked as taken", async () => {
    const user = userEvent.setup();
    const dialog = await openAdd(
      user,
      "#/explore/catalog/Solution/sol-1",
      /Addresses use cases/,
      "Add to Addresses use cases",
    );
    await waitFor(() => expect(labelsOf(choices(dialog))).toHaveLength(3));
    expect(labelsOf(choices(dialog))).toEqual([
      "Alert review (already linked)",
      "Runbook check (already linked)",
      "Log extraction (already linked)",
    ]);
    const taken = within(choices(dialog)).getByRole("option", {
      name: /Alert review/,
    }) as HTMLOptionElement;
    expect(taken.disabled).toBe(true);
    expect(within(dialog).getByRole("button", { name: "Add" })).toBeDisabled();
    expect(within(dialog).queryByText(/Showing the first/)).toBeNull();
  });

  it("narrows the list as the reader types, then invokes the link action for the one picked", async () => {
    const user = userEvent.setup();
    const dialog = await openAdd(
      user,
      "#/explore/catalog/Solution/sol-2",
      /Addresses use cases/,
      "Add to Addresses use cases",
    );
    await waitFor(() => expect(labelsOf(choices(dialog))).toHaveLength(3));
    await user.type(
      within(dialog).getByRole("textbox", { name: /Filter or search use case/ }),
      "check",
    );
    expect(labelsOf(choices(dialog))).toEqual(["Runbook check"]);
    await user.selectOptions(choices(dialog), "catalog.UseCase:uc-2");
    await user.click(within(dialog).getByRole("button", { name: "Add Runbook check" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(fake.writes.map((w) => `${w.verb} ${w.action}`)).toEqual([
      "validate AddressUseCase",
      "invoke AddressUseCase",
    ]);
    expect(fake.writes[1]?.inputs).toEqual({ solution: "sol-2", useCase: "uc-2" });
    expect(
      await within(await group(/Addresses use cases/)).findByRole("link", {
        name: /Runbook check/,
      }),
    ).toBeVisible();
  });

  it("says nothing matches when the typed text matches no choice", async () => {
    const user = userEvent.setup();
    const dialog = await openAdd(
      user,
      "#/explore/catalog/Solution/sol-2",
      /Addresses use cases/,
      "Add to Addresses use cases",
    );
    await waitFor(() => expect(labelsOf(choices(dialog))).toHaveLength(3));
    await user.type(within(dialog).getByRole("textbox"), "zzz");
    expect(labelsOf(choices(dialog))).toEqual([]);
    expect(within(dialog).getByText("Nothing matches.")).toBeVisible();
  });

  it("lists the first page of a long type, says so, and searches once the reader types", async () => {
    const user = userEvent.setup();
    fake.rows["catalog.UseCase"]?.push(
      ...Array.from({ length: 130 }, (_, i) => ({
        key: `uc-z-${String(i).padStart(3, "0")}`,
        props: { code: `z${i}`, name: `Bulk use case ${String(i).padStart(3, "0")}` },
        rels: {},
      })),
      { key: "uc-zzz", props: { code: "zzz", name: "Zebra pattern library" }, rels: {} },
    );
    const dialog = await openAdd(
      user,
      "#/explore/catalog/Solution/sol-2",
      /Addresses use cases/,
      "Add to Addresses use cases",
    );
    await waitFor(() => expect(labelsOf(choices(dialog))).toHaveLength(100));
    expect(
      within(dialog).getByText("Showing the first 100 of each type. Type to search for others."),
    ).toBeVisible();
    expect(labelsOf(choices(dialog)).join("|")).not.toMatch(/Zebra/); // past the first page
    await user.type(within(dialog).getByRole("textbox"), "zebra");
    await waitFor(() => expect(labelsOf(choices(dialog))).toEqual(["Zebra pattern library"]));
    expect(within(dialog).queryByText(/Showing the first/)).toBeNull();
  });

  it("adds from the other end of the relationship, with the keys in the action's own inputs", async () => {
    const user = userEvent.setup();
    const dialog = await openAdd(
      user,
      "#/explore/catalog/UseCase/uc-2",
      /Addressed by/,
      "Add to Addressed by",
    );
    await waitFor(() => expect(labelsOf(choices(dialog)).length).toBeGreaterThan(0));
    await user.selectOptions(choices(dialog), "catalog.Solution:sol-2");
    await user.click(within(dialog).getByRole("button", { name: /^Add Alert grouping/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(fake.writes[1]?.inputs).toEqual({ useCase: "uc-2", solution: "sol-2" });
  });

  it("shows why a change was refused and keeps the dialog open", async () => {
    const user = userEvent.setup();
    fake.invalid = "that link is not allowed";
    const dialog = await openAdd(
      user,
      "#/explore/catalog/Solution/sol-2",
      /Addresses use cases/,
      "Add to Addresses use cases",
    );
    await waitFor(() => expect(labelsOf(choices(dialog))).toHaveLength(3));
    await user.selectOptions(choices(dialog), "catalog.UseCase:uc-2");
    await user.click(within(dialog).getByRole("button", { name: "Add Runbook check" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("that link is not allowed");
    expect(fake.writes.map((w) => w.verb)).toEqual(["validate"]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("closes with Escape or Cancel and writes nothing", async () => {
    const user = userEvent.setup();
    await openAdd(
      user,
      "#/explore/catalog/Solution/sol-2",
      /Addresses use cases/,
      "Add to Addresses use cases",
    );
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fake.writes).toEqual([]);
    expect(screen.getByRole("button", { name: "Add to Addresses use cases" })).toHaveFocus();
  });

  it("returns focus to the Add button after Cancel", async () => {
    const user = userEvent.setup();
    const dialog = await openAdd(
      user,
      "#/explore/catalog/Solution/sol-2",
      /Addresses use cases/,
      "Add to Addresses use cases",
    );
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Add to Addresses use cases" })).toHaveFocus();
  });

  it("returns focus to the Add button after the link is added", async () => {
    const user = userEvent.setup();
    const dialog = await openAdd(
      user,
      "#/explore/catalog/Solution/sol-2",
      /Addresses use cases/,
      "Add to Addresses use cases",
    );
    await waitFor(() => expect(labelsOf(choices(dialog)).length).toBeGreaterThan(0));
    await user.selectOptions(choices(dialog), "catalog.UseCase:uc-2");
    await user.click(within(dialog).getByRole("button", { name: /^Add / }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("button", { name: "Add to Addresses use cases" })).toHaveFocus();
  });
});

describe("a relationship that allows several types at the other end", () => {
  const twoTypes = () => {
    const rel = fake.mods[0]?.relationships.find((r) => r.name === "addresses");
    if (rel) rel.target = ["catalog.UseCase", "catalog.Product"];
  };

  it("offers only the type the link action's other input takes", async () => {
    twoTypes();
    const user = userEvent.setup();
    open("#/explore/catalog/Solution/sol-2");
    await unlock(user);
    await user.click(
      await within(await group(/Addresses use cases/)).findByRole("button", {
        name: "Add to Addresses use cases",
      }),
    );
    const dialog = await screen.findByRole("dialog");
    const select = within(dialog).getByRole("combobox", { name: /^Choose / });
    await waitFor(() => expect(within(select).getAllByRole("option").length).toBeGreaterThan(1));
    const texts = within(select)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(texts).toContain("Runbook check");
    expect(texts.join("|")).not.toMatch(/Lumen/); // the product is not one the action's input takes
  });

  it("shows the remove control only on members of the unlink input's type", () => {
    twoTypes();
    const module = defined(fake.mods[0]);
    const links = defined(groupLinks(module, "catalog.Solution", "addresses"));
    const centre = { entry: { module } as TypeEntry, key: "sol-1" };
    const member = (type: string, key: string) => (
      <RemoveLink
        item={{ module: "catalog", type, key }}
        title={key}
        links={links}
        centre={centre}
      />
    );
    renderPart(
      <>
        {member("catalog.UseCase", "uc-1")}
        {member("catalog.Product", "p-1")}
      </>,
    );
    expect(screen.getByRole("button", { name: "Remove link to uc-1" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Remove link to p-1" })).toBeNull();
  });
});

describe("the picker's search when the list is cut", () => {
  it("covers end types of other modules, not only the first one's", async () => {
    fake.rows["catalog.UseCase"]?.push(
      ...Array.from({ length: 130 }, (_, i) => ({
        key: `uc-z-${String(i).padStart(3, "0")}`,
        props: { code: `z${i}`, name: `Bulk use case ${String(i).padStart(3, "0")}` },
        rels: {},
      })),
    );
    const entryOf = (module: string, type: string) => {
      const m = defined(fake.mods.find((x) => x.name === module));
      return defined(typesOf(m).find((t) => t.type.name === `${module}.${type}`));
    };
    const catalog = defined(fake.mods.find((x) => x.name === "catalog"));
    const links = defined(groupLinks(catalog, "catalog.Solution", "addresses"));
    // The real dialog, with an end type of another module after the first: only the dialog's own rows are asserted.
    const user = userEvent.setup();
    renderPart(
      <LinkDialog
        title="Add to Addresses use cases"
        module={catalog}
        pageKey="sol-1"
        plan={defined(links.add)}
        links={links}
        linked={new Set()}
        ends={[entryOf("catalog", "UseCase"), entryOf("other", "Note")]}
        onClose={() => undefined}
      />,
    );
    const dialog = await screen.findByRole("dialog");
    const select = within(dialog).getByRole("combobox", { name: /^Choose / });
    await waitFor(() => expect(within(select).getAllByRole("option").length).toBeGreaterThan(100));
    await user.type(within(dialog).getByRole("textbox"), "elsewhere");
    // Once the pause has passed the search answers, not the narrowed first page (whose note says so).
    await waitFor(() => expect(dialog).not.toHaveTextContent(/Showing the first/));
    await waitFor(() =>
      expect(
        within(select)
          .getAllByRole("option")
          .map((o) => o.textContent)
          .filter((t) => t !== "Choose…"),
      ).toEqual(["Note · A note elsewhere"]),
    );
  });
});
