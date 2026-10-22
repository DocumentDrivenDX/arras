// SPDX-License-Identifier: MIT OR Apache-2.0
import { afterAll, describe, expect, it } from "vitest";
import {
  SCHEMA_CHANGE_ELEMENTS,
  SCHEMA_CHANGE_KINDS,
  type SchemaPlan,
  SUPPORTED_SCHEMA_VERSION,
} from "../api/types";
import { devWire, schemaWire } from "../test/fake";
import { call, control, withDevHost } from "./harness";
import { type CompareOpts, shapeDiff } from "./shapes";
import { registered, withProperty } from "./umf";

// Drift guard for the schema administration surface (CONTRACT-011): the shapes `ui/src/api/types.ts` writes by
// hand (and the fake in src/test/fake.ts, which is typed with them) against a real SchemaPlan, RegistryResult,
// error body and the dev host's own people and control answers: the same keys at every level, the same JSON
// types, the same enumerations. A change in CONTRACT-011's JSON fails here until the types and the fake follow.
withDevHost();

const ANA = { name: "ana", role: "schema author" };
const VIC = { name: "vic", role: "viewer" };
/** `revision` is an object keyed by backend name, null for a module the store does not hold. */
const SHAPE: CompareOpts = { open: [".revision"], nullable: [".revision"] };

const covered: string[] = [];
afterAll(() => {
  // Every `schemaWire` fixture is compared with the real dev host, or named here as unreachable on it.
  const unreachable = ["notAuthorized"]; // the dev host mounts the app without an authorize_schema hook
  const fixtures = Object.keys(schemaWire).filter((k) => !unreachable.includes(k));
  expect(fixtures.filter((k) => !covered.includes(k))).toEqual([]);
});

function same(
  name: string,
  real: { status: number; body: unknown },
  status: number,
  fake: unknown,
  opts: CompareOpts = SHAPE,
) {
  covered.push(name);
  expect({ name, status: real.status }).toEqual({ name, status });
  expect(
    shapeDiff(real.body, fake, opts),
    `${name}: real ${JSON.stringify(real.body).slice(0, 400)}`,
  ).toEqual([]);
}
const post = (verb: "validate" | "register", body: unknown, who = ANA) =>
  call(`/api/schema/${verb}`, body, who);

describe("drift guard: the schema surface", () => {
  it("GET /version", async () => {
    const real = await call("/api/schema/version");
    same("version", real, 200, schemaWire.version());
    expect((real.body as { contracts: { schema: number } }).contracts.schema).toBe(
      SUPPORTED_SCHEMA_VERSION,
    );
  });

  it("validate: a plan with changes, a plan that changes nothing, a plan that is not ok", async () => {
    const base = await registered("alice");
    const ok = await post("validate", {
      document: withProperty(base, "driftA", { required: false }),
    });
    same("plan", ok, 200, schemaWire.plan());
    const plan = ok.body as SchemaPlan;
    expect(plan.changes.length).toBeGreaterThan(0);
    same(
      "planUnchanged",
      await post("validate", { document: base }),
      200,
      schemaWire.planUnchanged(),
    );
    const bad = await post("validate", {
      document: withProperty(base, "driftB", { required: true }),
    });
    same("planIncompatible", bad, 200, schemaWire.planIncompatible());
    // the values of the enumerations the UI's types name
    for (const c of (bad.body as SchemaPlan).changes.concat(plan.changes)) {
      expect(SCHEMA_CHANGE_KINDS).toContain(c.kind);
      expect(SCHEMA_CHANGE_ELEMENTS).toContain(c.element);
    }
    expect((bad.body as SchemaPlan).violations.map((v) => v.code)).toEqual(["incompatible_change"]);
  });

  it("register: a result, and the refusals the console shows", async () => {
    const base = await registered("alice");
    const plan = (
      await post("validate", { document: withProperty(base, "driftC", { required: false }) })
    ).body as SchemaPlan;
    same(
      "registryResult",
      await post("register", {
        document: withProperty(base, "driftC", { required: false }),
        expected_revision: plan.revision,
      }),
      200,
      schemaWire.registryResult(),
    );
    const now = await registered("alice");
    same(
      "conflict",
      await post("register", {
        document: withProperty(now, "driftD", { required: false }),
        expected_revision: { memory: 99 },
      }),
      409,
      { error: schemaWire.conflict() },
    );
    same(
      "incompatible",
      await post("register", { document: withProperty(now, "driftE", { required: true }) }),
      400,
      { error: schemaWire.incompatible() },
    );
    same("invalidDocument", await post("validate", { document: "nope" }), 400, {
      error: schemaWire.invalidDocument(),
    });
    same("badRequest", await post("validate", { document: 5 }), 400, {
      error: schemaWire.badRequest(),
    });
    same("refused", await post("validate", { document: now }, VIC), 403, {
      error: schemaWire.refused(),
    });
  });

  it("an expired token is 401 with the reason", async () => {
    const now = await registered("alice");
    await post("validate", { document: now }); // ana exists
    await control({ op: "expire", user: "ana" });
    try {
      same("tokenExpired", await post("validate", { document: now }), 401, {
        error: schemaWire.tokenExpired(),
      });
    } finally {
      await control({ op: "restore", user: "ana" });
    }
  });
});

describe("drift guard: the dev host's own endpoints (the toolbar)", () => {
  it("GET /api/people and POST /api/dev/control", async () => {
    const people = await call("/api/people");
    expect(shapeDiff(people.body, devWire.people())).toEqual([]);
    expect((people.body as { roles: unknown }).roles).toEqual(devWire.people().roles);
    expect((people.body as { people: unknown }).people).toEqual(devWire.people().people);
    const feed = await call("/api/dev/control", { op: "feed" });
    expect(feed.status).toBe(200);
    expect(shapeDiff(feed.body, devWire.control())).toEqual([]);
  });
});
