// SPDX-License-Identifier: MIT OR Apache-2.0
// What an integration test uses: the file's real dev host, the console's connection props for a
// sandbox person, raw calls (for setup and for comparing with what the UI shows) and the control
// endpoint. Node's fetch may set `Origin`; the server refuses a POST without its own origin.
import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterAll, beforeAll } from "vitest";
import { ArrasConsole, type ArrasConsoleProps } from "../ArrasConsole";
import { createClient } from "../api/client";
import { ArrasProvider } from "../api/context";
import { type DevHost, startDevHost } from "./server";

export type Person = "root" | "alice" | "carol" | "bob" | "dave" | "nobody";
/** A sandbox person, or a made-up name holding a role (`x-arras-role`, the dev host's role picker). */
export type Who = Person | { name: string; role: string };

let host: DevHost | null = null;

/** Start this file's dev host before its tests and stop it after them. */
export function withDevHost(opts: { demo?: boolean } = {}) {
  beforeAll(async () => {
    host = await startDevHost(opts);
  }, 120_000);
  afterAll(async () => {
    await host?.stop();
    host = null;
  });
}

export function server(): DevHost {
  if (!host) throw new Error("no dev host: call withDevHost() at the top of the file");
  return host;
}

export const headersFor = (who: Who): Record<string, string> =>
  typeof who === "string"
    ? { "x-arras-user": who, origin: server().base }
    : { "x-arras-user": who.name, "x-arras-role": who.role, origin: server().base };

/** The props a host passes: absolute bases on the dev host and the person's header. */
export function conn(person: Who | (() => Who), onUnauthorized?: () => void) {
  const who = typeof person === "function" ? person : () => person;
  return {
    operateBase: `${server().base}/api/operate`,
    consoleBase: `${server().base}/api/console`,
    schemaBase: `${server().base}/api/schema`,
    getHeaders: () => headersFor(who()),
    onUnauthorized,
  };
}

export const client = (person: Who, onUnauthorized?: () => void) =>
  createClient(conn(person, onUnauthorized));

export const testQueryClient = (staleTime = 0) =>
  new QueryClient({ defaultOptions: { queries: { retry: false, staleTime, gcTime: 0 } } });

export function renderLive(
  ui: ReactElement,
  person: Who = "alice",
  opts: { onUnauthorized?: () => void; queryClient?: QueryClient } = {},
) {
  return render(
    <ArrasProvider
      queryClient={opts.queryClient ?? testQueryClient()}
      {...conn(person, opts.onUnauthorized)}
    >
      {ui}
    </ArrasProvider>,
  );
}

export function renderLiveConsole(person: Who = "alice", props: Partial<ArrasConsoleProps> = {}) {
  return render(<ArrasConsole {...conn(person, props.onUnauthorized)} {...props} />);
}

/** A raw call to the dev host, as JSON. */
export async function call<T = unknown>(
  path: string,
  body?: unknown,
  person: Who = "alice",
): Promise<{ status: number; body: T; headers: Headers }> {
  const r = await fetch(`${server().base}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      ...headersFor(person),
      ...(body === undefined ? {} : { "content-type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await r.text();
  let parsed: unknown = text;
  try {
    parsed = JSON.parse(text);
  } catch {
    /* not JSON */
  }
  return { status: r.status, body: parsed as T, headers: r.headers };
}

export const gql = <T = unknown>(
  query: string,
  variables?: Record<string, unknown>,
  person: Who = "alice",
  module?: string,
) => call<T>(`/api/console/graphql${module ? `/${module}` : ""}`, { query, variables }, person);

export const invoke = <T = unknown>(
  action: string,
  inputs: Record<string, unknown>,
  person: Who = "alice",
  extra: Record<string, unknown> = {},
) => call<T>(`/api/operate/actions/catalog/${action}/invoke`, { inputs, ...extra }, person);

/** Break or mend the sandbox through the dev host's control endpoint. */
export async function control(
  body:
    | { op: "expire" | "restore"; user: string }
    | { op: "outage"; backend: "memory" | "memory_replica"; reason: string | null }
    | { op: "feed" }
    | { op: "register"; document: string }
    | { op: "grant" | "revoke"; user: Person; module: string; modes?: string[] }
    | {
        op: "search";
        backend: "memory" | "memory_replica";
        type: string;
        mode: "none" | "substring" | null;
      },
) {
  const r = await call("/api/dev/control", body);
  if (r.status !== 200)
    throw new Error(
      `control ${JSON.stringify(body)} answered ${r.status}: ${JSON.stringify(r.body)}`,
    );
}

let n = 0;
/** A key no other test in this file uses (the sandbox has no reset). */
export const unique = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${++n}`;

/**
 * Run `fn` while bob holds only the `keep` modes on `catalog`. The sandbox's operators are alice, bob
 * and root (CONTRACT-010); carol and dave are not, so an operator with less access is bob with some
 * of it revoked, and what is revoked is granted back.
 */
export async function asBob(
  keep: ("read" | "write" | "journal")[],
  fn: () => Promise<void>,
): Promise<void> {
  const all = ["read", "write", "journal"] as const;
  const revoked = all.filter((m) => !keep.includes(m));
  await control({ op: "revoke", user: "bob", module: "catalog", modes: [...revoked] });
  try {
    await fn();
  } finally {
    await control({ op: "grant", user: "bob", module: "catalog", modes: [...revoked] });
  }
}
