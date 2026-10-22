// SPDX-License-Identifier: MIT OR Apache-2.0
// The header's edit pencils on an ontology unlike the catalog (`people`, browserFake's second
// module): what a title or summary template may do for any module.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { addPeople, type BrowserFake, stageBrowser } from "./browserFake";
import { renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
  addPeople(fake);
});
afterEach(() => {
  window.location.hash = "";
});

const open = async (type: string, key: string, canEdit = true) => {
  window.location.hash = `#/explore/people/${type}/${key}`;
  renderBrowser({ canEdit });
  const title = await screen.findByRole("heading", { level: 1 });
  const header = title.closest("header") as HTMLElement;
  return { title, header, user: userEvent.setup() };
};
const unlock = (user: ReturnType<typeof userEvent.setup>) =>
  screen.findByRole("button", { name: "Edit mode" }).then((b) => user.click(b));
const pencils = () => screen.queryAllByRole("button", { name: /^Edit (?!mode)/ });

describe("header pencils on a module that is not the catalog", () => {
  it("gives each property of a title its own pencil and its own action", async () => {
    const { title, header, user } = await open("Contact", "c-1");
    expect(title).toHaveTextContent("Ada Lovelace");
    await unlock(user);
    expect(within(title).getByRole("button", { name: "Edit Given" })).toBeVisible();
    await user.click(within(title).getByRole("button", { name: "Edit Family" }));
    const box = within(header).getByRole("textbox", { name: "Family" });
    await user.clear(box);
    await user.type(box, "Byron{Enter}");
    await waitFor(() => expect(fake.writes.at(-1)?.verb).toBe("invoke"));
    expect(fake.writes.at(-1)?.action).toBe("SetContactFamily");
    expect(fake.writes.at(-1)?.inputs).toEqual({ family: "Byron", contact: "c-1" });
    expect(await screen.findByRole("heading", { level: 1, name: /Ada Byron/ })).toBeVisible();
  });

  it("offers one pencil, opening one dialog, where a form changes both properties of a title", async () => {
    const { title, user } = await open("Place", "pl-1");
    await unlock(user);
    expect(within(title).getAllByRole("button", { name: /^Edit / })).toHaveLength(1);
    await user.click(within(title).getByRole("button", { name: /^Edit / }));
    expect(await screen.findByRole("dialog")).toBeVisible();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  it("puts one pencil on a property that is both a badge and in the title, and shows an empty summary as not set", async () => {
    const { header, user } = await open("Ticket", "t-1");
    expect(header.querySelector(".gb-sum")).toBeNull();
    expect(within(header).queryByText("Not set")).toBeNull();
    await unlock(user);
    expect(screen.getAllByRole("button", { name: "Edit Status" })).toHaveLength(1);
    const summary = header.querySelector(".gb-sum") as HTMLElement;
    expect(within(summary).getByText("Not set")).toBeVisible();
    await user.click(within(summary).getByRole("button", { name: "Edit Body" }));
    await user.type(within(summary).getByRole("textbox", { name: "Body" }), "Broken link{Enter}");
    await waitFor(() => expect(fake.writes.at(-1)?.verb).toBe("invoke"));
    expect(fake.writes.at(-1)?.inputs).toEqual({ body: "Broken link", ticket: "t-1" });
    expect(await within(header).findByText("Broken link")).toBeVisible();
  });

  it("opens the summary editor without invalid DOM nesting", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const { header, user } = await open("Ticket", "t-1");
      await unlock(user);
      const summary = header.querySelector(".gb-sum") as HTMLElement;
      await user.click(within(summary).getByRole("button", { name: "Edit Body" }));
      expect(within(summary).getByRole("textbox", { name: "Body" })).toBeVisible();
      expect(summary.tagName).toBe("DIV");
      expect(error.mock.calls.flat().join(" ")).not.toMatch(
        /cannot be a descendant|cannot contain a nested/,
      );
    } finally {
      error.mockRestore();
    }
  });

  it("never edits a title that is the key, but edits the summary beside it", async () => {
    const { title, user } = await open("Handle", "h-1");
    await unlock(user);
    expect(within(title).queryByRole("button")).toBeNull();
    expect(screen.getAllByRole("button", { name: "Edit About" })).toHaveLength(1);
  });

  it("offers no pencil where the host offers no edits", async () => {
    await open("Contact", "c-1", false);
    expect(pencils()).toEqual([]);
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
  });
});
