// SPDX-License-Identifier: MIT OR Apache-2.0
// A property's value in the format the resolved view chose (CONTRACT-010, Formats). Every value is
// rendered as React text: no markup is ever interpreted, and a link is checked before it is one.
import { useState } from "react";
import type { FieldView } from "../api/types";
import { toneClass } from "./tones";
import {
  formatDate,
  formatDateTime,
  formatNumber,
  isEmpty,
  jsonText,
  listOf,
  safeLink,
  yesNo,
} from "./valueFormat";

export function Badge({ tone, children }: { tone?: string; children: string }) {
  return <span className={`gb-badge ${toneClass(tone)}`}>{children}</span>;
}

function Link({ text }: { text: string }) {
  const link = safeLink(text);
  if (!link) return <>{text}</>;
  return (
    <a href={link.href} target="_blank" rel="noopener noreferrer" className="gb-link" title={text}>
      {link.display}
    </a>
  );
}

/** A timestamp as a local, readable value; the stored RFC 3339 value on demand. */
export function When({
  value,
  time,
  label,
}: {
  value: string;
  time: boolean;
  /** The field this value belongs to, so the control says what it shows the stored value of. */
  label?: string;
}) {
  const [exact, setExact] = useState(false);
  return (
    <>
      <time dateTime={value}>{time ? formatDateTime(value) : formatDate(value)}</time>{" "}
      <button
        type="button"
        className="gb-exact"
        aria-expanded={exact}
        title="Show the stored value"
        aria-label={label ? `Show stored value of ${label}` : "Show stored value"}
        onClick={() => setExact((x) => !x)}
      >
        exact
      </button>
      {exact && (
        <span className="gb-exact-value" role="status">
          {" "}
          {value}
        </span>
      )}
    </>
  );
}

function Scalar({ field, value }: { field: FieldView; value: unknown }) {
  const text = String(value);
  switch (field.format) {
    case "prose":
      return <p className="gb-prose">{text}</p>;
    case "code":
      return <code className="gb-code">{text}</code>;
    case "link":
      return <Link text={text} />;
    case "badge":
      return <Badge tone={field.tones?.[text]}>{text}</Badge>;
    case "date":
      return <When value={text} time={false} label={field.label} />;
    case "datetime":
      return <When value={text} time label={field.label} />;
    case "number":
      return <span className="gb-num">{formatNumber(value)}</span>;
    case "boolean":
      return <>{yesNo(value)}</>;
    default:
      return <>{text}</>;
  }
}

/** Each tag with a key of its own: a value may repeat, so a repeat is numbered, never keyed by place. */
function keyed(tags: string[]): [string, string][] {
  const seen = new Map<string, number>();
  return tags.map((t) => {
    const n = seen.get(t) ?? 0;
    seen.set(t, n + 1);
    return [`${t}#${n}`, t];
  });
}

export function Value({ field, value }: { field: FieldView; value: unknown }) {
  if (field.format === "tags") {
    return (
      <span className="gb-tags">
        {keyed(listOf(value)).map(([k, t]) => (
          <Badge key={k}>{t}</Badge>
        ))}
      </span>
    );
  }
  if (field.format === "json") {
    return (
      <details className="gb-json">
        <summary>JSON</summary>
        <pre>{jsonText(value)}</pre>
      </details>
    );
  }
  return <Scalar field={field} value={value} />;
}

export const NotSet = () => <span className="gb-unset">Not set</span>;

export { isEmpty };
