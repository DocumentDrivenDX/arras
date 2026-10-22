// SPDX-License-Identifier: MIT OR Apache-2.0
// The action kit (SD-013): what every surface that works on declared actions shares, with no
// knowledge of a surface. Imported by `areas/` and `browser/`; imports neither.
export { type ActionState, reasonOf, toApiError, useActionCore } from "./actionCore";
export { CrossAnchor } from "./CrossAnchor";
export { changedIds } from "./changed";
export { type Claim, claimsOf, entityActionsOf } from "./claims";
export {
  type CreateKey,
  type CreatePlan,
  createdKey,
  createPlan,
  createPlans,
} from "./createPlan";
export { type EditField, type EditPlan, editClaims, editPlan } from "./editPlan";
export {
  type EntityAction,
  entityActions,
  PRIMARY_ACTIONS,
  type PropertyAction,
  propertyActions,
  splitActions,
  type UpdateOf,
  updateOf,
} from "./entityActions";
export { APPLY_KEYS, invalidateAfterApply } from "./invalidate";
export {
  type GroupLinks,
  groupLinks,
  type LinkPlan,
  linkClaims,
  linkInputs,
  planTakes,
} from "./linkPlan";
export type {
  CrossLink,
  LinkArea,
  LinkTarget,
  LinkTo,
} from "./links";
export * from "./pieces";
export { type RetirePlan, retirePlan, retirePlans } from "./retirePlan";
export type { ActionFormArgs, ActionFormModel, Checked } from "./types";
export { useActionForm } from "./useActionForm";
