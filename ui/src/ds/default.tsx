// SPDX-License-Identifier: MIT OR Apache-2.0
// The built-in design system (ADR-029): plain React and the `.arras-*` classes of ./default.css, which
// read the role tokens through src/styles.css. It installs no theme and touches nothing outside its own
// elements.
import { type ReactNode, useId } from "react";
import type {
  ButtonProps,
  DesignSystem,
  MarkProps,
  NoticeProps,
  SelectProps,
  TextAreaProps,
  TextFieldProps,
} from "./contract";

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

function Button({
  variant = "primary",
  size = "md",
  busy = false,
  type = "button",
  className,
  onClick,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={cx("arras-btn", `arras-btn--${variant}`, `arras-btn--${size}`, className)}
      aria-busy={busy || undefined}
      data-busy={busy || undefined}
      onClick={(e) => {
        if (busy) e.preventDefault();
        else onClick?.(e);
      }}
    >
      {busy && <span className="arras-btn__spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

interface Ids {
  field: string;
  hint: string | undefined;
  error: string | undefined;
  described: string | undefined;
}

/** The ids tying a control to its hint and error, joined with the `aria-describedby` the caller gave. */
function useIds(
  id: string | undefined,
  hint: ReactNode,
  error: ReactNode,
  given: string | undefined,
): Ids {
  const generated = useId();
  const field = id ?? generated;
  const hintId = hint ? `${field}-hint` : undefined;
  const errorId = error ? `${field}-error` : undefined;
  const described = [given, hintId, errorId].filter(Boolean).join(" ") || undefined;
  return { field, hint: hintId, error: errorId, described };
}

function Field({
  ids,
  label,
  hint,
  error,
  children,
}: {
  ids: Ids;
  label: ReactNode;
  hint: ReactNode;
  error: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="arras-field">
      {label ? (
        <label className="arras-field__label" htmlFor={ids.field}>
          {label}
        </label>
      ) : null}
      {children}
      {hint ? (
        <div className="arras-field__hint" id={ids.hint}>
          {hint}
        </div>
      ) : null}
      {error ? (
        <div className="arras-field__error" id={ids.error}>
          {error}
        </div>
      ) : null}
    </div>
  );
}

function TextField({ label, hint, error, id, className, ...rest }: TextFieldProps) {
  const ids = useIds(id, hint, error, rest["aria-describedby"]);
  return (
    <Field ids={ids} label={label} hint={hint} error={error}>
      <input
        type="text"
        {...rest}
        id={ids.field}
        className={cx("arras-field__input", className)}
        aria-invalid={error ? true : rest["aria-invalid"]}
        aria-describedby={ids.described}
      />
    </Field>
  );
}

function TextArea({ label, hint, error, id, className, ...rest }: TextAreaProps) {
  const ids = useIds(id, hint, error, rest["aria-describedby"]);
  return (
    <Field ids={ids} label={label} hint={hint} error={error}>
      <textarea
        {...rest}
        id={ids.field}
        className={cx("arras-field__input", "arras-field__input--area", className)}
        aria-invalid={error ? true : rest["aria-invalid"]}
        aria-describedby={ids.described}
      />
    </Field>
  );
}

function Select({ label, hint, error, id, className, options, placeholder, ...rest }: SelectProps) {
  const ids = useIds(id, hint, error, rest["aria-describedby"]);
  return (
    <Field ids={ids} label={label} hint={hint} error={error}>
      <select
        {...rest}
        id={ids.field}
        className={cx("arras-field__input", "arras-field__select", className)}
        aria-invalid={error ? true : rest["aria-invalid"]}
        aria-describedby={ids.described}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

const GLYPH = { info: "i", success: "✓", warning: "!", error: "×" } as const;

function Notice({ tone = "info", title, role, className, children }: NoticeProps) {
  return (
    <div
      className={cx("arras-notice", `arras-notice--${tone}`, className)}
      role={role ?? (tone === "error" || tone === "warning" ? "alert" : "status")}
    >
      <span className="arras-notice__glyph" aria-hidden="true">
        {GLYPH[tone]}
      </span>
      <div className="arras-notice__body">
        {title ? <div className="arras-notice__title">{title}</div> : null}
        {children}
      </div>
    </div>
  );
}

/** A woven grid: the warp and the weft of an arras. */
function Mark({ label, size = 20 }: MarkProps) {
  return (
    <svg
      className="arras-mark"
      data-logo=""
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <path d="M3 8h18M3 16h18M8 3v18M16 3v18" />
    </svg>
  );
}

/** The design system the interface uses when its host provides none. */
export const defaultDesignSystem: DesignSystem = {
  Button,
  TextField,
  TextArea,
  Select,
  Notice,
  Mark,
};
