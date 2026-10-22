// SPDX-License-Identifier: MIT OR Apache-2.0
import { defineConfig } from "vitest/config";

// Both tiers in one run, for one merged coverage report: `npm run coverage`.
export default defineConfig({
  test: {
    projects: ["./vitest.config.ts", "./vitest.integration.config.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/test/**", "src/integration/**", "src/main.tsx", "src/**/*.d.ts"],
      reporter: ["text", "json-summary", "html"],
    },
  },
});
