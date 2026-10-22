// SPDX-License-Identifier: MIT OR Apache-2.0
// The neutral shapes of the action kit's form model (SD-013 D2): what a surface hands in and what it
// gets back. Nothing here knows a surface's caches, routes or impact view.
import type { ArrasClient } from "../api/client";
import type { ApiError } from "../api/errors";
import type {
  ActionInfo,
  Effect,
  InputSpec,
  ModuleInfo,
  Receipt,
  Revision,
  Validation,
} from "../api/types";
import type { Built, FieldValue, violationsByField } from "../lib/inputs";

/** A validation and the input signature it answers. */
export interface Checked {
  sig: string;
  result: Validation;
}

export interface ActionFormArgs {
  /** The module the action belongs to; undefined while the surface has not loaded it. */
  module: ModuleInfo | undefined;
  /** The qualified action name. */
  action: string;
  /** Initial text by input name. */
  prefill?: Record<string, string>;
  /** Called once after an apply, with the receipt; the surface invalidates its own reads here. */
  onApplied: (receipt: Receipt) => void;
  /** Reload the registry after a revision conflict; the form is rebuilt from the module it returns. */
  reloadModule: () => Promise<ModuleInfo | undefined>;
  client: ArrasClient;
  /** A refusal the surface already holds for this action: the form is locked while it is set. */
  refusal?: ApiError | null;
  /** Told when the provider refuses the viewer, so the surface can keep it; the kit decides nothing. */
  onRefused?: (error: ApiError) => void;
}

export interface ActionFormModel {
  info: ActionInfo | undefined;
  specs: InputSpec[];
  revision: Revision;
  values: Record<string, FieldValue>;
  touched: Record<string, boolean>;
  built: Built;
  violations: ReturnType<typeof violationsByField>;
  failures: { id: string; reason: string }[];
  checked: Checked | null;
  fresh: Validation | null;
  stale: boolean;
  validating: boolean;
  submitting: boolean;
  receipt: Receipt | null;
  error: ApiError | null;
  /** The provider's refusal of this viewer, as held by the form or given in; the kit never acts on it. */
  refusal: ApiError | null;
  conflict: boolean;
  epoch: number;
  locked: boolean;
  canConfirm: boolean;
  effects: Effect[];
  status: "preview" | "stale" | "applied";
  valid: boolean;
  validate: () => Promise<Validation | null>;
  confirm: () => Promise<void>;
  onChange: (field: string, value: string) => void;
  onBlur: (field: string) => void;
  reset: () => void;
  editAgain: () => void;
}
