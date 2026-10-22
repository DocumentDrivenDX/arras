// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  AREA_KEYS,
  GROUP_MODES,
  GROUP_TITLES,
  isTyping,
  keyIntent,
  SHORTCUTS,
  type Shortcut,
  shortcutForKey,
  shortcutGroups,
  shortcutSections,
  worksIn,
} from "../lib/shortcuts";
import { ArrasApp } from "../shell";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { seedCatalog, stage } from "./fake";
import { qc, renderConsole } from "./render";

// Keyboard shortcuts (FEAT-010, OPR-18; SD-013, Keyboard): one table drives the handlers and the help
// for both modes; the `?` help, the Single-key shortcuts switch, the guards, the Actions mode tablist,
// the focus-visible rules.
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "#/catalog/model";
  seedCatalog(stage());
});
afterEach(() => {
  window.location.hash = "";
});

const selected = () =>
  within(screen.getByRole("tablist", { name: "Areas" })).getByRole("tab", { selected: true })
    .textContent;
const HELP = /Keyboard shortcuts/;
const open = async (user: ReturnType<typeof userEvent.setup>) => {
  renderConsole({ hashRouting: true });
  await screen.findByTestId("schema");
  await user.keyboard("?");
  return screen.findByRole("dialog", { name: HELP });
};
const key = (
  k: string,
  over: Partial<KeyboardEvent> = {},
  target: EventTarget | null = document.body,
) => ({
  key: k,
  metaKey: false,
  ctrlKey: false,
  altKey: false,
  target,
  ...over,
});
const MODES = ["explore", "operate"] as const;

/** What the table says a plain key means in a mode: nothing where the entry does not work. */
function checkKey(s: Shortcut, k: string, mode: (typeof MODES)[number]) {
  const intent = keyIntent(key(k), mode);
  if (!worksIn(s, mode)) {
    expect(intent, `${k} in ${mode}`).toBeNull();
    expect(shortcutForKey(k, mode)?.id).not.toBe(s.id);
    return;
  }
  expect(shortcutForKey(k, mode)?.id).toBe(s.id);
  const want = { help: { kind: "help" }, find: { kind: "find" } }[s.id] ?? {
    kind: "area",
    index: AREA_KEYS.indexOf(k as never),
  };
  expect(intent).toEqual(want);
}

describe("the shortcut table", () => {
  it("has unique ids, a title and a mode for every group it uses, and each entry has its group's mode", () => {
    expect(new Set(SHORTCUTS.map((s) => s.id)).size).toBe(SHORTCUTS.length);
    for (const s of SHORTCUTS) {
      expect(Object.keys(GROUP_TITLES)).toContain(s.group);
      expect(s.mode).toBe(GROUP_MODES[s.group]);
      expect(["both", "operate", "explore"]).toContain(s.mode);
    }
  });

  it("every key the table lists means what the table says, once in each mode it works in and in none other", () => {
    for (const s of SHORTCUTS.filter((x) => x.keys.length > 0)) {
      expect(s.single).toBe(true);
      for (const k of s.keys) for (const mode of MODES) checkKey(s, k, mode);
    }
  });

  it("`/` and `?` mean the same in both modes; the digits are Operate's alone; Ctrl or Cmd+K is the palette in both", () => {
    for (const mode of MODES) {
      expect(keyIntent(key("/"), mode)).toEqual({ kind: "find" });
      expect(keyIntent(key("?"), mode)).toEqual({ kind: "help" });
      expect(keyIntent(key("k", { ctrlKey: true }), mode)).toEqual({ kind: "palette" });
      expect(keyIntent(key("K", { metaKey: true }), mode)).toEqual({ kind: "palette" });
    }
    for (const d of AREA_KEYS) {
      expect(keyIntent(key(d), "explore")).toBeNull();
      expect(keyIntent(key(d), "operate")).toEqual({ kind: "area", index: AREA_KEYS.indexOf(d) });
    }
  });

  it("the handler is the table: a key it does not list does nothing, and a modifier turns a plain key off", () => {
    for (const mode of MODES) {
      expect(keyIntent(key("x"), mode)).toBeNull();
      expect(keyIntent(key("k"), mode)).toBeNull();
      expect(keyIntent(key("3", { metaKey: true }), mode)).toBeNull();
      expect(keyIntent(key("?", { ctrlKey: true }), mode)).toBeNull();
      expect(keyIntent(key("/", { altKey: true }), mode)).toBeNull();
      expect(keyIntent(key("k", { ctrlKey: true, altKey: true }), mode)).toBeNull();
    }
  });

  it("a plain key never fires in a field, in a contenteditable, or with a dialog open", () => {
    const plain = SHORTCUTS.filter((s) => s.keys.length > 0).flatMap((s) => [...s.keys]);
    for (const mode of MODES) {
      for (const k of plain) {
        for (const tag of ["input", "textarea", "select"]) {
          const el = document.body.appendChild(document.createElement(tag));
          expect(keyIntent(key(k, {}, el), mode)).toBeNull();
          el.remove();
        }
        const ce = document.body.appendChild(document.createElement("div"));
        Object.defineProperty(ce, "isContentEditable", { value: true });
        expect(isTyping(ce)).toBe(true);
        expect(keyIntent(key(k, {}, ce), mode)).toBeNull();
        ce.remove();
        const dlg = document.body.appendChild(document.createElement("div"));
        dlg.setAttribute("role", "dialog");
        dlg.setAttribute("aria-modal", "true");
        expect(keyIntent(key(k), mode)).toBeNull();
        expect(keyIntent(key("k", { ctrlKey: true }), mode)).toBeNull();
        dlg.remove();
      }
    }
    // the palette chord still works from a field when no dialog is open
    const input = document.body.appendChild(document.createElement("input"));
    expect(keyIntent(key("k", { ctrlKey: true }, input), "explore")).toEqual({ kind: "palette" });
    input.remove();
  });

  it("the help's sections hold every shortcut once: Anywhere, Explore, and Operate only when it is offered", () => {
    const ids = (operate: boolean) =>
      shortcutSections(operate).flatMap((s) =>
        s.groups.flatMap((g) => g.items.map((i: Shortcut) => i.id)),
      );
    expect(ids(true).sort()).toEqual(SHORTCUTS.map((s) => s.id).sort());
    expect(shortcutSections(true).map((s) => s.title)).toEqual(["Anywhere", "Explore", "Operate"]);
    expect(shortcutSections(false).map((s) => s.title)).toEqual(["Anywhere", "Explore"]);
    for (const s of shortcutSections(false)) expect(s.mode).not.toBe("operate");
    expect(
      shortcutGroups("explore").every((g) => g.items.every((i) => worksIn(i, "explore"))),
    ).toBe(true);
  });
});

describe("the shortcuts help of a standalone console", () => {
  it("? opens a labelled modal dialog with focus inside; the header button opens it too", async () => {
    const user = userEvent.setup();
    const dialog = await open(user);
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: HELP }));
    expect(await screen.findByRole("dialog", { name: HELP })).toBeInTheDocument();
  });

  it("lists every shortcut of the table, in the section and group the table gives it", async () => {
    const user = userEvent.setup();
    const dialog = await open(user);
    for (const section of shortcutSections(true)) {
      const region = within(dialog).getByRole("region", { name: section.title });
      for (const g of section.groups) {
        for (const s of g.items) {
          const row = region.querySelector(`[data-shortcut="${s.id}"]`);
          expect(row, s.id).not.toBeNull();
          expect(row?.textContent).toContain(s.label);
        }
      }
    }
    expect(dialog.querySelectorAll("[data-shortcut]")).toHaveLength(SHORTCUTS.length);
  });

  it("keeps Tab inside, and Escape closes it and returns the focus to where it was", async () => {
    const user = userEvent.setup();
    renderConsole({ hashRouting: true });
    await screen.findByTestId("schema");
    const opener = screen.getByRole("button", { name: HELP });
    opener.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog");
    const inside = () => dialog.contains(document.activeElement);
    for (let i = 0; i < 6; i++) {
      await user.tab();
      expect(inside()).toBe(true);
    }
    for (let i = 0; i < 6; i++) {
      await user.tab({ shift: true });
      expect(inside()).toBe(true);
    }
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });
});

describe("the Single-key shortcuts switch", () => {
  it("is on by default; off, the digits, ? and / do nothing, the button still opens the help", async () => {
    const user = userEvent.setup();
    const dialog = await open(user);
    const sw = within(dialog).getByRole("switch", { name: "Single-key shortcuts" });
    expect(sw).toBeChecked();
    await user.click(sw);
    expect(sw).not.toBeChecked();
    await user.keyboard("{Escape}");
    await user.keyboard("3");
    expect(selected()).toBe("Model");
    await user.keyboard("?");
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.keyboard("/");
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: HELP }));
    const again = await screen.findByRole("dialog");
    await user.click(within(again).getByRole("switch", { name: "Single-key shortcuts" }));
    await user.keyboard("{Escape}");
    await user.keyboard("3");
    await waitFor(() => expect(selected()).toBe("Entities"));
  });

  it("an area digit is consumed: its keydown is default-prevented, as the help key's is", async () => {
    renderConsole({ hashRouting: true });
    await screen.findByTestId("schema");
    const digit = new KeyboardEvent("keydown", { key: "3", bubbles: true, cancelable: true });
    act(() => {
      document.body.dispatchEvent(digit);
    });
    expect(digit.defaultPrevented).toBe(true);
    await waitFor(() => expect(selected()).toBe("Entities"));
  });

  it("a digit does nothing while a dialog is open, and none is typed over a field", async () => {
    const user = userEvent.setup();
    await open(user);
    await user.keyboard("3");
    await user.keyboard("{Escape}");
    expect(selected()).toBe("Model");
    await user.click(screen.getByRole("tab", { name: "Query" }));
    const box = await screen.findByTestId("query-input");
    await user.click(box);
    await user.keyboard("2?");
    expect(box).toHaveValue("2?");
    expect(selected()).toBe("Query");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("the shell's keys, in both modes (SD-013, Keyboard)", () => {
  let fake: BrowserFake;
  beforeEach(() => {
    fake = stageBrowser();
    fake.mods = fake.mods.slice(0, 1);
    window.location.hash = "#/explore/catalog";
  });
  const app = (props: Parameters<typeof ArrasApp>[0] = {}) =>
    render(<ArrasApp queryClient={qc()} {...props} />);
  const explore = () => screen.findByRole("heading", { level: 1, name: "Product catalog" });
  const inAdmin = () => {
    window.location.hash = "#/operate/catalog/model";
  };
  const dialogs = () => screen.queryAllByRole("dialog");

  it("? opens one help dialog in Explore, headed with the brand and listing both modes' keys", async () => {
    const user = userEvent.setup();
    app();
    await explore();
    await screen.findByRole("group", { name: "Mode" });
    await user.keyboard("?");
    const dialog = await screen.findByRole("dialog", { name: "Arras · Keyboard shortcuts" });
    expect(dialogs()).toHaveLength(1);
    expect(within(dialog).getByRole("heading", { level: 2 })).toHaveTextContent(
      "Arras · Keyboard shortcuts",
    );
    for (const title of ["Anywhere", "Explore", "Operate"])
      expect(within(dialog).getByRole("region", { name: title })).toBeInTheDocument();
    expect(dialog.querySelectorAll("[data-shortcut]")).toHaveLength(SHORTCUTS.length);
    await user.keyboard("{Escape}");
    expect(dialogs()).toHaveLength(0);
  });

  it("? opens one help dialog in Operate too, and the header button opens the same one", async () => {
    const user = userEvent.setup();
    inAdmin();
    app();
    await screen.findByTestId("console-header");
    await user.keyboard("?");
    await screen.findByRole("dialog", { name: "Arras · Keyboard shortcuts" });
    expect(dialogs()).toHaveLength(1);
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: HELP }));
    await screen.findByRole("dialog", { name: "Arras · Keyboard shortcuts" });
    expect(dialogs()).toHaveLength(1);
  });

  it("the help takes its heading from the host's brand", async () => {
    const user = userEvent.setup();
    app({ brand: { name: "Praxis" } });
    await explore();
    await user.keyboard("?");
    expect(
      await screen.findByRole("dialog", { name: "Praxis · Keyboard shortcuts" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Arras/)).toBeNull();
  });

  it("for a viewer who is not an operator the help lists Explore's keys and says nothing of Operate", async () => {
    fake.viewerModes = ["user"];
    const user = userEvent.setup();
    app();
    await explore();
    await act(async () => undefined);
    await user.keyboard("?");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("region", { name: "Operate" })).toBeNull();
    expect(dialog.textContent).not.toMatch(/operate/i);
    expect(dialog.querySelector('[data-shortcut="area"]')).toBeNull();
    expect(dialog.querySelector('[data-shortcut="find"]')).not.toBeNull();
  });

  it("the digits switch Operate's areas and do nothing in Explore", async () => {
    const user = userEvent.setup();
    app();
    await explore();
    await screen.findByRole("group", { name: "Mode" });
    await user.keyboard("3");
    expect(window.location.hash).toBe("#/explore/catalog");
    expect(dialogs()).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Operate" }));
    await screen.findByTestId("console-header");
    await user.keyboard("3");
    await waitFor(() => expect(selected()).toBe("Entities"));
  });

  it("/ focuses Explore's search box when search is served, and opens no dialog", async () => {
    const user = userEvent.setup();
    app();
    await explore();
    const box = await screen.findByRole("textbox", { name: /Search/ });
    await user.keyboard("/");
    expect(box).toHaveFocus();
    expect(dialogs()).toHaveLength(0);
  });

  it("/ opens the palette in Explore when no search is served, and Explore's search box takes it otherwise", async () => {
    for (const t of fake.mods[0]?.entityTypes ?? [])
      for (const c of Object.values(t.capabilities)) (c as { search: string }).search = "none";
    const user = userEvent.setup();
    app();
    await explore();
    expect(screen.queryByRole("search")).toBeNull();
    await user.keyboard("/");
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    expect(dialogs()).toHaveLength(1);
  });

  it("/ opens the palette in Operate", async () => {
    const user = userEvent.setup();
    inAdmin();
    app();
    await screen.findByTestId("console-header");
    await user.keyboard("/");
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    expect(dialogs()).toHaveLength(1);
  });

  it("Ctrl+K and Cmd+K open one palette in either mode, even from the search box", async () => {
    const user = userEvent.setup();
    app();
    await explore();
    const box = await screen.findByRole("textbox", { name: /Search/ });
    await user.click(box);
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    await user.keyboard("{Control>}k{/Control}");
    expect(dialogs()).toHaveLength(1);
    await user.keyboard("{Escape}");
    expect(dialogs()).toHaveLength(0);
    expect(box).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Operate" }));
    await screen.findByTestId("console-header");
    await user.keyboard("{Meta>}k{/Meta}");
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    expect(dialogs()).toHaveLength(1);
  });

  it("no plain key fires while typing in the search box or while a dialog is open", async () => {
    const user = userEvent.setup();
    app();
    await explore();
    const box = await screen.findByRole("textbox", { name: /Search/ });
    await user.click(box);
    await user.keyboard("a?/3");
    expect(box).toHaveValue("a?/3");
    expect(dialogs()).toHaveLength(0);
    await user.keyboard("{Escape}");
    await user.click(document.body);
    await user.keyboard("?");
    await screen.findByRole("dialog");
    await user.keyboard("?");
    await user.keyboard("/");
    await user.keyboard("3");
    expect(dialogs()).toHaveLength(1);
    const help = screen.getByRole("dialog", { name: HELP });
    expect(box).not.toHaveFocus();
    expect(help.contains(document.activeElement)).toBe(true);
    await user.keyboard("{Escape}");
    await user.keyboard("{Control>}k{/Control}");
    const palette = await screen.findByRole("dialog", { name: "Command palette" });
    await user.keyboard("/");
    expect(box).not.toHaveFocus();
    expect(palette.contains(document.activeElement)).toBe(true);
    expect(dialogs()).toHaveLength(1);
  });

  it("the single-key switch turns ? and / off in Explore, and Explore's search box ignores / too", async () => {
    const user = userEvent.setup();
    app();
    const box = await screen.findByRole("textbox", { name: /Search/ });
    await user.keyboard("?");
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("switch", { name: "Single-key shortcuts" }));
    await user.keyboard("{Escape}");
    await user.keyboard("?");
    await user.keyboard("/");
    expect(dialogs()).toHaveLength(0);
    expect(box).not.toHaveFocus();
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
  });
});

describe("the Actions mode tablist", () => {
  it("moves between One and Batch with the arrow keys, Home and End", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/actions";
    renderConsole({ hashRouting: true });
    const list = await screen.findByRole("tablist", { name: "Mode" });
    const one = within(list).getByRole("tab", { name: "One" });
    const batch = within(list).getByRole("tab", { name: "Batch" });
    expect(one).toHaveAttribute("aria-selected", "true");
    one.focus();
    await user.keyboard("{ArrowRight}");
    expect(batch).toHaveFocus();
    expect(batch).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}");
    expect(one).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(batch).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowRight}");
    expect(one).toHaveFocus();
  });
});

describe("focus rings", () => {
  const css = readFileSync(join(import.meta.dirname, "..", "styles.css"), "utf8");
  it("every control gets an accent outline on :focus-visible, drawn inside tabs and the module rail", () => {
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--accent\)/);
    const inside =
      /\[role="tab"\]:focus-visible,\s*nav\[aria-label="Modules"\] button:focus-visible\s*\{([^}]*)\}/.exec(
        css,
      );
    expect(inside?.[1]).toMatch(/outline:\s*2px solid var\(--accent\)/);
    expect(inside?.[1]).toMatch(/outline-offset:\s*-2px/);
  });

  it("nothing in the console's own markup removes the outline from a tab or rail button", () => {
    for (const f of ["console/AreaTabs.tsx", "console/ModuleRail.tsx", "components/Tabs.tsx"]) {
      expect(readFileSync(join(import.meta.dirname, "..", f), "utf8"), f).not.toMatch(
        /outline-none|focus:outline-none/,
      );
    }
  });
});
