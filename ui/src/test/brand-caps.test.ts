// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { readBrandMeta } from "../lib/brand";

// The caps arras.ui.Brand refuses past (tests/test_ui.py reads the same file): the page keeps a
// field of exactly the cap whole and cuts a longer one to it.
const file = resolve(dirname(fileURLToPath(import.meta.url)), "../../../tests/vectors/brand.json");
const { caps } = JSON.parse(readFileSync(file, "utf8")) as { caps: Record<string, number> };

function read(field: string, text: string) {
  const doc = new DOMParser().parseFromString("<head></head>", "text/html");
  const meta = doc.createElement("meta");
  meta.setAttribute("name", "arras-brand");
  meta.setAttribute("content", JSON.stringify({ name: "A", [field]: text }));
  doc.head.append(meta);
  return readBrandMeta(doc) as unknown as Record<string, string>;
}

describe("the brand caps agree with the server (tests/vectors/brand.json)", () => {
  it("names the four fields", () => {
    expect(Object.keys(caps).sort()).toEqual(["name", "tagline", "title", "wordmark"]);
  });

  for (const [field, cap] of Object.entries(caps)) {
    it(`keeps ${field} whole at ${cap} characters and cuts one more`, () => {
      const whole = "x".repeat(cap);
      expect(read(field, whole)[field]).toHaveLength(cap);
      expect(read(field, `${whole}x`)[field]).toHaveLength(cap);
    });
  }
});
