// SPDX-License-Identifier: MIT OR Apache-2.0
// The sandbox's side of the standalone host (FEAT-010 OPR-15): who is being viewed, the headers that say
// so, and the dev host's control calls. Nothing here is exported for embedding; nothing is stored.

/** The dev host's rule for a made-up name (`arras.sandbox.NAME`); checked here first, so a bad name sends nothing. */
export const NAME_RULE = /^[a-z][a-z0-9_-]{0,31}$/;

/** `GET /api/people`: the sandbox's fixed people, the roles a made-up person can hold, and the default person. */
export interface People {
  people: string[];
  roles: string[];
  default: string;
}

/** Whose console this is: one of the sandbox's own people, or a made-up name holding a role. */
export type Identity =
  | { kind: "fixed"; name: string }
  | { kind: "custom"; name: string; role: string };

/** `x-arras-user` for everyone, and `x-arras-role` only for a made-up person (headers only the dev host reads). */
export function identityHeaders(who: Identity | null): Record<string, string> {
  if (!who) return {};
  return who.kind === "custom"
    ? { "x-arras-user": who.name, "x-arras-role": who.role }
    : { "x-arras-user": who.name };
}

/** Why a made-up name cannot be used, or null. The server decides too (a name that is taken is refused there). */
export function nameProblem(name: string, fixed: readonly string[]): string | null {
  if (!NAME_RULE.test(name))
    return "A name is 1 to 32 characters: a lower-case letter, then lower-case letters, digits, - or _.";
  if (fixed.includes(name)) return `${name} is one of the sandbox's own people; pick another name.`;
  return null;
}

/** The identity as one string, to give a remounted console a fresh query cache per person. */
export const identityKey = (who: Identity | null) =>
  who ? (who.kind === "custom" ? `custom:${who.name}:${who.role}` : `fixed:${who.name}`) : "none";

/** The backend names the sandbox is documented to have, used only when the registry's status cannot be read. */
export const DEFAULT_BACKENDS = ["memory", "memory_replica"];

export type Control =
  | { op: "outage"; backend: string; reason: "unreachable" | null }
  | { op: "expire" | "restore"; user: string }
  | { op: "feed" };
