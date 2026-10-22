// SPDX-License-Identifier: MIT OR Apache-2.0
/** What the interface is called, and how it is shown. */
export interface Brand {
  /** The application name: the top bar, the document title and every label that names the product. */
  name: string;
  /** An `https://` image URL for the top bar; any other value is shown as text in place of the name. */
  wordmark?: string;
  /** The page title, when it differs from the name. */
  title?: string;
  /** A line under the name. */
  tagline?: string;
  /** `"theme"` shows the design system's mark before the name; a wordmark takes precedence. */
  logo?: "theme";
}

export const DEFAULT_BRAND: Brand = { name: "Arras" };
