// SPDX-License-Identifier: MIT OR Apache-2.0
// A real Chromium host bundles only public exports from the wheel-carried npm tarball.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import react from "@vitejs/plugin-react";
import { build } from "vite";

const ui = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(ui, "..");
const version = /^version\s*=\s*"([^"]+)"/m.exec(
  readFileSync(join(repo, "pyproject.toml"), "utf8"),
)?.[1];
const tarball = process.argv[2]
  ? resolve(process.argv[2])
  : join(repo, `src/arras/ui/npm/documentdrivendx-arras-ui-${version}.tgz`);
const temp = mkdtempSync(join(tmpdir(), "arras-packed-browser-"));
let browser;
let host;
let hostLogs = "";
try {
  const modules = join(temp, "node_modules");
  const packageRoot = join(modules, "@documentdrivendx/arras-ui");
  mkdirSync(packageRoot, { recursive: true });
  execFileSync("tar", ["-xzf", tarball, "-C", packageRoot, "--strip-components=1"]);
  const pkg = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
  assert.equal(pkg.version, version);
  for (const name of [
    "react",
    "react-dom",
    "@tanstack/react-query",
    "@documentdrivendx/umf-schema-browser",
  ]) {
    mkdirSync(dirname(join(modules, name)), { recursive: true });
    symlinkSync(join(ui, "node_modules", name), join(modules, name), "dir");
  }
  writeFileSync(
    join(temp, "index.html"),
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Embedding host</title></head><body><div id="host-root"></div><script type="module" src="/host.tsx"></script></body></html>',
  );
  writeFileSync(
    join(temp, "host.tsx"),
    `
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { ArrasProvider, EntityTable } from "@documentdrivendx/arras-ui";
import { GraphBrowser } from "@documentdrivendx/arras-ui/browser";
import { ArrasApp } from "@documentdrivendx/arras-ui/shell";
import "@documentdrivendx/arras-ui/styles.css";

document.title = "Embedding host";
history.replaceState({ host: 7 }, "", "#host-route");
window.__effects = [];
for (const key of ["pushState", "replaceState", "back"]) {
  const original = history[key].bind(history);
  history[key] = (...args) => { window.__effects.push(key); return original(...args); };
}
const scrollTo = window.scrollTo.bind(window);
window.scrollTo = (...args) => { window.__effects.push("scrollTo"); return scrollTo(...args); };
function Host() {
  const [person, setPerson] = useState("alice");
  const [left, setLeft] = useState({ module: "catalog", type: "Solution", key: "sol-1" });
  const [right, setRight] = useState({ module: "catalog", type: "Solution", key: "sol-1" });
  return <>
    <button type="button" onClick={() => setPerson("carol")}>Switch to viewer</button>
    <button type="button">Host shortcut target</button>
    <section aria-label="Host left"><ArrasApp identity={person} getHeaders={() => ({ "x-arras-user": person })} location={left} onLocation={setLeft} pageEffects={false} /></section>
    <section aria-label="Host right"><GraphBrowser identity="carol" getHeaders={() => ({ "x-arras-user": "carol" })} location={right} onLocation={setRight} pageEffects={false} /></section>
    <section aria-label="Host raw areas"><ArrasProvider identity="carol" getHeaders={() => ({ "x-arras-user": "carol" })} pageEffects={false}><EntityTable module="catalog" type="catalog.Solution" /></ArrasProvider></section>
  </>;
}
createRoot(document.getElementById("host-root")).render(<Host />);
`,
  );
  await build({
    configFile: false,
    root: temp,
    plugins: [react()],
    build: { outDir: join(temp, "dist"), emptyOutDir: true },
    logLevel: "warn",
  });
  // Node or a test runner must not leak into the production consumer bundle.
  for (const name of readdirSync(join(temp, "dist/assets"))) {
    if (name.endsWith(".js")) {
      const text = readFileSync(join(temp, "dist/assets", name), "utf8");
      assert.ok(!text.includes("node:fs") && !text.includes("@playwright/test"));
    }
  }
  const socket = createServer();
  await new Promise((done) => socket.listen(0, "127.0.0.1", done));
  const port = socket.address().port;
  await new Promise((done) => socket.close(done));
  const url = `http://127.0.0.1:${port}`;
  host = spawn(
    "uv",
    [
      "run",
      "--no-sync",
      "--extra",
      "devhost",
      "python",
      "-m",
      "arras.devhost",
      "--port",
      String(port),
      "--ui",
      join(temp, "dist"),
    ],
    {
      cwd: repo,
      env: { ...process.env, UV_CACHE_DIR: join(temp, "uv-cache") },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  host.stdout.on("data", (data) => {
    hostLogs = (hostLogs + data).slice(-12000);
  });
  host.stderr.on("data", (data) => {
    hostLogs = (hostLogs + data).slice(-12000);
  });
  const started = Date.now();
  while (true) {
    assert.equal(host.exitCode, null, hostLogs);
    try {
      if ((await fetch(`${url}/api/people`)).ok) break;
    } catch {
      /* host starting */
    }
    assert.ok(Date.now() - started < 60000, `embedding host startup timed out: ${hostLogs}`);
    await new Promise((done) => setTimeout(done, 100));
  }
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url);
  const left = page.getByRole("region", { name: "Host left" });
  const right = page.getByRole("region", { name: "Host right" });
  await left.getByRole("heading", { name: "Pipeline extractor", exact: true }).waitFor();
  await right.getByRole("heading", { name: "Pipeline extractor", exact: true }).waitFor();
  await left.getByRole("button", { name: "Operate", exact: true }).waitFor();
  await left.getByRole("button", { name: "History", exact: true }).click();
  await left.getByRole("button", { name: /Back to Pipeline/ }).click();
  await page.getByRole("button", { name: "Host shortcut target" }).click();
  await page.keyboard.press("/");
  await page.keyboard.press("?");
  await page.keyboard.press("Control+k");
  assert.equal(await page.getByRole("dialog").count(), 0);
  assert.equal(await page.title(), "Embedding host");
  assert.equal(new URL(page.url()).hash, "#host-route");
  assert.deepEqual(await page.evaluate(() => window.history.state), { host: 7 });
  assert.deepEqual(await page.evaluate(() => window.__effects), []);
  const ids = await page.locator("[id]").evaluateAll((elements) => elements.map((el) => el.id));
  assert.equal(new Set(ids).size, ids.length, "component IDs must be instance-local");
  assert.equal(
    await page.getByRole("region", { name: "Host raw areas" }).locator(".arras-root").count(),
    1,
  );
  await page.getByRole("button", { name: "Switch to viewer" }).click();
  await left.getByRole("heading", { name: "Pipeline extractor", exact: true }).waitFor();
  assert.equal(await left.getByRole("button", { name: "Operate", exact: true }).count(), 0);
  assert.deepEqual(errors, []);
  process.stdout.write(
    `${JSON.stringify({ status: "passed", version, checks: ["packed-public-exports", "real-api", "controlled-navigation", "host-page-effects", "unique-ids", "raw-area-css-scope", "identity-viewer-reset"], browser: await browser.version() })}\n`,
  );
} finally {
  await browser?.close();
  if (host && host.exitCode === null) {
    const stopped = new Promise((done) => host.once("exit", done));
    host.kill("SIGTERM");
    const kill = setTimeout(() => host.kill("SIGKILL"), 5000);
    await stopped;
    clearTimeout(kill);
  }
  rmSync(temp, { recursive: true, force: true });
}
