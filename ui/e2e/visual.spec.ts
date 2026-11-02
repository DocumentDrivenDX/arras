// SPDX-License-Identifier: MIT OR Apache-2.0
import { expect, type Page, test } from "@playwright/test";
import { acceptance, ORIGIN } from "./acceptance";
import { control, ensureAtlas, ensureHub, moduleNames } from "./gb-fixtures";

// Visual review (SD-011, Verification Plan 5; DESIGN-GB, Review): every screen of the design, from
// the running app, light and dark, at 1280 x 900 and 390 x 844, compared with reviewed baselines
// (e2e/__screenshots__) at a 0.5% pixel threshold. The data is the repository's example catalog
// registered as `atlas` with its declared views and seed, and a hub of 120 solutions; carol (who is
// not an operator) reads only `atlas` while these run, so the top bar has one module and no switch.
// `npm run e2e:visual:update` rewrites the baselines; each change is reviewed against the mockup in
// docs/helix/02-design/graph-browser-mockup/.

const HUB = "uc-hub-120";
const SOLUTION = "lumen-runbook-prompt";
// The use case the operator states are shot on: it is only opened, never retired or changed.
const OPS_CASE = "uc-visual-ops";

// The modules carol holds besides `atlas` while these run: the run shares one dev host, so what the
// earlier projects registered (`catalog`, `intake`) is hidden from her and given back afterwards.
let hidden: string[] = [];

test.beforeAll(async ({ playwright }) => {
  // Only this project compares screenshots, so only it needs the host's reviewed baselines (testkit/config.ts).
  if (!acceptance.baselineDir)
    throw new Error(
      "The visual project compares screenshots and needs baselineDir in createAcceptanceConfig(); " +
        "run --project=chromium --project=schema-admin --project=browser to skip it",
    );
  const request = await playwright.request.newContext({ baseURL: ORIGIN });
  await ensureAtlas(request);
  await ensureHub(request, HUB, 120, "Hub solution", "atlas");
  await ensureHub(request, OPS_CASE, 2, "Ops solution", "atlas");
  hidden = (await moduleNames(request)).filter((m) => m !== "atlas");
  for (const module of hidden) await control(request, { op: "revoke", user: "carol", module });
  await request.dispose();
});

test.afterAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: ORIGIN });
  for (const module of hidden)
    await control(request, { op: "grant", user: "carol", module, modes: ["read"] });
  await request.dispose();
});

async function open(page: Page, person: string, hash: string) {
  await page.goto(`/${hash}`);
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

/** Nothing is loading and nothing is moving: the picture and the labels are all in. */
async function settle(page: Page) {
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
}

/** What changes from run to run (who changed what, when, how current) is covered by a mask. */
const volatile = (page: Page) => [
  page.getByTestId("gb-attribution"),
  page.getByTestId("gb-freshness"),
  page.getByTestId("gb-answer-freshness"),
];

interface Shot {
  name: string;
  person?: string;
  hash: string;
  before?: (page: Page) => Promise<void>;
  ready: (page: Page) => Promise<void>;
  after?: (page: Page) => Promise<void>;
  /** Only the top bar. */
  clip?: boolean;
}

const search = (text: string) => async (p: Page) => {
  await p.getByRole("textbox", { name: /Search/ }).fill(text);
};

const SHOTS: Shot[] = [
  {
    name: "entry",
    hash: "#/explore/atlas",
    ready: (p) =>
      expect(p.getByRole("heading", { level: 1, name: "Product catalog" })).toBeVisible(),
  },
  {
    name: "type-list",
    hash: "#/explore/atlas/Product",
    ready: (p) => expect(p.locator("a.gb-hit").first()).toBeVisible(),
  },
  {
    name: "results",
    hash: "#/explore/atlas",
    before: search("lumen"),
    ready: (p) => expect(p.getByTestId("gb-status")).toBeVisible(),
  },
  {
    name: "results-not-searched",
    hash: "#/explore/atlas",
    before: async (p) => {
      await control(p.request, {
        op: "search",
        backend: "memory",
        type: "atlas.UseCase",
        mode: "none",
      });
      await p.reload();
      await p.getByLabel("Person").selectOption("carol");
      await search("lumen")(p);
    },
    ready: (p) => expect(p.getByTestId("gb-banner")).toBeVisible(),
    after: (p) =>
      control(p.request, { op: "search", backend: "memory", type: "atlas.UseCase", mode: null }),
  },
  {
    name: "no-results",
    hash: "#/explore/atlas",
    before: search("zzzzqqq"),
    ready: (p) => expect(p.getByRole("heading", { name: /No results for/ })).toBeVisible(),
  },
  {
    name: "node-solution",
    hash: `#/explore/atlas/Solution/${SOLUTION}`,
    // in a narrow window the picture is behind a button
    ready: (p) => expect(p.locator("a.gb-node, button.gb-wide").first()).toBeVisible(),
  },
  {
    name: "node-solution-picture-open",
    hash: `#/explore/atlas/Solution/${SOLUTION}`,
    before: async (p) => {
      await p.getByRole("button", { name: "Show neighbourhood picture" }).click();
    },
    ready: (p) => expect(p.locator("a.gb-node").first()).toBeVisible(),
  },
  {
    name: "node-product",
    hash: "#/explore/atlas/Product/lumen",
    ready: (p) => expect(p.locator("a.gb-node").first()).toBeVisible(),
  },
  {
    name: "node-finding-four-groups",
    hash: "#/explore/atlas/Finding/fnd-seed-logs-1",
    ready: (p) => expect(p.locator("a.gb-node").first()).toBeVisible(),
  },
  {
    name: "node-hub",
    hash: `#/explore/atlas/UseCase/${HUB}`,
    ready: (p) => expect(p.locator("a.gb-node")).toHaveCount(40),
  },
  {
    name: "not-available",
    hash: "#/explore/atlas/Solution/ghost",
    ready: (p) => expect(p.getByTestId("gb-state")).toContainText("Not available"),
  },
  {
    name: "backend-down",
    hash: `#/explore/atlas/Solution/${SOLUTION}`,
    before: async (p) => {
      await control(p.request, { op: "outage", backend: "memory", reason: "unreachable" });
      await p.reload();
      await p.getByLabel("Person").selectOption("carol");
    },
    ready: (p) =>
      expect(p.getByRole("heading", { name: "The catalog did not answer" })).toBeVisible(),
    after: (p) => control(p.request, { op: "outage", backend: "memory", reason: null }),
  },
  {
    name: "topbar-operator",
    person: "alice",
    hash: `#/explore/atlas/Solution/${SOLUTION}`,
    clip: true,
    ready: (p) => expect(p.getByRole("group", { name: "Mode" })).toBeVisible(),
  },
  {
    name: "topbar-reader",
    hash: `#/explore/atlas/Solution/${SOLUTION}`,
    clip: true,
    ready: (p) => expect(p.getByRole("heading", { level: 1 })).toBeVisible(),
  },
];

const SIZES = [
  { tag: "wide", viewport: { width: 1280, height: 900 }, only: undefined },
  {
    tag: "narrow",
    viewport: { width: 390, height: 844 },
    only: new Set([
      "entry",
      "results",
      "node-solution",
      "no-results",
      "not-available",
      "topbar-reader",
    ]),
  },
] as const;

for (const scheme of ["light", "dark"] as const) {
  for (const size of SIZES) {
    test.describe(`${size.tag}, ${scheme}`, () => {
      test.use({ colorScheme: scheme, viewport: size.viewport });
      for (const shot of SHOTS) {
        if (size.only ? !size.only.has(shot.name) : shot.name === "node-solution-picture-open")
          continue;
        test(shot.name, async ({ page }) => {
          await open(page, shot.person ?? "carol", shot.hash);
          try {
            await shot.before?.(page);
            await shot.ready(page);
            await settle(page);
            const name = `${shot.name}-${size.tag}-${scheme}.png`;
            if (shot.clip) {
              await expect(page.getByRole("banner")).toHaveScreenshot(name, {
                mask: volatile(page),
              });
            } else {
              await expect(page).toHaveScreenshot(name, { fullPage: true, mask: volatile(page) });
            }
          } finally {
            await shot.after?.(page);
          }
        });
      }
    });
  }
}

test.describe("the picture on a node with the keyboard focus on a node and its card open", () => {
  test.use({ colorScheme: "light", viewport: { width: 1280, height: 900 } });
  test("focus-card", async ({ page }) => {
    await open(page, "carol", `#/explore/atlas/Solution/${SOLUTION}`);
    await page.locator("a.gb-node").first().focus();
    await expect(page.getByTestId("gb-hover")).toBeVisible();
    await settle(page);
    await expect(page.locator(".gb-pic")).toHaveScreenshot("picture-focus-wide-light.png");
  });
});

// The operator's states (FR-67 to FR-70, FR-73): alice with edit mode on, shot at 1280 and 390 in both
// schemes. Each only opens a dialog or panel; nothing is applied, so the data stays as it was.
/** The viewport, so the dialog's backdrop is in the picture; the page behind it is not the subject. */
const OPERATOR_SHOTS: {
  name: string;
  hash: string;
  open: (page: Page) => Promise<void>;
  ready: (page: Page) => Promise<void>;
}[] = [
  {
    name: "new-form",
    hash: "#/explore/atlas/Solution",
    open: async (p) => {
      await p.getByRole("button", { name: "Edit mode" }).click();
      await p.getByRole("button", { name: "New solution" }).click();
    },
    ready: (p) => expect(p.getByRole("dialog")).toBeVisible(),
  },
  {
    name: "actions-menu",
    hash: `#/explore/atlas/UseCase/${OPS_CASE}`,
    open: async (p) => {
      await p.getByRole("button", { name: "Edit mode" }).click();
      await p.getByRole("button", { name: "Entity menu" }).click();
    },
    ready: (p) => expect(p.getByRole("menu")).toBeVisible(),
  },
  {
    name: "actions-dialog",
    hash: `#/explore/atlas/UseCase/${OPS_CASE}`,
    open: async (p) => {
      await p.getByRole("button", { name: "Edit mode" }).click();
      await p.getByRole("button", { name: "Entity menu" }).click();
      await p.getByRole("menuitem", { name: /^AddSolution/ }).click();
    },
    ready: (p) => expect(p.getByRole("dialog")).toBeVisible(),
  },
  {
    name: "retire-confirm",
    hash: `#/explore/atlas/Solution/${SOLUTION}`,
    open: async (p) => {
      await p.getByRole("button", { name: "Edit mode" }).click();
      await p.getByRole("button", { name: "Entity menu" }).click();
      await p.getByRole("menuitem", { name: /^Retire/ }).click();
    },
    ready: (p) => expect(p.getByRole("dialog")).toContainText("cannot be used again"),
  },
  {
    name: "history-panel",
    hash: `#/explore/atlas/UseCase/${OPS_CASE}`,
    open: (p) => p.getByRole("button", { name: "History" }).click(),
    ready: (p) =>
      expect(p.getByTestId("gb-history").getByTestId("gb-change").first()).toBeVisible(),
  },
];

for (const scheme of ["light", "dark"] as const) {
  for (const size of SIZES) {
    test.describe(`operator, ${size.tag}, ${scheme}`, () => {
      test.use({ colorScheme: scheme, viewport: size.viewport });
      for (const shot of OPERATOR_SHOTS) {
        test(shot.name, async ({ page }) => {
          await open(page, "alice", shot.hash);
          await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
          await shot.open(page);
          await shot.ready(page);
          await settle(page);
          await expect(page).toHaveScreenshot(`${shot.name}-${size.tag}-${scheme}.png`, {
            mask: [...volatile(page), page.getByTestId("gb-history")],
          });
        });
      }
    });
  }
}

// The brand in the top bar (SD-013): a custom text wordmark, and the theme's mark with the name.
const BRANDS = [
  { name: "topbar-wordmark", brand: { name: "Example Ledger", wordmark: "Example Ledger" } },
  { name: "topbar-logo-theme", brand: { name: "Example Ledger", logo: "theme" } },
] as const;

for (const scheme of ["light", "dark"] as const) {
  for (const size of SIZES) {
    test.describe(`brand, ${size.tag}, ${scheme}`, () => {
      test.use({ colorScheme: scheme, viewport: size.viewport });
      for (const b of BRANDS) {
        test(b.name, async ({ page }) => {
          await page.route("**/*", async (route) => {
            if (route.request().resourceType() !== "document") return route.continue();
            const response = await route.fetch();
            const meta = `<meta name="arras-brand" content='${JSON.stringify(b.brand)}'>`;
            const html = (await response.text()).replace(/<meta name="arras-brand"[^>]*>/, "");
            await route.fulfill({ response, body: html.replace("</head>", `${meta}</head>`) });
          });
          await open(page, "carol", `#/explore/atlas/Solution/${SOLUTION}`);
          await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
          await settle(page);
          await expect(page.getByRole("banner")).toHaveScreenshot(
            `${b.name}-${size.tag}-${scheme}.png`,
            { mask: volatile(page) },
          );
        });
      }
    });
  }
}
