// SPDX-License-Identifier: MIT OR Apache-2.0
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, type FrameLocator, type Page, test } from "@playwright/test";
import { ASSETS_DIR, differences, files, RELEASE } from "../scripts/umf-schema-browser.ts";
import { defined } from "../src/test/defined";
import { asBob } from "./gb-fixtures";

// OPR-11: the module's registered UMF document in UMF's own schema browser, the npm package
// @documentdrivendx/umf-schema-browser (pinned exactly), mounted with its `mountSchemaBrowser` (a
// srcdoc iframe) and the catalog the console reads with the viewer's credentials. The dev host
// serves the package's assets at /umf-explorer and the console's page under UMF's strict CSP
// profile (srcdoc inherits it). Everything here is the real server; any CSP violation or page error
// fails a test unless the test provokes it.

const FRAME = 'iframe[title="UMF schema browser"]';
const CATALOG_TEXT = readFileSync(
  new URL("../../src/arras/conformance/module.umf.json", import.meta.url),
  "utf8",
);
const DIST = new URL("../dist/umf-explorer/", import.meta.url).pathname;
const STRICT =
  "default-src 'none'; base-uri 'none'; script-src 'self'; style-src 'self'; img-src 'self'; frame-src 'self' about:; connect-src 'self'; frame-ancestors 'self'";
// The record badges the console derives from the live registry (src/areas/umfBrowser.ts): one per
// backend, each on its own line of the record map (package 1.1.2 reserves the space).
const RECORD_BADGES = ["memory · mutable", "memory_replica · read-only"];
const RECORD_TONES = ["positive", "neutral"];
const TONES = ["neutral", "info", "positive", "warning", "negative"] as const;

/** Every CSP violation and script error in the page and its frames, as text. */
function watch(page: Page): string[] {
  const seen: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || /Content Security Policy|CSP violation/.test(m.text()))
      seen.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => seen.push(`pageerror: ${e.message}`));
  // Runs in every frame, the srcdoc one included: the browser's iframe reports its own violations.
  void page.exposeFunction("reportCspViolation", (message: string) => {
    seen.push(`console: ${message}`);
  });
  void page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      const report = Reflect.get(window, "reportCspViolation");
      if (typeof report === "function")
        report(
          `CSP violation: ${e.violatedDirective} ${e.blockedURI} ${e.sourceFile}:${e.lineNumber}`,
        );
    });
  });
  return seen;
}

async function as(page: Page, person: string, hash = "#/catalog/model") {
  await page.goto(`/${hash}`);
  await page.reload();
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

async function openUmfSource(page: Page): Promise<FrameLocator> {
  await expect(page.getByTestId("schema")).toBeVisible();
  expect(await page.locator(FRAME).count()).toBe(0); // created only when the view is opened
  await page.getByRole("button", { name: "UMF source" }).click();
  await expect(page.getByRole("button", { name: "UMF source" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const frame = page.frameLocator(FRAME);
  await expect(frame.locator("#inspector")).toContainText("Use Case", { timeout: 20_000 });
  await expect(
    page.getByRole("status").filter({ hasText: "Loading UMF's schema browser" }),
  ).toHaveCount(0);
  return frame;
}

/** Mark the frame element, so a later check can tell the same element from a remounted one. */
const mark = (page: Page) =>
  page
    .locator(FRAME)
    .evaluate((f) => ((f as HTMLIFrameElement & { arrasMark?: number }).arrasMark = 1));
const marked = (page: Page) =>
  page
    .locator(FRAME)
    .evaluate((f) => (f as HTMLIFrameElement & { arrasMark?: number }).arrasMark === 1);
/** The badge text of a record in the map (an SVG text whose title child is the tooltip). */
const recordBadges = (frame: FrameLocator, record: string) =>
  frame
    .locator(`.ontology-map svg a[aria-label^="Inspect record ${record}"] text.umf-annotation`)
    .evaluateAll((ts) =>
      ts.map((t) =>
        Array.from(t.childNodes)
          .filter((n) => n.nodeType === Node.TEXT_NODE)
          .map((n) => n.textContent)
          .join(""),
      ),
    );
const recordTips = (frame: FrameLocator, record: string) =>
  frame
    .locator(
      `.ontology-map svg a[aria-label^="Inspect record ${record}"] text.umf-annotation title`,
    )
    .allTextContents();
const recordTones = (frame: FrameLocator, record: string) =>
  frame
    .locator(`.ontology-map svg a[aria-label^="Inspect record ${record}"] text.umf-annotation`)
    .evaluateAll((ts) => ts.map((t) => t.getAttribute("data-tone")));

interface Painted {
  tone: string | null;
  text: string;
  ratio: number;
  visible: boolean;
}
interface Paint {
  theme: string | undefined;
  heading: Painted[];
  legend: Painted[];
  map: Painted[];
  numbers: Painted[];
  records: { label: string; notes: number; overlaps: number; inside: boolean }[];
}

/**
 * What the frame paints, measured in it: each annotation's colour against what is behind it
 * (WCAG contrast ratio, from the computed colours through a canvas, so `light-dark()` and
 * `var()` are resolved), in the entry heading, the relationship legend and the record map (SVG
 * text, which axe cannot measure: its fill against its record's rect), the relationship numbers
 * against their circles, and each record's boxes: annotations and property count overlap nowhere
 * and stay inside the record.
 */
const paint = (page: Page, frameSelector = FRAME): Promise<Paint> =>
  page.locator(frameSelector).evaluate((f: HTMLIFrameElement) => {
    const need = <T>(v: T | null | undefined): T => {
      if (v === null || v === undefined) throw new Error("missing in the frame");
      return v;
    };
    const d = need(f.contentDocument);
    const w = need(f.contentWindow);
    const cv = d.createElement("canvas");
    cv.width = 1;
    cv.height = 1;
    const cx = need(cv.getContext("2d", { willReadFrequently: true }));
    const rgba = (c: string) => {
      cx.clearRect(0, 0, 1, 1);
      cx.fillStyle = "#000";
      cx.fillStyle = c;
      cx.fillRect(0, 0, 1, 1);
      return Array.from(cx.getImageData(0, 0, 1, 1).data);
    };
    const lum = (c: string) => {
      const [r, g, b] = rgba(c).map((v) => {
        const u = v / 255;
        return u <= 0.03928 ? u / 12.92 : ((u + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * need(r) + 0.7152 * need(g) + 0.0722 * need(b);
    };
    const ratio = (a: string, b: string) => {
      const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
      return Math.round(((need(x) + 0.05) / (need(y) + 0.05)) * 100) / 100;
    };
    const behind = (el: Element) => {
      for (let e: Element | null = el; e; e = e.parentElement) {
        const c = w.getComputedStyle(e).backgroundColor;
        if (need(rgba(c)[3]) > 0) return c;
      }
      return w.getComputedStyle(d.documentElement).backgroundColor;
    };
    const shown = (e: Element) => {
      const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && w.getComputedStyle(e).visibility !== "hidden";
    };
    const own = (e: Element) =>
      Array.from(e.childNodes)
        .filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => n.textContent)
        .join("");
    const html = (sel: string): Painted[] =>
      Array.from(d.querySelectorAll(sel), (e) => ({
        tone: e.getAttribute("data-tone"),
        text: own(e),
        ratio: ratio(w.getComputedStyle(e).color, behind(e)),
        visible: shown(e),
      }));
    const svgText = (t: Element, under: Element): Painted => ({
      tone: t.getAttribute("data-tone"),
      text: own(t),
      ratio: ratio(w.getComputedStyle(t).fill, w.getComputedStyle(under).fill),
      visible: shown(t),
    });
    const records = Array.from(
      d.querySelectorAll(".ontology-map svg a[aria-label^='Inspect record']"),
    );
    const box = (e: Element) => e.getBoundingClientRect();
    return {
      theme: d.documentElement.dataset.theme,
      heading: html("#inspector h2 .umf-annotation"),
      legend: html(".map-relationships .umf-annotation"),
      map: records.flatMap((a) =>
        Array.from(a.querySelectorAll("text.umf-annotation"), (t) =>
          svgText(t, need(a.querySelector("rect"))),
        ),
      ),
      numbers: Array.from(
        d.querySelectorAll(".ontology-map svg a[aria-label^='Inspect relationship']"),
        (a) =>
          svgText(
            need(
              Array.from(a.querySelectorAll("text")).find((t) => /^\d+$/.test(t.textContent ?? "")),
            ),
            need(a.querySelector("circle")),
          ),
      ),
      records: records.map((a) => {
        const rect = box(need(a.querySelector("rect")));
        const parts = [
          ...a.querySelectorAll("text.umf-annotation"),
          need(a.querySelector("text.map-count")),
        ].map(box);
        let overlaps = 0;
        for (let i = 0; i < parts.length; i++)
          for (let j = i + 1; j < parts.length; j++) {
            const [p, q] = [need(parts[i]), need(parts[j])];
            if (p.left < q.right && q.left < p.right && p.top < q.bottom && q.top < p.bottom)
              overlaps++;
          }
        return {
          label: need(a.getAttribute("aria-label")),
          notes: parts.length - 1,
          overlaps,
          inside: parts.every((p) => p.top >= rect.top && p.bottom <= rect.bottom),
        };
      }),
    };
  });

/** A second frame from the console's own srcdoc (same assets, CSP and theme), with other annotations. */
async function probeFrame(
  page: Page,
  annotations: Record<string, { badge: string; tone: string; tooltip: string }[]>,
): Promise<FrameLocator> {
  await page.evaluate((notes) => {
    const f = document.querySelector('iframe[title="UMF schema browser"]') as HTMLIFrameElement;
    const m = /<script id="umf-browser-config" type="application\/json">([\s\S]*?)<\/script>/.exec(
      f.srcdoc,
    );
    const raw = m?.[1];
    if (raw === undefined) throw new Error("the browser config is not in the srcdoc");
    const config = { ...JSON.parse(raw), instance: "probe", annotations: notes };
    const probe = document.createElement("iframe");
    probe.title = "probe";
    probe.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;z-index:9";
    probe.srcdoc = f.srcdoc.replace(raw, JSON.stringify(config).replace(/</g, "\\u003c"));
    document.body.append(probe);
  }, annotations);
  const frame = page.frameLocator('iframe[title="probe"]');
  await expect(frame.locator("#inspector")).toContainText("Use Case", { timeout: 20_000 });
  await expect(frame.locator(".ontology-map svg text.umf-annotation").first()).toBeVisible();
  return frame;
}

test("Schema → UMF source: the package shows the viewer's module with the live registry's badges, under the strict policy", async ({
  page,
}) => {
  const problems = watch(page);
  await as(page, "alice");
  const frame = await openUmfSource(page);
  // The package's own mount: a srcdoc frame, no src, no sandbox, filling the console's area.
  const iframe = page.locator(FRAME);
  await expect(iframe).toHaveAttribute("srcdoc", /umf-browser-config/);
  expect(await iframe.getAttribute("src")).toBeNull();
  expect(await iframe.getAttribute("sandbox")).toBeNull();
  const box = defined(await iframe.boundingBox(), "(await iframe.boundingBox())");
  const area = defined(
    await page.getByTestId("umf-browser").boundingBox(),
    '(await page.getByTestId("umf-browser").boundingBox())',
  );
  expect(box.height).toBeGreaterThanOrEqual(600);
  expect(Math.abs(area.height - 2 - box.height)).toBeLessThanOrEqual(1); // height: '100%' of the container
  await expect(page.getByTestId("umf-source")).toContainText("The declared UMF document");
  await expect(page.getByTestId("umf-source")).toContainText("what this deployment serves");
  await expect(page.getByRole("link", { name: "Open in new tab" })).toHaveCount(0);
  // hideHero, readOnlyLocalFiles, categories: no hero heading, no local-file control, our label.
  await expect(frame.locator(".page-top")).toBeHidden();
  await expect(frame.getByText("Open local schema")).toBeHidden();
  await expect(frame.getByRole("heading", { name: "Registered modules" })).toBeVisible();
  // The module is selected (the `selection` option); choosing it from the catalog list shows the same.
  const inspector = frame.locator("#inspector");
  await expect(inspector).toContainText("Registered at revision memory");
  await frame
    .getByRole("button", { name: /catalog/i })
    .first()
    .click();
  await expect(inspector).toContainText("Solution");
  // Annotations from the live registry: the entry heading, each record (one per backend), the relationship.
  await expect(inspector.locator("h2 .umf-annotation")).toHaveText([
    "record: memory",
    "replica: memory_replica",
  ]);
  await expect
    .poll(() =>
      inspector
        .locator("h2 .umf-annotation")
        .evaluateAll((es) => es.map((e) => e.getAttribute("data-tone"))),
    )
    .toEqual(["positive", "neutral"]);
  await expect.poll(() => recordBadges(frame, "Use Case")).toEqual(RECORD_BADGES);
  await expect.poll(() => recordBadges(frame, "Solution")).toEqual(RECORD_BADGES);
  await expect.poll(() => recordTones(frame, "Solution")).toEqual(RECORD_TONES);
  await expect
    .poll(() => recordTips(frame, "Use Case"))
    .toEqual([
      "memory (record store): mutable, applies this type's actions; latency interactive; filter columns: code, name; counts",
      "memory_replica (replica): read-only replica; latency batch; filter columns: code, name; counts",
    ]);
  await expect(frame.locator(".map-relationships .umf-annotation")).toHaveText([
    "follows: memory, memory_replica",
  ]);
  await expect(frame.locator(".map-relationships .umf-annotation")).toHaveAttribute(
    "data-tone",
    "info",
  );
  // schemaFormat "umf": the record map and the relationship list.
  await expect(inspector).toContainText("Relationship map");
  await expect(inspector).toContainText("addresses");
  // The original source is the registered document, character for character.
  await inspector.getByText("Original schema source", { exact: true }).first().click();
  const source = inspector
    .locator("details", { hasText: "Original schema source" })
    .locator("pre")
    .first();
  expect(await source.textContent()).toBe(CATALOG_TEXT);
  // Its search box filters the catalog.
  await frame.locator("#search").fill("no-such-thing-anywhere");
  await expect(frame.getByText("No matching schemas")).toBeVisible();
  await frame.locator("#search").fill("catalog");
  await expect(frame.getByRole("button", { name: /catalog/i }).first()).toBeVisible();
  expect(problems, problems.join("\n")).toEqual([]);
});

test("events reach the console: the selection line, and Open in Entities / Show in Graph switch areas", async ({
  page,
}) => {
  const problems = watch(page);
  await as(page, "alice");
  const frame = await openUmfSource(page);
  const line = page.getByTestId("umf-selection");
  await expect(line).toContainText("Selected: catalog");
  await expect(line.getByRole("button", { name: /in Entities/ })).toHaveCount(0); // the entry is no type
  await frame.locator('.ontology-map svg a[aria-label^="Inspect record Use Case"]').first().click();
  await expect(line).toContainText("Selected: catalog › UseCase");
  // A relationship is no type either.
  await frame.locator(".map-relationships button").first().click();
  await expect(line).toContainText("Selected: catalog › relationship solution-addresses");
  await expect(line.getByRole("button", { name: /in Entities/ })).toHaveCount(0);
  await frame.locator('.ontology-map svg a[aria-label^="Inspect record Use Case"]').first().click();
  await line.getByRole("button", { name: "Open UseCase in Entities" }).click();
  await expect(page).toHaveURL(/#\/operate\/catalog\/entities\/catalog\.UseCase$/);
  await expect(page.getByText("uc-pipeline", { exact: true })).toBeVisible();
  // Back, and to the graph with Solution alone shown; its type toggles bring the others back.
  await page.getByRole("tab", { name: "Model" }).click();
  await openUmfSource(page);
  await frame.locator('.ontology-map svg a[aria-label^="Inspect record Solution"]').first().click();
  await line.getByRole("button", { name: "Show Solution in Graph" }).click();
  await expect(page).toHaveURL(/#\/operate\/catalog\/graph$/);
  const types = page.getByRole("group", { name: "Types" });
  await expect(types.getByRole("button", { name: /^Solution/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(types.getByRole("button", { name: /^UseCase/ })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect(page.getByTestId("node").first()).toBeVisible();
  // Held for that visit only: the Graph tab later shows every type.
  await page.getByRole("tab", { name: "Model" }).click();
  await page.getByRole("tab", { name: "Graph" }).click();
  await expect(types.getByRole("button", { name: /^UseCase/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(problems, problems.join("\n")).toEqual([]);
});

test("routes stay inside the frame: a definition opened in the browser changes only the frame's hash and the console's selected type", async ({
  page,
}) => {
  const problems = watch(page);
  await as(page, "alice");
  const frame = await openUmfSource(page);
  const route = await page.evaluate(() => location.hash);
  // Opening the source writes the view word and nothing else.
  expect(route).toBe("#/operate/catalog/model?view=umf");
  const frameHash = () =>
    page.locator(FRAME).evaluate((f: HTMLIFrameElement) => f.contentWindow?.location.hash);
  expect(await frameHash()).toBe("#schema=arras%3Acatalog");
  await frame.locator('.ontology-map svg a[aria-label^="Inspect record Solution"]').first().click();
  await expect(frame.locator("#inspector")).toContainText("Solution");
  expect(await frameHash()).toContain(
    `definition=${encodeURIComponent(JSON.stringify(["catalog", "Solution"]))}`,
  );
  // The console's address carries only the view and the type the frame reported.
  await expect
    .poll(() => page.evaluate(() => location.hash))
    .toBe("#/operate/catalog/model/catalog.Solution?view=umf");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("a registry change replaces the badges in place (setAnnotations): a memory_replica outage, then mended", async ({
  page,
  request,
  baseURL,
}) => {
  const problems = watch(page);
  const control = (data: Record<string, unknown>) =>
    request.post("/api/dev/control", { data, headers: { origin: defined(baseURL, "baseURL") } });
  await as(page, "alice");
  const frame = await openUmfSource(page);
  await mark(page);
  await expect.poll(() => recordBadges(frame, "Use Case")).toEqual(RECORD_BADGES);
  expect(
    (await control({ op: "outage", backend: "memory_replica", reason: "unreachable" })).status(),
  ).toBe(200);
  try {
    await page.getByRole("button", { name: "Refresh badges" }).click();
    await expect
      .poll(() => recordBadges(frame, "Use Case"))
      .toEqual(["memory · mutable", "memory_replica · unavailable"]);
    await expect.poll(() => recordTones(frame, "Use Case")).toEqual(["positive", "warning"]);
    await expect(frame.locator("#inspector h2 .umf-annotation")).toHaveText([
      "record: memory",
      "replica: memory_replica",
      "memory_replica · unavailable",
    ]);
    // The warning tone the outage brings is readable where it is drawn (>= 4.5:1).
    await expect
      .poll(async () =>
        (await paint(page)).heading.filter((a) => a.tone === "warning").map((a) => a.ratio >= 4.5),
      )
      .toEqual([true]);
    expect(await marked(page)).toBe(true); // the same frame: no remount
  } finally {
    expect(
      (await control({ op: "outage", backend: "memory_replica", reason: null })).status(),
    ).toBe(200);
  }
  await page.getByRole("button", { name: "Refresh badges" }).click();
  await expect.poll(() => recordBadges(frame, "Use Case")).toEqual(RECORD_BADGES);
  await expect(frame.locator("#inspector h2 .umf-annotation")).toHaveText([
    "record: memory",
    "replica: memory_replica",
  ]);
  expect(await marked(page)).toBe(true);
  expect(await page.locator("iframe").count()).toBe(1);
  expect(problems, problems.join("\n")).toEqual([]);
});

test("dark: the frame follows the console's scheme and tokens, and a scheme change remounts it in the other", async ({
  page,
}) => {
  const problems = watch(page);
  await page.emulateMedia({ colorScheme: "dark" });
  await as(page, "alice");
  const frame = await openUmfSource(page);
  const colours = () =>
    page.locator(FRAME).evaluate((f: HTMLIFrameElement) => {
      const d = f.contentDocument;
      if (!d) throw new Error("the frame has no document");
      return {
        theme: d.documentElement.dataset.theme,
        bg: getComputedStyle(d.body).backgroundColor,
        fg: getComputedStyle(d.body).color,
      };
    });
  const surface = () =>
    page.evaluate(() => {
      const probe = document.createElement("div");
      probe.style.background = "var(--surface)";
      probe.style.color = "var(--fg)";
      document.querySelector(".arras-root")?.append(probe); // the tokens are on the console's root
      const s = { bg: getComputedStyle(probe).backgroundColor, fg: getComputedStyle(probe).color };
      probe.remove();
      return s;
    });
  const dark = await colours();
  expect(dark.theme).toBe("dark");
  // The same tones as in light (package 1.1.2 draws them readable on a dark paper).
  await expect.poll(() => recordTones(frame, "Use Case")).toEqual(RECORD_TONES);
  expect({ bg: dark.bg, fg: dark.fg }).toEqual(await surface()); // --paper/--ink are the console's tokens
  await page.emulateMedia({ colorScheme: "light" });
  await expect
    .poll(async () => (await colours().catch(() => ({ theme: "" }))).theme, { timeout: 20_000 })
    .toBe("light");
  await expect(frame.locator("#inspector")).toContainText("Use Case", { timeout: 20_000 });
  const light = await colours();
  expect(light.bg).not.toBe(dark.bg);
  await expect.poll(() => recordTones(frame, "Use Case")).toEqual(RECORD_TONES);
  expect({ bg: light.bg, fg: light.fg }).toEqual(await surface());
  expect(await page.locator("iframe").count()).toBe(1);
  expect(problems, problems.join("\n")).toEqual([]);
});

test("opened with the keyboard, focus moves into the browser's inspector heading (focus())", async ({
  page,
}) => {
  const problems = watch(page);
  await as(page, "alice");
  await expect(page.getByTestId("schema")).toBeVisible();
  await page.getByRole("button", { name: "UMF source" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.frameLocator(FRAME).locator("#inspector")).toContainText("Use Case", {
    timeout: 20_000,
  });
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.getAttribute("title")))
    .toBe("UMF schema browser");
  const inner = () =>
    page.locator(FRAME).evaluate((f: HTMLIFrameElement) => {
      const a = f.contentDocument?.activeElement;
      return `${a?.tagName}:${a?.textContent?.slice(0, 40)}`;
    });
  await expect.poll(inner).toMatch(/^H2:Catalog/);
  // Opened with the mouse, focus stays on the console's button.
  await page.getByRole("button", { name: "Live registry" }).click();
  await page.getByRole("button", { name: "UMF source" }).click();
  await expect(page.frameLocator(FRAME).locator("#inspector")).toContainText("Use Case", {
    timeout: 20_000,
  });
  expect(await page.evaluate(() => document.activeElement?.textContent)).toBe("UMF source");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("an operator who reads no module (bob, his read revoked) has an empty catalog and never reaches the view", async ({
  page,
  request,
}) => {
  await asBob(request, [], async () => {
    await as(page, "bob", "#/operate");
    await expect(page.getByTestId("no-modules")).toBeVisible();
    expect(await page.locator(FRAME).count()).toBe(0);
    const r = await request.get("/api/operate/explorer/schema-catalog.json", {
      headers: { "x-arras-user": "bob" },
    });
    expect(await r.json()).toEqual({ version: 1, entries: [] });
    // carol and dave are not operators: the operate surface refuses them (CONTRACT-010)
    const dave = await request.get("/api/operate/explorer/schema-catalog.json", {
      headers: { "x-arras-user": "dave" },
    });
    expect([dave.status(), await dave.json()]).toEqual([
      403,
      { error: "REFUSED", reason: "not_operator" },
    ]);
    // Nothing in the browser names the person: no cookie, no storage.
    expect(await page.evaluate(() => document.cookie)).toBe("");
  });
});

test("an expired token: the catalog asks to sign in again, and Retry mounts the browser once restored", async ({
  page,
  request,
  baseURL,
}) => {
  const problems = watch(page);
  await as(page, "bob");
  await expect(page.getByTestId("schema")).toBeVisible();
  const control = (data: Record<string, unknown>) =>
    request.post("/api/dev/control", { data, headers: { origin: defined(baseURL, "baseURL") } });
  expect((await control({ op: "expire", user: "bob" })).status()).toBe(200);
  try {
    await page.getByRole("button", { name: "UMF source" }).click();
    const error = page.getByTestId("umf-catalog-error");
    await expect(error).toContainText("Sign in again", { timeout: 20_000 });
    await expect(error).toContainText("token_expired");
    expect(await page.locator(FRAME).count()).toBe(0);
  } finally {
    expect((await control({ op: "restore", user: "bob" })).status()).toBe(200);
  }
  await page.getByTestId("umf-catalog-error").getByRole("button", { name: "Retry" }).click();
  await expect(page.frameLocator(FRAME).locator("#inspector")).toContainText("Use Case", {
    timeout: 20_000,
  });
  // The 401 the browser console reports for the refused fetch is the expected one.
  expect(
    problems.filter((p) => !/401/.test(p)),
    problems.join("\n"),
  ).toEqual([]);
});

test("switching views destroys the browser: one working instance, however fast", async ({
  page,
}) => {
  const problems = watch(page);
  await as(page, "alice");
  await expect(page.getByTestId("schema")).toBeVisible();
  const umf = page.getByRole("button", { name: "UMF source" });
  const live = page.getByRole("button", { name: "Live registry" });
  for (let i = 0; i < 4; i++) {
    await umf.click(); // destroyed before its load, most of these
    await live.click();
    expect(await page.locator(FRAME).count()).toBe(0);
  }
  await umf.click();
  await expect(page.frameLocator(FRAME).locator("#inspector")).toContainText("Use Case", {
    timeout: 20_000,
  });
  expect(await page.locator(FRAME).count()).toBe(1);
  expect(await page.locator("iframe").count()).toBe(1);
  expect(problems, problems.join("\n")).toEqual([]);
});

test("the console page and the assets carry UMF's strict policy, no 'unsafe-eval'; the assets are the installed package's bytes", async ({
  page,
  request,
}) => {
  const problems = watch(page);
  const csp = (await request.get("/")).headers()["content-security-policy"] ?? "";
  expect(csp).toBe(STRICT);
  expect(csp).not.toContain("unsafe-eval");
  expect(csp).not.toContain("unsafe-inline");
  expect((await request.get("/umf-explorer/index.html")).headers()["content-security-policy"]).toBe(
    csp,
  );
  // The build's copy and what the server sends are the installed package's assets/, byte for byte.
  expect(differences(ASSETS_DIR, DIST)).toEqual([]);
  const names = files(ASSETS_DIR);
  expect(names).toEqual(
    expect.arrayContaining([
      "explorer.js",
      "explorer.css",
      "style.css",
      "components.css",
      "index.html",
    ]),
  );
  for (const name of names) {
    const r = await request.get(`/umf-explorer/${name}`);
    expect(r.status(), name).toBe(200);
    const want = createHash("sha256")
      .update(readFileSync(join(ASSETS_DIR, name)))
      .digest("hex");
    expect(
      createHash("sha256")
        .update(await r.body())
        .digest("hex"),
      name,
    ).toBe(want);
  }
  expect((await request.get("/umf-explorer/explorer.js")).headers()["content-type"]).toMatch(
    /^text\/javascript/,
  );
  // Load time, from opening the view to the module shown inside the frame, and what it fetched.
  await as(page, "alice");
  await expect(page.getByTestId("schema")).toBeVisible();
  const started = Date.now();
  await page.getByRole("button", { name: "UMF source" }).click();
  await expect(page.frameLocator(FRAME).locator("#inspector")).toContainText("Use Case", {
    timeout: 20_000,
  });
  const shown = Date.now() - started;
  const fetched = await page
    .locator(FRAME)
    .evaluate((f: HTMLIFrameElement) =>
      (
        (f.contentWindow?.performance.getEntriesByType("resource") ??
          []) as PerformanceResourceTiming[]
      ).map((e) => ({ name: e.name.split("/").pop() ?? e.name, bytes: e.encodedBodySize })),
    );
  const bytes = fetched.reduce((n, e) => n + e.bytes, 0);
  const js = fetched.find((e) => e.name === "explorer.js")?.bytes ?? 0;
  process.stderr.write(
    `UMF schema browser ${RELEASE.version}: explorer.js ${js} bytes; ${fetched.length} files, ${bytes} bytes fetched to show the module; shown ${shown} ms after opening the view\n`,
  );
  expect(js).toBeGreaterThan(50_000);
  expect(bytes).toBeLessThan(2_000_000); // lazy chunks: the 14 MB validator chunk is not fetched for a UMF document
  expect(problems, problems.join("\n")).toEqual([]);
});

test("a policy narrower than the browser needs is the console's failure state, not a blank frame; no 'unsafe-eval' is asked for", async ({
  page,
  baseURL,
}) => {
  test.setTimeout(90_000);
  // The real server's page, `script-src` narrowed to the console's own bundle: the srcdoc frame
  // inherits it, so the browser's explorer.js is refused and its `ready` rejects (30 s bound).
  await page.route("/", async (route) => {
    const res = await route.fetch();
    const csp = defined(
      res.headers()["content-security-policy"],
      'res.headers()["content-security-policy"]',
    );
    expect(csp).toBe(STRICT);
    await route.fulfill({
      response: res,
      headers: {
        ...res.headers(),
        "content-security-policy": csp.replace(
          "script-src 'self'",
          `script-src ${baseURL}/assets/`,
        ),
      },
    });
  });
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  await page.evaluate(() => (location.hash = "#/operate/catalog/model"));
  await expect(page.getByTestId("schema")).toBeVisible();
  await page.getByRole("button", { name: "UMF source" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText(
    "UMF's schema browser did not load (Schema browser initialization timed out)",
    { timeout: 40_000 },
  );
  await expect(alert).toContainText("Content-Security-Policy");
  expect(errors.join("\n")).toMatch(/explorer\.js/);
  expect(errors.join("\n")).not.toMatch(/unsafe-eval/);
  await expect(page.locator(FRAME)).toBeHidden();
  expect(await page.locator("iframe").count()).toBe(1);
});

test("a browser whose assets failed once (ready rejected) recovers on Retry", async ({ page }) => {
  test.setTimeout(90_000);
  let refused = 0;
  await page.route("**/umf-explorer/explorer.js", async (route) => {
    if (refused++ === 0) return route.fulfill({ status: 503, body: "" });
    return route.continue();
  });
  await as(page, "alice");
  await expect(page.getByTestId("schema")).toBeVisible();
  await page.getByRole("button", { name: "UMF source" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("did not load (Schema browser initialization timed out)", {
    timeout: 40_000,
  });
  await alert.getByRole("button", { name: "Retry" }).click();
  await expect(page.frameLocator(FRAME).locator("#inspector")).toContainText("Use Case", {
    timeout: 20_000,
  });
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(await page.locator("iframe").count()).toBe(1);
});

// Package 1.1.2, measured in Chromium inside the frame with the console's theme variables (white
// paper in light, #161b24 in dark). Contrast ratios, light / dark:
//   entry heading   neutral 17.44 / 14.46, info 8.40 / 10.34, positive 7.80 / 10.23,
//                   warning 8.19 / 10.60, negative 8.65 / 8.58   (1.1.1: info 4.35, warning 4.49 in
//                   light; 3.56-3.97 for every coloured tone in dark)
//   legend          neutral 17.15 / 11.85, info 7.08, positive 6.86, warning 7.26, negative 7.15
//                   in both (fixed light pills)                (1.1.1: the same)
//   record map SVG  every tone 17.44 / 14.46: drawn in --ink   (1.1.1: 7.8-8.65 / 2.0-2.21)
//   numbers         17.44 / 14.65                              (1.1.1: 1.00, the circle's colour)
// The tests assert >= 4.5:1, the WCAG AA bound, so a regression below it fails.
for (const scheme of ["light", "dark"] as const) {
  test(`${scheme}: the console's badges in their real tones are readable, one line each, and the relationship numbers are painted`, async ({
    page,
  }) => {
    const problems = watch(page);
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 1440, height: 1600 });
    await as(page, "alice");
    const frame = await openUmfSource(page);
    await expect.poll(() => recordTones(frame, "Use Case")).toEqual(RECORD_TONES);
    const p = await paint(page);
    expect(p.theme).toBe(scheme);
    expect(p.heading.map((a) => [a.text, a.tone])).toEqual([
      ["record: memory", "positive"],
      ["replica: memory_replica", "neutral"],
    ]);
    expect(p.legend.map((a) => [a.text, a.tone])).toEqual([
      ["follows: memory, memory_replica", "info"],
    ]);
    expect(p.map.map((a) => [a.text, a.tone])).toEqual([
      ["memory · mutable", "positive"],
      ["memory_replica · read-only", "neutral"],
      ["memory · mutable", "positive"],
      ["memory_replica · read-only", "neutral"],
    ]);
    for (const a of [...p.heading, ...p.legend, ...p.map, ...p.numbers]) {
      expect(a.visible, `${a.text} is drawn`).toBe(true);
      expect(a.ratio, `${a.text} (${a.tone ?? "number"}) ${a.ratio}:1`).toBeGreaterThanOrEqual(4.5);
    }
    expect(p.numbers.map((n) => n.text)).toEqual(["1"]);
    // Two annotations per record: neither overlaps the other or the property count, all inside.
    expect(p.records.map((r) => [r.notes, r.overlaps, r.inside])).toEqual([
      [2, 0, true],
      [2, 0, true],
    ]);
    expect(problems, problems.join("\n")).toEqual([]);
  });

  test(`${scheme}: every tone the contract allows is readable where the browser draws it; three annotations on a record still clear the count`, async ({
    page,
  }) => {
    const problems = watch(page);
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 1440, height: 1600 });
    await as(page, "alice");
    await openUmfSource(page);
    const all = TONES.map((t) => ({ badge: `tone ${t}`, tone: t, tooltip: t }));
    await probeFrame(page, {
      "arras:catalog": all,
      [JSON.stringify(["catalog", "UseCase"])]: all.slice(0, 2),
      [JSON.stringify(["catalog", "Solution"])]: all.slice(2),
      [JSON.stringify(["relationship", "catalog", "solution-addresses"])]: all,
    });
    const p = await paint(page, 'iframe[title="probe"]');
    expect(p.theme).toBe(scheme);
    for (const where of [p.heading, p.legend, p.map])
      expect(where.map((a) => a.tone)).toEqual([...TONES]);
    for (const a of [...p.heading, ...p.legend, ...p.map, ...p.numbers]) {
      expect(a.visible, `${a.text} is drawn`).toBe(true);
      expect(a.ratio, `${a.text} ${a.ratio}:1`).toBeGreaterThanOrEqual(4.5);
    }
    expect(p.records.map((r) => [r.notes, r.overlaps, r.inside])).toEqual([
      [2, 0, true],
      [3, 0, true],
    ]);
    expect(problems, problems.join("\n")).toEqual([]);
  });
}

test("the original source pane is reached with Tab and scrolls with the keyboard", async ({
  page,
}) => {
  const problems = watch(page);
  await as(page, "alice");
  const frame = await openUmfSource(page);
  await frame
    .locator("#inspector")
    .getByText("Original schema source", { exact: true })
    .first()
    .click();
  const pane = frame
    .locator("#inspector details", { hasText: "Original schema source" })
    .locator("pre")
    .first();
  await expect(pane).toBeVisible();
  await expect(pane).toHaveAttribute("tabindex", "0");
  const focused = () => pane.evaluate((p) => p.ownerDocument.activeElement === p);
  for (let i = 0; i < 40 && !(await focused()); i++) await page.keyboard.press("Tab");
  expect(await focused()).toBe(true);
  expect(
    await pane.evaluate(
      (p) => p.matches(":focus-visible") && getComputedStyle(p).outlineStyle !== "none",
    ),
  ).toBe(true);
  expect(await pane.evaluate((p) => p.scrollHeight > p.clientHeight)).toBe(true);
  await page.keyboard.press("PageDown");
  await expect.poll(() => pane.evaluate((p) => p.scrollTop)).toBeGreaterThan(0);
  expect(problems, problems.join("\n")).toEqual([]);
});

test("selecting records and a relationship fetches nothing: the catalog's entries are inline", async ({
  page,
}) => {
  const problems = watch(page);
  await as(page, "alice");
  const frame = await openUmfSource(page);
  const fetched = () =>
    page
      .locator(FRAME)
      .evaluate((f: HTMLIFrameElement) =>
        (
          (f.contentWindow?.performance.getEntriesByType("resource") ??
            []) as PerformanceResourceTiming[]
        ).map((e) => e.name),
      );
  const before = await fetched();
  await frame.locator('.ontology-map svg a[aria-label^="Inspect record Solution"]').first().click();
  await expect(frame.locator("#inspector")).toContainText("Solution");
  await frame.locator(".map-relationships button").first().click();
  await expect(page.getByTestId("umf-selection")).toContainText("relationship solution-addresses");
  expect(await fetched()).toEqual(before);
  expect(before.every((u) => new URL(u).pathname.startsWith("/umf-explorer/"))).toBe(true);
  expect(problems, problems.join("\n")).toEqual([]);
});

// Last in the run: it registers a second module on the shared dev host, which stays registered.
test("another module of the same catalog is a select() in the same frame, not a remount", async ({
  page,
  request,
  baseURL,
}) => {
  const problems = watch(page);
  const intake = CATALOG_TEXT.replaceAll('"catalog"', '"intake"');
  const r = await request.post("/api/dev/control", {
    data: { op: "register", document: intake },
    headers: { origin: defined(baseURL, "baseURL") },
  });
  expect(r.status(), await r.text()).toBe(200);
  await as(page, "alice");
  const frame = await openUmfSource(page);
  await mark(page);
  const frameHash = () =>
    page.locator(FRAME).evaluate((f: HTMLIFrameElement) => f.contentWindow?.location.hash);
  await page
    .getByRole("navigation", { name: "Modules" })
    .getByRole("button", { name: /^intake/ })
    .click();
  await expect(page).toHaveURL(/#\/operate\/intake\/model\?view=umf$/);
  await expect.poll(frameHash).toBe("#schema=arras%3Aintake");
  await expect(page.getByTestId("umf-selection")).toContainText("Selected: intake");
  expect(await marked(page)).toBe(true);
  expect(await page.locator("iframe").count()).toBe(1);
  // Its records carry its own badges: the annotations cover every module of the catalog.
  await expect.poll(() => recordBadges(frame, "Use Case")).toEqual(RECORD_BADGES);
  await frame.locator('.ontology-map svg a[aria-label^="Inspect record Use Case"]').first().click();
  await expect(
    page.getByTestId("umf-selection").getByRole("button", { name: "Open UseCase in Entities" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Modules" })
    .getByRole("button", { name: /^catalog/ })
    .click();
  await expect.poll(frameHash).toBe("#schema=arras%3Acatalog");
  expect(await marked(page)).toBe(true);
  expect(problems, problems.join("\n")).toEqual([]);
});
