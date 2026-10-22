// SPDX-License-Identifier: MIT OR Apache-2.0
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { PlaywrightTestConfig } from "@playwright/test";
import { type Brand, DEFAULT_BRAND } from "../lib/brand-values";
import { resolveAcceptanceTestDir } from "./layout";
import { materializePackedAcceptanceSuite, verifyPackedAcceptanceResources } from "./resources";

export interface AcceptanceConfigOptions {
  baseURL: string;
  schemaBaseURL: string;
  outputDir: string;
  themeId?: string;
  expectedBrand?: Brand;
  expectedSurface?: { light: string; dark: string };
  baselineDir?: string;
}

export interface AcceptanceRuntimeOptions {
  baseURL: string;
  schemaBaseURL: string;
  outputDir: string;
  themeId: string;
  expectedBrand: Brand;
  expectedSurface: { light: string; dark: string };
  baselineDir?: string;
}

const DEFAULT_SURFACES = { light: "rgb(246, 247, 249)", dark: "rgb(15, 19, 26)" };
const OPTION_KEYS = new Set([
  "baseURL",
  "schemaBaseURL",
  "outputDir",
  "themeId",
  "expectedBrand",
  "expectedSurface",
  "baselineDir",
]);

function origin(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) throw new TypeError(`${name} must be a URL`);
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new TypeError(`${name} must be a root HTTP(S) origin`);
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  )
    throw new TypeError(`${name} must be a credential-free root HTTP(S) origin`);
  return parsed.origin;
}

function directory(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim())
    throw new TypeError(`${name} must be a non-empty host-owned directory`);
  return resolve(value);
}

function optionalBrandText(record: Record<string, unknown>, key: string): string | undefined {
  const field = record[key];
  if (field === undefined) return undefined;
  if (typeof field !== "string" || !field.trim())
    throw new TypeError(`expectedBrand.${key} must be a non-empty string`);
  return field;
}

function brand(value: unknown): Brand {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new TypeError("expectedBrand must be a Brand object");
  const record = value as Record<string, unknown>;
  const keys = new Set(["name", "title", "wordmark", "tagline", "logo"]);
  if (Object.keys(record).some((key) => !keys.has(key)))
    throw new TypeError("expectedBrand contains an unsupported field");
  if (typeof record.name !== "string" || !record.name.trim())
    throw new TypeError("expectedBrand.name must be a non-empty string");
  const title = optionalBrandText(record, "title");
  const wordmark = optionalBrandText(record, "wordmark");
  const tagline = optionalBrandText(record, "tagline");
  if (record.logo !== undefined && record.logo !== "theme")
    throw new TypeError('expectedBrand.logo must be "theme"');
  const normalized: Brand = { name: record.name };
  if (title !== undefined) normalized.title = title;
  if (wordmark !== undefined) normalized.wordmark = wordmark;
  if (tagline !== undefined) normalized.tagline = tagline;
  if (record.logo === "theme") normalized.logo = "theme";
  return normalized;
}

function surfaces(value: unknown): { light: string; dark: string } {
  if (value === undefined) return { ...DEFAULT_SURFACES };
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new TypeError("expectedSurface must contain light and dark RGB colors");
  const record = value as Record<string, unknown>;
  if (
    Object.keys(record).sort().join(",") !== "dark,light" ||
    typeof record.light !== "string" ||
    typeof record.dark !== "string"
  )
    throw new TypeError("expectedSurface must contain exactly light and dark RGB colors");
  const normalize = (color: string, key: string) => {
    const match = /^\s*rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)\s*$/.exec(color);
    if (!match || match.slice(1).some((channel) => Number(channel) > 255))
      throw new TypeError(`expectedSurface.${key} must be opaque rgb(r, g, b)`);
    return `rgb(${Number(match[1])}, ${Number(match[2])}, ${Number(match[3])})`;
  };
  return { light: normalize(record.light, "light"), dark: normalize(record.dark, "dark") };
}

export function normalizeAcceptanceOptions(input: unknown): AcceptanceRuntimeOptions {
  if (input === null || typeof input !== "object" || Array.isArray(input))
    throw new TypeError("acceptance options must be an object");
  const options = input as Record<string, unknown>;
  if (Object.keys(options).some((key) => !OPTION_KEYS.has(key)))
    throw new TypeError("acceptance options contain an unsupported field");
  const baseURL = origin(options.baseURL, "baseURL");
  const schemaBaseURL = origin(options.schemaBaseURL, "schemaBaseURL");
  if (baseURL === schemaBaseURL) throw new TypeError("baseURL and schemaBaseURL must differ");
  const themeId = options.themeId ?? "default";
  if (typeof themeId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(themeId))
    throw new TypeError("themeId must be a bounded non-secret label");
  const baselineDir =
    options.baselineDir === undefined ? undefined : directory(options.baselineDir, "baselineDir");
  return {
    baseURL,
    schemaBaseURL,
    outputDir: directory(options.outputDir, "outputDir"),
    themeId,
    expectedBrand:
      options.expectedBrand === undefined ? { ...DEFAULT_BRAND } : brand(options.expectedBrand),
    expectedSurface: surfaces(options.expectedSurface),
    ...(baselineDir ? { baselineDir } : {}),
  };
}

function canonicalTestFiles(profileIdentity: string) {
  const here = dirname(fileURLToPath(import.meta.url));
  const packed = resolve(here, "../support/acceptance/e2e");
  if (existsSync(packed)) {
    const supportRoot = resolve(here, "../support");
    verifyPackedAcceptanceResources(supportRoot);
    const consumerRequire = createRequire(import.meta.url);
    try {
      consumerRequire.resolve("@playwright/test");
      consumerRequire.resolve("@axe-core/playwright");
    } catch {
      throw new Error(
        "Install @playwright/test and @axe-core/playwright in the consumer before using the Arras acceptance suite",
      );
    }
    return materializePackedAcceptanceSuite(supportRoot, process.cwd(), profileIdentity);
  }
  return { testDir: resolveAcceptanceTestDir(here, existsSync) };
}

export function createAcceptanceConfig(options: AcceptanceConfigOptions): PlaywrightTestConfig {
  const normalized = normalizeAcceptanceOptions(options);
  process.env.ARRAS_ACCEPTANCE_RUNTIME = JSON.stringify(normalized);
  const darwin = process.platform === "darwin";
  if (darwin && !normalized.baselineDir)
    throw new TypeError("Darwin acceptance requires baselineDir");
  const acceptanceFiles = canonicalTestFiles(JSON.stringify(normalized));
  const projects: NonNullable<PlaywrightTestConfig["projects"]> = [
    {
      name: "chromium",
      testIgnore: /(schema-admin|browser|browse-history|routes|visual)\.spec/,
      use: { browserName: "chromium", baseURL: normalized.baseURL },
    },
    {
      name: "schema-admin",
      testMatch: /schema-admin\.spec\.ts$/,
      use: { browserName: "chromium", baseURL: normalized.schemaBaseURL },
    },
    {
      name: "browser",
      testMatch: /(browser|browse-history|routes)\.spec\.ts$/,
      use: { browserName: "chromium", baseURL: normalized.baseURL },
    },
  ];
  if (darwin) {
    projects.push({
      name: "visual",
      testMatch: /visual\.spec\.ts$/,
      use: {
        browserName: "chromium",
        baseURL: normalized.baseURL,
        timezoneId: "UTC",
        locale: "en-GB",
      },
    });
  }
  const config: PlaywrightTestConfig = {
    timeout: 30_000,
    fullyParallel: false,
    workers: 1,
    reporter: [["list"]],
    outputDir: normalized.outputDir,
    testDir: acceptanceFiles.testDir,
    ...("globalTeardown" in acceptanceFiles
      ? { globalTeardown: acceptanceFiles.globalTeardown }
      : {}),
    updateSnapshots: "none",
    use: { trace: "retain-on-failure" },
    snapshotPathTemplate: normalized.baselineDir
      ? `${normalized.baselineDir}/{arg}-{projectName}-{platform}{ext}`
      : `${normalized.outputDir}/screenshots/{arg}-{projectName}-{platform}{ext}`,
    expect: {
      toHaveScreenshot: { maxDiffPixelRatio: 0.005, animations: "disabled", caret: "hide" },
    },
    projects,
    metadata: {
      arrasAcceptance: {
        themeId: normalized.themeId,
        visualComparison: darwin ? "enabled-with-reviewed-baselines" : "skipped-non-Darwin",
      },
    },
  };
  return config;
}

export function acceptanceRuntime(): AcceptanceRuntimeOptions {
  const serialized = process.env.ARRAS_ACCEPTANCE_RUNTIME;
  if (!serialized)
    throw new Error("Use createAcceptanceConfig() to load the canonical Arras suite");
  return JSON.parse(serialized) as AcceptanceRuntimeOptions;
}
