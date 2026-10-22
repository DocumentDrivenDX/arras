// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ReactNode } from "react";
import { ApiError, describeError } from "../api/errors";
import { SignInButton } from "../components/ui";
import { keyed } from "../lib/format";

function Violations({ error }: { error: ApiError }) {
  if (error.violations.length === 0) return null;
  return (
    <ul className="m-0 list-disc pl-5" data-testid="query-violations">
      {keyed(error.violations, (v) => `${v.path}:${v.code}:${v.message}`).map(
        ({ key, item: v }) => (
          <li key={key}>
            <span className="arras-mono">{v.path}</span>{" "}
            <span className="arras-mono text-muted">{v.code}</span>: {v.message}
          </li>
        ),
      )}
    </ul>
  );
}

function Unsupported({ error, detail }: { error: ApiError; detail: string }) {
  return (
    <>
      {detail}
      {error.construct && (
        <div>
          Not served: <span className="arras-mono">{error.construct}</span>
        </div>
      )}
      {error.supported.length > 0 && (
        <div>
          Supported:
          <ul className="m-0 list-disc pl-5">
            {keyed(error.supported, (s) => s).map(({ key, item: s }) => (
              <li key={key} className="arras-mono">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

/** What the library said, in the words of its status; the query's own text is never in it. */
function bodyOf(error: unknown, detail: string): ReactNode {
  if (!(error instanceof ApiError)) return detail;
  switch (error.kind) {
    case "invalid":
      return error.violations.length > 0 ? <Violations error={error} /> : detail;
    case "not_found":
      // An unreadable module is answered as an unknown one, so its violations name only what was typed.
      return (
        <>
          No such module or type, or you cannot read it.
          <Violations error={error} />
        </>
      );
    case "unsupported":
      return <Unsupported error={error} detail={detail} />;
    case "sign_in":
      return `${detail} Your history here is kept. What you typed is kept.`;
    case "conflict":
    case "revision_conflict":
      return `${detail} The answer is not yet current; try again shortly, or choose LATEST.`;
    default:
      return detail;
  }
}

/** A failed run, as the library states it: never an empty grid. */
export function QueryError({ error }: { error: unknown }) {
  const { title, detail } = describeError(error);
  return (
    <div
      role="alert"
      data-testid="query-error"
      className="mx-3 mt-2 rounded border border-bad/40 bg-badsoft p-3 text-bad"
    >
      <div className="font-semibold">{title}</div>
      <div className="mt-0.5 text-fg">{bodyOf(error, detail)}</div>
      <SignInButton error={error} className="mt-2" />
    </div>
  );
}
