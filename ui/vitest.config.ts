// SPDX-License-Identifier: MIT OR Apache-2.0
import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    name: "unit",
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // The integration tier (real dev host) has its own config: vitest.integration.config.ts.
    exclude: [...configDefaults.exclude, "src/integration/**"],
    // The package check copies the installed assets (about 3s alone), which a loaded machine stretches.
    testTimeout: 30_000,
    css: false,
  },
});
