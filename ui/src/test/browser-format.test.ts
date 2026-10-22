// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { ICON_NAMES, iconPaths } from "../browser/icons";
import { toneOf } from "../browser/tones";
import {
  formatDate,
  formatDateTime,
  formatNumber,
  isEmpty,
  safeLink,
  yesNo,
} from "../browser/valueFormat";
import { evaluate, parseTemplate, placeholders, titleOf } from "../lib/template";

const get = (row: Record<string, string>) => (n: string) => row[n] ?? "";

describe("templates (CONTRACT-010 grammar)", () => {
  it("US-070-AC2: a placeholder is the property's text, an optional group appears only when every placeholder in it is non-empty", () => {
    const t = "{name}[ ({code})]";
    expect(evaluate(t, get({ name: "Lumen", code: "S-017" }))).toBe("Lumen (S-017)");
    expect(evaluate(t, get({ name: "Lumen" }))).toBe("Lumen");
    expect(evaluate(t, get({ name: "Lumen", code: "" }))).toBe("Lumen");
  });

  it("US-070-AC2: a missing property produces no text, and a title that comes out empty is the key", () => {
    expect(evaluate("{nope}", get({}))).toBe("");
    expect(titleOf("{name}", { name: null }, "k-1")).toBe("k-1");
    expect(titleOf("{name}", { name: "N" }, "k-1")).toBe("N");
  });

  it("US-070-AC2: escapes give a literal character and nothing else is interpreted", () => {
    expect(evaluate("\\{x\\} \\[y\\] \\\\ <b>{name}</b>", get({ name: "n" }))).toBe(
      "{x} [y] \\ <b>n</b>",
    );
  });

  it("US-070-AC2: a malformed template reads as plain text and names no property", () => {
    for (const bad of ["{name", "name}", "[{name}", "{name}]", "{na me}"]) {
      expect(parseTemplate(bad)).toBeNull();
      expect(placeholders(bad)).toEqual([]);
    }
    expect(evaluate("{name", get({ name: "n" }))).toBe("{name");
  });

  it("US-070-AC2: a backslash before anything but an escapable character is plain text", () => {
    expect(evaluate("a\\q \\", get({}))).toBe("a\\q \\");
  });

  it("the properties a template reads are listed once each, in order", () => {
    expect(placeholders("{b}[ {a}]{b}")).toEqual(["b", "a"]);
    expect(placeholders(null)).toEqual([]);
  });
});

describe("tones and icons (closed sets)", () => {
  it("US-070-AC2: a name outside the set draws slate and the default icon", () => {
    expect(toneOf("violet")).toBe("violet");
    expect(toneOf("magenta")).toBe("slate");
    expect(toneOf(undefined)).toBe("slate");
    expect(iconPaths("nonesuch")).toEqual(iconPaths("circle"));
  });

  it("the 24 icons of the vocabulary are all drawn", () => {
    expect(ICON_NAMES).toHaveLength(24);
    for (const n of ICON_NAMES) expect(iconPaths(n).length).toBeGreaterThan(0);
  });
});

describe("value formats", () => {
  it("US-067-AC2: a number's integer part is grouped by the locale, the stored digits unchanged", () => {
    expect(formatNumber("1234567.50", "en-US")).toBe("1,234,567.50");
    expect(formatNumber("-1234", "en-US")).toBe("-1,234");
    expect(formatNumber("12345678901234567890", "en-US")).toBe("12,345,678,901,234,567,890");
    expect(formatNumber("1234567", "de-DE")).toBe("1.234.567");
    expect(formatNumber("abc")).toBe("abc");
  });

  it("US-067-AC2: dates read as local, readable values and a value that does not parse stays as stored", () => {
    expect(formatDate("2026-10-09T14:12:08+00:00", "en-US")).toMatch(/Oct 9, 2026|Oct 10, 2026/);
    expect(formatDateTime("2026-10-09T14:12:08+00:00", "en-US")).toMatch(/2026/);
    expect(formatDate("not a date")).toBe("not a date");
    expect(yesNo(true)).toBe("Yes");
    expect(yesNo(false)).toBe("No");
  });

  it("US-067-AC3: emptiness is null, undefined, an empty string or an empty list; false and 0 are values", () => {
    expect(isEmpty(null)).toBe(true);
    expect(isEmpty("")).toBe(true);
    expect(isEmpty([])).toBe(true);
    expect(isEmpty(false)).toBe(false);
    expect(isEmpty(0)).toBe(false);
  });

  it("US-070-AC5: a link is http, https or mailto; any other value is not a link", () => {
    expect(safeLink("https://praxis.example/a")?.href).toBe("https://praxis.example/a");
    expect(safeLink("mailto:a@b.example")?.href).toBe("mailto:a@b.example");
    for (const bad of [
      "javascript:alert(1)",
      "data:text/html,x",
      "ftp://x",
      "//x",
      "not a url",
      "",
    ])
      expect(safeLink(bad)).toBeNull();
  });

  it("a long link is shown by its host and last segment", () => {
    const u = "https://praxis.example/solutions/a/very/long/path/to/s-017";
    expect(safeLink(u)?.display).toBe("praxis.example/…/s-017");
  });
});
