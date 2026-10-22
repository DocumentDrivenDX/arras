// SPDX-License-Identifier: MIT OR Apache-2.0
// @vitest-environment node
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  ASSETS_DIR,
  checkInstalled,
  copyAssets,
  differences,
  files,
  LICENSE_FILES,
  PACKAGE,
  PACKAGE_DIR,
  pin,
  RELEASE,
} from "../../scripts/umf-schema-browser.ts";
import { defined } from "./defined";

// UMF's schema browser as a dependency: the npm package at an exact version, the lockfile's
// integrity, the installed files, and the build's byte-for-byte copy of its assets. The registry
// half (`npm run check:umf -- --download`) needs the network and runs in CI.
const UI = join(__dirname, "..", "..");
const scratch: string[] = [];
const tmp = () => {
  const d = mkdtempSync(join(tmpdir(), "umf-"));
  scratch.push(d);
  return d;
};
afterEach(() => {
  for (const d of scratch.splice(0)) rmSync(d, { recursive: true, force: true });
});

describe(`${PACKAGE} as the console depends on it`, () => {
  it("is pinned exactly, locked to the registry's tarball with sha512 integrity, and installed whole", () => {
    expect(checkInstalled()).toEqual([]);
    const { declared, locked } = pin();
    expect(declared).toBe(RELEASE.version);
    expect(locked?.resolved).toBe(
      `https://registry.npmjs.org/${PACKAGE}/-/umf-schema-browser-${RELEASE.version}.tgz`,
    );
    expect(locked?.integrity).toBe(
      "sha512-MuCXD6aRu36nss+KXfVinexh/RDiQgoBk7hx6SAEf0AwQViUny5jp3jpeWLcyFTI2xizWbffR1iYMLxzFGMviQ==",
    );
    expect(RELEASE.sha256).toBe("03e13341c79f29fe891fa6d97a3e504b36a483ba51c98b2e1bcb557b6036e8e1");
    const installed = JSON.parse(readFileSync(join(PACKAGE_DIR, "package.json"), "utf8")) as {
      version: string;
      license: string;
    };
    expect(installed).toMatchObject({ version: RELEASE.version, license: "(MIT OR Apache-2.0)" });
    for (const f of LICENSE_FILES)
      expect(readFileSync(join(PACKAGE_DIR, f), "utf8").length, f).toBeGreaterThan(100);
  });

  it("refuses a range, another version, a non-registry lock and a missing licence", () => {
    const ui = tmp();
    const pkg = JSON.parse(readFileSync(join(UI, "package.json"), "utf8")) as {
      dependencies: Record<string, string>;
    };
    const lock = JSON.parse(readFileSync(join(UI, "package-lock.json"), "utf8")) as {
      packages: Record<string, Record<string, string>>;
    };
    const write = (dep: string, entry: Record<string, string>) => {
      writeFileSync(
        join(ui, "package.json"),
        JSON.stringify({ ...pkg, dependencies: { ...pkg.dependencies, [PACKAGE]: dep } }),
      );
      writeFileSync(
        join(ui, "package-lock.json"),
        JSON.stringify({
          ...lock,
          packages: { ...lock.packages, [`node_modules/${PACKAGE}`]: entry },
        }),
      );
    };
    const good = defined(
      lock.packages[`node_modules/${PACKAGE}`],
      "the locked entry for the package",
    );
    write(`^${RELEASE.version}`, good);
    expect(checkInstalled(ui).join("\n")).toMatch(/not exactly/);
    write(RELEASE.version, { ...good, resolved: "https://example.com/x.tgz" });
    expect(checkInstalled(ui).join("\n")).toMatch(/resolves https:\/\/example.com/);
    write(RELEASE.version, { ...good, version: "1.1.0" });
    expect(checkInstalled(ui).join("\n")).toMatch(/locks 1.1.0/);
    write(RELEASE.version, { ...good, integrity: "sha1-abc" });
    expect(checkInstalled(ui).join("\n")).toMatch(/no sha512 integrity/);
    const copy = tmp();
    cpSync(PACKAGE_DIR, copy, { recursive: true });
    rmSync(join(copy, "LICENSE-APACHE"));
    write(RELEASE.version, good);
    expect(checkInstalled(ui, copy)).toEqual(["installed package lacks LICENSE-APACHE"]);
  });

  it("the build copies the installed assets byte for byte, and a changed, missing or extra file is reported", () => {
    const out = tmp();
    copyAssets(out);
    const copy = join(out, "umf-explorer");
    expect(differences(ASSETS_DIR, copy)).toEqual([]);
    expect(files(copy)).toEqual(files(ASSETS_DIR));
    expect(files(copy)).toEqual(
      expect.arrayContaining([
        "index.html",
        "explorer.js",
        "explorer.css",
        "style.css",
        "components.css",
      ]),
    );
    writeFileSync(join(copy, "explorer.css"), "body{}");
    rmSync(join(copy, "style.css"));
    writeFileSync(join(copy, "extra.js"), "");
    expect(differences(ASSETS_DIR, copy)).toEqual([
      "missing: style.css",
      "extra: extra.js",
      "differs: explorer.css",
    ]);
    expect(differences(ASSETS_DIR, join(out, "nowhere"))).toEqual([
      `${join(out, "nowhere")} is missing`,
    ]);
  });

  it("nothing vendored remains in the repository", () => {
    expect(() => readFileSync(join(UI, "vendor", "umf-schema-browser", "package.json"))).toThrow();
  });
});
