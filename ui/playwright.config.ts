// SPDX-License-Identifier: MIT OR Apache-2.0
import { defineConfig } from "@playwright/test";

// Whole-stack run (B-012b): the built UI served by the dev host, which seeds the sandbox fakes.
// `npm run build` first; the web servers start from the repository root.
//
// Four projects, run in order by one worker, because the sandbox has no reset:
//   chromium      the Operator Console's specs, on the shared host (8123)
//   schema-admin  schema-admin.spec.ts, which registers a revision of `catalog`, on a host of its own
//                 (8124) so no other spec sees a module it did not expect
//   browser       the Graph Browser's whole-stack specs (browser.spec.ts, browse-history.spec.ts,
//                 routes.spec.ts), which add a hub through the operate surface, on the shared host
//   visual        screenshots of every screen of DESIGN-GB against reviewed baselines (visual.spec.ts)
// They are not chained with `dependencies`, so a failing console spec never silently skips the browser
// and visual specs. `npm run e2e` runs all of them; `npm run e2e:visual` runs the screenshots alone.
// Visual baselines are macOS only (see ui/README.md), so CI skips the visual project and runs only
// `--project=chromium --project=schema-admin --project=browser`.
const PORT = 8123;
const ADMIN_PORT = 8124;
const host = (port: number) => ({
  command: `uv run --extra devhost python -m arras.devhost --port ${port} --ui ui/dist`,
  cwd: "..",
  url: `http://127.0.0.1:${port}/api/people`,
  reuseExistingServer: false,
  timeout: 60_000,
});

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { trace: "retain-on-failure" },
  // Baselines live beside the specs, one per screen, project and platform: font rasterisation
  // differs between macOS and Linux, so a baseline is only ever compared on its own platform.
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}-{projectName}-{platform}{ext}",
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.005, animations: "disabled", caret: "hide" } },
  webServer: [host(PORT), host(ADMIN_PORT)],
  projects: [
    {
      name: "chromium",
      testIgnore: /(schema-admin|browser|browse-history|routes|visual)\.spec/,
      use: { browserName: "chromium", baseURL: `http://127.0.0.1:${PORT}` },
    },
    {
      name: "schema-admin",
      testMatch: /schema-admin\.spec/,
      use: { browserName: "chromium", baseURL: `http://127.0.0.1:${ADMIN_PORT}` },
    },
    {
      name: "browser",
      testMatch: /(browser|browse-history|routes)\.spec\.ts/,
      use: { browserName: "chromium", baseURL: `http://127.0.0.1:${PORT}` },
    },
    {
      name: "visual",
      testMatch: /visual\.spec\.ts/,
      // The same clock and language wherever the baselines are made.
      use: {
        browserName: "chromium",
        baseURL: `http://127.0.0.1:${PORT}`,
        timezoneId: "UTC",
        locale: "en-GB",
      },
    },
  ],
});
