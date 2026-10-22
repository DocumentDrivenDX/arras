// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Request, test } from "@playwright/test";
import { ensureHub } from "./gb-fixtures";

// Entity actions on an entity page (FR-70) through the whole stack: the built UI on the dev host as
// alice. The sandbox's catalog declares AddSolution (a create and a link, taking a use case), which is an
// entity action of a use case. Each run makes its own use cases; the sandbox has no reset.

const stamp = Date.now().toString(36);
// The keys avoid the word "action": the Operate spec finds its Action filter by label, and a key in the Changes list would match it too.
const AXE_CASE = "uc-kit-axe";
const RUN_CASE = `uc-kit-${stamp}`;

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: "http://127.0.0.1:8123" });
  await ensureHub(request, AXE_CASE, 1, "Kit axe");
  await ensureHub(request, RUN_CASE, 1, "Kit run");
  await request.dispose();
});

async function as(page: Page, person: string, hash: string) {
  await page.goto(`/${hash}`);
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

async function openMenu(page: Page) {
  await page.getByRole("button", { name: "Edit mode" }).click();
  await page.getByRole("button", { name: "Entity menu" }).click();
  await expect(page.getByRole("menu")).toBeVisible();
}

test("AddSolution from a use case validates then invokes as alice and writes nothing else", async ({
  page,
}) => {
  const writes: { path: string; body: unknown }[] = [];
  page.on("request", (r: Request) => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith("/api/operate") && r.method() === "POST")
      writes.push({ path, body: r.postDataJSON() });
  });
  await as(page, "alice", `#/explore/catalog/UseCase/${RUN_CASE}`);
  await expect(page.getByRole("heading", { level: 1, name: /Hub use case 1/ })).toBeVisible();
  await openMenu(page);
  await expect(page.getByRole("menuitem")).toHaveText([/^Retire/, /^AddSolution/]);
  await page.getByRole("menuitem", { name: /^AddSolution/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("textbox", { name: /useCase/ })).toHaveCount(0);
  const code = `${RUN_CASE}-new`;
  await dialog.getByRole("textbox", { name: /^code/ }).fill(code);
  await dialog.getByRole("textbox", { name: /^name/ }).fill("Added from the page");
  await dialog.getByRole("button", { name: "Validate" }).click();
  await expect(dialog.getByTestId("effects-summary")).toBeVisible();
  await dialog.getByRole("button", { name: "Apply" }).click();
  const receipt = dialog.getByTestId("receipt-summary");
  await expect(receipt).toBeFocused();
  await expect(receipt.getByRole("link", { name: new RegExp(`Solution ${code}`) })).toBeVisible();
  const actions = writes.filter((w) => /\/actions\//.test(w.path));
  expect(new Set(actions.map((w) => w.path))).toEqual(
    new Set([
      "/api/operate/actions/catalog/AddSolution/validate",
      "/api/operate/actions/catalog/AddSolution/invoke",
    ]),
  );
  expect(actions.filter((w) => w.path.endsWith("/invoke"))).toHaveLength(1);
  expect(writes.filter((w) => !/\/actions\//.test(w.path))).toEqual([]);
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("button", { name: "Entity menu" })).toBeFocused();
  await expect(page.getByRole("link", { name: /Added from the page/ }).first()).toBeVisible();
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

      test("the menu with its actions and the dialog pass axe", async ({ page }) => {
        await as(page, "alice", `#/explore/catalog/UseCase/${AXE_CASE}`);
        await expect(page.getByRole("heading", { level: 1, name: /Hub use case 1/ })).toBeVisible();
        await openMenu(page);
        await expect(page.getByRole("menuitem", { name: /^AddSolution/ })).toBeVisible();
        await audit(page);
        await page.getByRole("menuitem", { name: /^AddSolution/ }).click();
        const dialog = page.getByRole("dialog");
        await expect(dialog).toBeVisible();
        await audit(page);
        await dialog.getByRole("textbox", { name: /^code/ }).fill("axe-sol");
        await dialog.getByRole("textbox", { name: /^name/ }).fill("Axe solution");
        await dialog.getByRole("button", { name: "Validate" }).click();
        await expect(dialog.getByTestId("effects-summary")).toBeVisible();
        await audit(page);
        await page.keyboard.press("Escape");
        await expect(page.getByRole("button", { name: "Entity menu" })).toBeFocused();
      });
    });
  }
}
