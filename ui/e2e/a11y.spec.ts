// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// An accessibility pass with axe-core over each area, in light and dark, on the dev host.
// WCAG 2.1 A and AA rules. Violations fail, and so do "incomplete" (needs review) results, with one
// justified allowlist: ALLOW_REVIEW below.

/**
 * axe cannot compute the background of SVG `<text>` (the graph's and diagram's node labels sit on an
 * SVG rect) or of a `<kbd>` hint drawn with a border, so it reports their contrast as "needs review".
 * Their colours are the same tokens as the HTML text (`--fg`, `--fg-muted`, `--bad`, ... on
 * `--surface`), whose pairs are checked >= 4.5:1 in styles.css for light and dark. Anything else
 * axe cannot decide fails this test.
 */
const ALLOW_REVIEW = (id: string, html: string, why: string) =>
  id === "color-contrast" && (/^<(text|kbd)\b/.test(html) || /only non-text characters/.test(why));
// A glyph-only control (the ✕ that closes a panel, ⧉ copy) has an aria-label; its glyph uses the
// same tokens. The viewport is tall so that nothing axe checks is below the fold of a scroll area
// (axe reports text it cannot see as "obscured").

/**
 * The UMF source view mounts UMF's schema browser package (the npm package, unchanged) in a srcdoc
 * iframe. The host page around it is audited like every other area, with the frame excluded; the
 * frame is audited on its own below, in both schemes, with the console's theme variables and
 * annotations in it (their real tones in both schemes, package 1.1.2), with the original source
 * pane open, under the same rules and the same review allowlist: no finding is pinned. axe cannot
 * measure the record map's SVG text; e2e/umf-explorer.spec.ts computes those contrasts.
 */
const UMF_EXPLORER_FRAME = 'iframe[title="UMF schema browser"]';

const AREAS: {
  name: string;
  path: string;
  ready: (p: Page) => Promise<void>;
  exclude?: string[];
}[] = [
  {
    name: "schema",
    path: "/#/catalog/model",
    ready: (p) => expect(p.getByTestId("schema")).toBeVisible(),
  },
  {
    name: "schema, UMF source",
    path: "/#/catalog/model",
    ready: async (p) => {
      await p.getByRole("button", { name: "UMF source" }).click();
      await expect(p.frameLocator(UMF_EXPLORER_FRAME).locator("#inspector")).toContainText(
        "Use Case",
        { timeout: 20_000 },
      );
    },
    exclude: [UMF_EXPLORER_FRAME],
  },
  {
    name: "graph",
    path: "/#/catalog/graph",
    ready: (p) => expect(p.getByTestId("node").first()).toBeVisible(),
  },
  {
    name: "graph with an entity open",
    path: "/#/catalog/graph",
    ready: async (p) => {
      await p.getByRole("button", { name: /Solution Pipeline extractor/ }).click();
      await expect(p.getByTestId("entity-panel").getByTestId("prop-name")).toBeVisible();
    },
  },
  {
    name: "data",
    path: "/#/catalog/entities/catalog.UseCase",
    ready: (p) => expect(p.getByText("uc-pipeline", { exact: true })).toBeVisible(),
  },
  {
    name: "actions with an impact preview",
    path: "/#/catalog/actions/catalog.RetireUseCase",
    ready: async (p) => {
      await p.getByLabel(/^useCase/).fill("uc-alerts");
      await p.getByLabel(/^useCase/).blur();
      await expect(p.getByTestId("impact-graph")).toBeVisible();
    },
  },
  {
    name: "actions with violations",
    path: "/#/catalog/actions/catalog.AddUseCase",
    ready: async (p) => {
      await p.getByLabel(/^code/).fill("uc-pipeline");
      await p.getByLabel(/^name/).fill("x");
      await p.getByTestId("validate").click();
      await expect(p.getByTestId("not-valid")).toBeVisible();
    },
  },
  {
    name: "query with a grid and its history",
    path: "/#/catalog/query",
    ready: async (p) => {
      await p
        .getByLabel("Query (Weft SQL, read-only)")
        .fill("SELECT s.* FROM catalog.Solution s ORDER BY s.code LIMIT 50");
      await p.getByRole("button", { name: "Run", exact: true }).click();
      await expect(p.getByTestId("query-row").first()).toBeVisible();
      await p.getByTestId("query-types").getByText("What can I query?").click();
      await expect(p.getByTestId("query-type").first()).toBeVisible();
    },
  },
  {
    name: "query with violations",
    path: "/#/catalog/query",
    ready: async (p) => {
      await p.getByLabel("Query (Weft SQL, read-only)").fill("DELETE FROM catalog.UseCase");
      await p.getByRole("button", { name: "Run", exact: true }).click();
      await expect(p.getByTestId("query-violations")).toBeVisible();
    },
  },
  {
    name: "audit",
    path: "/#/catalog/changes",
    ready: (p) => expect(p.getByTestId("change-row").first()).toBeVisible(),
  },
];

for (const scheme of ["light", "dark"] as const) {
  test.describe(`axe, ${scheme}`, () => {
    test.use({ colorScheme: scheme, viewport: { width: 1440, height: 2400 } });
    for (const a of AREAS) {
      test(`${a.name} has no WCAG A/AA violations`, async ({ page }) => {
        await page.goto(a.path);
        await a.ready(page);
        expect(
          await page.evaluate(
            () => getComputedStyle(document.querySelector(".arras-root") as Element).colorScheme,
          ),
        ).toBe(scheme);
        let axe = new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]);
        for (const sel of a.exclude ?? []) axe = axe.exclude(sel);
        const r = await axe.analyze();
        expect(r.passes.length).toBeGreaterThan(20); // axe ran over a rendered page
        const found = r.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          help: v.help,
          nodes: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
        }));
        expect(found, JSON.stringify(found, null, 2)).toEqual([]);
        const review = r.incomplete.flatMap((v) =>
          v.nodes
            .filter((n) => !ALLOW_REVIEW(v.id, n.html, n.any.map((c) => c.message).join(" ")))
            .map(
              (n) => `${v.id}: ${n.html.slice(0, 120)} (${n.any.map((c) => c.message).join("; ")})`,
            ),
        );
        expect(review, review.join("\n")).toEqual([]);
      });
    }
  });
}

for (const scheme of ["light", "dark"] as const) {
  test(`inside UMF's schema browser frame, ${scheme}: no WCAG A/AA violations`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 1440, height: 2400 });
    await page.goto("/#/catalog/model");
    await page.getByRole("button", { name: "UMF source" }).click();
    await expect(page.frameLocator(UMF_EXPLORER_FRAME).locator("#inspector")).toContainText(
      "Use Case",
      { timeout: 20_000 },
    );
    expect(
      await page
        .locator(UMF_EXPLORER_FRAME)
        .evaluate((f: HTMLIFrameElement) => f.contentDocument?.documentElement.dataset.theme),
    ).toBe(scheme);
    // The console's badges in their real tones (positive, neutral, info), not neutral in dark.
    const frame = page.frameLocator(UMF_EXPLORER_FRAME);
    await expect
      .poll(() =>
        frame
          .locator("#inspector .umf-annotation[data-tone]")
          .evaluateAll((es) => [...new Set(es.map((e) => e.getAttribute("data-tone")))].sort()),
      )
      .toEqual(["info", "neutral", "positive"]);
    // A scrollable source pane in view: it must be keyboard-focusable (scrollable-region-focusable).
    await frame
      .locator("#inspector")
      .getByText("Original schema source", { exact: true })
      .first()
      .click();
    await expect(frame.locator("#inspector details[open] pre").first()).toBeVisible();
    const r = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .include(UMF_EXPLORER_FRAME)
      .analyze();
    expect(r.passes.length).toBeGreaterThan(10); // axe ran inside the frame
    const found = r.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes
        .slice(0, 8)
        .map((n) => `${n.target.join(" ")} ${n.any.map((c) => c.message).join(" ")}`),
    }));
    expect(found, JSON.stringify(found, null, 2)).toEqual([]);
    const review = r.incomplete.flatMap((v) =>
      v.nodes
        .filter((n) => !ALLOW_REVIEW(v.id, n.html, n.any.map((c) => c.message).join(" ")))
        .map((n) => `${v.id}: ${n.html.slice(0, 120)} (${n.any.map((c) => c.message).join("; ")})`),
    );
    expect(review, review.join("\n")).toEqual([]);
  });
}

// The console's area tab strip scrolls sideways on a phone, with an edge fade drawn as a mask on the
// scroller (no layer over the labels). Axe must still decide the tabs' contrast with the mask on
// and with both edges faded.
for (const scheme of ["light", "dark"] as const) {
  test(`the area tab strip at 390px with its scroll cue, ${scheme}: no WCAG A/AA violations`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/#/catalog/model");
    const strip = page.getByRole("tablist", { name: "Areas" });
    await expect(strip).toBeVisible();
    const cue = strip.locator(
      "xpath=ancestor::div[contains(concat(' ', @class, ' '), ' arras-cue ')][1]",
    );
    await expect(cue).toHaveAttribute("data-cue-end", "true");
    // Scroll a little: both edges fade.
    await strip.evaluate((el) => {
      (el.parentElement as HTMLElement).scrollLeft = 24;
    });
    await expect(cue).toHaveAttribute("data-cue-start", "true");
    await expect(cue).toHaveAttribute("data-cue-end", "true");
    const mask = await cue.evaluate(
      (el) => getComputedStyle(el.firstElementChild as Element).maskImage,
    );
    expect(mask).not.toBe("none");
    const r = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(r.passes.length).toBeGreaterThan(20);
    const found = r.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.slice(0, 5).map((n) => `${n.target.join(" ")} ${n.html.slice(0, 160)}`),
    }));
    expect(found, JSON.stringify(found, null, 2)).toEqual([]);
    const review = r.incomplete.flatMap((v) =>
      v.nodes
        .filter((n) => !ALLOW_REVIEW(v.id, n.html, n.any.map((c) => c.message).join(" ")))
        .map((n) => `${v.id}: ${n.html.slice(0, 120)} (${n.any.map((c) => c.message).join("; ")})`),
    );
    expect(review, review.join("\n")).toEqual([]);
  });
}
