// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { fitLines, measure } from "../browser/fitText";
import {
  type Centre,
  clip,
  type Group,
  type Layout,
  layoutGroups,
  MAX_NODES,
  NODE_H,
  WIDTH,
} from "../browser/layoutGroups";

// Golden vectors for the picture's layout (SD-011): a change to the geometry is a reviewed diff of
// layout.vectors.json. `UPDATE_VECTORS=1 npm test -- layout` rewrites the file from the cases below.
const FILE = join(import.meta.dirname, "layout.vectors.json");

interface Spec {
  name: string;
  centre?: Partial<Centre>;
  groups: {
    label: string;
    order: number;
    n: number;
    prefix?: string;
    extra?: number;
    self?: boolean;
    capped?: boolean;
  }[];
}

const CASES: Spec[] = [
  { name: "0 neighbours", groups: [] },
  { name: "1 neighbour", groups: [{ label: "Addresses", order: 10, n: 1 }] },
  {
    name: "7 neighbours in 3 groups (the mockup)",
    groups: [
      { label: "Addresses", order: 10, n: 4, prefix: "uc" },
      { label: "Provided by", order: 20, n: 1, prefix: "p" },
      { label: "Findings", order: 30, n: 2, prefix: "f" },
    ],
  },
  { name: "40 neighbours in one group", groups: [{ label: "Addresses", order: 10, n: 40 }] },
  { name: "120 neighbours in one group", groups: [{ label: "Addresses", order: 10, n: 120 }] },
  {
    name: "a hub: 100, 10 and 10 in three groups",
    groups: [
      { label: "Addresses", order: 10, n: 100, prefix: "s" },
      { label: "Provided by", order: 20, n: 10, prefix: "p" },
      { label: "Findings", order: 30, n: 10, prefix: "f" },
    ],
  },
  {
    name: "5 groups",
    groups: ["A", "B", "C", "D", "E"].map((l, i) => ({
      label: l,
      order: i,
      n: 3,
      prefix: l.toLowerCase(),
    })),
  },
  {
    name: "6 groups",
    groups: ["A", "B", "C", "D", "E", "F"].map((l, i) => ({
      label: l,
      order: i,
      n: 2,
      prefix: l.toLowerCase(),
    })),
  },
  {
    name: "groups tie on order and sort by label; a group's total passes what was given",
    groups: [
      { label: "Zeta", order: 50, n: 2, prefix: "z" },
      { label: "Alpha", order: 50, n: 2, prefix: "a", extra: 3 },
    ],
  },
  {
    name: "a self link is a loop and an entity in two groups is drawn once",
    groups: [
      { label: "Related", order: 10, n: 2, prefix: "r", self: true },
      { label: "Also related", order: 20, n: 2, prefix: "r" },
    ],
  },
];

const CENTRE: Centre = {
  type: "t.centre",
  key: "c-1",
  title: "Lumen alert correlation",
  typeLabel: "Solution",
  tone: "blue",
  icon: "puzzle",
};

function build(spec: Spec): { centre: Centre; groups: Group[] } {
  const centre = { ...CENTRE, ...spec.centre };
  const groups = spec.groups.map((g, gi): Group => {
    const prefix = g.prefix ?? `g${gi}`;
    const members = Array.from({ length: g.n }, (_, i) => ({
      type: `t.${prefix}`,
      key: `${prefix}-${i}`,
      title: `${g.label} ${i}`,
      typeLabel: "T",
      tone: "slate",
      icon: "circle",
    }));
    if (g.self) members.unshift({ ...CENTRE, ...spec.centre });
    return {
      id: `g${gi}`,
      label: g.label,
      order: g.order,
      members,
      total: g.extra ? g.n + g.extra : undefined,
      capped: g.capped,
    };
  });
  return { centre, groups };
}

const summary = (l: Layout) => ({
  size: l.size,
  centre: { x: l.centre.x, y: l.centre.y, w: l.centre.w, h: l.centre.h, label: l.centre.label },
  nodes: l.nodes.map((n) => [n.id, n.side, n.x, n.y, n.w, n.label]),
  edges: l.edges.map((e) => e.d),
  captions: l.captions.map((c) => [c.x, c.y, c.text]),
  shown: l.shown,
  total: l.total,
  omitted: l.omitted,
  selfLinks: l.selfLinks,
});

const run = (spec: Spec) => {
  const { centre, groups } = build(spec);
  return layoutGroups(centre, groups);
};

describe("layoutGroups golden vectors (US-069-AC1, AC2, AC3)", () => {
  if (process.env.UPDATE_VECTORS) {
    const out = CASES.map((spec) => ({ name: spec.name, spec, expected: summary(run(spec)) }));
    writeFileSync(FILE, `${JSON.stringify(out, null, 1)}\n`);
  }
  const golden = JSON.parse(readFileSync(FILE, "utf8")) as {
    name: string;
    spec: Spec;
    expected: unknown;
  }[];

  it("every case has a vector and every vector a case", () => {
    expect(golden.map((g) => g.name)).toEqual(CASES.map((c) => c.name));
  });

  for (const g of golden) {
    it(`US-069-AC2: ${g.name}`, () => {
      expect(summary(run(g.spec))).toEqual(g.expected);
    });
  }
});

describe("layoutGroups rules", () => {
  it("US-069-AC3: 120 neighbours draw 40 and say how many each group left out", () => {
    const l = run({ name: "x", groups: [{ label: "Addresses", order: 10, n: 120 }] });
    expect(l.nodes).toHaveLength(MAX_NODES);
    expect(l.shown).toBe(40);
    expect(l.total).toBe(120);
    expect(l.omitted).toEqual([{ label: "Addresses", count: 80 }]);
    expect(l.captions[0]?.text).toBe("ADDRESSES · +80 more");
  });

  it("US-069-AC3: a relationship that returned its key limit says '+N or more'", () => {
    const l = run({
      name: "x",
      groups: [{ label: "Addresses", order: 1, n: 40, extra: 60, capped: true }],
    });
    expect(l.captions[0]?.text).toBe("ADDRESSES · +60 or more");
  });

  it("US-069-AC3: a block of members is one bundled edge, and two blocks leave the centre between them", () => {
    const l = run({
      name: "x",
      groups: [
        { label: "A", order: 1, n: 30, prefix: "a" },
        { label: "B", order: 2, n: 30, prefix: "b" },
      ],
    });
    expect(l.edges.map((e) => e.id).sort()).toEqual(["edge:group:g0", "edge:group:g1"]);
    const tops = l.nodes.filter((n) => n.side === "top").map((n) => n.y);
    const bottoms = l.nodes.filter((n) => n.side === "bottom").map((n) => n.y);
    expect(Math.max(...tops)).toBeLessThan(l.centre.y);
    expect(Math.min(...bottoms)).toBeGreaterThan(l.centre.y + l.centre.h);
  });

  it("US-069-AC3: the cap is taken round-robin, so every group is represented", () => {
    const l = run({
      name: "x",
      groups: [
        { label: "Big", order: 1, n: 100, prefix: "b" },
        { label: "Small", order: 2, n: 3, prefix: "s" },
        { label: "Tiny", order: 3, n: 1, prefix: "t" },
      ],
    });
    const per = (p: string) => l.nodes.filter((n) => n.id.startsWith(`t.${p}`)).length;
    expect([per("b"), per("s"), per("t")]).toEqual([36, 3, 1]);
  });

  it("US-069-AC2: groups go by order then label, members by title then key, and pills never overlap", () => {
    const l = run({
      name: "x",
      groups: [
        { label: "Zeta", order: 50, n: 3, prefix: "z" },
        { label: "Alpha", order: 50, n: 3, prefix: "a" },
        { label: "First", order: 5, n: 3, prefix: "f" },
      ],
    });
    expect(l.nodes.map((n) => n.group)).toEqual([
      "g2",
      "g2",
      "g2",
      "g1",
      "g1",
      "g1",
      "g0",
      "g0",
      "g0",
    ]);
    const left = l.nodes.filter((n) => n.side === "left").map((n) => n.title);
    expect(left).toEqual([...left].sort());
    for (const a of l.nodes)
      for (const b of l.nodes) {
        if (a.id === b.id) continue;
        const apart =
          a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + NODE_H <= b.y || b.y + NODE_H <= a.y;
        expect(apart).toBe(true);
      }
    for (const n of l.nodes) {
      expect(n.x).toBeGreaterThanOrEqual(0);
      expect(n.x + n.w).toBeLessThanOrEqual(WIDTH);
      expect(n.y + NODE_H).toBeLessThanOrEqual(l.size.h);
    }
  });

  it("the same input always gives the same picture", () => {
    const spec = CASES[2] as Spec;
    expect(run(spec)).toEqual(run(spec));
  });

  it("US-069-AC1: a title is fitted to its box on at most two lines, cut with an ellipsis only on the last; the full title is kept", () => {
    expect(clip("Lumen alert correlation", 11)).toBe("Lumen aler…");
    expect(fitLines("short", 90)).toEqual(["short"]);
    expect(fitLines("Assess incident risk and escalation position", 100)).toEqual([
      "Assess incident",
      "risk and escalat…",
    ]);
    // Words stay whole where they fit; a long code breaks at a separator, not mid-letter.
    expect(fitLines("Describe table statistics", 100)).toEqual(["Describe table", "statistics"]);
    expect(fitLines("example.assess-deployment-risk", 92)[0]).toMatch(/[-.]$/);
    const l = run({ name: "x", groups: [{ label: "A", order: 1, n: 1 }] });
    expect(l.centre.lines.length).toBeLessThanOrEqual(2);
    expect(l.centre.label).toBe(l.centre.lines.join(" "));
    expect(l.centre.title).toBe("Lumen alert correlation");
  });

  it("no drawn line is wider than its box", () => {
    const titles = [
      "Assess incident risk and escalation position",
      "Run capacity planning review across a data room",
      "example.assess-deployment-risk-and-escalation",
      "W".repeat(40),
      "A title with an unbroken_identifier_that_is_very_long_indeed here",
    ];
    for (const t of titles)
      for (const w of [74, 80, 92, 104, 118]) {
        for (const line of fitLines(t, w)) expect(measure(line)).toBeLessThanOrEqual(w);
        expect(fitLines(t, w).length).toBeLessThanOrEqual(2);
      }
  });

  it("the reading order is group by group", () => {
    const l = run(CASES[2] as Spec);
    expect(l.nodes.map((n) => n.seq)).toEqual([...l.nodes.keys()]);
  });
});
