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
// Tests that synthesize page-level appearance choices require the explicitly declared bare-host profile.
// Host-owned profiles are exercised separately at both the Arras root and an ancestor; no failure changes
// which profile applies.
const SKIP_BARE_HOST =
  "hostAppearanceProvider is true: this spec drives page appearance on a declared bare host";

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

// Snapshot contents, not storage counts: a write can replace a value or key without changing length.
async function hostState(page: Page) {
  return page.evaluate(() => {
    const attributes = (element: Element) =>
      [...element.attributes]
        .map(({ name, value }) => [name, value] as const)
        .sort(([a], [b]) => a.localeCompare(b));
    const storageEntries = (storage: Storage) =>
      Array.from({ length: storage.length }, (_, index) => storage.key(index))
        .filter((key): key is string => key !== null)
        .sort()
        .map((key) => [key, storage.getItem(key)]);
    const element = (selector: string) => {
      const found = document.querySelector(selector);
      if (!found) throw new Error(`Missing host fixture element: ${selector}`);
      return found;
    };
    const root = element(".arras-root");
    const ancestors = [];
    for (let element = root.parentElement; element; element = element.parentElement) {
      ancestors.push({ tag: element.tagName, attributes: attributes(element) });
    }
    const subtreeAppearance = [root, ...root.querySelectorAll("*")].flatMap((element, index) => {
      const appearance = {
        appearance: element.getAttribute("data-appearance"),
        theme: element.getAttribute("data-theme"),
        scheme: (element as HTMLElement).style?.getPropertyValue("color-scheme") ?? "",
      };
      return appearance.appearance !== null || appearance.theme !== null || appearance.scheme !== ""
        ? [{ index, ...appearance }]
        : [];
    });
    return {
      ancestors,
      rootAttributes: attributes(root),
      subtreeAppearance,
      localStorage: storageEntries(localStorage),
      sessionStorage: storageEntries(sessionStorage),
      outside: [
        getComputedStyle(element("#host-probe h1")).fontSize,
        getComputedStyle(element("#host-probe a")).textDecorationLine,
        getComputedStyle(element("#host-probe table")).borderCollapse,
        getComputedStyle(element("#host-probe p")).marginTop,
        getComputedStyle(document.body).backgroundColor,
      ],
    };
  });
}

function assertHostPreserved(
  before: Awaited<ReturnType<typeof hostState>>,
  after: Awaited<ReturnType<typeof hostState>>,
) {
  expect(after).toEqual(before);
}

async function assertNoArrasAppearance(page: Page) {
  const declarations = await page.evaluate(
    (hostOwnsRoot) =>
      [...document.querySelectorAll(hostOwnsRoot ? ".arras-root *" : ".arras-root, .arras-root *")]
        .filter(
          (element) =>
            element.hasAttribute("data-appearance") ||
            element.hasAttribute("data-theme") ||
            ((element as HTMLElement).style?.getPropertyValue("color-scheme") ?? "") !== "",
        )
        .map((element) => element.outerHTML.slice(0, 200)),
    HOST_APPEARANCE_PROVIDER,
  );
  expect(declarations, "Arras must not install appearance declarations in its subtree").toEqual([]);
}

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
    const surface = await style(page, ".arras-root", "background-color");
    expect(ours.trim()).not.toBe("");
    await hostCss(
      page,
      ":root { --accent: #ff0000; --bg: #000000; --fg: #00ff00; --font-sans: serif }",
    );
    expect(await style(page, ".arras-root", "--accent")).toBe(ours);
    expect(await style(page, ".arras-root", "background-color")).toBe(surface);
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

  test("a bare host's data-appearance wins over the OS, and Arras sets no appearance", async ({
    page,
  }) => {
    test.skip(HOST_APPEARANCE_PROVIDER, SKIP_BARE_HOST);
    await page.emulateMedia({ colorScheme: "light" });
    await openWithHost(page);
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
    test.skip(HOST_APPEARANCE_PROVIDER, SKIP_BARE_HOST);
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
    const before = await hostState(page);
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
    // The host's existing document-level appearance and storage remain exactly host-owned.
    assertHostPreserved(before, await hostState(page));
  });

  for (const provider of ["root", "ancestor"] as const) {
    test(`a bare fixture's ${provider} appearance provider and role tokens drive the library`, async ({
      page,
    }) => {
      test.skip(HOST_APPEARANCE_PROVIDER, SKIP_BARE_HOST);
      await page.emulateMedia({ colorScheme: "light" });
      await openWithHost(page);
      const host = provider === "root" ? ".arras-root" : ".host-appearance-provider";
      if (provider === "ancestor") {
        await page.evaluate(() => {
          const root = document.querySelector(".arras-root") as HTMLElement;
          const host = document.createElement("div");
          host.className = "host-appearance-provider";
          root.parentElement?.replaceChild(host, root);
          host.append(root);
        });
      }
      await hostCss(
        page,
        `${host} { --arras-color-ground: rgb(240, 238, 230) } ${host}[data-appearance=dark] { --arras-color-ground: rgb(27, 26, 25) }`,
      );
      const choose = (appearance: "light" | "dark") =>
        page
          .locator(host)
          .evaluate((element, value) => element.setAttribute("data-appearance", value), appearance);
      const bg = () => style(page, ".arras-root", "background-color");
      await choose("light");
      const before = await hostState(page);
      await expect.poll(bg).toBe(THEME.lightBg);
      await choose("dark");
      await expect.poll(bg).toBe(THEME.darkBg);
      await choose("light");
      await expect.poll(bg).toBe(THEME.lightBg);

      // The declared host provider remains host-owned and does not change unrelated page styles or storage.
      expect(await style(page, "#host-probe h1", "font-size")).toBe("32px");
      assertHostPreserved(before, await hostState(page));
      expect(await page.locator(host).getAttribute("data-appearance")).toBe("light");
    });
  }

  test("the actual host retains its full appearance, subtree and storage state across system changes", async ({
    page,
  }) => {
    await openWithHost(page);
    const before = await hostState(page);
    await assertNoArrasAppearance(page);
    for (const colorScheme of ["dark", "light"] as const) {
      await page.emulateMedia({ colorScheme });
      // Let the host-observation effect run; appearance changes must never install a preference.
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      await assertNoArrasAppearance(page);
      assertHostPreserved(before, await hostState(page));
    }
  });

  for (const mutation of [
    "local value",
    "session key",
    "host appearance",
    "subtree appearance",
  ] as const) {
    test(`the preservation guard rejects a ${mutation} mutation`, async ({ page }) => {
      await openWithHost(page);
      await page.evaluate(() => {
        localStorage.setItem("preservation-local", "original");
        sessionStorage.setItem("preservation-session", "original");
        document.documentElement.setAttribute("data-theme", "original");
      });
      const before = await hostState(page);
      await page.emulateMedia({ colorScheme: "dark" });
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      assertHostPreserved(before, await hostState(page));
      await page.evaluate((kind) => {
        switch (kind) {
          case "local value":
            localStorage.setItem("preservation-local", "changed");
            break;
          case "session key":
            sessionStorage.removeItem("preservation-session");
            sessionStorage.setItem("replacement-session", "original");
            break;
          case "host appearance":
            document.documentElement.setAttribute("data-theme", "changed");
            break;
          case "subtree appearance":
            document.querySelector(".arras-root button")?.setAttribute("data-theme", "unexpected");
            break;
        }
      }, mutation);
      const after = await hostState(page);
      expect(after.localStorage.length).toBe(before.localStorage.length);
      expect(after.sessionStorage.length).toBe(before.sessionStorage.length);
      expect(() => assertHostPreserved(before, after)).toThrow();
      if (mutation === "subtree appearance")
        await expect(assertNoArrasAppearance(page)).rejects.toThrow();
    });
  }

  test("the isolation guard rejects a deliberate global host-style leak", async ({ page }) => {
    await openWithHost(page);
    await hostCss(page, "#host-probe h1 { font-size: 13px !important }");
    expect(await style(page, "#host-probe h1", "font-size")).toBe("13px");
    // This is the same canonical assertion used by the unmutated isolation control above.
    let isolationAssertionRejected = false;
    try {
      expect(await style(page, "#host-probe h1", "font-size")).toBe("32px");
    } catch {
      isolationAssertionRejected = true;
    }
    expect(isolationAssertionRejected).toBe(true);
  });

  test("a bare host's root role token is the library's surface, and its own `--bg` changes nothing", async ({
    page,
  }) => {
    test.skip(HOST_APPEARANCE_PROVIDER, SKIP_BARE_HOST);
    await page.emulateMedia({ colorScheme: "light" });
    await openWithHost(page);
    await hostCss(page, ":root { --arras-color-ground: rgb(240, 238, 230) }");
    const bg = () => style(page, ".arras-root", "background-color");
    expect(await bg()).toBe(THEME.lightBg);
    await hostCss(page, ":root { --bg: #000000; --accent: #ff0000 }");
    expect(await bg()).toBe(THEME.lightBg);
  });
});
