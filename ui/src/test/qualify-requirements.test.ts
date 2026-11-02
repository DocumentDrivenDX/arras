// SPDX-License-Identifier: MIT OR Apache-2.0
import { execFile } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { chromium } from "@playwright/test";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

// `arras-ui-qualify --host-build` fails with the host-fixture requirement it misses, by name, and points to the
// contract (support/QUALIFICATION.md), instead of only the phase it stopped in. It runs a real Chromium, so the
// cases are skipped where none is installed.

const RUNNER = join(import.meta.dirname, "../../support/qualify-downstream-theme.mjs");
const hasChromium = (() => {
  try {
    return existsSync(chromium.executablePath());
  } catch {
    return false;
  }
})();

const PAGES: Record<string, string> = {
  // a themed page with no host widgets at all
  "/no-widgets": '<div class="arras-root"><button>plain</button></div>',
  // all six markers, but no controls region and no Arras app
  "/no-app":
    '<div class="arras-root"><button data-theme-button>b</button><input data-theme-text-field>' +
    "<textarea data-theme-text-area></textarea><select data-theme-select></select>" +
    "<section data-theme-notice></section><span data-theme-mark></span></div>",
};

let server: Server;
let origin = "";
const out: string[] = [];

beforeAll(async () => {
  server = createServer((req, res) => {
    const body = PAGES[req.url ?? ""];
    res.writeHead(body ? 200 : 404, { "content-type": "text/html" });
    res.end(`<!doctype html><html lang="en"><title>t</title>${body ?? ""}`);
  });
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(async () => {
  await new Promise<void>((done) => server.close(() => done()));
  for (const dir of out) rmSync(dir, { recursive: true, force: true });
});

const run = promisify(execFile);

// Asynchronous: the page server is in this process, so a blocking spawn would stop it answering.
async function qualify(path: string) {
  const dir = mkdtempSync(join(tmpdir(), "arras-qualify-"));
  out.push(dir);
  const result = await run(
    process.execPath,
    [RUNNER, `${origin}${path}`, "--host-build", "--output", dir],
    { cwd: join(import.meta.dirname, "../.."), timeout: 90_000 },
  ).then(
    ({ stderr }) => ({ status: 0, stderr }),
    (error: { code?: number; stderr?: string }) => ({
      status: error.code ?? -1,
      stderr: error.stderr ?? "",
    }),
  );
  const receipt = JSON.parse(
    readFileSync(
      join(dir, `external-theme-compiled-host-browser-${process.platform}-failure.json`),
      "utf8",
    ),
  ) as Record<string, string>;
  return { run: result, receipt };
}

describe.skipIf(!hasChromium)(
  "arras-ui-qualify --host-build names the fixture requirement it misses",
  () => {
    it("a page without the host widgets: names the first missing marker and the contract", async () => {
      const { run, receipt } = await qualify("/no-widgets");
      expect(run.status).toBe(1);
      expect(run.stderr).toContain("[data-theme-button]");
      expect(run.stderr).toContain("Button widget");
      expect(run.stderr).toContain("QUALIFICATION.md");
      expect(run.stderr).toContain("Host-build fixture contract");
      expect(receipt.requirement).toContain("[data-theme-button]");
      expect(receipt.contract).toContain("Host-build fixture contract");
      expect(receipt.phase).toBe("checking themed widgets in light mode");
    });

    it("a page with the six markers but no app: names the app, not a bare phase", async () => {
      const { run, receipt } = await qualify("/no-app");
      expect(run.status).toBe(1);
      expect(run.stderr).toContain("ArrasApp");
      expect(run.stderr).toContain(".gb");
      expect(receipt.requirement).toContain("ArrasApp");
      expect(run.stderr).not.toContain(origin);
    });
  },
);
