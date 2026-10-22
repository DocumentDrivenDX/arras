// SPDX-License-Identifier: MIT OR Apache-2.0
export const CANONICAL_SPECS = [
  "a11y.spec.ts",
  "brand.spec.ts",
  "browse-actions.spec.ts",
  "browse-history.spec.ts",
  "browse-new.spec.ts",
  "browse-retire.spec.ts",
  "browser.spec.ts",
  "cross-links.spec.ts",
  "flows.spec.ts",
  "host-isolation.spec.ts",
  "operator.spec.ts",
  "query.spec.ts",
  "routes.spec.ts",
  "schema-admin.spec.ts",
  "shortcuts.spec.ts",
  "umf-explorer.spec.ts",
  "visual.spec.ts",
] as const;

// Source discovery on macOS: Linux omits only the visual project by contract.
export const CANONICAL_TEST_COUNTS = {
  chromium: 132,
  "schema-admin": 3,
  browser: 70,
  visual: 67,
} as const;
