// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect } from "react";

/** Keeps `document.title` in step with `title`, and puts the page's own title back on unmount. */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    const before = document.title;
    return () => {
      document.title = before;
    };
  }, []);
  useEffect(() => {
    document.title = title;
  }, [title]);
}

/** A module as a title names it: its view's title, else its name. */
export const moduleTitle = (m: { name: string; view?: { title: string } | null }): string =>
  m.view?.title || m.name;

/**
 * The one title rule of both modes (SD-013, FR-72, FR-74): the parts most specific first, each the
 * entity's title-template name, the type's plural label or the area's label, and the module's title,
 * then the brand's name last, empty parts dropped. Explore and Operate each choose their parts and
 * call this.
 */
export function joinTitle(parts: readonly (string | undefined)[], brand: string): string {
  return [...parts, brand].filter(Boolean).join(" · ");
}
