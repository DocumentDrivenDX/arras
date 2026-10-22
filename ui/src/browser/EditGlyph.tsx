// SPDX-License-Identifier: MIT OR Apache-2.0
// The small drawings of edit mode. They are interface chrome, not one of a view's 24 icons.
const GLYPHS = {
  pencil: ["M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19l-4 1Z", "M14.5 6.5l3 3"],
  lock: ["M6 11h12v9H6v-9Z", "M8.5 11V8a3.5 3.5 0 0 1 7 0v3", "M12 15v2"],
  unlock: ["M6 11h12v9H6v-9Z", "M8.5 11V8a3.5 3.5 0 0 1 6.8-1.2", "M12 15v2"],
  plus: ["M12 5v14M5 12h14"],
  more: ["M5 12h.01M12 12h.01M19 12h.01"],
  unlink: ["M6 6l12 12M18 6 6 18"],
} as const;

export type EditGlyphName = keyof typeof GLYPHS;

export function EditGlyph({ name, size }: { name: EditGlyphName; size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {GLYPHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
