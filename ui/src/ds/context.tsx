// SPDX-License-Identifier: MIT OR Apache-2.0
// The design-system seam (ADR-029). The interface draws every button, field, dropdown, notice and mark
// through the design system in context: the built-in one, or the one a host gives `DesignSystemProvider`.
import { createContext, type ReactNode, useContext } from "react";
import type {
  ButtonProps,
  DesignSystem,
  MarkProps,
  NoticeProps,
  SelectProps,
  TextAreaProps,
  TextFieldProps,
} from "./contract";
import { defaultDesignSystem } from "./default";

const DesignSystemContext = createContext<DesignSystem>(defaultDesignSystem);

/** The design system in context: the built-in one when no provider is above. */
export const useDesignSystem = (): DesignSystem => useContext(DesignSystemContext);

/**
 * Provides `designSystem` to everything below. A partial one is completed from the built-in: a host
 * that supplies only its `Button` gets the built-in fields and notices.
 */
export function DesignSystemProvider({
  designSystem,
  children,
}: {
  designSystem?: Partial<DesignSystem>;
  children: ReactNode;
}) {
  const outer = useDesignSystem();
  const value = designSystem ? { ...outer, ...designSystem } : outer;
  return <DesignSystemContext.Provider value={value}>{children}</DesignSystemContext.Provider>;
}

// The widgets as components, so a call site imports `Button` and does not ask the context itself.
export function Button(props: ButtonProps) {
  const { Button: Widget } = useDesignSystem();
  return <Widget {...props} />;
}
export function TextField(props: TextFieldProps) {
  const { TextField: Widget } = useDesignSystem();
  return <Widget {...props} />;
}
export function TextArea(props: TextAreaProps) {
  const { TextArea: Widget } = useDesignSystem();
  return <Widget {...props} />;
}
export function Select(props: SelectProps) {
  const { Select: Widget } = useDesignSystem();
  return <Widget {...props} />;
}
export function Notice(props: NoticeProps) {
  const { Notice: Widget } = useDesignSystem();
  return <Widget {...props} />;
}
export function Mark(props: MarkProps) {
  const { Mark: Widget } = useDesignSystem();
  return <Widget {...props} />;
}
