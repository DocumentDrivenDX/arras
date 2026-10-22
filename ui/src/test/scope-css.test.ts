// SPDX-License-Identifier: MIT OR Apache-2.0
import postcss from "postcss";
import { describe, expect, it } from "vitest";
import {
  ROOT,
  scopeCss,
  scopeRoot,
  scopeSelector,
  splitSelectors,
  unscoped,
} from "../../scripts/scope-css";

const scoped = (css: string) => {
  const root = postcss.parse(css);
  scopeRoot(root);
  return root;
};

describe("scope-css: a stylesheet that reaches only the root (ADR-027)", () => {
  it("splits a selector list only at its top-level commas", () => {
    expect(splitSelectors("a, b:is(.x, .y), [title='a,b'], c\\,d")).toEqual([
      "a",
      "b:is(.x, .y)",
      "[title='a,b']",
      "c\\,d",
    ]);
  });

  it("puts every selector inside the root and the root-level ones on it", () => {
    expect(scopeSelector(".flex")).toEqual([`${ROOT} .flex`]);
    expect(scopeSelector("button")).toEqual([`${ROOT} button`]);
    for (const s of [":root", ":host", "html", "body"]) expect(scopeSelector(s)).toEqual([ROOT]);
    expect(scopeSelector("*")).toEqual([ROOT, `${ROOT} *`]);
    expect(scopeSelector("::file-selector-button")).toEqual([`${ROOT} ::file-selector-button`]);
    expect(scopeSelector(`${ROOT}[data-appearance="dark"]`)).toEqual([
      `${ROOT}[data-appearance="dark"]`,
    ]);
  });

  it("scopes rules inside a media query and leaves nested rules, keyframes and @property alone", () => {
    const root = scoped(`
      @media (prefers-reduced-motion: reduce) { * { transition-duration: 0s } }
      .hover\\:x { &:hover { color: red } }
      @keyframes spin { from { opacity: 0 } to { opacity: 1 } }
      @property --tw-x { syntax: "*"; inherits: false }
      h1, a { margin: 0 }
    `);
    expect(unscoped(root)).toEqual([]);
    const css = root.toString();
    expect(css).toContain("&:hover");
    expect(css).toMatch(/from \{/);
    expect(css).toContain(`${ROOT} h1`);
    expect(css).toContain(`${ROOT} a`);
  });

  it("keeps the layers, so the library's own cascade is the one it was written for", () => {
    const root = scoped(`
      @layer theme, base, utilities;
      @layer base { a { color: red } }
      @layer utilities { .p-2 { padding: 8px } }
      .arras-x { color: blue }
    `);
    const css = root.toString();
    expect(css).toContain("@layer base");
    expect(css).toContain(`${ROOT} a`);
    expect(css).toContain(`${ROOT} .p-2`);
    expect(css).toContain(`${ROOT} .arras-x`);
    expect(unscoped(root)).toEqual([]);
  });

  it("finds a selector that reaches outside the root", () => {
    expect(
      unscoped(postcss.parse(`${ROOT} a { x: y } .loose { x: y } @layer base { b { x: y } }`)),
    ).toEqual([".loose", "b"]);
  });

  it("scopes only the library stylesheet", async () => {
    const run = (from: string) =>
      postcss([scopeCss()])
        .process("a { color: red }", { from })
        .then((r) => r.css);
    expect(await run("/x/ui/src/styles.css")).toContain(`${ROOT} a`);
    expect(await run("/x/ui/src/page.css")).not.toContain(ROOT);
  });
});
