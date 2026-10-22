// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Request, test } from "@playwright/test";
import { ORIGIN } from "./acceptance";
import { ensureHub } from "./gb-fixtures";

// New on a type's list (FR-67) through the whole stack: the built UI on the dev host as alice. The
// sandbox's catalog declares AddSolution (a create of a solution and a link to a use case), so the
// Solutions list offers New solution in edit mode. Each run makes its own use case and solution; the
// sandbox has no reset.

const stamp = Date.now().toString(36);
const CASE = `uc-new-${stamp}`;
const CASE_NAME = "Hub use case 1";
const SOLUTION = `sol-new-${stamp}`;

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: ORIGIN });
  await ensureHub(request, CASE, 1, "New target");
  await request.dispose();
});

async function as(page: Page, person: string, hash: string) {
  await page.goto(`/${hash}`);
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

/** Edit mode on, then New solution pressed: the form. */
async function openForm(page: Page) {
  await page.getByRole("button", { name: "Edit mode" }).click();
  await page.getByRole("button", { name: "New solution" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // The catalog also declares DraftSolution (a name only, listed first): this spec is about the
  // action that creates and links, so it is chosen.
  await dialog.getByRole("combobox", { name: "Create with" }).selectOption("AddSolution");
  return dialog;
}

/** Pick the run's use case in the picker: narrow the list by its key, then choose it. */
async function pickCase(page: Page) {
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: /^Filter or search use cases/ }).fill(CASE);
  const box = dialog.getByRole("combobox", { name: /^useCase/ });
  await expect(box.getByRole("option", { name: CASE_NAME })).toHaveCount(1);
  await box.selectOption({ label: CASE_NAME });
}

test("New validates then invokes as alice, opens the created solution and writes nothing else", async ({
  page,
}) => {
  const writes: { method: string; path: string; body: unknown }[] = [];
  page.on("request", (r: Request) => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith("/api/operate") && r.method() === "POST")
      writes.push({ method: r.method(), path, body: r.postDataJSON() });
  });
  await as(page, "alice", "#/explore/catalog/Solution");
  await expect(page.getByRole("heading", { level: 2, name: "Solutions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New solution" })).toHaveCount(0);
  const dialog = await openForm(page);
  await dialog.getByRole("textbox", { name: /^code/ }).fill(SOLUTION);
  await dialog.getByRole("textbox", { name: /^name/ }).fill("Made from New");
  await pickCase(page);
  await dialog.getByRole("button", { name: "Validate" }).click();
  await expect(dialog.getByTestId("effects-summary")).toBeVisible();
  expect(writes.filter((w) => /\/invoke$/.test(w.path))).toEqual([]);
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`#/explore/catalog/Solution/${SOLUTION}$`));
  const title = page.getByRole("heading", { level: 1, name: /Made from New/ });
  await expect(title).toBeVisible();
  await expect(title).toBeFocused();
  const actions = writes.filter((w) => /\/actions\//.test(w.path));
  expect(actions.at(-1)?.path).toBe("/api/operate/actions/catalog/AddSolution/invoke");
  expect(actions.filter((w) => /\/invoke$/.test(w.path))).toHaveLength(1);
  expect(actions.filter((w) => /\/validate$/.test(w.path)).length + 1).toBe(actions.length);
  expect(
    (actions[actions.length - 1]?.body as { inputs: unknown } | undefined)?.inputs,
  ).toMatchObject({
    code: SOLUTION,
    name: "Made from New",
    useCase: CASE,
  });
  // Nothing else of the operate surface was written to.
  expect(writes.filter((w) => !/\/actions\//.test(w.path))).toEqual([]);
  // The page is bookmarkable, and Back is the list the reader was on.
  await page.goBack();
  expect(new URL(page.url()).hash).toBe("#/explore/catalog/Solution");
});

test("a viewer who is not an operator has no lock and no New", async ({ page }) => {
  await as(page, "carol", "#/explore/catalog/Solution");
  await expect(page.getByRole("heading", { level: 2, name: "Solutions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit mode" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "New solution" })).toHaveCount(0);
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

      test("the list with the lock open and the New form pass axe", async ({ page }) => {
        await as(page, "alice", "#/explore/catalog/Solution");
        await expect(page.getByRole("heading", { level: 2, name: "Solutions" })).toBeVisible();
        await page.getByRole("button", { name: "Edit mode" }).click();
        await expect(page.getByRole("button", { name: "New solution" })).toBeVisible();
        await audit(page);
        await page.getByRole("button", { name: "New solution" }).click();
        const dialog = page.getByRole("dialog");
        await expect(dialog).toBeVisible();
        await dialog.getByRole("combobox", { name: "Create with" }).selectOption("AddSolution");
        await expect(dialog.getByRole("combobox", { name: /^useCase/ })).toBeVisible();
        await audit(page);
        // A validation that found problems is audited too: the messages sit at their fields.
        await dialog.getByRole("button", { name: "Validate" }).click();
        await expect(dialog.getByText(/Expected a value \(required\)/).first()).toBeVisible();
        await audit(page);
        await page.keyboard.press("Escape");
        await expect(page.getByRole("button", { name: "New solution" })).toBeFocused();
      });
    });
  }
}
