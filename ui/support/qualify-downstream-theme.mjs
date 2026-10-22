#!/usr/bin/env node
// SPDX-License-Identifier: MIT OR Apache-2.0
// Browser qualification for an Arras host URL. The host owns rendering; this runner checks delivered UI behavior.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

function usage() {
  return "Usage: arras-ui-qualify <http(s) URL> [--host-build] [--console] [--output <dir>] [--baselines <dir>] [--update-baselines] [--help]";
}
function safeTarget(value) {
  const target = new URL(value);
  return `${target.origin}${target.pathname}`;
}
function safeDiagnostic(error) {
  return String(error?.message ?? "accessibility analysis failed")
    .replace(/https?:\/\/[^\s"'<>]+/gi, "[URL]")
    .replace(/file:\/\/[^\s"'<>]+/gi, "[file]")
    .replace(/(token|secret|password|authorization)=[^\s&"']+/gi, "$1=[redacted]")
    .replace(/[\r\n]+/g, " ")
    .slice(0, 400);
}

function parseArgs(args) {
  const options = {
    hostBuild: false,
    console: false,
    output: resolve(process.cwd(), "arras-ui-qualification"),
    baselines: undefined,
    updateBaselines: false,
    url: undefined,
    help: false,
    seen: new Set(),
  };
  const single = (flag) => {
    if (options.seen.has(flag)) throw new Error("duplicate option");
    options.seen.add(flag);
  };
  for (let index = 0; index < args.length; index++) {
    const arg = args[index];
    if (arg === "--help" || arg === "-h") { single("--help"); options.help = true; }
    else if (arg === "--host-build") { single(arg); options.hostBuild = true; }
    else if (arg === "--console") { single(arg); options.console = true; }
    else if (arg === "--output") {
      single(arg);
      const value = args[++index];
      if (!value || value.startsWith("--")) throw new Error("--output requires a directory path");
      options.output = resolve(value);
    } else if (arg === "--baselines") {
      single(arg);
      const value = args[++index];
      if (!value || value.startsWith("--")) throw new Error("--baselines requires a directory path");
      options.baselines = resolve(value);
    } else if (arg === "--update-baselines") {
      single(arg);
      options.updateBaselines = true;
    } else if (arg.startsWith("-")) throw new Error("unknown option");
    else if (options.url) throw new Error("unexpected extra argument");
    else options.url = arg;
  }
  if (options.help) {
    if (options.seen.size !== 1 || options.url) throw new Error("--help must be used by itself");
    return options;
  }
  if (!options.url) throw new Error("a target URL is required");
  let parsed;
  try {
    parsed = new URL(options.url);
  } catch {
    throw new Error("the target must be an absolute http:// or https:// URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:")
    throw new Error("the target must use http:// or https://");
  if (parsed.username || parsed.password) throw new Error("target URLs must not contain user information");
  if (options.updateBaselines && !options.baselines)
    throw new Error("--update-baselines requires --baselines <dir>");
  if (options.updateBaselines && process.platform !== "darwin")
    throw new Error("baseline updates are supported only on macOS");
  return options;
}

let options;
try {
  options = parseArgs(process.argv.slice(2));
} catch (error) {
  process.stderr.write(`${error.message}\n${usage()}\n`);
  process.exit(2);
}
if (options.help) {
  process.stdout.write(`${usage()}\n`);
  process.exit(0);
}
let qualificationPhase = "validating target";

async function qualify() {
qualificationPhase = "loading browser tools";
let AxeBuilder;
let chromium;
try {
  ({ default: AxeBuilder } = await import("@axe-core/playwright"));
  ({ chromium } = await import("@playwright/test"));
} catch (error) {
  throw new Error("Browser qualification requires optional peers @playwright/test@1.63.0 and @axe-core/playwright@4.13.0 plus a compatible Chromium browser. Install them manually; this command does not download dependencies or browsers.");
}

const hostBuild = options.hostBuild;
const surface = options.console ? "console" : "browser";
const delivery = hostBuild ? "compiled-host" : "prebuilt-page";
const themeId = "external-theme";
const screenshotDir = options.output;
const baselineDir = options.baselines;
const updateBaselines = options.updateBaselines;
const skipVisualComparison = process.platform !== "darwin";
mkdirSync(screenshotDir, { recursive: true });
const url = options.url;
const safeUrl = safeTarget(url);
const focusMeasurements = [];
function rgb(color) {
  const hex = /^#([0-9a-f]{6})$/i.exec(color);
  if (hex) return [0, 2, 4].map((offset) => Number.parseInt(hex[1].slice(offset, offset + 2), 16));
  const values = /^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:\s*,\s*([\d.]+))?\)$/i.exec(color);
  assert.ok(values, `unsupported computed CSS color ${color}`);
  assert.ok(values[4] === undefined || Number(values[4]) === 1, `translucent color cannot be used for contrast: ${color}`);
  const channels = values.slice(1, 4).map(Number);
  assert.ok(channels.every((value) => Number.isInteger(value) && value >= 0 && value <= 255), `computed RGB channels are out of range: ${color}`);
  return channels;
}
function luminance(color) {
  const channels = rgb(color)
    .map((value) => value / 255)
    .map((value) => (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4));
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
function contrast(first, second) {
  const [light, dark] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}
async function assertFocusContrast(page, description) {
  qualificationPhase = `${description}: measuring focus indicator`;
  const indicator = await page.evaluate(() => {
    const element = document.activeElement;
    if (!(element instanceof HTMLElement)) throw new Error("focused element is unavailable");
    const measured = window.__arrasMeasureFocusBackdrop(element);
    const style = getComputedStyle(element);
    const outlineVisible = style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) > 0;
    const shadowColor = /rgba?\([^)]*\)|#[\da-f]{6}/i.exec(style.boxShadow)?.[0];
    return {
      visible: outlineVisible || style.boxShadow !== "none",
      color: outlineVisible ? style.outlineColor : shadowColor,
      width: outlineVisible ? Number.parseFloat(style.outlineWidth) : undefined,
      background: measured.background,
    };
  });
  assert.ok(indicator.visible && indicator.color, `${description}: focus indicator must have a measurable color`);
  if (indicator.width !== undefined) assert.ok(indicator.width >= 2, `${description}: focus outline must be at least 2px`);
  const ratio = contrast(indicator.color, indicator.background);
  qualificationPhase = `${description}: focus contrast ${ratio.toFixed(2)}:1`;
  assert.ok(ratio >= 3, `${description}: focus indicator/background contrast`);
  focusMeasurements.push({ description, indicator: indicator.color, background: indicator.background, contrast: Number(ratio.toFixed(2)) });
}
async function installAndCheckBackdropProbe(page) {
  const result = await page.evaluate(() => {
    window.__arrasMeasureFocusBackdrop = (element) => {
      const parse = (value) => {
        const match = /^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:\s*,\s*([\d.]+))?\)$/i.exec(value);
        if (!match) throw new Error("unsupported computed background color");
        const channels = match.slice(1, 4).map(Number);
        const alpha = match[4] === undefined ? 1 : Number(match[4]);
        if (channels.some((channel) => !Number.isInteger(channel) || channel < 0 || channel > 255) || alpha < 0 || alpha > 1)
          throw new Error("computed focus colors are out of range");
        return [...channels, alpha];
      };
      const over = (front, back) => {
        const alpha = front[3] + back[3] * (1 - front[3]);
        if (!alpha) return [0, 0, 0, 0];
        return [0, 1, 2].map((i) => Math.round((front[i] * front[3] + back[i] * back[3] * (1 - front[3])) / alpha)).concat(alpha);
      };
      let backdrop = [0, 0, 0, 0];
      for (let node = element; node; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (Number.parseFloat(style.opacity) !== 1) throw new Error("ancestor opacity is unsupported for focus contrast");
        if (style.backgroundImage !== "none") throw new Error("gradient focus backgrounds are unsupported");
        if (node !== element && backdrop[3] < 1) backdrop = over(backdrop, parse(style.backgroundColor));
      }
      if (backdrop[3] < 1) {
        const probe = document.createElement("span");
        probe.style.backgroundColor = "Canvas";
        document.documentElement.append(probe);
        backdrop = over(backdrop, parse(getComputedStyle(probe).backgroundColor));
        probe.remove();
      }
      return { background: `rgb(${backdrop[0]}, ${backdrop[1]}, ${backdrop[2]})` };
    };
    const outer = document.createElement("div");
    const inner = document.createElement("div");
    const button = document.createElement("button");
    outer.style.cssText = "position:fixed;left:-10000px;top:0;background:rgb(0, 0, 255)";
    inner.style.backgroundColor = "rgba(255, 0, 0, 0.4)";
    outer.append(inner);
    inner.append(button);
    document.body.append(outer);
    const composite = window.__arrasMeasureFocusBackdrop(button).background;
    outer.style.opacity = "0.5";
    let rejectedOpacity = false;
    try { window.__arrasMeasureFocusBackdrop(button); }
    catch (error) { rejectedOpacity = /ancestor opacity is unsupported/.test(error.message); }
    inner.style.backgroundColor = "rgb(255, 0, 0)";
    outer.style.opacity = "1";
    let rejectedOpaqueChildOpacity = false;
    try {
      window.__arrasMeasureFocusBackdrop(button);
      outer.style.opacity = "0.5";
      window.__arrasMeasureFocusBackdrop(button);
    } catch (error) {
      rejectedOpaqueChildOpacity = /ancestor opacity is unsupported/.test(error.message);
    }
    outer.remove();
    return { composite, rejectedOpacity, rejectedOpaqueChildOpacity };
  });
  assert.equal(result.composite, "rgb(102, 0, 153)", "focus backdrop must composite the nearest translucent child over its opaque parent");
  assert.ok(result.rejectedOpacity, "focus measurement must reject opacity on any ancestor");
  assert.ok(result.rejectedOpaqueChildOpacity, "focus measurement must inspect opacity beyond an already opaque child background");
}
qualificationPhase = "launching Chromium";
const browser = await chromium.launch({ headless: true });
const browserVersion = browser.version();
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  for (const scheme of ["light", "dark"]) {
    qualificationPhase = `navigating ${surface} in ${scheme} mode`;
    await page.emulateMedia({ colorScheme: scheme });
    const target = surface === "console" ? `${url.replace(/#.*$/, "")}#admin` : url;
    await page.goto(target, { waitUntil: "networkidle" });
    qualificationPhase = `checking focus backdrop composition in ${scheme} mode`;
    await installAndCheckBackdropProbe(page);
    if (!hostBuild) {
      qualificationPhase = `checking ${surface} theme assets in ${scheme} mode`;
      const theme = await page.locator('link[rel="stylesheet"][href*="/theme-assets/"]').count();
      assert.ok(theme > 0, "external theme stylesheet is not linked through the digest route");
      assert.ok(
        await page.locator('link[rel="icon"][href*="/theme-assets/"]').count(),
        "theme favicon is missing",
      );
      const themeResponses = await page.evaluate(() =>
        performance
          .getEntriesByType("resource")
          .filter((entry) => entry.name.includes("/theme-assets/"))
          .map((entry) => ({
            url: entry.name,
            sameOrigin: new URL(entry.name).origin === location.origin,
          })),
      );
      assert.ok(
        themeResponses.length > 0 && themeResponses.every((entry) => entry.sameOrigin),
        "theme assets must be same-origin",
      );
    }
    const root = page.locator(".arras-root").first();
    qualificationPhase = `checking rendered Arras root in ${scheme} mode`;
    assert.ok(await root.count(), "host fixture must render the public Arras root");
    qualificationPhase = `checking themed widgets in ${scheme} mode`;
    const widgetSelectors = hostBuild
      ? [
          "[data-theme-button]",
          "[data-theme-text-field]",
          "[data-theme-text-area]",
          "[data-theme-select]",
          "[data-theme-notice]",
          "[data-theme-mark]",
        ]
      : ["button"];
    for (const selector of widgetSelectors) {
      assert.ok(
        await root.locator(selector).count(),
        `host fixture is missing themed widget ${selector}`,
      );
    }
    if (hostBuild) {
      qualificationPhase = `checking app-owned themed controls in ${scheme} mode`;
      const appSelector = surface === "console" ? '[data-testid="console-header"]' : ".gb";
      const app = page.locator(".arras-root").filter({ has: page.locator(appSelector) }).last();
      assert.ok(await app.count(), `${surface} public ArrasApp did not mount`);
      assert.ok(
        await app.locator("[data-theme-mark]").count(),
        `${surface} ArrasApp did not consume the host Mark for its configured brand`,
      );
      const appButton = root.locator('[aria-label="Downstream widget controls"] button[data-theme-button]').first();
      assert.ok(await appButton.count(), "host fixture is missing its deterministic keyboard opener");
      await appButton.focus();
      await page.keyboard.press("ControlOrMeta+k");
      const palette = app.getByRole("dialog", { name: "Command palette" });
      await palette.waitFor({ state: "visible" });
      const paletteField = palette.getByRole("combobox", { name: "Search entities and commands" });
      assert.ok(
        await paletteField.evaluate((node) => node.matches("[data-theme-text-field]")),
        `${surface} app-owned palette did not consume the host TextField`,
      );
      assert.ok(
        await palette.locator("button[data-theme-button]").count(),
        `${surface} app-owned palette did not consume the host Button`,
      );
      await paletteField.fill("entity");
      await page.keyboard.press("Escape");
      assert.ok(
        await appButton.evaluate((node) => node === document.activeElement),
        `${surface} palette did not restore keyboard focus to its opener`,
      );
    }
    qualificationPhase = `validating rendered theme tokens in ${scheme} mode`;
    const tokens = await root.evaluate((node) => {
      const style = getComputedStyle(node);
      return [
        "--arras-color-text",
        "--arras-color-text-muted",
        "--arras-color-surface",
        "--arras-color-surface-sunken",
        "--arras-color-ground",
        "--arras-color-border",
        "--arras-color-accent",
        "--arras-color-on-accent",
        "--arras-radius-control",
        "--arras-radius-card",
        "--arras-font-body",
        "--arras-font-mono",
        "--arras-font-size-small",
        "--arras-font-size-heading",
        "--arras-state-live",
        "--arras-state-limited",
        "--arras-state-closed",
        "--arras-state-purchasing",
      ].map((token) => [token, style.getPropertyValue(token).trim()]);
    });
    assert.equal(tokens.length, 18);
    assert.ok(
      tokens.every(([, value]) => value),
      `all role tokens must resolve in ${scheme} mode`,
    );
    const noncolor = Object.fromEntries(
      tokens.filter(([name]) => /radius|font-(size|body|mono)/.test(name)),
    );
    assert.match(noncolor["--arras-radius-control"], /^(?:\d*\.)?\d+(?:px|rem|em)$/);
    assert.match(noncolor["--arras-radius-card"], /^(?:\d*\.)?\d+(?:px|rem|em)$/);
    assert.match(noncolor["--arras-font-size-small"], /^(?:\d*\.)?\d+(?:px|rem|em)$/);
    assert.match(noncolor["--arras-font-size-heading"], /^(?:\d*\.)?\d+(?:px|rem|em)$/);
    assert.ok(Number.parseFloat(noncolor["--arras-font-size-small"]) > 0, `${scheme}: body font size must be positive`);
    assert.ok(Number.parseFloat(noncolor["--arras-font-size-heading"]) > 0, `${scheme}: heading font size must be positive`);
    const fontSupport = await root.evaluate((node) => {
      const style = getComputedStyle(node);
      const body = style.getPropertyValue("--arras-font-body").trim();
      const mono = style.getPropertyValue("--arras-font-mono").trim();
      return { body: CSS.supports("font-family", body), mono: CSS.supports("font-family", mono) };
    });
    assert.ok(fontSupport.body && fontSupport.mono, `${scheme}: body and mono font tokens must be valid font-family values`);
    const pairs = await root.evaluate((node) => {
      const style = getComputedStyle(node);
      const get = (name) => style.getPropertyValue(name).trim();
      const color = (name) => {
        const value = get(name);
        if (!CSS.supports("color", value)) throw new Error(`invalid color token ${name}`);
        const probe = document.createElement("span");
        probe.style.color = value;
        document.documentElement.append(probe);
        const normalized = getComputedStyle(probe).color;
        probe.remove();
        return normalized;
      };
      return {
        text: color("--arras-color-text"),
        muted: color("--arras-color-text-muted"),
        surface: color("--arras-color-surface"),
        sunken: color("--arras-color-surface-sunken"),
        ground: color("--arras-color-ground"),
        accent: color("--arras-color-accent"),
        onAccent: color("--arras-color-on-accent"),
        border: color("--arras-color-border"),
        live: color("--arras-state-live"),
        limited: color("--arras-state-limited"),
        closed: color("--arras-state-closed"),
        purchasing: color("--arras-state-purchasing"),
      };
    });
    assert.ok(contrast(pairs.text, pairs.surface) >= 4.5, `${scheme}: text/surface contrast`);
    assert.ok(contrast(pairs.muted, pairs.surface) >= 4.5, `${scheme}: muted/surface contrast`);
    for (const name of ["sunken", "ground"]) {
      assert.ok(contrast(pairs.text, pairs[name]) >= 4.5, `${scheme}: text/${name} contrast`);
      assert.ok(contrast(pairs.muted, pairs[name]) >= 4.5, `${scheme}: muted/${name} contrast`);
    }
    assert.ok(
      contrast(pairs.onAccent, pairs.accent) >= 4.5,
      `${scheme}: on-accent/accent contrast`,
    );
    assert.ok(contrast(pairs.border, pairs.surface) >= 3, `${scheme}: border/surface contrast`);
    for (const name of ["live", "limited", "closed", "purchasing"])
      assert.ok(
        contrast(pairs[name], pairs.surface) >= 3,
        `${scheme}: state ${name}/surface contrast`,
      );
    qualificationPhase = `running accessibility checks in ${scheme} mode`;
    let violations;
    try {
      violations = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
    } catch (error) {
      qualificationPhase = `accessibility analysis failed in ${scheme} mode: ${safeDiagnostic(error)}`;
      throw error;
    }
    const violationIds = violations.violations.map(({ id }) => id);
    if (violationIds.length) qualificationPhase = `accessibility violations in ${scheme}: ${violationIds.join(",")}`;
    assert.deepEqual(
      violationIds,
      [],
      `${scheme} axe violations`,
    );
    if (hostBuild) {
      const widgetControls = root.getByRole("region", { name: "Downstream widget controls" });
      const expected = [
        "[data-theme-button]",
        "[data-theme-text-field]",
        "[data-theme-text-area]",
        "[data-theme-select]",
      ];
      const firstControl = widgetControls.locator(expected[0]).first();
      await firstControl.focus();
      assert.ok(
        await firstControl.evaluate((node) => node === document.activeElement),
        "host theme Button must be focusable",
      );
      await page.keyboard.press("Tab");
      await page.keyboard.press("Shift+Tab");
      assert.ok(
        await firstControl.evaluate((node) => node === document.activeElement),
        "keyboard navigation returns to the host theme Button with a visible focus indicator",
      );
      await assertFocusContrast(page, `${scheme}: host Button focus`);
      await page.keyboard.press("Tab");
      for (const [index, selector] of expected.slice(1).entries()) {
        assert.ok(
          await widgetControls
            .locator(selector)
            .first()
            .evaluate((node) => node === document.activeElement),
          `keyboard order reaches ${selector}`,
        );
        await assertFocusContrast(page, `${scheme}: ${selector} focus`);
        if (index < expected.length - 2) await page.keyboard.press("Tab");
      }
    } else {
      const control = root
        .locator(
          "button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled)",
        )
        .first();
      assert.ok(
        (await control.count()) > 0,
        "the served interface has a keyboard-focusable control",
      );
      await control.focus();
      await page.keyboard.press("Tab");
      const focused = await page.evaluate(() => document.activeElement !== document.body);
      assert.ok(
        focused,
        "keyboard Tab navigation must retain a visible focus indicator",
      );
      await assertFocusContrast(page, `${scheme}: host focus`);
    }
    qualificationPhase = `capturing and comparing ${surface} in ${scheme} mode`;
    const screenshotName = `${themeId}-${delivery}-${surface}-${scheme}-${process.platform}.png`;
    const screenshotPath = join(screenshotDir, screenshotName);
    const screenshot = await page.screenshot({
      path: screenshotPath,
      fullPage: true,
      animations: "disabled",
    });
    if (baselineDir && !skipVisualComparison) {
      const baselinePath = join(baselineDir, screenshotName);
      if (updateBaselines) {
        mkdirSync(baselineDir, { recursive: true });
        writeFileSync(baselinePath, screenshot);
      } else {
        assert.ok(
          existsSync(baselinePath),
          `missing visual baseline ${baselinePath}; capture explicitly with --update-baselines`,
        );
        const baseline = readFileSync(baselinePath).toString("base64");
        const diff = await page.evaluate(
          async ({ current, reference }) => {
            const decode = async (base64) => {
              const bytes = Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
              return createImageBitmap(new Blob([bytes], { type: "image/png" }));
            };
            const [a, b] = await Promise.all([decode(current), decode(reference)]);
            if (a.width !== b.width || a.height !== b.height)
              return { ratio: 1, dimensionsMatch: false };
            const canvas = document.createElement("canvas");
            canvas.width = a.width;
            canvas.height = a.height;
            const context = canvas.getContext("2d", { willReadFrequently: true });
            context.drawImage(a, 0, 0);
            const first = context.getImageData(0, 0, a.width, a.height).data;
            context.clearRect(0, 0, a.width, a.height);
            context.drawImage(b, 0, 0);
            const second = context.getImageData(0, 0, b.width, b.height).data;
            let different = 0;
            for (let i = 0; i < first.length; i += 4) {
              if (
                Math.max(
                  Math.abs(first[i] - second[i]),
                  Math.abs(first[i + 1] - second[i + 1]),
                  Math.abs(first[i + 2] - second[i + 2]),
                ) > 12
              )
                different++;
            }
            return { ratio: different / (a.width * a.height), dimensionsMatch: true };
          },
          { current: screenshot.toString("base64"), reference: baseline },
        );
        assert.ok(
          diff.dimensionsMatch && diff.ratio <= 0.01,
          `${screenshotName} differs from baseline (${(diff.ratio * 100).toFixed(2)}% pixels)`,
        );
      }
    }
  }
} finally {
  await browser.close();
}
const receipt = {
  schema: "arras.ui.qualification-receipt.v1",
  target: safeUrl,
  route: delivery,
  surface,
  platform: process.platform,
  browser: `Chromium ${browserVersion}`,
  visual: baselineDir
    ? skipVisualComparison
      ? "comparison-skipped-platform"
      : updateBaselines
        ? "baselines-updated"
        : "compared"
    : "screenshots-only-unqualified",
  screenshots: ["light", "dark"].map((scheme) => `${themeId}-${delivery}-${surface}-${scheme}-${process.platform}.png`),
  checks: ["axe-wcag21aa", "theme-tokens", "contrast", "keyboard-focus", ...(hostBuild ? ["arras-app-theme-provider", "command-palette-keyboard"] : [])],
  focusMeasurements,
};
writeFileSync(join(screenshotDir, `${themeId}-${delivery}-${surface}-${process.platform}.json`), `${JSON.stringify(receipt, null, 2)}\n`);
process.stdout.write(`${JSON.stringify(receipt)}\n`);
}

try {
  await qualify();
} catch (error) {
  const route = options.hostBuild ? "compiled-host" : "prebuilt-page";
  const surface = options.console ? "console" : "browser";
  const receipt = {
    schema: "arras.ui.qualification-receipt.v1",
    status: "failed",
    target: safeTarget(options.url),
    route,
    surface,
    platform: process.platform,
    visual: options.baselines
      ? process.platform === "darwin"
        ? "comparison-failed-or-incomplete"
        : "comparison-skipped-platform"
      : "screenshots-only-unqualified",
    phase: qualificationPhase,
    error: "qualification did not pass; see the runner output for the failing gate",
  };
  try {
    mkdirSync(options.output, { recursive: true });
    writeFileSync(
      join(options.output, `external-theme-${route}-${surface}-${process.platform}-failure.json`),
      `${JSON.stringify(receipt, null, 2)}\n`,
    );
  } catch {}
  process.stderr.write(`${receipt.error} (${error?.name ?? "unknown error"})\n`);
  process.exitCode = 1;
}
