// SPDX-License-Identifier: MIT OR Apache-2.0
import { type ButtonHTMLAttributes, type ReactNode, type Ref, useState } from "react";
import { useSignIn } from "../api/context";
import { ApiError, describeError } from "../api/errors";

export function Chip({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "bad" | "accent";
  title?: string;
}) {
  const tones = {
    neutral: "bg-surface2 text-muted border-line",
    ok: "bg-oksoft text-ok border-ok/40",
    warn: "bg-warnsoft text-warn border-warn/40",
    bad: "bg-badsoft text-bad border-bad/40",
    accent: "bg-accentsoft text-accent border-accent/40",
  } as const;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-px text-[11px] font-medium leading-4 ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Button({
  variant = "default",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "danger" | "ghost";
  ref?: Ref<HTMLButtonElement>;
}) {
  const v = {
    default: "bg-surface text-fg border-strong hover:bg-surface2",
    primary: "bg-accent text-accentfg border-accent hover:opacity-90",
    danger: "bg-bad text-accentfg border-bad hover:opacity-90",
    ghost: "bg-transparent text-fg border-transparent hover:bg-surface2",
  }[variant];
  return (
    <button
      type="button"
      {...rest}
      className={`inline-flex items-center gap-1 rounded border px-2.5 py-1 text-[12px] font-medium disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 ${v} ${className}`}
    />
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 p-3 text-muted">
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-strong border-t-accent" />
      {label}…
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="p-6 text-center text-muted">
      <div className="font-medium text-fg">{title}</div>
      {children && <div className="mt-1">{children}</div>}
    </div>
  );
}

/** "Sign in again", for a sign-in failure when the host supplied `onUnauthorized`; nothing otherwise. */
export function SignInButton({ error, className = "" }: { error: unknown; className?: string }) {
  const signIn = useSignIn();
  if (!signIn || !(error instanceof ApiError) || error.kind !== "sign_in") return null;
  return (
    <Button variant="primary" className={className} onClick={signIn}>
      Sign in again
    </Button>
  );
}

/**
 * A failed call, in the words of the contract: sign in again, no access, not found, or the message. A
 * sign-in failure offers "Sign in again" where the host can sign the viewer in; `inputsKept` is for a
 * panel beside a form or draft that stays as it is, and then says so.
 */
export function ErrorPanel({
  error,
  onRetry,
  inputsKept = false,
}: {
  error: unknown;
  onRetry?: () => void;
  inputsKept?: boolean;
}) {
  const { title, detail } = describeError(error);
  const signIn = error instanceof ApiError && error.kind === "sign_in";
  return (
    <div role="alert" className="m-3 rounded border border-bad/40 bg-badsoft p-3 text-bad">
      <div className="font-semibold">{title}</div>
      <div className="mt-0.5 text-fg">
        {detail}
        {signIn && inputsKept && " What you typed is kept."}
      </div>
      <div className="flex flex-wrap gap-2">
        <SignInButton error={error} className="mt-2" />
        {onRetry && (
          <Button className="mt-2" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}

export function Notice({
  tone = "neutral",
  children,
  role,
}: {
  tone?: "neutral" | "warn" | "bad" | "ok";
  children: ReactNode;
  role?: string;
}) {
  const t = {
    neutral: "border-line bg-surface2 text-fg",
    warn: "border-warn/40 bg-warnsoft text-fg",
    bad: "border-bad/40 bg-badsoft text-fg",
    ok: "border-ok/40 bg-oksoft text-fg",
  }[tone];
  return (
    <div role={role} className={`rounded border px-3 py-2 text-[12px] ${t}`}>
      {children}
    </div>
  );
}

export function Section({
  title,
  children,
  aside,
}: {
  title: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="mb-4">
      <div className="mb-1 flex items-center justify-between border-b border-line pb-1">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Copies a key or group id; the clipboard is the only place it goes. */
export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      aria-label={label}
      title={done ? "Copied" : label}
      className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[11px] text-muted hover:bg-surface2 hover:text-fg"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(
          () => {
            setDone(true);
            setTimeout(() => setDone(false), 1200);
          },
          () => undefined,
        );
      }}
    >
      {done ? "✓" : "⧉"}
    </button>
  );
}

/** A small uppercase caption for a block of a pane. */
export function Caption({ children }: { children: ReactNode }) {
  return (
    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{children}</div>
  );
}
