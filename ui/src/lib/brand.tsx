// SPDX-License-Identifier: MIT OR Apache-2.0
// The interface's name and branding (SD-013, FR-73): one configuration read through `useBrand()`.
// The product name appears in no user-visible string except as `DEFAULT_BRAND.name`, here.

import { createContext, type ReactNode, useContext } from "react";
import { Mark } from "../ds";
import { type Brand, DEFAULT_BRAND } from "./brand-values";

export type { Brand } from "./brand-values";
export { DEFAULT_BRAND } from "./brand-values";

const BrandCtx = createContext<Brand>(DEFAULT_BRAND);

/** The host's brand, or the default when none is provided. */
export const useBrand = (): Brand => useContext(BrandCtx);

/** Provides `brand` (the default when it is undefined) to everything below. */
export function BrandProvider({ brand, children }: { brand?: Brand; children: ReactNode }) {
  return <BrandCtx.Provider value={brand ?? DEFAULT_BRAND}>{children}</BrandCtx.Provider>;
}

/** The name a document title carries. */
export const titleName = (b: Brand): string => b.title ?? b.name;

/** Whether a wordmark is an image URL: only the literal `https://` scheme is, everything else is text. */
export const isImageWordmark = (w: string | undefined): w is string =>
  typeof w === "string" && w.startsWith("https://");

/** The top bar's brand: the wordmark image for an `https://` URL, else the wordmark or the name as text. */
export function Wordmark({ className }: { className?: string }) {
  const b = useBrand();
  if (isImageWordmark(b.wordmark))
    return (
      <img className={className} src={b.wordmark} alt={b.name} style={{ maxHeight: "1.5em" }} />
    );
  if (b.logo === "theme" && b.wordmark === undefined)
    return (
      <span className={[className, "inline-flex items-center gap-2"].filter(Boolean).join(" ")}>
        <Mark label={b.name} />
        {b.name}
      </span>
    );
  return <span className={className}>{b.wordmark ?? b.name}</span>;
}

const CAPS = { name: 80, wordmark: 2048, title: 120, tagline: 200 } as const;

function field(v: unknown, cap: number): string | undefined {
  if (typeof v !== "string") return undefined;
  const t = v.trim().slice(0, cap).trim();
  return t === "" ? undefined : t;
}

/** The brand a served page carries in `<meta name="arras-brand">`; the default when it is missing or malformed. */
export function readBrandMeta(doc: Document): Brand {
  const content = doc.querySelector('meta[name="arras-brand"]')?.getAttribute("content");
  if (!content) return DEFAULT_BRAND;
  let raw: unknown;
  try {
    raw = JSON.parse(content);
  } catch {
    return DEFAULT_BRAND;
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return DEFAULT_BRAND;
  const o = raw as Record<string, unknown>;
  const name = field(o.name, CAPS.name);
  if (!name) return DEFAULT_BRAND;
  const wordmark = field(o.wordmark, CAPS.wordmark);
  const title = field(o.title, CAPS.title);
  const tagline = field(o.tagline, CAPS.tagline);
  const logo = o.logo === "theme" ? "theme" : undefined;
  return {
    name,
    ...(wordmark ? { wordmark } : {}),
    ...(title ? { title } : {}),
    ...(tagline ? { tagline } : {}),
    ...(logo ? { logo } : {}),
  };
}
