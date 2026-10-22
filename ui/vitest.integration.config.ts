// SPDX-License-Identifier: MIT OR Apache-2.0
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The integration tier: the real components and client against the real dev host (one per test file,
// started by src/integration/harness.tsx), no fetch double. Needs `uv` and the repository's Python
// environment; global-setup fails the run at once, with the reason, when the host cannot start.
export default defineConfig({
  plugins: [react()],
  test: {
    name: "integration",
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts", "./src/integration/setup.ts"],
    globalSetup: ["./src/integration/global-setup.ts"],
    include: ["src/integration/**/*.int.test.{ts,tsx}"],
    css: false,
    testTimeout: 30_000,
    hookTimeout: 120_000,
    maxWorkers: 4,
    // After the unit tier when both run together (vitest.coverage.config.ts).
    sequence: { groupOrder: 1 },
  },
});
