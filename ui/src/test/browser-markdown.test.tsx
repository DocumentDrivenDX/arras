// SPDX-License-Identifier: MIT OR Apache-2.0
// The `markdown` format (CONTRACT-010 A, vocabulary 0.2.0, ADR-032): the closed subset is drawn as elements, and
// nothing outside it becomes markup. The hostile inputs are the ones a text field of a public graph could hold.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownText } from "../browser/MarkdownText";
import { linkHref, MAX_MARKDOWN_CHARS, parseMarkdown } from "../browser/markdown";

const html = (md: string) => render(<MarkdownText text={md} />).container;

describe("the subset", () => {
  it("draws headings (shifted below the page's own), paragraphs, emphasis, code and a rule", () => {
    const c = html("# One\n\nSome **strong**, *em*, _also em_ and `code`.\n\n---\n\n###### Six");
    expect([...c.querySelectorAll("h4,h5,h6")].map((h) => h.tagName + h.textContent)).toEqual([
      "H4One",
      "H6Six",
    ]);
    expect(c.querySelector("strong")?.textContent).toBe("strong");
    expect([...c.querySelectorAll("em")].map((e) => e.textContent)).toEqual(["em", "also em"]);
    expect(c.querySelector("p code")?.textContent).toBe("code");
    expect(c.querySelector("hr")).not.toBeNull();
  });

  it("draws lists, nested by indentation, and numbered lists", () => {
    const c = html("- a\n- b\n  - b1\n  - b2\n- c\n\n1. x\n2. y");
    expect(c.querySelectorAll("ul > li").length).toBe(5);
    expect(c.querySelector("ul ul")?.querySelectorAll("li").length).toBe(2);
    expect(c.querySelectorAll("ol > li").length).toBe(2);
  });

  it("draws a pipe table with a header, and a pipe escaped in a cell", () => {
    const c = html("| A | B |\n|---|:-:|\n| 1 | x \\| y |\n| 2 | `c` |");
    expect([...c.querySelectorAll("th")].map((t) => t.textContent)).toEqual(["A", "B"]);
    expect([...c.querySelectorAll("td")].map((t) => t.textContent)).toEqual([
      "1",
      "x | y",
      "2",
      "c",
    ]);
  });

  it("draws fenced code verbatim, and a block quote", () => {
    const c = html("```\n# not a heading\n**not strong**\n```\n\n> quoted *text*\n> more");
    expect(c.querySelector("pre code")?.textContent).toBe("# not a heading\n**not strong**");
    expect(c.querySelector("blockquote em")?.textContent).toBe("text");
  });

  it("leaves snake_case and a lone star alone", () => {
    expect(html("supported_by and a * b and 2*3").textContent).toBe(
      "supported_by and a * b and 2*3",
    );
  });

  it("keeps a link to http, https or mailto, opened safely", () => {
    const a = html("[Docs](https://example.com/a?b=1) and [m](mailto:a@b.co)").querySelectorAll(
      "a",
    );
    expect([...a].map((x) => x.getAttribute("href"))).toEqual([
      "https://example.com/a?b=1",
      "mailto:a@b.co",
    ]);
    for (const x of a) expect(x.getAttribute("rel")).toBe("noopener noreferrer");
  });
});

describe("nothing outside the subset becomes markup", () => {
  const HOSTILE = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<iframe src='https://x'></iframe> <style>*{display:none}</style>",
    "[x](javascript:alert(1))",
    "[x](JaVaScRiPt:alert(1))",
    "[x](data:text/html;base64,PHNjcmlwdD4=)",
    "[x](vbscript:msgbox)",
    "[x](//evil.example/a)",
    "[x](/relative/path)",
    "[x](https://user:secret@example.com/)",
    "![img](https://example.com/p.png)",
    "![img](javascript:alert(1))",
    '[a](https://e.com "title" onclick="x")',
    '<a href="javascript:alert(1)">x</a>',
    "&lt;script&gt; &#60;b&#62;",
    "\\<script>",
    "<!-- c --> <svg onload=alert(1)>",
  ];
  it.each(HOSTILE)("%s", (md) => {
    const c = html(md);
    for (const tag of [
      "script",
      "img",
      "iframe",
      "style",
      "svg",
      "object",
      "embed",
      "form",
      "input",
    ])
      expect(c.querySelector(tag), tag).toBeNull();
    for (const el of c.querySelectorAll("*")) {
      for (const attr of el.getAttributeNames()) expect(attr.startsWith("on"), attr).toBe(false);
    }
    for (const a of c.querySelectorAll("a"))
      expect(a.getAttribute("href")).toMatch(/^(https?:|mailto:)/);
    for (const a of c.querySelectorAll("a"))
      expect(a.getAttribute("href")).not.toMatch(/@.*secret|secret@/);
  });

  it("shows the markup it refuses as the text it was", () => {
    expect(html("<b>x</b>").textContent).toBe("<b>x</b>");
    expect(html("![alt text](https://e.com/i.png)").textContent).toBe("alt text");
    expect(html("[x](javascript:alert(1))").textContent).toBe("[x](javascript:alert(1))");
  });

  it("refuses credentials, and every other scheme, in a link address", () => {
    expect(linkHref("https://user:pw@e.com/")).toBeNull();
    expect(linkHref("ftp://e.com/")).toBeNull();
    expect(linkHref("https://e.com/")).toBe("https://e.com/");
  });
});

describe("bounds", () => {
  it("shows a value past the bound as text, not parsed", () => {
    const big = `**x** ${"y".repeat(MAX_MARKDOWN_CHARS)}`;
    expect(parseMarkdown(big)).toBeNull();
    expect(html(big).querySelector("strong")).toBeNull();
  });

  it("reads a large, hostile, deeply nested value in bounded time", () => {
    const t = performance.now();
    parseMarkdown(
      `${"*a ".repeat(20_000)}\n${"[".repeat(20_000)}\n${"> ".repeat(2_000)}x\n${"  - n\n".repeat(2_000)}`,
    );
    expect(performance.now() - t).toBeLessThan(3_000);
  });

  it("reads Atlas-shaped text: criteria table, lists and bold run-ins", () => {
    const c = html(
      "## Scope\n\nCompares **A** and *B*.\n\n| Criterion | Concern |\n|---|---|\n| Licence | datastore |\n\n- **PostgreSQL**: community. Brief: component-profile-postgresql-reusable\n- **SQL Server**: commercial.",
    );
    expect(c.querySelector("table")).not.toBeNull();
    expect(c.querySelectorAll("li").length).toBe(2);
    expect(c.querySelector("li strong")?.textContent).toBe("PostgreSQL");
  });
});
