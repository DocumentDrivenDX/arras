// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { EXPECTED_SURFACE, HOST_APPEARANCE_PROVIDER } from "./acceptance";

// The library's styles must not reach a host page, and a host's must not break the library (ADR-027).
// The built page stands in for a host: markup and rules a host might have are planted around the root.
// A host's own `:root` tokens use the same names as ours (`--accent`, `--bg`), and its element rules are
// the kind a design system writes.
//
// Assumption: the host installs no appearance provider. The specs that drive the appearance (`data-appearance`
// on the page, nested providers, inline `color-scheme`, the OS preference) put their own provider around the
// root, which only means something where nothing above it already says one. A host that sets `data-appearance`
// or `color-scheme` above the root, or wraps a design-system provider that does, sets
// `hostAppearanceProvider: true` in `createAcceptanceConfig`: those specs are then skipped, and the one that
// asserts "the library sets none" checks the Arras subtree alone (the appearance test below).
const SKIP_BARE_HOST =
  "the host installs its own appearance provider (hostAppearanceProvider): this spec drives the appearance on a bare host";

const TOKENS = { lightBg: EXPECTED_SURFACE.light, darkBg: EXPECTED_SURFACE.dark };
// The page the dev host serves loads no theme (ADR-029), so the library's own tokens are what most specs
// measure; THEME is what a host's role tokens set in the two specs that plant them.
const THEME = { lightBg: "rgb(240, 238, 230)", darkBg: "rgb(27, 26, 25)" };

async function openWithHost(page: Page) {
  await page.goto("/");
  await expect(page.locator(".arras-root")).toBeVisible();
  await page.evaluate(() => {
    const probe = document.createElement("div");
    probe.id = "host-probe";
    probe.innerHTML =
      '<h1>h</h1><a href="#x">a</a><button>b</button><table><tr><td>c</td></tr></table><img alt="i" width="4" height="4"><p>p</p>';
    document.body.append(probe);
  });
}

// The page's policy refuses an inline <style>, so a host's rules go in by the CSSOM, which it does not govern.
const hostCss = (page: Page, css: string) =>
  page.evaluate((text) => {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(text);
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
  }, css);

const style = (page: Page, selector: string, prop: string) =>
  page.evaluate(
    ([s, p]) =>
      getComputedStyle(document.querySelector(s as string) as Element).getPropertyValue(
        p as string,
      ),
    [selector, prop],
  );

test.describe("host isolation", () => {
  test("the library's reset and utilities do not reach the host's elements", async ({ page }) => {
    await openWithHost(page);
    // Browser defaults: Tailwind's preflight would make the heading inherit its size, the link inherit
    // its colour with no underline, and the button transparent.
    expect(await style(page, "#host-probe h1", "font-size")).toBe("32px");
    expect(await style(page, "#host-probe a", "text-decoration-line")).toBe("underline");
    expect(await style(page, "#host-probe button", "background-color")).not.toBe(
      "rgba(0, 0, 0, 0)",
    );
    expect(await style(page, "#host-probe table", "border-collapse")).toBe("separate");
    expect(await style(page, "#host-probe p", "margin-top")).not.toBe("0px");
    expect(await style(page, "body", "background-color")).toBe("rgba(0, 0, 0, 0)");
  });

  test("the library's tokens are on its root only, and a host's tokens of the same names do not change them", async ({
    page,
  }) => {
    await openWithHost(page);
    expect(await style(page, "html", "--accent")).toBe("");
    expect(await style(page, "#host-probe", "--bg")).toBe("");
    const ours = await style(page, ".arras-root", "--accent");
    expect(ours.trim()).not.toBe("");
    await hostCss(
      page,
      ":root { --accent: #ff0000; --bg: #000000; --fg: #00ff00; --font-sans: serif }",
    );
    expect(await style(page, ".arras-root", "--accent")).toBe(ours);
    expect(await style(page, ".arras-root", "background-color")).toBe(TOKENS.lightBg);
  });

  test("a host's layered utilities and element rules do not undo the library's, and its one-class button rule wins over the control reset", async ({
    page,
  }) => {
    await openWithHost(page);
    // The kind of rule a Tailwind host has: its own utilities and reset, in its own layers.
    await hostCss(
      page,
      "@layer base { button, a { color: rgb(255, 0, 0); padding: 40px } } @layer utilities { .flex { display: none } .p-3 { padding: 40px } }",
    );
    const probe = await page.evaluate(() => {
      const el = document.querySelector(".arras-root .flex") as Element;
      return { display: getComputedStyle(el).display };
    });
    expect(probe.display).not.toBe("none");
    // Inside the browser, a design system's themed button (one unlayered class) beats the library's control
    // reset without `!important`; an unstyled control still takes the text colour it sits in.
    await page.goto("/#/explore/catalog");
    await expect(page.locator(".arras-root .gb")).toBeVisible();
    // A design system's themed button: one class, an accent fill and the text colour that goes with it.
    await hostCss(
      page,
      ".host-btn { background-color: rgb(31, 79, 216); color: rgb(255, 255, 255); font-size: 17px }",
    );
    await page.evaluate(() => {
      const button = document.createElement("button");
      button.id = "host-btn";
      button.className = "host-btn";
      button.textContent = "Themed";
      document.querySelector(".arras-root .gb")?.append(button);
    });
    expect(await style(page, "#host-btn", "color")).toBe("rgb(255, 255, 255)");
    expect(await style(page, "#host-btn", "font-size")).toBe("17px");
    // The reset still applies to a control the host did not style: it takes the text colour it sits in.
    const inherited = await page.evaluate(() => {
      const plain = document.createElement("button");
      document.querySelector(".arras-root .gb")?.append(plain);
      const gb = document.querySelector(".arras-root .gb") as Element;
      return [getComputedStyle(plain).color, getComputedStyle(gb).color];
    });
    expect(inherited[0]).toBe(inherited[1]);
  });

  test("appearance follows the host's data-appearance, then the OS, and the library sets none", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await openWithHost(page);
    if (HOST_APPEARANCE_PROVIDER) {
      // The host's provider owns the appearance, so only what is Arras's own is checked: nothing on or beneath
      // its root says an appearance, whichever way the OS preference goes.
      const arrasAppearance = () =>
        page.evaluate(() =>
          [
            document.querySelector(".arras-root")?.hasAttribute("data-appearance"),
            ...[...document.querySelectorAll(".arras-root, .arras-root *")].map(
              (e) =>
                e.hasAttribute("data-appearance") ||
                e.hasAttribute("data-theme") ||
                ((e as HTMLElement).style?.colorScheme ?? "") !== "",
            ),
          ].some(Boolean),
        );
      expect(await arrasAppearance()).toBe(false);
      await page.emulateMedia({ colorScheme: "dark" });
      expect(await arrasAppearance()).toBe(false);
      return;
    }
    const bg = () => style(page, ".arras-root", "background-color");
    expect(await bg()).toBe(TOKENS.lightBg);

    await page.evaluate(() => document.documentElement.setAttribute("data-appearance", "dark"));
    expect(await bg()).toBe(TOKENS.darkBg);

    await page.evaluate(() => document.documentElement.setAttribute("data-appearance", "light"));
    await page.emulateMedia({ colorScheme: "dark" });
    expect(await bg()).toBe(TOKENS.lightBg); // the host's light wins over the OS's dark

    await page.evaluate(() => document.documentElement.removeAttribute("data-appearance"));
    expect(await bg()).toBe(TOKENS.darkBg); // no host choice: the OS

    // The library chose nothing: no appearance on its root, none written to the page.
    expect(
      await page.evaluate(() =>
        document.querySelector(".arras-root")?.hasAttribute("data-appearance"),
      ),
    ).toBe(false);
    expect(
      await page.evaluate(() => [
        document.documentElement.getAttribute("data-appearance"),
        document.documentElement.getAttribute("data-theme"),
        document.documentElement.style.colorScheme,
        document.body.style.colorScheme,
        localStorage.length + sessionStorage.length,
      ]),
    ).toEqual([null, null, "", "", 0]);
  });

  test("the nearest ancestor that gives an appearance decides, however the providers nest", async ({
    page,
  }) => {
    test.skip(HOST_APPEARANCE_PROVIDER, SKIP_BARE_HOST);
    await page.emulateMedia({ colorScheme: "light" });
    await openWithHost(page);
    const bg = () => style(page, ".arras-root", "background-color");
    // Wrap the console's root in providers, outermost first: each is `data-appearance`, or an inline
    // `color-scheme` where the host's provider was given only its tokens.
    const wrap = (layers: string[]) =>
      page.evaluate((spec) => {
        const root = document.querySelector(".arras-root") as HTMLElement;
        const parent = root.parentElement as HTMLElement;
        const slot = document.createComment("root");
        parent.replaceChild(slot, root);
        let inner: HTMLElement = root;
        for (const layer of [...spec].reverse()) {
          const el = document.createElement("div");
          el.className = "probe-layer";
          if (layer.includes(":")) el.setAttribute("style", layer);
          else el.setAttribute("data-appearance", layer);
          el.append(inner);
          inner = el;
        }
        parent.replaceChild(inner, slot);
      }, layers);
    const unwrap = () =>
      page.evaluate(() => {
        const root = document.querySelector(".arras-root") as HTMLElement;
        const outermost = [...document.querySelectorAll(".probe-layer")].find(
          (e) => !e.parentElement?.closest(".probe-layer"),
        );
        outermost?.parentElement?.replaceChild(root, outermost);
      });
    for (const [layers, want] of [
      [["dark", "light"], TOKENS.lightBg],
      [["light", "dark"], TOKENS.darkBg],
      [["dark", "light", "dark"], TOKENS.darkBg],
      [["light", "dark", "light"], TOKENS.lightBg],
      [["dark", "color-scheme: light"], TOKENS.lightBg],
      [["color-scheme: dark"], TOKENS.darkBg],
      [["light", "color-scheme: dark"], TOKENS.darkBg],
    ] as [string[], string][]) {
      await wrap(layers);
      expect(await bg(), layers.join(" > ")).toBe(want);
      await unwrap();
    }
    // A host that gives no appearance leaves the OS's preference to decide.
    await page.emulateMedia({ colorScheme: "dark" });
    expect(await bg()).toBe(TOKENS.darkBg);
    await wrap(["color-scheme: light"]);
    expect(await bg()).toBe(TOKENS.lightBg); // the host's inline light wins over the OS's dark
  });

  test("an inline color-scheme names a scheme only as light or dark, alone or with `only`; the two-value forms leave it to the OS, as the frame's scheme reads them (scheme.vectors.json)", async ({
    page,
  }) => {
    test.skip(HOST_APPEARANCE_PROVIDER, SKIP_BARE_HOST);
    const vectors = JSON.parse(
      readFileSync(join(import.meta.dirname, "../src/test/scheme.vectors.json"), "utf8"),
    ) as { style: string; os: "light" | "dark"; want: "light" | "dark" }[];
    await openWithHost(page);
    await page.evaluate(() => {
      const root = document.querySelector(".arras-root") as HTMLElement;
      const layer = document.createElement("div");
      layer.id = "scheme-layer";
      root.parentElement?.replaceChild(layer, root);
      layer.append(root);
    });
    for (const { style: declared, os, want } of vectors) {
      await page.emulateMedia({ colorScheme: os });
      await page.evaluate(
        (css) => document.getElementById("scheme-layer")?.setAttribute("style", css),
        declared,
      );
      expect(await style(page, ".arras-root", "background-color"), `${declared}, OS ${os}`).toBe(
        want === "dark" ? TOKENS.darkBg : TOKENS.lightBg,
      );
    }
  });

  test("a host that sets the role tokens and switches its own appearance re-themes the library, and the library writes nothing to the page", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await openWithHost(page);
    // The host's element carries its tokens and its own `data-appearance` switch; the library's root is inside it.
    await hostCss(
      page,
      ".host-theme { --arras-color-ground: rgb(240, 238, 230) } .host-theme[data-appearance=dark] { --arras-color-ground: rgb(27, 26, 25) }",
    );
    await page.evaluate(() => {
      const root = document.querySelector(".arras-root") as HTMLElement;
      const host = document.createElement("div");
      host.className = "host-theme";
      root.parentElement?.replaceChild(host, root);
      host.append(root);
    });
    const bg = () => style(page, ".arras-root", "background-color");
    const choose = (appearance: string | null) =>
      page.evaluate((a) => {
        const host = document.querySelector(".host-theme") as HTMLElement;
        if (a) host.setAttribute("data-appearance", a);
        else host.removeAttribute("data-appearance");
      }, appearance);
    expect(await bg()).toBe(THEME.lightBg);
    await choose("dark");
    await expect.poll(bg).toBe(THEME.darkBg); // the host's dark, with the OS light
    await choose("light");
    await expect.poll(bg).toBe(THEME.lightBg);
    await choose(null);
    await page.emulateMedia({ colorScheme: "dark" });
    await expect.poll(bg).toBe(THEME.lightBg); // no appearance given: the host's token, whatever the OS says
    // A host with its own appearance provider has written to its page itself; the bare host has not.
    if (HOST_APPEARANCE_PROVIDER) return;
    expect(
      await page.evaluate(() => [
        document.documentElement.getAttribute("data-appearance"),
        document.documentElement.style.colorScheme,
        localStorage.length + sessionStorage.length,
      ]),
    ).toEqual([null, "", 0]);
  });

  test("a host's role token is the library's surface, and a host's own `--bg` still changes nothing", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await openWithHost(page);
    await hostCss(page, ":root { --arras-color-ground: rgb(240, 238, 230) }");
    const bg = () => style(page, ".arras-root", "background-color");
    expect(await bg()).toBe(THEME.lightBg);
    await hostCss(page, ":root { --bg: #000000; --accent: #ff0000 }");
    expect(await bg()).toBe(THEME.lightBg);
  });
});
