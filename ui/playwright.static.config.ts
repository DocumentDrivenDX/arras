// SPDX-License-Identifier: MIT OR Apache-2.0
import { defineConfig, devices } from "@playwright/test";

// The static read-only host, whole stack (ADR-031): the built page served as plain files, read in Chromium.
// `npm run e2e:static` builds the host first. One worker: the synthetic-graph measurements are timings.
const port = Number(process.env.ARRAS_STATIC_PORT ?? 8130);
export default defineConfig({
  testDir: "./e2e-static",
  outputDir: "test-results/arras-static",
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}`, ...devices["Desktop Chrome"] },
  webServer: {
    command: `node scripts/serve-static-sites.mjs ${port}`,
    url: `http://127.0.0.1:${port}/catalog/arras-static.json`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
