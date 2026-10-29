// SPDX-License-Identifier: MIT OR Apache-2.0
// One-shot focus requests belong to one browser instance, including across its routes.
export interface FocusState {
  list: boolean;
  entity: boolean;
}
export function requestListFocus(scope?: FocusState) {
  if (scope) scope.list = true;
}
export function takeListFocus(scope?: FocusState): boolean {
  const pending = scope?.list ?? false;
  if (scope) scope.list = false;
  return pending;
}
export function requestEntityFocus(scope?: FocusState) {
  if (scope) scope.entity = true;
}
export function takeEntityFocus(scope?: FocusState): boolean {
  const pending = scope?.entity ?? false;
  if (scope) scope.entity = false;
  return pending;
}
