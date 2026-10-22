// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// The keyboard across both modes (SD-013, Keyboard) on the dev host: `/` is find, Ctrl or Cmd+K opens the
// palette anywhere, `?` opens one help listing both modes' keys, the digits are Operate's. The help and the
// palette pass axe in both modes and both colour schemes.

const MODES = [
  {
    name: "explore",
    hash: "#/explore/catalog",
    ready: (p: Page) => expect(p.getByRole("search")).toBeVisible(),
  },
  {
    name: "operate",
    hash: "#/operate/catalog/model",
    ready: (p: Page) => expect(p.getByRole("tablist", { name: "Areas" })).toBeVisible(),
  },
] as const;

const HELP = "Arras · Keyboard shortcuts";

for (const m of MODES) {
  test(`${m.name}: ? opens one help dialog headed with the brand and listing both modes' keys`, async ({
    page,
  }) => {
    await page.goto(`/${m.hash}`);
    await m.ready(page);
    await page.keyboard.press("?");
    const dialog = page.getByRole("dialog", { name: HELP });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
    await expect(dialog.getByRole("heading", { level: 2 })).toHaveText(HELP);
    for (const section of ["Anywhere", "Explore", "Operate"])
      await expect(dialog.getByRole("region", { name: section })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test(`${m.name}: Ctrl or Cmd+K opens the command palette`, async ({ page }) => {
    await page.goto(`/${m.hash}`);
    await m.ready(page);
    await page.keyboard.press("ControlOrMeta+k");
    await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`${m.name}: the help dialog has no WCAG A/AA violations, ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(`/${m.hash}`);
      await m.ready(page);
      await page.keyboard.press("?");
      await expect(page.getByRole("dialog", { name: HELP })).toBeVisible();
      await expectClean(page);
    });

    test(`${m.name}: the command palette has no WCAG A/AA violations, ${scheme}`, async ({
      page,
    }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(`/${m.hash}`);
      await m.ready(page);
      await page.keyboard.press("ControlOrMeta+k");
      const dialog = page.getByRole("dialog", { name: "Command palette" });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole("option").first()).toBeVisible();
      await expectClean(page);
    });
  }
}

async function expectClean(page: Page) {
  const r = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(r.passes.length).toBeGreaterThan(0);
  const found = r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }));
  expect(found, JSON.stringify(found)).toEqual([]);
  // axe cannot compute the background of a `<kbd>` drawn with a border: its contrast is "needs review"
  // (a11y.spec.ts); it is the same tokens as the text beside it. Anything else it cannot decide fails.
  const review = r.incomplete
    .filter((v) => !(v.id === "color-contrast" && v.nodes.every((n) => /^<kbd\b/.test(n.html))))
    .map((v) => v.id);
  expect(review).toEqual([]);
}

test("explore: / focuses the search box", async ({ page }) => {
  await page.goto("/#/explore/catalog");
  const box = page.getByRole("search").getByRole("textbox");
  await expect(box).toBeVisible();
  await page.keyboard.press("/");
  await expect(box).toBeFocused();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("operate: / opens the command palette", async ({ page }) => {
  await page.goto("/#/operate/catalog/model");
  await expect(page.getByRole("tablist", { name: "Areas" })).toBeVisible();
  await page.keyboard.press("/");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
});

test("the digits switch Operate's areas and do nothing in Explore", async ({ page }) => {
  await page.goto("/#/explore/catalog");
  await expect(page.getByRole("search")).toBeVisible();
  await page.keyboard.press("3");
  await expect(page).toHaveURL(/#\/explore\/catalog$/);
  await page.getByRole("button", { name: "Operate" }).click();
  await expect(page.getByTestId("console-header")).toBeVisible();
  await page.keyboard.press("3");
  await expect(page.getByRole("tab", { name: "Entities" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("a plain key is not taken while typing in the search box", async ({ page }) => {
  await page.goto("/#/explore/catalog");
  const box = page.getByRole("search").getByRole("textbox");
  await box.click();
  await page.keyboard.type("a?/3");
  await expect(box).toHaveValue("a?/3");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("the single-key switch survives a switch of mode", async ({ page }) => {
  await page.goto("/#/operate/catalog/model");
  await expect(page.getByTestId("console-header")).toBeVisible();
  await page.keyboard.press("?");
  await page.getByRole("switch", { name: "Single-key shortcuts" }).uncheck();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Explore" }).click();
  await expect(page.getByRole("search")).toBeVisible();
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
});
