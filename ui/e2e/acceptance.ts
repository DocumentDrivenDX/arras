// SPDX-License-Identifier: MIT OR Apache-2.0
type Runtime = {
  baseURL: string;
  schemaBaseURL: string;
  outputDir: string;
  themeId: string;
  expectedBrand: {
    name: string;
    title?: string;
    wordmark?: string;
    tagline?: string;
    logo?: string;
  };
  expectedSurface: { light: string; dark: string };
  baselineDir?: string;
};

const serialized = process.env.ARRAS_ACCEPTANCE_RUNTIME;
if (!serialized) throw new Error("Playwright config did not initialize the Arras acceptance profile");
export const acceptance = JSON.parse(serialized) as Runtime;
export const ORIGIN = acceptance.baseURL;
export const SCHEMA_ORIGIN = acceptance.schemaBaseURL;
export const EXPECTED_BRAND = acceptance.expectedBrand;
export const EXPECTED_SURFACE = acceptance.expectedSurface;
