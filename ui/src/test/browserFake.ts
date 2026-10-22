// SPDX-License-Identifier: MIT OR Apache-2.0
// A fetch double for the Graph Browser: the browser's meta read with resolved views (CONTRACT-010 B),
// `GET /viewer`, per-module by-key and list reads, and `_search`, answered from a small dataset the
// test can change. It enforces CONTRACT-006's limit of 50 selections, so a request the planner built
// too large fails here as it would on the server.
import type {
  Change,
  ChangesQuery,
  Effect,
  MetaData,
  ModuleInfo,
  Receipt,
  SearchSegment,
  TypeView,
} from "../api/types";
import { evaluate, valueText } from "../lib/template";
import { decl, err, FakeApi, FRESH, json, type Recorded, receipt, view, wire } from "./fake";
import { countSelections, type Field, parseQuery, project } from "./gqlmini";

export interface Row {
  key: string;
  props: Record<string, unknown>;
  /** Relationship field to keys. */
  rels?: Record<string, string[]>;
}

const f = (
  property: string,
  label: string,
  format = "text",
  extra: Partial<TypeView["fields"][number]> = {},
) => ({
  property,
  label,
  format,
  hideWhenEmpty: false,
  tones: null,
  ...extra,
});

const rel = (field: string, label: string, order: number, hideWhenEmpty = false) => ({
  field,
  label,
  order,
  hideWhenEmpty,
});

const prop = (name: string, type = "string", required = false) => ({
  name,
  type,
  required,
  cardinality: required ? "one" : "optional",
});

const caps = (search: "none" | "substring" = "substring") => ({
  memory: { read: true, mutable: true, search, searchable: ["name", "title", "code", "summary"] },
});

export const SOLUTION_VIEW = view({
  label: "Solution",
  icon: "puzzle",
  tone: "blue",
  title: "{name}[ ({code})]",
  summary: "{summary}",
  sections: [
    {
      label: "Delivery",
      properties: ["deliveryMode", "audience", "launchUrl", "caveat"],
      collapsed: false,
    },
    { label: "How it works", properties: ["workflow"], collapsed: true },
    {
      label: "Facts",
      properties: ["builtAt", "cost", "active", "tags", "config"],
      collapsed: false,
    },
  ],
  search: ["name", "code", "summary"],
  fields: [
    f("code", "Code"),
    f("name", "Name"),
    f("deliveryMode", "Delivery", "badge", { tones: { Embedded: "teal", Standalone: "blue" } }),
    f("audience", "Audience"),
    f("launchUrl", "Launch", "link"),
    f("caveat", "Caveat"),
    f("workflow", "Workflow", "prose"),
    f("summary", "Summary", "prose"),
    f("builtAt", "Built", "datetime"),
    f("cost", "Cost", "number"),
    f("active", "Active", "boolean"),
    f("tags", "Tags", "tags"),
    f("config", "Config", "json"),
  ],
  relationships: [
    rel("addresses", "Addresses use cases", 10),
    rel("providedBy", "Provided by", 20),
    rel("notedIn", "Notes", 30, true),
  ],
});

export const USE_CASE_VIEW = view({
  label: "Use case",
  icon: "book",
  tone: "violet",
  title: "{name}",
  summary: "{description}",
  sections: [{ label: "Details", properties: ["workArea"], collapsed: false }],
  search: ["name", "code", "description"],
  fields: [
    f("code", "Code"),
    f("name", "Name"),
    f("workArea", "Work area"),
    f("description", "Description", "prose"),
  ],
  relationships: [rel("addressedBy", "Addressed by", 20)],
});

export const PRODUCT_VIEW = view({
  label: "Product",
  icon: "package",
  tone: "teal",
  title: "{name}",
  sections: [{ label: "Details", properties: [], collapsed: false }],
  search: ["name", "code"],
  fields: [f("code", "Code"), f("name", "Name")],
  relationships: [rel("provides", "Provides", 10)],
});

export const NOTE_VIEW = view({
  label: "Note",
  icon: "file-text",
  tone: "amber",
  title: "{title}",
  sections: [{ label: "Details", properties: [], collapsed: false }],
  search: ["title"],
  fields: [f("ref", "Ref"), f("title", "Title")],
  relationships: [],
});

const type = (
  module: string,
  name: string,
  key: string,
  props: string[],
  v: TypeView,
  search?: "none" | "substring",
) => ({
  name: `${module}.${name}`,
  key,
  properties: props.map((p) => prop(p, "string", p === key)),
  capabilities: caps(search),
  view: v,
});

const spec = (name: string, type = "string", cardinality = "optional", kind = "scalar") => ({
  name,
  type,
  kind: kind as "scalar" | "ref",
  cardinality: cardinality as "one" | "optional",
});

interface Target {
  module: string;
  type: string;
  ref: string;
  /** Every property a required input: they can only change together (a form). */
  together: boolean;
}

const update = (
  name: string,
  props: string[],
  extra: ReturnType<typeof spec>[] = [],
  {
    module = "catalog",
    type = "Solution",
    ref = "solution",
    together = false,
  }: Partial<Target> = {},
) => ({
  name: `${module}.${name}`,
  description: name,
  inputSpecs: [
    ...props.map((p, i) =>
      spec(p, "string", together || (props.length === 1 && i === 0) ? "one" : "optional"),
    ),
    ...extra,
    spec(ref, type, "one", "ref"),
  ],
  preconditions: [],
  effects: [
    decl({
      op: "update",
      ref_type: type,
      key: { name: ref },
      properties: Object.fromEntries(props.map((p) => [p, { name: p }])),
    }),
  ],
});

/** A declared `link` or `unlink` of a relationship between two references. */
const link = (
  name: string,
  op: "link" | "unlink",
  relationship: string,
  sourceInput: string,
  sourceType: string,
  targetInput: string,
  targetType: string,
) => ({
  name: `catalog.${name}`,
  description: name,
  inputSpecs: [
    spec(sourceInput, sourceType, "one", "ref"),
    spec(targetInput, targetType, "one", "ref"),
  ],
  preconditions: [],
  effects: [
    decl({
      op,
      type: relationship,
      source: { name: sourceInput },
      target: { name: targetInput },
    }),
  ],
});

/** The module's declared actions: updates of a Solution, and one that creates (not an edit). */
export const ACTIONS = [
  update("CorrectSolution", ["summary", "audience", "workflow"]),
  update("RenameSolution", ["name"]),
  update("ChangeSolutionDelivery", ["deliveryMode"]),
  // Two required inputs, so neither property can change without the other: a form.
  {
    ...update("SetCaveatAndCost", ["caveat", "cost"]),
    inputSpecs: [
      spec("caveat", "string", "one"),
      spec("cost", "string", "one"),
      spec("solution", "Solution", "one", "ref"),
    ],
  },
  link("AddressUseCase", "link", "addresses", "solution", "Solution", "useCase", "UseCase"),
  link("UnaddressUseCase", "unlink", "addresses", "solution", "Solution", "useCase", "UseCase"),
  link("SetSolutionProvider", "link", "providedBy", "solution", "Solution", "product", "Product"),
  // One delete of a Solution by a ref input, the other input optional: a retire plan.
  {
    name: "catalog.RetireSolution",
    description: "RetireSolution",
    inputSpecs: [spec("solution", "Solution", "one", "ref"), spec("reason")],
    preconditions: [],
    effects: [decl({ op: "delete", ref_type: "Solution", key: { name: "solution" } })],
  },
  {
    name: "catalog.AddSolution",
    description: "AddSolution",
    inputSpecs: [spec("code", "string", "one"), spec("name", "string", "one")],
    preconditions: [],
    effects: [decl({ op: "create", type: "Solution", properties: { name: { name: "name" } } })],
  },
];

export function modules(): ModuleInfo[] {
  const base = {
    record: "memory",
    replicas: [],
    providers: {},
    revision: { memory: 1 },
    actions: [],
  };
  return [
    {
      ...base,
      name: "catalog",
      actions: ACTIONS,
      view: { title: "Product catalog", description: "Use cases, solutions and products" },
      entityTypes: [
        type(
          "catalog",
          "UseCase",
          "code",
          ["code", "name", "workArea", "description"],
          USE_CASE_VIEW,
        ),
        type(
          "catalog",
          "Solution",
          "code",
          [
            "code",
            "name",
            "deliveryMode",
            "audience",
            "launchUrl",
            "caveat",
            "workflow",
            "summary",
            "builtAt",
            "cost",
            "active",
            "tags",
            "config",
          ],
          SOLUTION_VIEW,
        ),
        type("catalog", "Product", "code", ["code", "name"], PRODUCT_VIEW),
      ],
      relationships: [
        {
          name: "addresses",
          source: ["catalog.Solution"],
          target: ["catalog.UseCase"],
          sourceMultiplicity: "0..*",
          targetMultiplicity: "0..*",
          lifecycle: "independent",
          inverse: "addressedBy",
        },
        {
          name: "providedBy",
          source: ["catalog.Solution"],
          target: ["catalog.Product"],
          sourceMultiplicity: "0..*",
          targetMultiplicity: "0..1",
          lifecycle: "independent",
          inverse: "provides",
        },
        {
          name: "notedIn",
          source: ["catalog.Solution"],
          target: ["other.Note"],
          sourceMultiplicity: "0..*",
          targetMultiplicity: "0..*",
          lifecycle: "independent",
          inverse: null,
        },
      ],
    },
    {
      ...base,
      name: "other",
      view: { title: "Other notes", description: null },
      entityTypes: [type("other", "Note", "ref", ["ref", "title"], NOTE_VIEW)],
      relationships: [],
    },
  ];
}

const TARGET_OF: Record<string, string> = {
  addresses: "catalog.UseCase",
  addressedBy: "catalog.Solution",
  providedBy: "catalog.Product",
  provides: "catalog.Solution",
  notedIn: "other.Note",
};

const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const short = (q: string) => q.slice(q.lastIndexOf(".") + 1);

export function dataset(): Record<string, Row[]> {
  return {
    "catalog.UseCase": [
      {
        key: "uc-1",
        props: {
          code: "uc-1",
          name: "Alert review",
          workArea: "operations",
          description: "Review a contract.\nSecond line.",
        },
        rels: { addressedBy: ["sol-1"] },
      },
      {
        key: "uc-2",
        props: { code: "uc-2", name: "Runbook check", workArea: "operations" },
        rels: { addressedBy: ["sol-1"] },
      },
      {
        key: "uc-3",
        props: { code: "uc-3", name: "Log extraction", workArea: "operations" },
        rels: { addressedBy: ["sol-1", "sol-2"] },
      },
    ],
    "catalog.Solution": [
      {
        key: "sol-1",
        props: {
          code: "S-017",
          name: "Lumen alert correlation",
          deliveryMode: "Embedded",
          audience: "Platform engineers",
          launchUrl: "https://praxis.example/solutions/s-017",
          caveat: null,
          workflow: "Upload a draft.\nLumen compares each pattern.",
          summary: "Groups alerts against recent deploys.",
          builtAt: "2026-10-09T14:12:08-04:00",
          cost: "1234567.50",
          active: true,
          tags: ["logs", "ai"],
          config: { retries: 2 },
        },
        rels: { addresses: ["uc-1", "uc-2", "uc-3"], providedBy: ["p-1"], notedIn: ["n-1"] },
      },
      {
        key: "sol-2",
        props: {
          code: "S-022",
          name: "Alert grouping",
          deliveryMode: "Standalone",
          summary: "Compares a pattern.",
        },
        rels: { addresses: ["uc-3"] },
      },
    ],
    "catalog.Product": [
      { key: "p-1", props: { code: "p-1", name: "Lumen" }, rels: { provides: ["sol-1"] } },
    ],
    "other.Note": [{ key: "n-1", props: { ref: "n-1", title: "A note elsewhere" } }],
  };
}

export class BrowserFake {
  api = new FakeApi();
  rows = dataset();
  mods = modules();
  /** "type:key" of entities the viewer may not read: a null, never an error. */
  hidden = new Set<string>();
  /** "type:key" to the code of the error that field answers with (cost, a backend). */
  failing = new Map<string, string>();
  /** A backend that is down: every module read answers UNAVAILABLE. */
  down: string | null = null;
  viewerModes: ("user" | "admin")[] | "fail" = ["user", "admin"];
  /** Every `validate` and `invoke` the browser sent, as the action and its inputs. */
  writes: { verb: string; action: string; inputs: Record<string, unknown> }[] = [];
  /** A refusal `validate` answers with (a violation message), or `invoke` with a status. */
  invalid: string | null = null;
  invokeStatus: number | null = null;
  /** The effects `validate` answers with (an action's preview), and the receipt `invoke` answers with. */
  validateEffects: Effect[] = [];
  nextReceipt: Partial<Receipt> | null = null;
  /** The next `validate` answers a revision conflict (409), once. */
  validateConflict = false;
  /** A status `POST /export` answers with instead of a page. */
  exportStatus: number | null = null;
  /** The journal `changes` answers from, newest first, and a status it answers with instead. */
  journal: Change[] = [];
  changesStatus: number | null = null;
  /** Types an export page says it could not give. */
  exportOmitted: string[] = [];
  notSearched: { type: string; reason: string; backend: string | null }[] = [];
  /** Types the viewer cannot read: absent from the module's meta. */
  log: Recorded[] = [];
  /** The next module read answers REVISION_CHANGED, and the registry moves to its next revision. */
  expireNext: ((mods: ModuleInfo[]) => void) | null = null;

  constructor() {
    this.api.install();
    this.api.on((r) => this.handle(r));
  }

  /** What the double answers for a query, without a request: the drift guard compares it with the real server. */
  answer(module: string | null, query: string, variables: Record<string, unknown> = {}) {
    const rec = {
      method: "POST",
      url: "",
      path: "",
      headers: {},
      body: { query, variables },
    } as unknown as Recorded;
    const reply = module === null ? this.meta(query) : this.module(module, rec);
    return { status: reply.status ?? 200, body: reply.body };
  }

  get requests() {
    return this.api.log;
  }

  /** Module-endpoint GraphQL requests, as the queries they sent. */
  moduleQueries(module?: string): string[] {
    return this.api.log
      .filter(
        (r) => r.method === "POST" && new RegExp(`/graphql/${module ?? "[^/]+"}$`).test(r.path),
      )
      .map((r) => r.body.query);
  }

  /** Hold every `invoke`'s answer (its write still lands) until the returned function is called. */
  holdInvoke(): () => void {
    let open = () => {};
    this.invokeHold = new Promise<void>((res) => (open = res));
    return open;
  }
  private invokeHold: Promise<void> | null = null;

  /** Hold the answer to a search for this text until the returned function is called. */
  gate(text: string): () => void {
    let open = () => {};
    this.gates.set(text, new Promise<void>((res) => (open = res)));
    return open;
  }

  private gates = new Map<string, Promise<void>>();

  /**
   * Hold the node read of this key (the by-key query, matched on its `key` variable) until `release`
   * is called. `held()` counts the reads the hold caught, so a test can prove the hold matched.
   */
  holdNode(key: string): { release: () => void; held: () => number } {
    let release = () => {};
    const gate = new Promise<void>((res) => (release = res));
    const hold = { gate, hits: 0 };
    this.nodeHolds.set(key, hold);
    return { release, held: () => hold.hits };
  }

  /** Hold every label read (the aliased by-key requests, `$k0`...) until `release` is called. */
  holdLabels(): () => void {
    let release = () => {};
    this.labelGate = new Promise<void>((res) => (release = res));
    return release;
  }

  private labelGate: Promise<void> | undefined;

  private nodeHolds = new Map<string, { gate: Promise<void>; hits: number }>();

  private heldFor(r: Recorded): Promise<void> | undefined {
    const vars = r.body.variables as { text?: string; key?: string; k0?: string } | undefined;
    if (vars && "k0" in vars && this.labelGate) return this.labelGate;
    if (r.body.query.includes("_search")) return this.gates.get(String(vars?.text ?? ""));
    const hold = vars?.key === undefined ? undefined : this.nodeHolds.get(vars.key);
    if (hold) hold.hits += 1;
    return hold?.gate;
  }

  /** An action's answer, an invoke's held where a test asked for it. */
  private acted(action: string, verb: string, body: { inputs: Record<string, unknown> }) {
    const reply = this.act(action, verb, body);
    return verb === "invoke" && this.invokeHold ? this.invokeHold.then(() => reply) : reply;
  }

  private handle(r: Recorded) {
    if (r.method === "GET" && r.path.endsWith("/viewer")) {
      if (this.viewerModes === "fail") return json(500, { error: "boom" });
      return json(200, { user: "alice", modes: this.viewerModes });
    }
    if (r.method === "POST" && r.path.endsWith("/api/operate/export"))
      return this.exportPage(r.body as { module: string; after?: string; limit?: number });
    if (r.method === "POST" && r.path.endsWith("/api/operate/audit/changes"))
      return this.changesPage(r.body as ChangesQuery);
    const act = /\/api\/operate\/actions\/[^/]+\/([^/]+)\/(validate|invoke)$/.exec(r.path);
    if (act?.[1] && act[2])
      return this.acted(act[1], act[2], r.body as { inputs: Record<string, unknown> });
    if (/\/api\/console\/graphql$/.test(r.path)) return this.meta(r.body.query);
    const m = /\/api\/console\/graphql\/([^/]+)$/.exec(r.path);
    if (m?.[1]) {
      const reply = this.module(decodeURIComponent(m[1]), r);
      const wait = this.heldFor(r);
      return wait ? wait.then(() => reply) : reply;
    }
    return undefined;
  }

  private entityRecords(mine: [string, Row[]][]): Record<string, unknown>[] {
    return mine.flatMap(([type, rows]) =>
      [...rows]
        .sort((a, b) => (a.key < b.key ? -1 : 1))
        .map((row) => {
          const { code: _c, ref: _r, ...properties } = row.props as Record<string, unknown>;
          return { type: short(type), key: row.key, properties };
        }),
    );
  }

  private linkRecords(mine: [string, Row[]][]): Record<string, unknown>[] {
    const forward = new Set(["addresses", "providedBy", "notedIn"]);
    return mine.flatMap(([, rows]) =>
      rows.flatMap((row) =>
        Object.entries(row.rels ?? {})
          .filter(([field]) => forward.has(field))
          .flatMap(([field, keys]) =>
            keys.map((target) => ({ relationship: field, source: row.key, target })),
          ),
      ),
    );
  }

  /** The module's graph as records: every entity by type then key, then each forward link. */
  private graphRecords(module: string): Record<string, unknown>[] {
    const mine = Object.entries(this.rows).filter(([type]) => type.startsWith(`${module}.`));
    return [...this.entityRecords(mine), ...this.linkRecords(mine)];
  }

  /** One page of the module's graph. */
  /** One page of the journal for a type and key; the cursor is the offset into the matches. */
  private changesPage(q: ChangesQuery) {
    if (this.changesStatus === 403) return err(403, wire.refused("changes"));
    if (this.changesStatus === 501) return err(501, wire.unsupported());
    if (this.changesStatus) return err(this.changesStatus, { type: "Error" });
    const touches = (c: Change) =>
      c.ops.some((o) =>
        [o, o.source, o.target].some(
          (e) => e && (!q.type || e.type === q.type) && (!q.key || e.key === q.key),
        ),
      );
    const all = this.journal.filter(touches);
    const from = Number(q.after ?? 0);
    const size = q.limit ?? 100;
    const next = from + size < all.length ? String(from + size) : null;
    return json(200, wire.page(all.slice(from, from + size), next));
  }

  private exportPage(body: { module: string; after?: string; limit?: number }) {
    if (this.exportStatus)
      return json(this.exportStatus, { error: { type: "Refused", reason: "no_access" } });
    const all = this.graphRecords(body.module);
    const start = Number(body.after ?? 0);
    const end = start + (body.limit ?? 500);
    return json(200, {
      items: all.slice(start, end),
      nextCursor: end < all.length ? String(end) : null,
      omitted: this.exportOmitted,
      freshness: null,
    });
  }

  private validated() {
    const violations = this.invalid
      ? [{ path: "inputs", code: "invalid", message: this.invalid }]
      : [];
    return json(200, {
      ok: violations.length === 0,
      violations,
      failures: [],
      effects: this.validateEffects,
      replay: null,
      freshness: null,
    });
  }

  /** A declared `link` or `unlink`: both ends' groups change, as the server's do. */
  private changeLink(
    effect: { op: string; type?: string | null; source?: unknown; target?: unknown },
    inputs: Record<string, unknown>,
  ) {
    const inverse: Record<string, string> = { addresses: "addressedBy", providedBy: "provides" };
    const name = effect.type ?? "";
    const sourceKey = inputs[(effect.source as { name: string }).name] as string;
    const targetKey = inputs[(effect.target as { name: string }).name] as string;
    const find = (key: string) =>
      Object.values(this.rows)
        .flat()
        .find((r) => r.key === key);
    const sides: [Row | undefined, string, string][] = [
      [find(sourceKey), name, targetKey],
      [find(targetKey), inverse[name] ?? "", sourceKey],
    ];
    for (const [row, field, other] of sides) {
      if (!row || !field) continue;
      const keys = new Set(row.rels?.[field] ?? []);
      if (effect.op === "link") keys.add(other);
      else keys.delete(other);
      row.rels = { ...row.rels, [field]: [...keys] };
    }
  }

  /** A declared delete takes the row and every link to it. */
  private remove(key: string) {
    this.rows["catalog.Solution"] = (this.rows["catalog.Solution"] ?? []).filter(
      (r) => r.key !== key,
    );
    for (const row of Object.values(this.rows).flat())
      for (const [field, keys] of Object.entries(row.rels ?? {}))
        row.rels = { ...row.rels, [field]: keys.filter((k) => k !== key) };
  }

  /** A declared update sets the named properties on the row; a link or unlink changes both ends. */
  private apply(action: string, inputs: Record<string, unknown>) {
    const declared = this.mods.flatMap((m) => m.actions).find((a) => a.name.endsWith(`.${action}`));
    const effect = declared?.effects[0];
    if (effect?.op === "link" || effect?.op === "unlink") this.changeLink(effect, inputs);
    else if (effect?.op === "delete") this.remove(String(inputs.solution));
    else {
      const props = effect?.properties as Record<string, { name: string }> | undefined;
      const table = `${declared?.name.split(".")[0]}.${effect?.ref_type}`;
      const keyInput = (effect?.key as { name: string } | undefined)?.name ?? "solution";
      const row = this.rows[table]?.find((x) => x.key === inputs[keyInput]);
      for (const [property, expr] of Object.entries(props ?? {}))
        if (row && expr.name in inputs) row.props[property] = inputs[expr.name];
    }
    return json(200, receipt({ action: `catalog.${action}`, updated: 1 }));
  }

  private act(action: string, verb: string, body: { inputs: Record<string, unknown> }) {
    this.writes.push({ verb, action, inputs: body.inputs });
    if (verb === "validate" && this.validateConflict) {
      this.validateConflict = false;
      return json(409, {
        error: { type: "Conflict", message: "conflict (revision)", reason: "revision" },
      });
    }
    if (verb === "validate") return this.validated();
    if (this.invokeStatus) return json(this.invokeStatus, { type: "Refused", reason: "no_access" });
    if (this.nextReceipt)
      return json(200, receipt({ action: `catalog.${action}`, ...this.nextReceipt }));
    return this.apply(action, body.inputs);
  }

  private meta(query: string) {
    const mods = this.mods;
    if (query.includes("declared")) {
      return json(200, {
        data: {
          modules: mods.map((x) => ({
            name: x.name,
            revision: x.revision,
            entityTypes: x.entityTypes.map((t) => ({ name: t.name, view: t.view })),
          })),
        },
      });
    }
    const data: MetaData = {
      modules: mods.map((x) => ({
        ...x,
        entityTypes: x.entityTypes.map(({ view: _v, ...t }) => t),
      })),
      status: this.api.status,
    };
    return json(200, { data, extensions: {} });
  }

  private rowObject(typeName: string, row: Row) {
    const refs = Object.fromEntries(
      Object.entries(row.rels ?? {}).map(([field, keys]) => {
        const target = TARGET_OF[field] ?? "";
        // The server returns at most 100 keys for a relationship (CONTRACT-006).
        return [
          field,
          keys.slice(0, 100).map((key) => ({ module: target.split(".")[0], type: target, key })),
        ];
      }),
    );
    return {
      key: row.key,
      type: typeName,
      version: "1",
      createdBy: "alice",
      createdAt: "2026-10-09T14:12:08+00:00",
      updatedBy: "alice",
      updatedAt: "2026-10-09T14:12:08+00:00",
      freshness: FRESH,
      ...row.props,
      ...refs,
    };
  }

  private module(name: string, r: Recorded) {
    const mod = this.mods.find((x) => x.name === name);
    if (!mod)
      return json(404, {
        errors: [{ message: "no such module", extensions: { code: "NOT_FOUND" } }],
      });
    if (this.expireNext) {
      this.expireNext(this.mods);
      this.expireNext = null;
      return json(200, {
        data: null,
        errors: [
          {
            message: "the module's revision changed",
            extensions: { code: "REVISION_CHANGED" },
          },
        ],
        extensions: {},
      });
    }
    const fields = parseQuery(
      r.body.query,
      (r.body.variables ?? {}) as unknown as Record<string, unknown>,
    );
    if (countSelections(fields) > 50)
      return json(200, {
        data: null,
        errors: [
          { message: "queries select at most 50 fields", extensions: { code: "COST_EXCEEDED" } },
        ],
        extensions: {},
      });
    const data: Record<string, unknown> = {};
    const errors: { message: string; path: string[]; extensions: Record<string, unknown> }[] = [];
    for (const field of fields) {
      const out = field.alias ?? field.name;
      const err = this.fail(mod, field);
      if (err) {
        data[out] = null;
        errors.push({
          message: err,
          path: [out],
          extensions: { code: err, backend: this.down ?? undefined },
        });
        continue;
      }
      data[out] = project(this.root(mod, field), field.children ?? [], (x) =>
        short(String((x as { type?: string }).type ?? "")),
      );
    }
    return json(200, errors.length ? { data, errors, extensions: {} } : { data, extensions: {} });
  }

  private fail(mod: ModuleInfo, field: Field): string | null {
    if (this.down) return "UNAVAILABLE";
    const t = mod.entityTypes.find((x) => lowerFirst(short(x.name)) === field.name);
    return t ? (this.failing.get(`${t.name}:${String(field.args.key)}`) ?? null) : null;
  }

  private root(mod: ModuleInfo, field: Field): unknown {
    if (field.name === "_search") return this.search(mod, field);
    const list = field.name.endsWith("List");
    const t = mod.entityTypes.find(
      (x) => lowerFirst(short(x.name)) === (list ? field.name.slice(0, -4) : field.name),
    );
    if (!t) return null;
    const rows = this.rows[t.name] ?? [];
    if (!list) {
      const row = rows.find((x) => x.key === field.args.key);
      return row && !this.hidden.has(`${t.name}:${row.key}`) ? this.rowObject(t.name, row) : null;
    }
    const filter = (field.args.filter ?? {}) as Record<string, string>;
    const all = rows
      .filter((x) =>
        Object.entries(filter).every(
          ([k, v]) => String(x.props[k]) === v || x.rels?.[k]?.includes(v),
        ),
      )
      .filter((x) => !this.hidden.has(`${t.name}:${x.key}`))
      .filter((x) => field.args.afterKey == null || x.key > String(field.args.afterKey))
      .sort((a, b) => (a.key < b.key ? -1 : 1));
    const limit = Number(field.args.limit ?? 50);
    return {
      items: all.slice(0, limit).map((x) => this.rowObject(t.name, x)),
      truncated: all.length > limit, // the limit cut the page: more follow its last key
      freshness: FRESH,
    };
  }

  private search(mod: ModuleInfo, field: Field) {
    const text = String(field.args.text).trim().replace(/\s+/g, " ").toLowerCase();
    const words = text.split(" ");
    const wanted =
      (field.args.types as string[] | null) ?? mod.entityTypes.map((t) => short(t.name));
    const skipped = this.notSearched.filter((n) => wanted.includes(n.type));
    const searched = mod.entityTypes.filter(
      (t) => wanted.includes(short(t.name)) && !skipped.some((n) => n.type === short(t.name)),
    );
    const hits: unknown[] = [];
    const counts: unknown[] = [];
    for (const t of searched) {
      const props = t.view?.search ?? [];
      const matching = (this.rows[t.name] ?? []).filter((row) =>
        words.every((w) => props.some((p) => valueText(row.props[p]).toLowerCase().includes(w))),
      );
      counts.push({ type: short(t.name), count: matching.length, atLeast: false });
      for (const row of matching) hits.push(this.hit(t.name, row, t.view, words, props));
    }
    return { text, hits, counts, notSearched: skipped, truncated: false, freshness: [FRESH] };
  }

  private hit(
    typeName: string,
    row: Row,
    v: TypeView | undefined,
    words: string[],
    props: string[],
  ) {
    const label = evaluate(v?.title ?? "{key}", (n) => valueText(row.props[n])).trim() || row.key;
    const prop =
      props.find((p) =>
        valueText(row.props[p])
          .toLowerCase()
          .includes(words[0] ?? ""),
      ) ??
      props[0] ??
      "";
    const value = valueText(row.props[prop]);
    const at = value.toLowerCase().indexOf(words[0] ?? "");
    const excerpt: SearchSegment[] =
      at < 0
        ? [{ text: value, mark: false }]
        : [
            { text: value.slice(0, at), mark: false },
            { text: value.slice(at, at + (words[0] ?? "").length), mark: true },
            { text: value.slice(at + (words[0] ?? "").length), mark: false },
          ].filter((s) => s.text !== "");
    return {
      type: short(typeName),
      key: row.key,
      score: 10,
      label,
      excerpt,
      matched: [prop],
      entity: this.rowObject(typeName, row),
    };
  }
}

/** A staged browser double: the dataset, the viewer and the log of every request. */
export const stageBrowser = () => new BrowserFake();

/**
 * A second module, `people`, shaped unlike the catalog (other words, other keys, other templates),
 * for what a header template can do: two properties each with an action of their own (`Contact`),
 * two that only a form changes (`Place`), a badge in the title and a summary that is null
 * (`Ticket`), and a title that is the key (`Handle`). Added to a fake only where a test asks.
 */
const person = (name: string, key: string, v: TypeView, props: string[]) =>
  type("people", name, key, props, v);

const PEOPLE_FIELDS = (...names: string[]) =>
  names.map((n) => f(n, n.charAt(0).toUpperCase() + n.slice(1)));

export function addPeople(fake: BrowserFake) {
  const mod = (over: Partial<TypeView> & Pick<TypeView, "label" | "icon" | "tone" | "title">) =>
    view({ sections: [], ...over });
  const T = { module: "people" } as const;
  const contact = mod({
    label: "Contact",
    icon: "user",
    tone: "green",
    title: "{given} {family}",
    summary: "{note}",
    fields: PEOPLE_FIELDS("id", "given", "family", "note"),
  });
  const place = mod({
    label: "Place",
    icon: "globe",
    tone: "teal",
    title: "{street} {number}",
    fields: PEOPLE_FIELDS("id", "street", "number"),
  });
  const ticket = mod({
    label: "Ticket",
    icon: "flag",
    tone: "rose",
    title: "{id} {status}",
    summary: "{body}",
    fields: [
      ...PEOPLE_FIELDS("id", "body"),
      f("status", "Status", "badge", { tones: { open: "amber" } }),
    ],
  });
  const handle = mod({
    label: "Handle",
    icon: "tag",
    tone: "slate",
    title: "{id}",
    summary: "{about}",
    fields: PEOPLE_FIELDS("id", "about"),
  });
  const act = (name: string, props: string[], t: string, together = false) =>
    update(name, props, [], { ...T, type: t, ref: lowerFirst(t), together });
  const actions = [
    act("SetContactGiven", ["given"], "Contact"),
    act("SetContactFamily", ["family"], "Contact"),
    act("SetContactNote", ["note"], "Contact"),
    act("MovePlace", ["street", "number"], "Place", true),
    act("ChangeTicketStatus", ["status"], "Ticket"),
    act("SetTicketBody", ["body"], "Ticket"),
    act("SetHandleAbout", ["about"], "Handle"),
  ];
  fake.mods.push({
    record: "memory",
    replicas: [],
    providers: {},
    revision: { memory: 1 },
    name: "people",
    actions,
    view: { title: "People", description: null },
    entityTypes: [
      person("Contact", "id", contact, ["id", "given", "family", "note"]),
      person("Place", "id", place, ["id", "street", "number"]),
      person("Ticket", "id", ticket, ["id", "status", "body"]),
      person("Handle", "id", handle, ["id", "about"]),
    ],
    relationships: [],
  });
  fake.rows["people.Contact"] = [
    {
      key: "c-1",
      props: { id: "c-1", given: "Ada", family: "Lovelace", note: "Wrote the first program" },
    },
  ];
  fake.rows["people.Place"] = [
    { key: "pl-1", props: { id: "pl-1", street: "Mill Road", number: "12" } },
  ];
  fake.rows["people.Ticket"] = [{ key: "t-1", props: { id: "t-1", status: "open", body: null } }];
  fake.rows["people.Handle"] = [{ key: "h-1", props: { id: "h-1", about: "Only the handle" } }];
}

/** A hub: one solution addressing `n` use cases, which each list it back. */
export function addHub(fake: BrowserFake, n: number, key = "sol-hub") {
  const ucs = Array.from({ length: n }, (_, i) => `uc-h-${String(i).padStart(3, "0")}`);
  fake.rows["catalog.UseCase"]?.push(
    ...ucs.map((k, i) => ({
      key: k,
      props: { code: k, name: `Hub use case ${String(i).padStart(3, "0")}`, workArea: "hub" },
      rels: { addressedBy: [key] },
    })),
  );
  fake.rows["catalog.Solution"]?.push({
    key,
    props: { code: "S-HUB", name: "Hub solution", deliveryMode: "Standalone" },
    rels: { addresses: ucs },
  });
  return ucs;
}
