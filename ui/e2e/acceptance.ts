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
  hostAppearanceProvider?: boolean;
};

const serialized = process.env.ARRAS_ACCEPTANCE_RUNTIME;
if (!serialized)
  throw new Error("Playwright config did not initialize the Arras acceptance profile");
export const acceptance = JSON.parse(serialized) as Runtime;
export const ORIGIN = acceptance.baseURL;
export const SCHEMA_ORIGIN = acceptance.schemaBaseURL;
export const EXPECTED_BRAND = acceptance.expectedBrand;
export const EXPECTED_SURFACE = acceptance.expectedSurface;
/** The host installs its own appearance provider (`hostAppearanceProvider` in createAcceptanceConfig). */
export const HOST_APPEARANCE_PROVIDER = acceptance.hostAppearanceProvider === true;

/** Whether a banner contains an exact, visible text node outside its brand glyph. */
export function hasExactVisibleBrandText(root: Element, expectedName: string): boolean {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (node.textContent?.trim() === expectedName && node.parentElement) {
      const parent = node.parentElement;
      if (
        parent.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
        !parent.closest('[role="img"], img, svg')
      ) {
        const range = document.createRange();
        range.selectNodeContents(node);
        const visible = Array.from(range.getClientRects()).some(
          (rect) => rect.width > 0 && rect.height > 0,
        );
        range.detach();
        if (visible) return true;
      }
    }
    node = walker.nextNode();
  }
  return false;
}
