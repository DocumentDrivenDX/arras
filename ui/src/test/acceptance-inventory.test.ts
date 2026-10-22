// SPDX-License-Identifier: MIT OR Apache-2.0
import { createHash } from "node:crypto";
import { linkSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  type AcceptanceInventory,
  assertNoAliasedResources,
  verifyAcceptanceInventory,
} from "../../scripts/acceptance-inventory.ts";
import { includeVisualInventoryProject } from "../../scripts/playwright-inventory.config.ts";
import { CANONICAL_SPECS, CANONICAL_TEST_COUNTS } from "../testkit/inventory";
import { verifyPackedAcceptanceResources } from "../testkit/resources";

let root = "";
afterEach(() => {
  if (root) rmSync(root, { recursive: true, force: true });
  root = "";
});

function fixture() {
  root = mkdtempSync(join(tmpdir(), "arras-acceptance-inventory-"));
  const e2e = join(root, "acceptance", "e2e");
  mkdirSync(e2e, { recursive: true });
  const files: Record<string, string> = {};
  for (const name of CANONICAL_SPECS) {
    const path = join(e2e, name);
    const bytes = `canonical ${name}`;
    writeFileSync(path, bytes);
    files[`acceptance/e2e/${name}`] = createHash("sha256").update(bytes).digest("hex");
  }
  return {
    files,
    manifest: {
      version: 1,
      specs: [...CANONICAL_SPECS],
      expectedCounts: { ...CANONICAL_TEST_COUNTS },
      files,
    } satisfies AcceptanceInventory,
  };
}

describe("packed canonical acceptance inventory", () => {
  it("adds the visual discovery project to a Linux-built package without running it", () => {
    const linuxProjects = includeVisualInventoryProject([
      { name: "chromium", testMatch: /a11y\.spec\.ts$/ },
      { name: "schema-admin", testMatch: /schema-admin\.spec\.ts$/ },
      { name: "browser", testMatch: /browser\.spec\.ts$/ },
    ]);
    expect(linuxProjects.map((project) => project.name)).toEqual([
      "chromium",
      "schema-admin",
      "browser",
      "visual",
    ]);
    expect(CANONICAL_TEST_COUNTS.visual).toBe(67);
  });

  it("accepts one complete canonical fixture", () => {
    const { manifest } = fixture();
    expect(verifyAcceptanceInventory(root, manifest)).toEqual([]);
  });

  it("refuses missing, changed, extra, aliased and spec-drifted resources", () => {
    const { manifest } = fixture();
    rmSync(join(root, "acceptance/e2e/a11y.spec.ts"));
    expect(verifyAcceptanceInventory(root, manifest).join("\n")).toMatch(/resource is missing/);

    const changed = join(root, "acceptance/e2e/brand.spec.ts");
    writeFileSync(changed, "changed assertion");
    expect(verifyAcceptanceInventory(root, manifest).join("\n")).toMatch(/digest differs/);

    writeFileSync(join(root, "acceptance/e2e/unlisted.ts"), "extra");
    expect(verifyAcceptanceInventory(root, manifest).join("\n")).toMatch(
      /unlisted acceptance resource/,
    );

    const alias = join(root, "acceptance/e2e/aliased.spec.ts");
    linkSync(changed, alias);
    expect(() => assertNoAliasedResources(root)).toThrow(/symlinks|alias/);

    const drifted = { ...manifest, specs: manifest.specs.slice(1) };
    expect(verifyAcceptanceInventory(root, drifted).join("\n")).toMatch(/spec inventory differs/);
  });

  it("verifies packed resources against their carried manifest and rejects tampering", () => {
    const { manifest } = fixture();
    writeFileSync(join(root, "acceptance/resources.json"), JSON.stringify(manifest));
    expect(() => verifyPackedAcceptanceResources(root)).not.toThrow();

    writeFileSync(join(root, "acceptance/e2e/brand.spec.ts"), "tampered");
    expect(() => verifyPackedAcceptanceResources(root)).toThrow(/digest differs/);
  });

  it("rejects a canonical spec removed together with its digest entry", () => {
    const { manifest } = fixture();
    const removed = "acceptance/e2e/a11y.spec.ts";
    rmSync(join(root, removed));
    delete manifest.files[removed];
    writeFileSync(join(root, "acceptance/resources.json"), JSON.stringify(manifest));
    expect(() => verifyPackedAcceptanceResources(root)).toThrow(/omits a canonical spec/);
    expect(verifyAcceptanceInventory(root, manifest).join("\n")).toMatch(
      /canonical acceptance spec is missing from the manifest/,
    );
  });
});
