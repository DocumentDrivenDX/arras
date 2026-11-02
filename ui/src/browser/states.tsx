// SPDX-License-Identifier: MIT OR Apache-2.0
// The states every screen shares (DESIGN-GB, States): loading, not available, backend down and the
// expired session. Each says what happened in words, never an error code or a backend message.
import type { ReactNode } from "react";
import { useId } from "react";
import { Glyph, type GlyphName } from "./icons";

export function Skeleton({ label = "Loading" }: { label?: string }) {
  return (
    <div className="gb-skeleton" role="status" aria-busy="true">
      <span className="gb-sr">{label}</span>
      <div className="gb-skel gb-skel-title" />
      <div className="gb-skel gb-skel-w80" />
      <div className="gb-skel gb-skel-w60" />
      <div className="gb-skel gb-skel-block" />
    </div>
  );
}

function State({
  glyph,
  title,
  children,
  action,
}: {
  glyph: GlyphName;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  const heading = useId();
  return (
    <section className="gb-state" data-testid="gb-state" aria-labelledby={heading}>
      <span className="gb-state-icon">
        <Glyph name={glyph} size={26} />
      </span>
      <h1 id={heading}>{title}</h1>
      <p>{children}</p>
      {action}
    </section>
  );
}

/** The same page for a missing, hidden, malformed or unreadable location: no key, type or reason. */
export function NotAvailable({ onBack, backTo }: { onBack?: () => void; backTo?: string }) {
  return (
    <State
      glyph="lock"
      title="Not available"
      action={
        onBack && (
          <button type="button" className="gb-btn" onClick={onBack}>
            Back to {backTo ?? "search"}
          </button>
        )
      }
    >
      This page does not exist or you cannot read it.
    </State>
  );
}

export function BackendDown({ backend, onRetry }: { backend?: string; onRetry: () => void }) {
  return (
    <State
      glyph="alert"
      title="The catalog did not answer"
      action={
        <button type="button" className="gb-btn gb-primary" onClick={onRetry}>
          Retry
        </button>
      }
    >
      {backend ? `${backend} is not responding.` : "The backend is not responding."} Try again in a
      moment.
    </State>
  );
}

export function Expired() {
  return (
    <State glyph="lock" title="Your session has expired">
      Sign in again to continue. This page and what you typed are kept.
    </State>
  );
}

export function Failed({ onRetry }: { onRetry: () => void }) {
  return (
    <State
      glyph="alert"
      title="Something went wrong"
      action={
        <button type="button" className="gb-btn gb-primary" onClick={onRetry}>
          Retry
        </button>
      }
    >
      The page could not be read. Try again.
    </State>
  );
}
