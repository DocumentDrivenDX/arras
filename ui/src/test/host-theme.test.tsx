// SPDX-License-Identifier: MIT OR Apache-2.0
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { act, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ArrasConsole } from "../ArrasConsole";
import { GraphBrowser } from "../browser/GraphBrowser";
import { ArrasApp } from "../shell";
import { stageBrowser } from "./browserFake";
import { qc } from "./render";

// The embedded components take the host's theme and appearance and choose none of their own. A host sets
// `data-appearance` on its own element (and, if it likes, `--arras-*` role tokens, or its own widgets through
// `DesignSystemProvider`); the components render inside it, never write to it or to the page, and never
// persist a choice.

const SRC = join(import.meta.dirname, "..");
const sources = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    return e.isDirectory() ? sources(p) : /\.tsx?$/.test(e.name) ? [p] : [];
  });

/** A file's text without its comments, which may name what the code must not do. */
const code = (f: string) =>
  readFileSync(f, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");

describe("the library installs no theme of its own", () => {
  it("no source, the page entries included, installs a theme or touches the page's theme attributes", () => {
    const offenders = sources(SRC)
      .filter((f) => !/\.(int\.)?test\.tsx?$/.test(f) && !f.includes(`${join(SRC, "test")}/`))
      .filter((f) => !f.includes(`${join(SRC, "dev")}/`))
      .filter((f) =>
        /ThemeProvider|setAttribute\(\s*["']data-(theme|appearance)|\.colorScheme\s*=|dataset\.(theme|appearance)|classList\.(add|toggle)\(\s*["']dark|(local|session)Storage/.test(
          code(f),
        ),
      );
    expect(offenders).toEqual([]);
  });

  it("the components take no appearance prop", () => {
    for (const f of ["ArrasConsole.tsx", "browser/GraphBrowser.tsx", "shell/ArrasApp.tsx"])
      expect(readFileSync(join(SRC, f), "utf8")).not.toMatch(/appearance\??:/);
  });
});

/** A host: its own element carrying the `data-appearance` its own switch writes. */
function Host({ appearance, children }: { appearance: string | null; children: ReactElement }) {
  return (
    <div data-testid="host" data-theme="host" data-appearance={appearance ?? undefined}>
      {children}
    </div>
  );
}

const MOUNTS: [string, () => ReactElement][] = [
  ["ArrasApp", () => <ArrasApp queryClient={qc()} />],
  ["GraphBrowser", () => <GraphBrowser queryClient={qc()} />],
  ["ArrasConsole", () => <ArrasConsole />],
];

describe.each(MOUNTS)("%s inside a host that switches light, dark and auto", (_name, make) => {
  let seen: MutationRecord[] = [];
  let watch: MutationObserver;
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    window.location.hash = "";
    const fake = stageBrowser();
    fake.mods = fake.mods.slice(0, 1);
    window.localStorage.clear();
    watch = new MutationObserver((r) => seen.push(...r));
    watch.observe(document.documentElement, { attributes: true });
    watch.observe(document.body, { attributes: true });
    seen = [];
  });
  afterEach(() => {
    watch.disconnect();
    window.location.hash = "";
  });

  it("renders in the host's element, never sets an appearance on its own root, and leaves the page's attributes alone", async () => {
    const { rerender, container } = render(<Host appearance="light">{make()}</Host>);
    await screen.findByRole("navigation", {}, { timeout: 3000 }).catch(() => undefined);
    const host = screen.getByTestId("host");
    const root = container.querySelector(".arras-root");
    expect(root).not.toBeNull();
    expect(host.contains(root)).toBe(true);
    for (const next of ["dark", null, "light"]) {
      act(() => host.toggleAttribute("data-appearance", false));
      if (next) act(() => host.setAttribute("data-appearance", next));
      rerender(<Host appearance={next}>{make()}</Host>);
      // The host's choice is the host's: the components did not rewrite it, and added none to their root.
      expect(host.getAttribute("data-appearance")).toBe(next);
      expect(host.getAttribute("data-theme")).toBe("host");
      expect(container.querySelector(".arras-root")?.hasAttribute("data-appearance")).toBe(false);
      expect(container.querySelector(".arras-root")?.hasAttribute("data-theme")).toBe(false);
    }
    expect(seen.filter((r) => r.target !== host)).toEqual([]);
    expect(document.documentElement.getAttribute("data-appearance")).toBeNull();
    expect(document.documentElement.getAttribute("data-theme")).toBeNull();
    expect(document.documentElement.style.colorScheme).toBe("");
    expect(document.body.style.colorScheme).toBe("");
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
  });
});
