// SPDX-License-Identifier: MIT OR Apache-2.0
// Fixtures for the Graph Browser's whole-stack tests, made through the operate surface as alice (the
// sandbox has no reset and one server serves the whole run): a hub, a use case that many solutions
// address through the declared AddSolution action, in batches of at most 100 (CONTRACT-009).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { type APIRequestContext, expect } from "@playwright/test";
import { ORIGIN } from "./acceptance";

const ALICE = { "x-arras-user": "alice", origin: ORIGIN };

async function post(request: APIRequestContext, path: string, data: unknown) {
  return request.post(`/api/operate${path}`, { data, headers: ALICE });
}

async function exists(
  request: APIRequestContext,
  query: string,
  field: string,
  module = "catalog",
): Promise<boolean> {
  const r = await request.post(`/api/console/graphql/${module}`, {
    data: { query },
    headers: ALICE,
  });
  const body = (await r.json()) as { data?: Record<string, unknown> };
  return !!body.data?.[field];
}

/** A use case `code` addressed by `n` solutions named "<prefix> 000" and on; made once per run. */
export async function ensureHub(
  request: APIRequestContext,
  code: string,
  n: number,
  prefix = "Hub solution",
  module = "catalog",
) {
  if (await exists(request, `{ useCase(key: "${code}") { key } }`, "useCase", module)) return;
  const made = await post(request, `/actions/${module}/AddUseCase/invoke`, {
    inputs: { code, name: `Hub use case ${n}`, workArea: "hub" },
  });
  expect(made.status(), await made.text()).toBe(200);
  for (let from = 0; from < n; from += 100) {
    const items = Array.from({ length: Math.min(100, n - from) }, (_, k) => {
      const i = from + k;
      return {
        code: `${code}-s${String(i).padStart(3, "0")}`,
        name: `${prefix} ${String(i).padStart(3, "0")}`,
        useCase: code,
        // the example catalog's AddSolution requires a delivery mode; the sandbox's does not take one
        ...(module === "atlas" ? { deliveryMode: i % 2 === 0 ? "chat" : "app" } : {}),
      };
    });
    const r = await post(request, `/actions/${module}/AddSolution/batch`, { items, atomic: true });
    expect(r.status(), await r.text()).toBe(200);
  }
}

/** One solution with a launch URL, long text and every format the page renders, for the screenshots. */
export async function ensureUseCase(
  request: APIRequestContext,
  code: string,
  name: string,
  workArea: string,
) {
  if (await exists(request, `{ useCase(key: "${code}") { key } }`, "useCase")) return;
  const r = await post(request, "/actions/catalog/AddUseCase/invoke", {
    inputs: { code, name, workArea },
  });
  expect(r.status(), await r.text()).toBe(200);
}

export async function control(request: APIRequestContext, data: Record<string, unknown>) {
  const r = await request.post("/api/dev/control", { data, headers: { origin: ORIGIN } });
  expect(r.status(), await r.text()).toBe(200);
}

/**
 * Run `fn` while bob holds only the `keep` modes on `catalog`. The sandbox's operators are alice, bob
 * and root; carol and dave are not (CONTRACT-010), so an operator with less access is bob with some
 * of it revoked, granted back afterwards.
 */
export async function asBob(
  request: APIRequestContext,
  keep: ("read" | "write" | "journal")[],
  fn: () => Promise<void>,
) {
  const revoked = (["read", "write", "journal"] as const).filter((m) => !keep.includes(m));
  await control(request, { op: "revoke", user: "bob", module: "catalog", modes: revoked });
  try {
    await fn();
  } finally {
    await control(request, { op: "grant", user: "bob", module: "catalog", modes: revoked });
  }
}

const repoFile = (...p: string[]) => join(import.meta.dirname, "../..", ...p);
const rename = (x: unknown): unknown => {
  if (Array.isArray(x)) return x.map(rename);
  if (x && typeof x === "object")
    return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, rename(v)]));
  return x === "catalog" ? "atlas" : x;
};

/** The names of the registered modules, read as alice. */
export async function moduleNames(request: APIRequestContext): Promise<string[]> {
  const meta = await request.post("/api/console/graphql", {
    data: { query: "{ modules { name } }" },
    headers: ALICE,
  });
  return ((await meta.json()) as { data: { modules: { name: string }[] } }).data.modules.map(
    (m) => m.name,
  );
}

/**
 * A second module, `atlas`: the repository's example catalog (examples/catalog, with its declared
 * `arras.view`) registered under another name through the dev host's `register` control, and its
 * seed run through the declared actions as alice. The people hold it as they hold `catalog`. Made once.
 */
export async function ensureAtlas(request: APIRequestContext) {
  if ((await moduleNames(request)).includes("atlas")) return;
  const doc = rename(
    JSON.parse(readFileSync(repoFile("examples/catalog/catalog.umf.json"), "utf8")),
  );
  await control(request, { op: "register", document: JSON.stringify(doc) });
  const steps = JSON.parse(readFileSync(repoFile("examples/catalog/seed.json"), "utf8")) as {
    action: string;
    inputs: Record<string, unknown>;
  }[];
  for (const step of steps) {
    const action = step.action.replace(/^catalog\./, "");
    const r = await post(request, `/actions/atlas/${action}/invoke`, { inputs: step.inputs });
    expect(r.status(), `${step.action}: ${await r.text()}`).toBe(200);
  }
}
