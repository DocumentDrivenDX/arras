// SPDX-License-Identifier: MIT OR Apache-2.0

import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createAcceptanceConfig, normalizeAcceptanceOptions } from "../testkit/config";
import { CANONICAL_SPECS } from "../testkit/inventory";
import { resolveAcceptanceTestDir } from "../testkit/layout";
import { materializePackedAcceptanceSuite } from "../testkit/resources";

const valid = {
  baseURL: "http://127.0.0.1:8123",
  schemaBaseURL: "http://127.0.0.1:8124",
  outputDir: "./test-results/consumer",
};

describe("the portable acceptance profile", () => {
  it("normalizes the exact default profile and fixes the canonical spec inventory", () => {
    expect(normalizeAcceptanceOptions(valid)).toMatchObject({
      baseURL: "http://127.0.0.1:8123",
      schemaBaseURL: "http://127.0.0.1:8124",
      themeId: "default",
      expectedBrand: { name: "Arras" },
      expectedSurface: { light: "rgb(246, 247, 249)", dark: "rgb(15, 19, 26)" },
    });
    expect(CANONICAL_SPECS).toHaveLength(17);
    expect(new Set(CANONICAL_SPECS).size).toBe(17);
  });

  it.each([
    [{ ...valid, unknown: true }, "unsupported field"],
    [{ ...valid, baseURL: "http://user:secret@127.0.0.1:8123" }, "credential-free"],
    [{ ...valid, baseURL: "http://127.0.0.1:8123/path" }, "root HTTP(S) origin"],
    [{ ...valid, schemaBaseURL: valid.baseURL }, "must differ"],
    [{ ...valid, themeId: "../other" }, "non-secret label"],
    [
      { ...valid, expectedSurface: { light: "rgba(1, 2, 3, .5)", dark: "rgb(0,0,0)" } },
      "opaque rgb",
    ],
    [
      { ...valid, expectedSurface: { light: "rgb(256, 2, 3)", dark: "rgb(0, 0, 0)" } },
      "opaque rgb",
    ],
    [{ ...valid, expectedBrand: { name: "Arras", source: "hook" } }, "unsupported field"],
    [{ ...valid, expectedBrand: { name: "Arras", title: " " } }, "non-empty string"],
    [{ ...valid, outputDir: "" }, "non-empty host-owned directory"],
    [null, "must be an object"],
  ])("refuses malformed profile options %#", (input, message) => {
    expect(() => normalizeAcceptanceOptions(input)).toThrow(message);
  });

  it("normalizes supported exact-color whitespace and accepts the existing Brand shape", () => {
    expect(
      normalizeAcceptanceOptions({
        ...valid,
        themeId: "theme-1",
        expectedBrand: { name: "Example", title: "Example Console", logo: "theme" },
        expectedSurface: { light: " rgb( 1,2,  3 ) ", dark: "rgb(255, 254, 253)" },
        baselineDir: "./baselines/example",
      }),
    ).toMatchObject({
      themeId: "theme-1",
      expectedBrand: { name: "Example", title: "Example Console", logo: "theme" },
      expectedSurface: { light: "rgb(1, 2, 3)", dark: "rgb(255, 254, 253)" },
      baselineDir: expect.stringContaining("baselines/example"),
    });
  });

  describe("the visual project's baselineDir", () => {
    afterEach(() => {
      vi.unstubAllGlobals();
      Reflect.deleteProperty(process.env, "ARRAS_ACCEPTANCE_RUNTIME");
    });
    const onPlatform = (platform: string) => {
      const real = process.platform;
      Object.defineProperty(process, "platform", { value: platform });
      return () => Object.defineProperty(process, "platform", { value: real });
    };
    const projectNames = (options: Parameters<typeof createAcceptanceConfig>[0]) =>
      (createAcceptanceConfig(options).projects ?? []).map((p) => p.name);

    it("is not needed to build a config on macOS: the nonvisual projects run without it", () => {
      const restore = onPlatform("darwin");
      try {
        expect(projectNames(valid)).toEqual(["chromium", "schema-admin", "browser", "visual"]);
        expect(createAcceptanceConfig(valid).metadata?.arrasAcceptance.visualComparison).toBe(
          "enabled-requires-baselineDir",
        );
      } finally {
        restore();
      }
    });

    it("is carried into the config when given, and the visual project is absent elsewhere", () => {
      const restore = onPlatform("darwin");
      try {
        const withDir = createAcceptanceConfig({ ...valid, baselineDir: "./baselines/example" });
        expect(withDir.metadata?.arrasAcceptance.visualComparison).toBe(
          "enabled-with-reviewed-baselines",
        );
        expect(withDir.snapshotPathTemplate).toContain("baselines/example");
      } finally {
        restore();
      }
      const restoreLinux = onPlatform("linux");
      try {
        expect(projectNames(valid)).toEqual(["chromium", "schema-admin", "browser"]);
      } finally {
        restoreLinux();
      }
    });

    it("is required by the visual spec itself, which fails with a message that names it", () => {
      const spec = readFileSync(join(import.meta.dirname, "../../e2e/visual.spec.ts"), "utf8");
      expect(spec).toMatch(
        /if \(!acceptance\.baselineDir\)\s+throw new Error\(\s*"The visual project/,
      );
    });
  });

  it("uses source specs only in the source tree and refuses an unpacked package fallback", () => {
    const source = resolveAcceptanceTestDir(
      "/work/ui/src/testkit",
      (path) => path === "/work/ui/e2e",
    );
    expect(source).toBe("/work/ui/e2e");
    expect(() =>
      resolveAcceptanceTestDir("/work/consumer/node_modules/arras-ui/dist/testkit", () => false),
    ).toThrow(/missing from this package/);
  });

  it("materializes packed acceptance resources outside node_modules and cleans them after the run", async () => {
    const source = mkdtempSync(join(tmpdir(), "arras-testkit-source-"));
    const consumer = mkdtempSync(join(tmpdir(), "arras-testkit-consumer-"));
    mkdirSync(join(source, "acceptance/e2e"), { recursive: true });
    mkdirSync(join(source, "examples/catalog"), { recursive: true });
    mkdirSync(join(source, "src/arras"), { recursive: true });
    writeFileSync(join(source, "acceptance/e2e/example.spec.ts"), 'test("example");\n');
    writeFileSync(join(source, "examples/catalog/catalog.json"), "{}\n");
    writeFileSync(join(source, "src/arras/module.json"), "{}\n");
    let testProject: ReturnType<typeof materializePackedAcceptanceSuite> | undefined;
    try {
      testProject = materializePackedAcceptanceSuite(source, consumer, "same-profile");
      const repeated = materializePackedAcceptanceSuite(source, consumer, "same-profile");
      expect(repeated).toEqual(testProject);
      expect(testProject.testDir).toContain("arras-acceptance-");
      expect(testProject.testDir).not.toContain("node_modules");
      expect(readFileSync(join(testProject.testDir, "example.spec.ts"), "utf8")).toBe(
        readFileSync(join(source, "acceptance/e2e/example.spec.ts"), "utf8"),
      );
      expect(
        readFileSync(join(testProject.testDir, "../../examples/catalog/catalog.json"), "utf8"),
      ).toBe("{}\n");
      const spec = join(testProject.testDir, "example.spec.ts");
      const specBytes = readFileSync(spec, "utf8");
      writeFileSync(spec, `${specBytes}//tampered\n`);
      expect(() => materializePackedAcceptanceSuite(source, consumer, "same-profile")).toThrow(
        /digest differs/,
      );
      writeFileSync(spec, specBytes);
      const teardownPath = testProject.globalTeardown;
      const teardownBytes = readFileSync(teardownPath, "utf8");
      const sentinel = join(consumer, "cleanup-executed");
      const maliciousTeardown = `import { writeFileSync } from "node:fs"; writeFileSync(${JSON.stringify(sentinel)}, "ran");\n`;
      writeFileSync(teardownPath, maliciousTeardown);
      expect(() => materializePackedAcceptanceSuite(source, consumer, "same-profile")).toThrow(
        /cleanup script differs/,
      );
      expect(existsSync(sentinel)).toBe(false);
      writeFileSync(teardownPath, teardownBytes);

      const maliciousTarget = join(consumer, "malicious-cleanup.mjs");
      writeFileSync(maliciousTarget, maliciousTeardown);
      unlinkSync(teardownPath);
      symlinkSync(maliciousTarget, teardownPath);
      expect(() => materializePackedAcceptanceSuite(source, consumer, "same-profile")).toThrow(
        /cleanup script is invalid/,
      );
      expect(existsSync(sentinel)).toBe(false);
      unlinkSync(teardownPath);
      writeFileSync(teardownPath, teardownBytes);

      execFileSync(process.execPath, [
        "--input-type=module",
        "-e",
        `const teardown = (await import(${JSON.stringify(pathToFileURL(testProject.globalTeardown).href)})).default; await teardown();`,
      ]);
      expect(existsSync(testProject.testDir)).toBe(false);
    } finally {
      if (testProject)
        rmSync(dirname(dirname(testProject.testDir)), { recursive: true, force: true });
      rmSync(source, { recursive: true, force: true });
      rmSync(consumer, { recursive: true, force: true });
    }
  });
});
