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

const row = (name: string) => screen.findByTestId(`prop-${name}`);

type User = ReturnType<typeof userEvent.setup>;
/** Turn edit mode on with the pencil in the card's header. */
const editMode = async (user: User) =>
  user.click(await screen.findByRole("button", { name: "Edit mode" }));

describe("editing a property in place", () => {
  it("offers an edit beside a property that a declared action updates, and not beside others", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    const audience = await row("audience");
    expect(await within(audience).findByRole("button", { name: "Edit Audience" })).toBeVisible();
    // No declared action updates these: the key's own row, a launch address, a list.
    expect(within(await row("launchUrl")).queryByRole("button")).toBeNull();
    expect(within(await row("tags")).queryByRole("button")).toBeNull();
  });

  it("offers no edit unless the host says the viewer may", async () => {
    renderBrowser({ canEdit: false });
    const audience = await row("audience");
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(within(audience).queryByRole("button")).toBeNull();
  });

  it("validates, then invokes the declared action with the key and only the new value, and shows it", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    const audience = await row("audience");
    await user.click(await within(audience).findByRole("button", { name: "Edit Audience" }));
    const box = within(audience).getByRole("textbox", { name: "Audience" });
    expect(box).toHaveValue("Platform engineers");
    await user.clear(box);
    await user.type(box, "Data analysts");
    await user.click(within(audience).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(within(audience).queryByRole("textbox")).toBeNull());
    expect(fake.writes.map((w) => `${w.verb} ${w.action}`)).toEqual([
      "validate CorrectSolution",
      "invoke CorrectSolution",
    ]);
    expect(fake.writes[1]?.inputs).toEqual({ audience: "Data analysts", solution: "sol-1" });
    expect(await within(await row("audience")).findByText("Data analysts")).toBeInTheDocument();
  });

  it("keeps the old value and says why when the change is refused, and sends nothing to invoke", async () => {
    const user = userEvent.setup();
    fake.invalid = "audience is not allowed";
    renderBrowser({ canEdit: true });
    await editMode(user);
    const audience = await row("audience");
    await user.click(await within(audience).findByRole("button", { name: "Edit Audience" }));
    await user.type(within(audience).getByRole("textbox", { name: "Audience" }), "x");
    await user.click(within(audience).getByRole("button", { name: "Save" }));
    expect(await within(audience).findByRole("alert")).toHaveTextContent("audience is not allowed");
    expect(fake.writes.map((w) => w.verb)).toEqual(["validate"]);
    expect(within(audience).getByRole("textbox")).toBeInTheDocument();
  });

  it("says the viewer can't change it when the backend refuses, and leaves the editor open", async () => {
    const user = userEvent.setup();
    fake.invokeStatus = 403;
    renderBrowser({ canEdit: true });
    await editMode(user);
    const audience = await row("audience");
    await user.click(await within(audience).findByRole("button", { name: "Edit Audience" }));
    await user.type(within(audience).getByRole("textbox", { name: "Audience" }), "x");
    await user.click(within(audience).getByRole("button", { name: "Save" }));
    expect(await within(audience).findByRole("alert")).toHaveTextContent("You can't change this.");
    expect(within(audience).getByRole("textbox")).toBeInTheDocument();
  });

  it("cancels with the button or Escape, writing nothing; and will not save an empty value", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    const audience = await row("audience");
    await user.click(await within(audience).findByRole("button", { name: "Edit Audience" }));
    await user.clear(within(audience).getByRole("textbox"));
    await user.click(within(audience).getByRole("button", { name: "Save" }));
    expect(within(audience).getByRole("alert")).toHaveTextContent("Enter a value");
    await user.keyboard("{Escape}");
    expect(within(audience).queryByRole("textbox")).toBeNull();
    expect(within(audience).getByRole("button", { name: "Edit Audience" })).toHaveFocus();
    expect(fake.writes).toEqual([]);
    expect(within(audience).getByText("Platform engineers")).toBeInTheDocument();
  });

  it("returns focus to the pencil after Cancel and after a save", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    const audience = await row("audience");
    const pencil = () => within(audience).findByRole("button", { name: "Edit Audience" });
    await user.click(await pencil());
    await user.click(within(audience).getByRole("button", { name: "Cancel" }));
    expect(await pencil()).toHaveFocus();
    await user.click(await pencil());
    await user.type(within(audience).getByRole("textbox"), "!{Enter}");
    await waitFor(() => expect(within(audience).queryByRole("textbox")).toBeNull());
    await waitFor(async () => expect(await pencil()).toHaveFocus());
  });

  it("saves with Enter in a one-line editor", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    const audience = await row("audience");
    await user.click(await within(audience).findByRole("button", { name: "Edit Audience" }));
    await user.type(within(audience).getByRole("textbox"), "!{Enter}");
    await waitFor(() => expect(fake.writes.at(-1)?.verb).toBe("invoke"));
  });

  it("edits a property shown as a header badge, in the header, and the badge shows the new value", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    const badges = (await screen.findByTitle("Delivery")).closest(".gb-badges") as HTMLElement;
    await user.click(await within(badges).findByRole("button", { name: "Edit Delivery" }));
    const box = within(badges).getByRole("textbox", { name: "Delivery" });
    expect(box).toHaveValue("Embedded");
    await user.clear(box);
    await user.type(box, "Standalone{Enter}");
    await waitFor(() => expect(fake.writes.at(-1)?.verb).toBe("invoke"));
    expect(fake.writes.at(-1)?.action).toBe("ChangeSolutionDelivery");
    expect(fake.writes.at(-1)?.inputs).toEqual({ deliveryMode: "Standalone", solution: "sol-1" });
    expect(await within(badges).findByText("Standalone")).toBeInTheDocument();
  });

  it("puts a pencil on a title or summary property that a declared action edits, and runs that action", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(screen.queryByRole("button", { name: "Edit Name" })).toBeNull();
    await editMode(user);
    const header = (await screen.findByRole("heading", { level: 1 })).closest(
      "header",
    ) as HTMLElement;
    // The title reads name and code: only name has a declared action. The summary reads summary.
    expect(within(header).queryByRole("button", { name: "Edit Code" })).toBeNull();
    expect(within(header).getByRole("button", { name: "Edit Summary" })).toBeVisible();
    await user.click(within(header).getByRole("button", { name: "Edit Name" }));
    const box = within(header).getByRole("textbox", { name: "Name" });
    await user.clear(box);
    await user.type(box, "Renamed{Enter}");
    await waitFor(() => expect(fake.writes.at(-1)?.verb).toBe("invoke"));
    expect(fake.writes.at(-1)?.action).toBe("RenameSolution");
    expect(fake.writes.at(-1)?.inputs).toEqual({ name: "Renamed", solution: "sol-1" });
  });

  it("puts the pencil beside the text it edits, edits the summary, and leaves the text alone outside edit mode", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    const title = await screen.findByRole("heading", { level: 1 });
    const before = title.textContent;
    const summaryOf = () => document.querySelector(".gb-sum") as HTMLElement;
    const summaryBefore = summaryOf().textContent;
    await editMode(user);
    // The pencil is inside the heading and the paragraph, next to the value, not on a line of its own.
    expect(within(title).getByRole("button", { name: "Edit Name" })).toBeVisible();
    await user.click(within(summaryOf()).getByRole("button", { name: "Edit Summary" }));
    const box = within(summaryOf()).getByRole("textbox", { name: "Summary" });
    await user.clear(box);
    await user.type(box, "A new summary");
    await user.click(within(summaryOf()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fake.writes.at(-1)?.verb).toBe("invoke"));
    expect(fake.writes.at(-1)?.action).toBe("CorrectSolution");
    expect(fake.writes.at(-1)?.inputs).toEqual({ summary: "A new summary", solution: "sol-1" });
    expect(await screen.findByText("A new summary")).toBeInTheDocument();
    await editMode(user); // off again
    expect(summaryOf().textContent).toBe("A new summary");
    expect(summaryBefore).not.toBe("A new summary");
    expect(title.textContent).toBe(before);
  });

  it("offers no edit on a header badge when the host does not offer edits", async () => {
    renderBrowser({ canEdit: false });
    const badges = (await screen.findByTitle("Delivery")).closest(".gb-badges") as HTMLElement;
    expect(within(badges).queryByRole("button")).toBeNull();
  });

  it("shows no edit control until edit mode is turned on, and hides them again when it is turned off", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    const audience = await row("audience");
    const toggle = await screen.findByRole("button", { name: "Edit mode" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(within(audience).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit Delivery" })).toBeNull();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(within(audience).getByRole("button", { name: "Edit Audience" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Edit Delivery" })).toBeVisible();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryAllByRole("button", { name: /^Edit (?!mode)/ })).toEqual([]);
  });

  it("has no edit mode switch unless the host offers edits", async () => {
    renderBrowser({ canEdit: false });
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
  });

  it("has no edit mode switch on a page with nothing a declared action can edit", async () => {
    window.location.hash = "#/explore/other/Note/n-1";
    renderBrowser({ canEdit: true });
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
  });

  it("keeps edit mode on when the reader opens another node", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    window.location.hash = "#/explore/catalog/Solution/sol-2";
    await screen.findByRole("heading", { level: 1, name: /Solution|S-022|Lumen|Datamap/ });
    expect(await screen.findByRole("button", { name: "Edit mode" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("opens a popup form with every property the action changes, started from their values, and sends them in one invoke", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    const caveat = await row("caveat");
    await user.click(await within(caveat).findByRole("button", { name: "Edit Caveat" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("textbox", { name: /Caveat/ })).toHaveValue("");
    const cost = within(dialog).getByRole("textbox", { name: /Cost/ });
    expect(cost).toHaveValue("1234567.50");
    await user.type(within(dialog).getByRole("textbox", { name: /Caveat/ }), "Beta only");
    await user.clear(cost);
    await user.type(cost, "99.00");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(fake.writes.map((w) => `${w.verb} ${w.action}`)).toEqual([
      "validate SetCaveatAndCost",
      "invoke SetCaveatAndCost",
    ]);
    expect(fake.writes[1]?.inputs).toEqual({
      caveat: "Beta only",
      cost: "99.00",
      solution: "sol-1",
    });
    expect(await within(await row("caveat")).findByText("Beta only")).toBeInTheDocument();
  });

  it("will not send a form with a required field empty, and cancels with Escape", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await editMode(user);
    await user.click(
      await within(await row("caveat")).findByRole("button", { name: "Edit Caveat" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Caveat: enter a value.");
    expect(fake.writes).toEqual([]);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fake.writes).toEqual([]);
    expect(within(await row("caveat")).getByRole("button", { name: "Edit Caveat" })).toHaveFocus();
  });

  it("shows why a form was refused and keeps it open", async () => {
    const user = userEvent.setup();
    fake.invalid = "cost is not allowed";
    renderBrowser({ canEdit: true });
    await editMode(user);
    await user.click(
      await within(await row("caveat")).findByRole("button", { name: "Edit Caveat" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox", { name: /Caveat/ }), "x");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("cost is not allowed");
    expect(fake.writes.map((w) => w.verb)).toEqual(["validate"]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
