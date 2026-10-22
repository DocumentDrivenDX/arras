// SPDX-License-Identifier: MIT OR Apache-2.0
// Focus after a navigation the browser made itself (SD-013 Accessibility): the dialog that caused it is
// gone, so the page it opens takes focus on its heading rather than leaving it on the body. One-shot:
// the destination consumes the request when its heading mounts.
let pending = false;

export const requestListFocus = () => {
  pending = true;
};

export const takeListFocus = (): boolean => {
  const was = pending;
  pending = false;
  return was;
};

// The same for an entity's page after a create: the new page takes focus on its title.
let entityPending = false;

export const requestEntityFocus = () => {
  entityPending = true;
};

export const takeEntityFocus = (): boolean => {
  const was = entityPending;
  entityPending = false;
  return was;
};
