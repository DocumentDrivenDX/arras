// SPDX-License-Identifier: MIT OR Apache-2.0
// The 24 icons of CONTRACT-010, drawn on a 24 px grid with a 1.8 px stroke, round caps and joins,
// in `currentColor` (DESIGN-GB, Icons). The glyph is decoration: the label next to it carries the
// meaning, so every drawing is `aria-hidden`.

export const ICON_PATHS = {
  box: ["M4 8l8-4 8 4v8l-8 4-8-4V8Z", "M4 8l8 4 8-4", "M12 12v8"],
  package: ["m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 9 8-4.5M12 12 4 7.5M12 12v9"],
  puzzle: [
    "M10 4a2 2 0 1 1 4 0v2h4v4h-2a2 2 0 1 0 0 4h2v4h-4v-2a2 2 0 1 0-4 0v2H6v-4h2a2 2 0 1 0 0-4H6V6h4V4Z",
  ],
  "file-text": ["M6 3h8l4 4v14H6V3Z", "M14 3v4h4", "M9 12h6M9 16h6"],
  folder: ["M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6Z"],
  user: ["M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z", "M4 21c0-4 3.5-6 8-6s8 2 8 6"],
  users: [
    "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
    "M2.5 20c0-3.5 3-5.5 6.5-5.5s6.5 2 6.5 5.5",
    "M16 4.5a3.5 3.5 0 0 1 0 6.5M18 14.8c2.2.6 3.5 2.3 3.5 5.2",
  ],
  building: ["M5 21V4h9v17", "M14 9h5v12", "M3 21h18", "M8 8h2M8 12h2M8 16h2"],
  tag: ["M3 12V4h8l10 10-8 8L3 12Z", "M7.5 8.5h.01"],
  flag: ["M6 21V4m0 1h11l-2 4 2 4H6"],
  alert: ["M12 4 2.5 20h19L12 4Zm0 6v5m0 3v.01"],
  "check-circle": ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M8 12l3 3 5-6"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5l3 2"],
  calendar: ["M4 6h16v14H4V6Z", "M4 10h16M8 3v4M16 3v4"],
  link: [
    "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1",
  ],
  globe: [
    "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z",
    "M3 12h18",
    "M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  ],
  wrench: [
    "M15 4a4.5 4.5 0 0 0-3.8 6.8L4 18l2 2 7.2-7.2A4.5 4.5 0 0 0 20 9l-3 3-3-1-1-3 3-3a4.5 4.5 0 0 0-1-1Z",
  ],
  scale: [
    "M12 4v16M7 20h10M4 7h16",
    "M7 7l-3 7a3 3 0 0 0 6 0L7 7Z",
    "M17 7l-3 7a3 3 0 0 0 6 0l-3-7Z",
  ],
  book: ["M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4Zm3 12h10"],
  chart: ["M4 20V4M4 20h16", "M8 16v-5M12 16V8M16 16v-8"],
  shield: ["M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3Z"],
  star: ["M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3Z"],
  bolt: ["M13 3 5 13h6l-1 8 8-10h-6l1-8Z"],
  circle: ["M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z"],
} as const;

export type IconName = keyof typeof ICON_PATHS;

/** The interface's own glyphs, outside the closed set a module may choose from. */
export const GLYPH_PATHS = {
  search: ["M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z", "m20 20-4-4"],
  lock: ["M5 11h14v9H5v-9Z", "M8 11V8a4 4 0 0 1 8 0v3"],
  alert: ICON_PATHS.alert,
  check: ["m5 12 5 5 9-10"],
  arrow: ["M5 12h14m-5-5 5 5-5 5"],
  chevron: ["m9 6 6 6-6 6"],
} as const;

export type GlyphName = keyof typeof GLYPH_PATHS;

export const ICON_NAMES = Object.keys(ICON_PATHS) as IconName[];

const hasIcon = (n: string): n is IconName => Object.hasOwn(ICON_PATHS, n);

/** An unknown name (a newer vocabulary) draws the default `circle`. */
export const iconPaths = (name: string): readonly string[] =>
  ICON_PATHS[hasIcon(name) ? name : "circle"];

export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return <Paths paths={iconPaths(name)} size={size} />;
}

export function Glyph({ name, size = 16 }: { name: GlyphName; size?: number }) {
  return <Paths paths={GLYPH_PATHS[name]} size={size} />;
}

function Paths({ paths, size }: { paths: readonly string[]; size: number }) {
  return (
    <svg
      className="gb-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
