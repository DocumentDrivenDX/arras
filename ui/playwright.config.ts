// SPDX-License-Identifier: MIT OR Apache-2.0
import { resolve } from "node:path";
import { createAcceptanceConfig } from "./src/testkit/index";

const port = Number(process.env.ARRAS_ACCEPTANCE_PORT ?? 8123);
const schemaPort = Number(process.env.ARRAS_ACCEPTANCE_SCHEMA_PORT ?? 8124);
const baseURL = `http://127.0.0.1:${port}`;
const schemaBaseURL = `http://127.0.0.1:${schemaPort}`;
const config = createAcceptanceConfig({
  baseURL,
  schemaBaseURL,
  outputDir: resolve("test-results/arras-acceptance"),
  expectedSurface: {
    light: "rgb(246, 247, 249)",
    dark: "rgb(15, 19, 26)",
  },
  ...(process.platform === "darwin" ? { baselineDir: resolve("e2e/__screenshots__") } : {}),
});

const host = (url: string) => ({
  command: `uv run --extra devhost python -m arras.devhost --port ${new URL(url).port} --ui ui/dist`,
  cwd: "..",
  url: `${url}/api/people`,
  reuseExistingServer: false,
  timeout: 60_000,
});

export default {
  ...config,
  webServer: [host(baseURL), host(schemaBaseURL)],
};
