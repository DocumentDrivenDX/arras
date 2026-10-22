// SPDX-License-Identifier: MIT OR Apache-2.0
// The design-system contract (ADR-029): the widgets the interface draws with, and the role tokens it
// reads. The built-in implementation is `defaultDesignSystem` (default.tsx); a host may pass its own
// through `DesignSystemProvider` (context.tsx).
import type {
  ButtonHTMLAttributes,
  ComponentType,
  InputHTMLAttributes,
  ReactNode,
  Ref,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

/** The visual weight of a button: `primary` is filled, `secondary` outlined, `text` has no border. */
export type ButtonVariant = "primary" | "secondary" | "text";

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  /** Work the button started is in progress: it is marked `aria-busy`, shows it, and ignores clicks. */
  busy?: boolean;
  /** `"button"` when omitted, so a button inside a form never submits it by accident. */
  type?: "button" | "submit" | "reset";
  ref?: Ref<HTMLButtonElement>;
}

/** What every field has: a visible label, a hint and an error, both tied to the control. */
export interface FieldChrome {
  /** The visible label. A field without one must carry an `aria-label`. */
  label?: ReactNode;
  /** Help text under the control, referenced by `aria-describedby`. */
  hint?: ReactNode;
  /** An error under the control: sets `aria-invalid` and is referenced by `aria-describedby`. */
  error?: ReactNode;
}

export interface TextFieldProps
  extends FieldChrome,
    Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  ref?: Ref<HTMLInputElement>;
}

export interface TextAreaProps extends FieldChrome, TextareaHTMLAttributes<HTMLTextAreaElement> {
  ref?: Ref<HTMLTextAreaElement>;
}

/** One entry of a `Select`. */
export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends FieldChrome,
    Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  options: SelectOption[];
  /** A first entry with the empty value, shown while nothing is chosen. */
  placeholder?: string;
  ref?: Ref<HTMLSelectElement>;
}

export type NoticeTone = "info" | "success" | "warning" | "error";

export interface NoticeProps {
  tone?: NoticeTone;
  title?: ReactNode;
  /** `alert` for an `error` or a `warning`, else `status`, when omitted. */
  role?: "alert" | "status" | "note";
  className?: string;
  children?: ReactNode;
}

export interface MarkProps {
  /** The accessible name; without it the mark is decorative. */
  label?: string;
  size?: number;
}

/** The widgets the interface draws with. Every one is a React component that takes the props above. */
export interface DesignSystem {
  Button: ComponentType<ButtonProps>;
  TextField: ComponentType<TextFieldProps>;
  TextArea: ComponentType<TextAreaProps>;
  Select: ComponentType<SelectProps>;
  Notice: ComponentType<NoticeProps>;
  /** The product's mark, for the top bar when a brand asks for the theme's logo. */
  Mark: ComponentType<MarkProps>;
}

/**
 * The role tokens the stylesheet reads (src/styles.css), as CSS custom properties. A host sets any of
 * them on an ancestor of the interface (or on its root) to restyle it; each has a built-in value in
 * light and in dark, so none is required.
 */
export const ROLE_TOKENS = [
  "--arras-color-text",
  "--arras-color-text-muted",
  "--arras-color-surface",
  "--arras-color-surface-sunken",
  "--arras-color-ground",
  "--arras-color-border",
  "--arras-color-accent",
  "--arras-color-on-accent",
  "--arras-radius-control",
  "--arras-radius-card",
  "--arras-font-body",
  "--arras-font-mono",
  "--arras-font-size-small",
  "--arras-font-size-heading",
  "--arras-state-live",
  "--arras-state-limited",
  "--arras-state-closed",
  "--arras-state-purchasing",
] as const;

export type RoleToken = (typeof ROLE_TOKENS)[number];
