// SPDX-License-Identifier: MIT OR Apache-2.0
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import * as browser from "../browser";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
});
afterEach(() => {
  window.location.hash = "";
});

const SRC = join(import.meta.dirname, "../browser");
const KIT = join(import.meta.dirname, "../kit");
const sourcesIn = (dir: string, prefix: string) =>
  readdirSync(dir)
    .filter((f) => /\.tsx?$/.test(f))
    .map((f) => [`${prefix}${f}`, readFileSync(join(dir, f), "utf8")] as const);
// What the browser can reach: its own modules and the kit's (ADR-030).
const sources = [...sourcesIn(SRC, ""), ...sourcesIn(KIT, "kit/")];

describe("the browser reads as the viewer, writes only by a declared action and holds no credential (US-071-AC6)", () => {
  it("US-071-AC6: the package exports the component and the location helpers, nothing that writes", () => {
    expect(Object.keys(browser).sort()).toEqual(["GraphBrowser", "formatExplore", "parseExplore"]);
  });

  it("US-071-AC6: the client methods the browser calls are reads (the journal's `changes` among them), the export (a read) and the declared action's validate and invoke", () => {
    const used = new Set<string>();
    for (const [, text] of sources)
      for (const m of text.matchAll(/\bclient\.(\w+)[(<]/g)) used.add(m[1] ?? "");
    expect([...used].sort()).toEqual(["changes", "export", "invoke", "moduleQuery", "validate"]);
  });

  it("US-071-AC6: only the kit's form model and core call validate or invoke, and no source invokes a batch", () => {
    for (const [file, text] of sources) {
      if (!["kit/useActionForm.ts", "kit/actionCore.ts"].includes(file))
        expect(text, file).not.toMatch(/\.(invoke|validate)\(/);
      expect(text, file).not.toMatch(/\.batch\(/);
    }
  });

  it("US-071-AC6: no browser source mutates, links into the console's actions or stores a credential", () => {
    for (const [file, text] of sources) {
      expect(text, file).not.toMatch(/\bmutation\b/);
      expect(text, file).not.toMatch(/\/actions\//);
      expect(text, file).not.toMatch(/localStorage|sessionStorage|document\.cookie/);
      expect(text, file).not.toMatch(/\bfrom "\.\.\/areas/);
    }
  });

  it("US-071-AC6: a session reads through GraphQL only, sends no credential of its own and leaves nothing in storage", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    const { container } = renderBrowser();
    const group = (
      await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ })
    ).closest("section") as HTMLElement;
    await user.click(await within(group).findByRole("link", { name: /Alert review/ }));
    await screen.findByRole("heading", { level: 1, name: "Alert review" });
    expect(fake.requests.length).toBeGreaterThan(0);
    for (const r of fake.requests) {
      expect(r.path).toMatch(/^\/api\/console\/graphql(\/[^/]+)?$/);
      expect(r.method).toBe("POST");
      expect(r.body.query).not.toMatch(/\bmutation\b/);
      expect(Object.keys(r.headers)).not.toContain("authorization");
    }
    expect(container.querySelector('a[href*="operate"], a[href*="/actions/"]')).toBeNull();
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
