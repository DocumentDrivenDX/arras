// SPDX-License-Identifier: MIT OR Apache-2.0
// The design-system seam: the contract, the provider and the widgets a call site imports (ADR-029).
export {
  Button,
  DesignSystemProvider,
  Mark,
  Notice,
  Select,
  TextArea,
  TextField,
  useDesignSystem,
} from "./context";
export type {
  ButtonProps,
  ButtonVariant,
  DesignSystem,
  FieldChrome,
  MarkProps,
  NoticeProps,
  NoticeTone,
  RoleToken,
  SelectOption,
  SelectProps,
  TextAreaProps,
  TextFieldProps,
} from "./contract";
export { ROLE_TOKENS } from "./contract";
export { defaultDesignSystem } from "./default";
