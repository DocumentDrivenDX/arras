// SPDX-License-Identifier: MIT OR Apache-2.0
// Public, synthetic downstream theme package used only by the external qualification fixture.
import { useId, type PropsWithChildren } from "react";
import {
  DesignSystemProvider,
  type DesignSystem,
  type ButtonProps,
  type TextFieldProps,
  type TextAreaProps,
  type SelectProps,
  type NoticeProps,
  type MarkProps,
  useDesignSystem,
} from "@documentdrivendx/arras-ui";

function HostButton({ busy, variant = "primary", children, ref, ...props }: ButtonProps) {
  return (
    <button ref={ref} data-theme-button data-variant={variant} aria-busy={busy || undefined} {...props}>
      {children}
    </button>
  );
}

function HostTextField({ label, hint, error, id, ref, ...props }: TextFieldProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <label>
      {label}
      <input ref={ref} id={inputId} data-theme-text-field aria-describedby={hint || error ? `${inputId}-hint` : undefined} aria-invalid={Boolean(error) || undefined} {...props} />
      {(hint || error) && <span id={`${inputId}-hint`}>{error ?? hint}</span>}
    </label>
  );
}

function HostTextArea({ label, hint, error, id, ref, ...props }: TextAreaProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <label>
      {label}
      <textarea ref={ref} id={inputId} data-theme-text-area aria-describedby={hint || error ? `${inputId}-hint` : undefined} aria-invalid={Boolean(error) || undefined} {...props} />
      {(hint || error) && <span id={`${inputId}-hint`}>{error ?? hint}</span>}
    </label>
  );
}

function HostSelect({ label, hint, error, id, options, placeholder, ref, ...props }: SelectProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <label>
      {label}
      <select ref={ref} id={inputId} data-theme-select aria-describedby={hint || error ? `${inputId}-hint` : undefined} aria-invalid={Boolean(error) || undefined} {...props}>
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((option) => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>)}
      </select>
      {(hint || error) && <span id={`${inputId}-hint`}>{error ?? hint}</span>}
    </label>
  );
}

function HostNotice({ tone = "info", title, children, ...props }: NoticeProps) {
  return (
    <section data-theme-notice data-tone={tone} role={props.role ?? (tone === "error" || tone === "warning" ? "alert" : "status")}>
      <strong>{title}</strong>{children}
    </section>
  );
}

function HostMark({ label, size = 24 }: MarkProps) {
  return (
    <span data-theme-mark role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} style={{ inlineSize: size, blockSize: size, display: "inline-grid", placeItems: "center", borderRadius: "var(--arras-radius-card)", color: "var(--arras-color-on-accent)", background: "var(--arras-color-accent)" }}>
      A
    </span>
  );
}

const neutralWidgets: Partial<DesignSystem> = {
  Button: HostButton,
  TextField: HostTextField,
  TextArea: HostTextArea,
  Select: HostSelect,
  Notice: HostNotice,
  Mark: HostMark,
};

export function NeutralThemeProvider({ children }: PropsWithChildren) {
  return <DesignSystemProvider designSystem={neutralWidgets}>{children}</DesignSystemProvider>;
}

export function NeutralThemeControls() {
  const widgets = useDesignSystem();
  return (
    <section aria-label="Downstream widget controls">
      <h1>Downstream themed controls</h1>
      <widgets.Mark label="Neutral host mark" />
      <widgets.Button>Host action</widgets.Button>
      <widgets.TextField label="Host name" name="name" />
      <widgets.TextArea label="Host notes" name="notes" />
      <widgets.Select label="Host mode" options={[{ value: "one", label: "One" }]} placeholder="Choose mode" />
      <widgets.Notice title="Host status">Theme fixture is ready.</widgets.Notice>
    </section>
  );
}
