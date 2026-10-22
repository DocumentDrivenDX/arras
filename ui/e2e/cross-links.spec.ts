// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { ensureUseCase } from "./gb-fixtures";

// Cross-mode links (FR-71) on the dev host, as the sandbox's people: alice is an operator and is
// offered Operate; carol is not, and her page carries no link into it.

const CODE = "uc-xlinks";
const ORIGIN = "http://127.0.0.1:8123";
const NODE = `#/explore/catalog/UseCase/${CODE}`;

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: ORIGIN });
  await ensureUseCase(request, CODE, "Cross-links use case", "links");
  await request.dispose();
});

async function as(page: Page, person: string, hash: string) {
  await page.goto(`/${hash}`);
  await page.getByTestId("sandbox-toolbar").getByLabel("Person").selectOption(person);
  await expect(page.getByTestId("sandbox-toolbar").getByLabel("Person")).toHaveValue(person);
}

const hash = (page: Page) => new URL(page.url()).hash;

test("from a node page a change group opens Operate's receipt, and Back returns to Explore", async ({
  page,
}) => {
  await as(page, "alice", NODE);
  await expect(page.getByRole("heading", { level: 1, name: "Cross-links use case" })).toBeVisible();
  await page
    .getByTestId("gb-open-in-operate")
    .getByRole("link", { name: /History of/ })
    .click();
  await expect(page.getByTestId("console-header")).toBeVisible();
  await expect.poll(() => hash(page)).toBe(`#/operate/catalog/changes/catalog.UseCase/${CODE}`);
  // the entity's change group opens its receipt in Changes
  await page
    .getByTestId("change-row")
    .first()
    .getByRole("link", { name: /Open receipt for group/ })
    .click();
  await expect.poll(() => hash(page)).toMatch(/^#\/operate\/catalog\/changes\?group=g-\d+$/);
  await expect(page.getByTestId("change-row")).toHaveCount(1);
  // Back leaves the receipt, then Operate, for the Explore page it came from
  await page.goBack();
  await expect.poll(() => hash(page)).toBe(`#/operate/catalog/changes/catalog.UseCase/${CODE}`);
  await page.goBack();
  await expect.poll(() => hash(page)).toBe(NODE);
  await expect(page.getByRole("heading", { level: 1, name: "Cross-links use case" })).toBeVisible();
});

test("Operate's context bar leads back to the Explore page", async ({ page }) => {
  await as(page, "alice", `#/operate/catalog/entities/catalog.UseCase/${CODE}`);
  const bar = page.getByRole("navigation", { name: "Entity context" });
  await bar.getByRole("link", { name: /View in Explore/ }).click();
  await expect.poll(() => hash(page)).toBe(NODE);
  await expect(page.getByRole("heading", { level: 1, name: "Cross-links use case" })).toBeVisible();
});

test("carol's page carries no link into Operate", async ({ page }) => {
  await as(page, "carol", NODE);
  await expect(page.getByRole("heading", { level: 1, name: "Cross-links use case" })).toBeVisible();
  await expect(page.getByTestId("gb-open-in-operate")).toHaveCount(0);
  await expect(page.locator('a[href*="operate"]')).toHaveCount(0);
  await expect(page.getByRole("link", { name: /operate/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /operate/i })).toHaveCount(0);
});

const SCREENS: { name: string; hash: string; ready: (p: Page) => Promise<void> }[] = [
  {
    name: "a node page's Open in Operate",
    hash: NODE,
    ready: (p) => expect(p.getByTestId("gb-open-in-operate")).toBeVisible(),
  },
  {
    name: "a type list's Model link",
    hash: "#/explore/catalog/UseCase",
    ready: (p) => expect(p.getByRole("link", { name: /Model of/ })).toBeVisible(),
  },
  {
    name: "Operate's Changes rows",
    hash: `#/operate/catalog/changes/catalog.UseCase/${CODE}`,
    ready: async (p) => {
      // the entity's context bar sits above the rows
      await expect(
        p
          .getByRole("navigation", { name: "Entity context" })
          .getByRole("link", { name: /View in Explore/ }),
      ).toBeVisible();
      await expect(
        p
          .getByTestId("change-row")
          .first()
          .getByRole("link", { name: /View in Explore/ }),
      ).toBeVisible();
    },
  },
  {
    name: "Operate's model cards",
    hash: "#/operate/catalog/model",
    ready: (p) =>
      expect(
        p.getByTestId("type-catalog.UseCase").getByRole("link", { name: /View in Explore/ }),
      ).toBeVisible(),
  },
];

for (const scheme of ["light", "dark"] as const) {
  test.describe(`axe, ${scheme}`, () => {
    test.use({ colorScheme: scheme, viewport: { width: 1280, height: 2400 } });
    for (const s of SCREENS) {
      test(`${s.name}: no WCAG A/AA violation`, async ({ page }) => {
        await as(page, "alice", s.hash);
        await s.ready(page);
        const r = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        const found = r.violations.map((v) => ({
          id: v.id,
          help: v.help,
          nodes: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
        }));
        expect(found, JSON.stringify(found, null, 2)).toEqual([]);
        const review = r.incomplete.flatMap((v) =>
          v.nodes
            .filter((n) => !(v.id === "color-contrast" && /^<(text|kbd)\b/.test(n.html)))
            .map((n) => `${v.id}: ${n.html.slice(0, 140)}`),
        );
        expect(review, review.join("\n")).toEqual([]);
      });
    }
  });
}
