// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Request, test } from "@playwright/test";
import { ensureHub } from "./gb-fixtures";

// Retire on an entity page (FR-68) through the whole stack: the built UI on the dev host as alice.
// The sandbox's catalog declares RetireUseCase (a delete of a use case by a ref input), so a use case
// with its solutions is what is retired. Each run makes its own use case; the sandbox has no reset.

const AXE_CASE = "uc-retire-axe";
const stamp = Date.now().toString(36);
const RETIRE_CASE = `uc-retire-${stamp}`;

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: "http://127.0.0.1:8123" });
  await ensureHub(request, AXE_CASE, 1, "Retire axe");
  await ensureHub(request, RETIRE_CASE, 2, "Retire me");
  await request.dispose();
});

async function as(page: Page, person: string, hash: string) {
  await page.goto(`/${hash}`);
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

/** Edit mode on, then the entity menu open. */
async function openMenu(page: Page) {
  await page.getByRole("button", { name: "Edit mode" }).click();
  await page.getByRole("button", { name: "Entity menu" }).click();
  await expect(page.getByRole("menu")).toBeVisible();
}

test("Retire validates then invokes as alice, opens the list and Back does not return to the retired page", async ({
  page,
}) => {
  const writes: { method: string; path: string; body: unknown }[] = [];
  page.on("request", (r: Request) => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith("/api/operate") && r.method() === "POST")
      writes.push({ method: r.method(), path, body: r.postDataJSON() });
  });
  await as(page, "alice", "#/explore/catalog");
  await page.evaluate((key) => {
    window.location.hash = `#/explore/catalog/UseCase/${key}`;
  }, RETIRE_CASE);
  await expect(page.getByRole("heading", { level: 1, name: /Hub use case 2/ })).toBeVisible();
  await openMenu(page);
  await page.getByRole("menuitem", { name: "Retire" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Addressed by (2)");
  await expect(dialog).toContainText("cannot be used again");
  expect(writes.filter((w) => /\/actions\//.test(w.path))).toEqual([]);
  await dialog.getByRole("button", { name: "Retire" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(/#\/explore\/catalog\/UseCase$/);
  const actions = writes.filter((w) => /\/actions\//.test(w.path));
  expect(actions.map((w) => w.path)).toEqual([
    "/api/operate/actions/catalog/RetireUseCase/validate",
    "/api/operate/actions/catalog/RetireUseCase/invoke",
  ]);
  expect(actions.map((w) => (w.body as { inputs: unknown }).inputs)).toEqual([
    { useCase: RETIRE_CASE },
    { useCase: RETIRE_CASE },
  ]);
  // Nothing else of the operate surface was written to.
  expect(writes.filter((w) => !/\/actions\//.test(w.path))).toEqual([]);
  // The list no longer shows it, and Back is the entry before the retired page.
  await expect(page.getByRole("heading", { level: 2, name: "Use cases" })).toBeVisible();
  await expect(page.locator("a.gb-hit", { hasText: "Hub use case 2" })).toHaveCount(0);
  await page.goBack();
  expect(new URL(page.url()).hash).toBe("#/explore/catalog");
  await expect(page.getByRole("heading", { level: 1, name: /Hub use case 2/ })).toHaveCount(0);
});

test("a viewer who is not an operator has no menu", async ({ page }) => {
  await as(page, "carol", `#/explore/catalog/UseCase/${AXE_CASE}`);
  await expect(page.getByRole("heading", { level: 1, name: /Hub use case 1/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit mode" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Entity menu" })).toHaveCount(0);
});

const SIZES = [
  { width: 1280, height: 900 },
  { width: 390, height: 844 },
] as const;

for (const scheme of ["light", "dark"] as const) {
  for (const viewport of SIZES) {
    test.describe(`axe, ${scheme}, ${viewport.width}`, () => {
      test.use({ colorScheme: scheme, viewport });

      const audit = async (page: Page) => {
        const r = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        const found = r.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
        }));
        expect(found, JSON.stringify(found, null, 2)).toEqual([]);
      };

      test("the entity menu and the confirmation pass axe", async ({ page }) => {
        await as(page, "alice", `#/explore/catalog/UseCase/${AXE_CASE}`);
        await expect(page.getByRole("heading", { level: 1, name: /Hub use case 1/ })).toBeVisible();
        await openMenu(page);
        await expect(page.getByRole("menuitem", { name: "Retire" })).toBeFocused();
        await audit(page);
        await page.getByRole("menuitem", { name: "Retire" }).click();
        await expect(page.getByRole("dialog")).toBeVisible();
        await audit(page);
        await page.keyboard.press("Escape");
        await expect(page.getByRole("button", { name: "Entity menu" })).toBeFocused();
      });
    });
  }
}
