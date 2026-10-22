// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ErrorBody, Failure, Violation } from "./types";

/** What the UI shows for a failed call; derived from the HTTP status and CONTRACT-009's error body. */
export type ErrorKind =
  | "sign_in" // 401
  | "no_access" // 403 Refused
  | "not_offered" // 403 from the host's authorize_action
  | "forbidden" // 403 origin
  | "not_found" // 404
  | "conflict" // 409
  | "revision_conflict" // 409 Conflict(revision)
  | "invalid" // 400
  | "precondition" // 422
  | "unsupported" // 501
  | "unavailable" // 503
  | "rate_limited" // 429
  | "version" // contract version mismatch
  | "network"
  | "other";

export class ApiError extends Error {
  readonly status: number;
  readonly type: string;
  readonly reason?: string;
  readonly backend?: string;
  readonly violations: Violation[];
  readonly failures: Failure[];
  readonly code?: string; // a GraphQL extensions.code
  /** A 501's `construct` and `supported` (CONTRACT-001, Unsupported): what was not served and what is. */
  readonly construct?: string;
  readonly supported: string[];
  readonly retryAfter?: number;
  readonly kind: ErrorKind;

  constructor(status: number, body: Partial<ErrorBody> & { code?: string }, retryAfter?: number) {
    super(body.message ?? `request failed (${status})`);
    this.status = status;
    this.type = body.type ?? "Error";
    this.reason = body.reason;
    this.backend = body.backend;
    this.violations = body.violations ?? [];
    this.failures = body.failures ?? [];
    this.code = body.code;
    this.construct = typeof body.construct === "string" ? body.construct : undefined;
    this.supported = Array.isArray(body.supported)
      ? body.supported.filter((x): x is string => typeof x === "string")
      : [];
    this.retryAfter = retryAfter;
    this.kind = kindOf(status, this.type, body.reason, body.message, body.code);
  }
}

const STATUS_KIND: Record<number, ErrorKind> = {
  404: "not_found",
  400: "invalid",
  422: "precondition",
  429: "rate_limited",
  501: "unsupported",
  503: "unavailable",
};

// A GraphQL error inside a 200 (CONTRACT-006 answers an executed query with 200): by its code.
const CODE_KIND: Record<string, ErrorKind> = {
  REFUSED: "no_access",
  NOT_FOUND: "not_found",
  UNAVAILABLE: "unavailable",
};

function forbiddenKind(type: string, reason?: string, message?: string, code?: string): ErrorKind {
  if (type === "Forbidden") return "forbidden";
  if (reason === "no_access" || type === "Refused" || code === "REFUSED") {
    return reason === undefined && message === "not offered" ? "not_offered" : "no_access";
  }
  return "forbidden";
}

function kindOf(
  status: number,
  type: string,
  reason?: string,
  message?: string,
  code?: string,
): ErrorKind {
  if (status === 401 || reason === "token_expired") return "sign_in";
  if (status === 0) return "network";
  if (status === 403) return forbiddenKind(type, reason, message, code);
  if (status === 409) return reason === "revision" ? "revision_conflict" : "conflict";
  return STATUS_KIND[status] ?? (code ? CODE_KIND[code] : undefined) ?? "other";
}

/** Plain words for an error that has no more specific place on screen. */
export function describeError(e: unknown): { title: string; detail: string } {
  if (!(e instanceof ApiError)) {
    return { title: "Something went wrong", detail: e instanceof Error ? e.message : String(e) };
  }
  switch (e.kind) {
    case "sign_in":
      return {
        title: "Sign in again",
        detail: "Your session has expired (token_expired). Sign in, then retry.",
      };
    case "no_access":
      return {
        title: "No access",
        detail: `You do not have access to this (${e.reason ?? "no_access"}). Ask the owner of the backend for the grant.`,
      };
    case "not_offered":
      return { title: "Not offered", detail: "This host does not offer that action to you." };
    case "not_found":
      return { title: "Not found", detail: "No such module or action, or you cannot read it." };
    case "unsupported":
      return { title: "Not supported", detail: e.message };
    case "unavailable":
      return {
        title: "Backend unavailable",
        detail: `${e.backend ?? "A backend"} is unavailable${e.reason ? ` (${e.reason})` : ""}.`,
      };
    case "rate_limited":
      return { title: "Too many requests", detail: "Slow down; the request will be retried." };
    case "network":
      return {
        title: "Network error",
        detail: `The server could not be reached (${e.message}). Check the connection and retry.`,
      };
    case "precondition":
      return {
        title: "A precondition failed",
        detail: ["Nothing was applied.", e.failures.map((f) => `${f.id}: ${f.reason}`).join("; ")]
          .join(" ")
          .trim(),
      };
    case "invalid":
      return {
        title: "Invalid request",
        detail: e.violations.length
          ? e.violations.map((v) => `${v.path}: ${v.message}`).join("; ")
          : e.message,
      };
    case "conflict":
    case "revision_conflict":
      return { title: "Conflict", detail: e.message };
    default:
      return {
        title: e.status ? `Request failed (${e.status})` : "Request failed",
        detail: e.message,
      };
  }
}
