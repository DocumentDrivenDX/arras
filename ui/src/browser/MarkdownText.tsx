// SPDX-License-Identifier: MIT OR Apache-2.0
// The `markdown` format drawn as React elements (CONTRACT-010 A, ADR-032). The tree comes from `markdown.ts`,
// which makes nothing of the text that is not one of a closed set of elements; no HTML string is built or set.
import type { ReactNode } from "react";
import { type Block, type Inline, parseMarkdown } from "./markdown";

function inline(nodes: Inline[]): ReactNode[] {
  return nodes.map(oneInline);
}

function oneInline(n: Inline): ReactNode {
  switch (n.t) {
    case "text":
      return n.v;
    case "code":
      return (
        <code key={n.id} className="gb-code">
          {n.v}
        </code>
      );
    case "strong":
      return <strong key={n.id}>{inline(n.c)}</strong>;
    case "em":
      return <em key={n.id}>{inline(n.c)}</em>;
    case "link":
      return (
        <a key={n.id} href={n.href} target="_blank" rel="noopener noreferrer" className="gb-link">
          {inline(n.c)}
        </a>
      );
  }
}

const HEADINGS = ["h4", "h5", "h6", "h6", "h6", "h6"] as const;

function rows(list: Block & { t: "ul" | "ol" }): ReactNode[] {
  return list.items.map((it) => (
    <li key={it.id}>
      {inline(it.c)}
      {it.sub && block(it.sub)}
    </li>
  ));
}

function block(b: Block): ReactNode {
  switch (b.t) {
    case "h": {
      const H = HEADINGS[b.level - 1] ?? "h6";
      return <H key={b.id}>{inline(b.c)}</H>;
    }
    case "p":
      return <p key={b.id}>{inline(b.c)}</p>;
    case "ul":
      return <ul key={b.id}>{rows(b)}</ul>;
    case "ol":
      return <ol key={b.id}>{rows(b)}</ol>;
    case "code":
      return (
        <pre key={b.id} className="gb-md-code">
          <code>{b.v}</code>
        </pre>
      );
    case "quote":
      return <blockquote key={b.id}>{b.c.map(block)}</blockquote>;
    case "hr":
      return <hr key={b.id} />;
    case "table":
      return (
        // a wide table scrolls on its own: the region is focusable so a keyboard can scroll it
        // biome-ignore lint/a11y/useSemanticElements: a labelled scroll region has no native element
        // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be focusable (WCAG 2.1.1)
        <div key={b.id} className="gb-md-table" role="region" aria-label="Table" tabIndex={0}>
          <table>
            <thead>
              <tr>
                {b.head.map((c, i) => (
                  // a table's columns are fixed by its header: their place is their identity
                  // biome-ignore lint/suspicious/noArrayIndexKey: columns of one row never reorder
                  <th key={i} scope="col">
                    {inline(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.rows.map((r, ri) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: rows of a parsed table never reorder
                <tr key={ri}>
                  {r.map((c, ci) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: cells of one row never reorder
                    <td key={ci}>{inline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}

/** Markdown text as elements; a value too long to read as Markdown is shown as text. */
export function MarkdownText({ text }: { text: string }) {
  const tree = parseMarkdown(text);
  if (!tree) return <p className="gb-prose">{text}</p>;
  return <div className="gb-md">{tree.map(block)}</div>;
}
