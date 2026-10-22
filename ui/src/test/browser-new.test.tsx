// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Effect, ModuleInfo } from "../api/types";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { exampleCatalog } from "./catalogModule";
import { qc as makeClient, renderBrowser } from "./render";

// New on a type's list (FR-67): in edit mode a button opens the form of the declared create action,
// a reference asked through the picker; Validate then Create invoke it and the created entity opens
// from the validated key. The catalog module is the example's, so the create plans are the real ones.

let fake: BrowserFake;
const catalog = () => fake.mods.find((m) => m.name === "catalog") as ModuleInfo;

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
  const example = exampleCatalog();
  const own = new Set(catalog().entityTypes.map((t) => t.name));
  const links = new Set(catalog().relationships.map((r) => r.name));
  catalog().actions = example.actions;
  catalog().entityTypes.push(...example.entityTypes.filter((t) => !own.has(t.name)));
  catalog().relationships.push(...example.relationships.filter((r) => !links.has(r.name)));
  window.location.hash = "#/explore/catalog/Solution";
});
afterEach(() => {
  window.location.hash = "";
});

type User = ReturnType<typeof userEvent.setup>;

const created = (key: string): Effect[] => [
  { kind: "create", ref: { type: "catalog.Solution", key }, properties: {} },
  {
    kind: "link",
    relationship: "addresses",
    source: { type: "catalog.Solution", key },
    target: { type: "catalog.UseCase", key: "uc-1" },
  },
];

/** Edit mode on, then the New button pressed: the form. */
async function openForm(user: User, canEdit = true, queryClient = makeClient()) {
  renderBrowser({ canEdit, queryClient });
  await screen.findByRole("heading", { level: 2, name: "Solutions" });
  await user.click(await screen.findByRole("button", { name: "Edit mode" }));
  await user.click(await screen.findByRole("button", { name: "New solution" }));
  return screen.findByRole("dialog");
}

/** The form filled as far as validating: the key, the name, how it is delivered and the use case. */
async function fill(user: User, dialog: HTMLElement, code = "s-new") {
  await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), code);
  await user.type(within(dialog).getByRole("textbox", { name: /^name/ }), "A new solution");
  await user.type(within(dialog).getByRole("textbox", { name: /^deliveryMode/ }), "Embedded");
  const box = await within(dialog).findByRole("combobox", { name: /^useCase/ });
  await within(box).findByRole("option", { name: "Alert review" });
  await user.selectOptions(box, "Alert review");
}

describe("New on a type's list (FR-67)", () => {
  it("offers the lock only to an operator, and the button only once edit mode is on", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await screen.findByRole("heading", { level: 2, name: "Solutions" });
    expect(screen.queryByRole("button", { name: "New solution" })).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Edit mode" }));
    expect(screen.getByRole("button", { name: "New solution" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit mode" }));
    expect(screen.queryByRole("button", { name: "New solution" })).toBeNull();
  });

  it("offers nothing to a viewer the host gave no edits (carol)", async () => {
    renderBrowser({ canEdit: false });
    await screen.findByRole("heading", { level: 2, name: "Solutions" });
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New solution" })).toBeNull();
  });

  it("offers nothing on a type no declared action creates", async () => {
    window.location.hash = "#/explore/other/Note";
    renderBrowser({ canEdit: true });
    await screen.findByRole("heading", { level: 2, name: "Notes" });
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
  });

  it("asks every input, a reference through the picker, and shows a required input's message at the field", async () => {
    const dialog = await openForm(userEvent.setup());
    for (const name of ["code", "name", "deliveryMode", "summary", "workflow", "prompt"])
      expect(within(dialog).getByRole("textbox", { name: new RegExp(`^${name}`) })).toBeVisible();
    const box = await within(dialog).findByRole("combobox", { name: /^useCase/ });
    expect(await within(box).findByRole("option", { name: "Runbook check" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("textbox", { name: /^useCase/ })).toBeNull();
  });

  it("does not send an incomplete form", async () => {
    const user = userEvent.setup();
    const dialog = await openForm(user);
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    expect(
      (await within(dialog).findAllByText(/Expected a value \(required\)/)).length,
    ).toBeGreaterThan(0);
    expect(fake.writes).toEqual([]);
    expect(within(dialog).getByRole("button", { name: "Create" })).toBeDisabled();
  });

  it("validates, then invokes with the picked key, and opens the created entity from the validated key", async () => {
    fake.validateEffects = created("s-new");
    fake.nextReceipt = {
      created: 1,
      linked: 1,
      refs: [{ type: "catalog.Solution", key: "s-new", version: 1 }],
    };
    fake.rows["catalog.Solution"]?.push({
      key: "s-new",
      props: { code: "s-new", name: "A new solution", deliveryMode: "Embedded" },
      rels: { addresses: ["uc-1"] },
    });
    const user = userEvent.setup();
    const dialog = await openForm(user);
    await fill(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    expect(await within(dialog).findByTestId("effects-summary")).toBeInTheDocument();
    expect(fake.writes.every((w) => w.verb === "validate" && w.action === "AddSolution")).toBe(
      true,
    );
    await user.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Every write is a validate, then the one invoke, of the declared action (leaving the last field
    // validates too, so the check may have been sent twice).
    expect(fake.writes.map((w) => w.verb).filter((v) => v === "invoke")).toEqual(["invoke"]);
    expect(fake.writes.at(-1)?.verb).toBe("invoke");
    expect(new Set(fake.writes.map((w) => w.action))).toEqual(new Set(["AddSolution"]));
    expect(fake.writes.at(-1)?.inputs).toMatchObject({
      code: "s-new",
      name: "A new solution",
      deliveryMode: "Embedded",
      useCase: "uc-1",
    });
    expect(window.location.hash).toBe("#/explore/catalog/Solution/s-new");
    const title = await screen.findByRole("heading", { level: 1, name: /A new solution/ });
    await waitFor(() => expect(title).toHaveFocus());
  });

  it("makes every family of reads stale after a create, as any other apply does", async () => {
    fake.validateEffects = created("s-new");
    fake.nextReceipt = {
      created: 1,
      linked: 1,
      refs: [{ type: "catalog.Solution", key: "s-new", version: 1 }],
    };
    const client = makeClient();
    const keys: unknown[] = [];
    const real = client.invalidateQueries.bind(client);
    client.invalidateQueries = ((f?: { queryKey?: unknown[] }) => {
      keys.push(f?.queryKey?.[0]);
      return real(f as never);
    }) as typeof client.invalidateQueries;
    const user = userEvent.setup();
    const dialog = await openForm(user, true, client);
    await fill(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await within(dialog).findByTestId("effects-summary");
    await user.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    for (const k of ["gb", "list", "graph", "entity", "status", "audit"]) expect(keys).toContain(k);
  });

  it("keeps the dialog open on Escape while a Create is in flight, and still opens the created page", async () => {
    fake.validateEffects = created("s-new");
    fake.nextReceipt = {
      created: 1,
      linked: 1,
      refs: [{ type: "catalog.Solution", key: "s-new", version: 1 }],
    };
    fake.rows["catalog.Solution"]?.push({
      key: "s-new",
      props: { code: "s-new", name: "A new solution", deliveryMode: "Embedded" },
      rels: { addresses: ["uc-1"] },
    });
    const release = fake.holdInvoke();
    const user = userEvent.setup();
    const dialog = await openForm(user);
    await fill(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await within(dialog).findByTestId("effects-summary");
    await user.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() => expect(fake.writes.at(-1)?.verb).toBe("invoke"));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    release();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(window.location.hash).toBe("#/explore/catalog/Solution/s-new");
  });

  it("shows a refusal in the dialog, applies nothing and keeps the inputs", async () => {
    fake.invalid = "a solution with that code exists";
    const user = userEvent.setup();
    const dialog = await openForm(user);
    await fill(user, dialog, "sol-1");
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "a solution with that code exists",
    );
    expect(fake.writes.every((w) => w.verb === "validate")).toBe(true);
    expect(within(dialog).getByRole("button", { name: "Create" })).toBeDisabled();
    expect(within(dialog).getByRole("textbox", { name: /^code/ })).toHaveValue("sol-1");
    expect(window.location.hash).toBe("#/explore/catalog/Solution");
  });

  it("closes on Escape and on Cancel, returning focus to the button, and creates nothing", async () => {
    const user = userEvent.setup();
    const dialog = await openForm(user);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "New solution" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "New solution" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "New solution" })).toHaveFocus();
    expect(dialog).not.toBeInTheDocument();
    expect(fake.writes).toEqual([]);
  });

  it("offers a Select where several declared actions create the type, the one with fewest inputs first", async () => {
    const quick = {
      ...catalog().actions.find((a) => a.name === "catalog.AddSolution"),
      name: "catalog.QuickSolution",
    } as ModuleInfo["actions"][number];
    quick.inputSpecs = quick.inputSpecs.filter((s) =>
      ["code", "name", "deliveryMode", "useCase"].includes(s.name),
    );
    catalog().actions.push(quick);
    const user = userEvent.setup();
    const dialog = await openForm(user);
    const select = within(dialog).getByRole("combobox", { name: "Create with" });
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["QuickSolution", "AddSolution"]);
    expect(within(dialog).queryByRole("textbox", { name: /^summary/ })).toBeNull();
    await user.selectOptions(select, "AddSolution");
    expect(within(dialog).getByRole("textbox", { name: /^summary/ })).toBeVisible();
  });
});
