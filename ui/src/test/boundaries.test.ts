// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { edges, files, inside, SRC, UI } from "./importGraph";

// SD-011, Boundary rules: `browser/` imports api/, components/ui, ds/, kit/, lib/format, lib/inputs, lib/download, lib/template, lib/relLabels, lib/brand, lib/documentTitle and its own modules,
// never areas/, the console or the shell; `kit/` (SD-013) imports an allow-list and nothing in `lib/` imports it; areas/ and the console never import browser/ or shell/;
// the console's entry does not export the browser; nothing renders server text as markup.
const BROWSER = join(SRC, "browser");
const BROWSER_MAY = [
  BROWSER,
  join(SRC, "api"),
  join(SRC, "components/ui"),
  join(SRC, "components/Scope"),
  join(SRC, "ds"),
  join(SRC, "lib/format"),
  join(SRC, "lib/inputs"),
  join(SRC, "lib/download"),
  join(SRC, "lib/template"),
  join(SRC, "lib/relLabels"),
  join(SRC, "kit"),
  join(SRC, "lib/brand"),
  join(SRC, "lib/documentTitle"),
  join(SRC, "lib/pageEffects"),
];

/** Forbidden edges out of the browser: anything outside BROWSER_MAY (its own modules, api/, components/ui, components/Scope, ds/, kit/ and the listed lib/ modules). */
function browserViolations(file: string, text: string): string[] {
  return edges(file, text)
    .filter((t) => !BROWSER_MAY.some((ok) => inside(t, ok)))
    .map((t) => `${relative(SRC, file)} imports ${relative(SRC, t)}`);
}

/** Forbidden edges into the browser and the shell from anything but the shell. */
function inboundViolations(file: string, text: string): string[] {
  return edges(file, text)
    .filter((t) => inside(t, BROWSER) || inside(t, join(SRC, "shell")))
    .map((t) => `${relative(SRC, file)} imports ${relative(SRC, t)}`);
}

const KIT = join(SRC, "kit");
const KIT_MAY = [
  KIT,
  join(SRC, "api"),
  join(SRC, "ds"),
  join(SRC, "lib/inputs"),
  join(SRC, "lib/format"),
  join(SRC, "lib/formFocus"),
  join(SRC, "lib/template"),
];

/** Forbidden edges out of the kit: anything but its own modules and the allow-list (SD-013). */
function kitViolations(file: string, text: string): string[] {
  return edges(file, text)
    .filter((t) => !KIT_MAY.some((ok) => inside(t, ok)))
    .map((t) => `${relative(SRC, file)} imports ${relative(SRC, t)}`);
}

/** Edges from `lib/` into the kit. */
function libToKitViolations(file: string, text: string): string[] {
  return edges(file, text)
    .filter((t) => inside(t, KIT))
    .map((t) => `${relative(SRC, file)} imports ${relative(SRC, t)}`);
}

/** The only modules of `browser/` and `kit/` that may call validate, invoke or batch (the console's BatchForm calls batch, outside both). */
const WRITERS = [join(KIT, "useActionForm.ts"), join(KIT, "actionCore.ts")];

const WRITE_VERBS = new Set(["validate", "invoke", "batch"]);

/** The verb a node reaches and the text of what it reaches it off, or undefined for a node that reaches none. */
function reach(node: ts.Node, sf: ts.SourceFile): { verb?: string; receiver: string } | undefined {
  if (ts.isPropertyAccessExpression(node))
    return { verb: node.name.text, receiver: node.expression.getText(sf) };
  if (ts.isElementAccessExpression(node)) {
    const arg = node.argumentExpression;
    const receiver = node.expression.getText(sf);
    if (ts.isStringLiteralLike(arg)) return { verb: arg.text, receiver };
    // a computed key on a client could be any verb: counted as one that no file may reach
    return /client/i.test(receiver) ? { verb: "invoke", receiver } : undefined;
  }
  if (!ts.isBindingElement(node)) return undefined;
  const named = node.propertyName ?? node.name;
  const decl = node.parent.parent;
  return {
    verb: ts.isIdentifier(named) || ts.isStringLiteralLike(named) ? named.text : undefined,
    receiver: (ts.isVariableDeclaration(decl) && decl.initializer?.getText(sf)) || "",
  };
}

/**
 * Every way a source reaches a write verb, found with the TypeScript parser rather than a call pattern:
 * a property access (`c.invoke`, called or not, so `const f = c.invoke` and `.bind` are caught), a
 * bracket access with a literal key (`c["invoke"]`) or with a computed key on a client (`client[k]`),
 * and a destructured binding (`const { invoke } = c`, `({ batch: b }) => ...`). A verb named by a
 * declaration, an object literal or a type is not a reach. The kit's form model offers its own
 * `validate` (a check the kit makes): a read of it off `form` is not the client's.
 */
function writeReaches(file: string, text: string): string[] {
  const kind = file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  const verbs: string[] = [];
  const visit = (node: ts.Node): void => {
    const r = reach(node, sf);
    if (r?.verb && WRITE_VERBS.has(r.verb) && !(r.verb === "validate" && r.receiver === "form"))
      verbs.push(r.verb);
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return verbs;
}

/** Storage use anywhere in `browser/` or `kit/`, and a write reach outside the kit's form model and core. */
function writeViolations(file: string, text: string): string[] {
  const name = relative(SRC, file);
  const out: string[] = [];
  if (/localStorage|sessionStorage|indexedDB|document\.cookie/.test(text))
    out.push(`${name} uses browser storage`);
  const reaches = writeReaches(file, text);
  if (!WRITERS.includes(file) && reaches.length > 0)
    out.push(`${name} reaches validate, invoke or batch`);
  if (WRITERS.includes(file) && reaches.includes("batch")) out.push(`${name} reaches batch`);
  return out;
}

/** Edges into the kit that name a module of it: only the kit's index is imported from outside it (SD-013). */
function kitInternalViolations(file: string, text: string): string[] {
  if (inside(file, KIT)) return [];
  return edges(file, text)
    .filter((t) => inside(t, KIT) && t !== KIT && t !== join(KIT, "index"))
    .map((t) => `${relative(SRC, file)} imports ${relative(SRC, t)}`);
}

const read = (f: string) => readFileSync(f, "utf8");
const sourcesOf = (dir: string) => files(dir);
const isTest = (f: string) => /\/(test|integration)\//.test(f);

describe("module boundaries (SD-011)", () => {
  it("the browser imports api/, components/ui, ds/, kit/, lib/format, lib/inputs, lib/download, lib/template, lib/relLabels, lib/brand, lib/documentTitle and its own modules only", () => {
    const own = sourcesOf(BROWSER);
    expect(own.length).toBeGreaterThan(20);
    expect(own.flatMap((f) => browserViolations(f, read(f)))).toEqual([]);
  });

  it("the kit imports api/, ds/, lib/inputs, lib/format, lib/formFocus, lib/template and its own modules only", () => {
    const own = sourcesOf(KIT);
    expect(own.length).toBeGreaterThan(5);
    expect(own.flatMap((f) => kitViolations(f, read(f)))).toEqual([]);
  });

  it("the design-system seam is a leaf: ds/ imports React and its own modules only", () => {
    const own = sourcesOf(join(SRC, "ds"));
    expect(own.length).toBeGreaterThan(3);
    const DS = join(SRC, "ds");
    expect(
      own.flatMap((f) =>
        edges(f, read(f))
          .filter((t) => !inside(t, DS))
          .map((t) => `${relative(SRC, f)} imports ${relative(SRC, t)}`),
      ),
    ).toEqual([]);
    expect(
      edges(join(DS, "x.ts"), 'import { a } from "../lib/format";').filter((t) => !inside(t, DS)),
    ).toHaveLength(1);
  });

  it("nothing in lib/ imports the kit", () => {
    const libs = sourcesOf(join(SRC, "lib"));
    expect(libs.length).toBeGreaterThan(5);
    expect(libs.flatMap((f) => libToKitViolations(f, read(f)))).toEqual([]);
  });

  it("the console's areas, libraries and component never import the browser or the shell", () => {
    const rest = sourcesOf(SRC).filter(
      (f) =>
        !isTest(f) &&
        !inside(f, BROWSER) &&
        !inside(f, join(SRC, "shell")) &&
        !inside(f, join(SRC, "dev")) && // the standalone host's page, like main.tsx, mounts the shell
        !f.endsWith("main.tsx") &&
        !f.endsWith("embed.tsx"), // the page `arras.ui` serves mounts the shell too
    );
    expect(rest.flatMap((f) => inboundViolations(f, read(f)))).toEqual([]);
  });

  it("the console's entry does not export the browser or the shell, and the package names both entries", () => {
    expect(read(join(SRC, "index.ts"))).not.toMatch(/browser|shell/);
    const pkg = JSON.parse(read(join(UI, "package.json"))) as { exports: Record<string, string> };
    expect(pkg.exports["./browser"]).toBe("./src/browser/index.ts");
    expect(pkg.exports["./shell"]).toBe("./src/shell/index.ts");
  });

  it("US-070-AC5: no module of the browser or the shell renders markup from text", () => {
    const all = [...sourcesOf(BROWSER), ...sourcesOf(join(SRC, "shell"))];
    for (const f of all) {
      const text = read(f);
      expect(text, f).not.toMatch(
        /dangerouslySetInnerHTML|innerHTML|insertAdjacentHTML|document\.write/,
      );
      expect(text, f).not.toMatch(/\bnew Function\b|\beval\(/);
    }
  });

  it("US-071-AC5: the browser and the kit store nothing in the browser's storage and write only from the kit's form model and core", () => {
    const own = [...sourcesOf(BROWSER), ...sourcesOf(KIT)];
    expect(own.length).toBeGreaterThan(30);
    expect(own.flatMap((f) => writeViolations(f, read(f)))).toEqual([]);
  });

  it("nothing outside the kit imports a module of it but its index (SD-013)", () => {
    const outside = sourcesOf(SRC).filter((f) => !inside(f, KIT) && f !== import.meta.filename);
    expect(outside.length).toBeGreaterThan(100);
    expect(outside.flatMap((f) => kitInternalViolations(f, read(f)))).toEqual([]);
  });

  it("an import of a kit module past its index is found (negative controls)", () => {
    const a = join(SRC, "areas/x.ts");
    for (const bad of [
      "../kit/invalidate",
      "../kit/pieces",
      "@/kit/types",
      `${SRC}/kit/useActionForm`,
    ])
      expect(kitInternalViolations(a, `import { a } from "${bad}";`), bad).toHaveLength(1);
    expect(kitInternalViolations(a, 'import("../kit/pieces");')).toHaveLength(1);
    expect(kitInternalViolations(a, 'export type { C } from "../kit/types";')).toHaveLength(1);
    expect(kitInternalViolations(a, 'import {\n  a,\n  b,\n} from "../kit/pieces";')).toHaveLength(
      1,
    );
    expect(kitInternalViolations(a, 'import { a } from "../kit";')).toEqual([]);
    expect(kitInternalViolations(a, 'import { a } from "../kit/index";')).toEqual([]);
    expect(kitInternalViolations(join(KIT, "x.ts"), 'import { a } from "./pieces";')).toEqual([]);
  });

  it("a write verb reached by destructuring, brackets, aliasing or binding is found (negative controls)", () => {
    const forms = [
      "const { invoke } = client;",
      "const { invoke: run } = client;",
      "const { batch, validate } = useClient();",
      'const { "invoke": run } = client;',
      "function f({ invoke }: C) { return invoke; }",
      "const f = (c) => c.invoke;",
      'client["invoke"](a);',
      "client['batch'](a);",
      "client[`validate`](a);",
      "client[verb](a);",
      "const run = client.invoke;",
      "const run = client.invoke.bind(client);",
      "client?.invoke?.(a);",
      "client\n  .validate(a);",
    ];
    for (const form of forms) {
      expect(writeViolations(join(BROWSER, "x.ts"), form), form).toHaveLength(1);
      expect(writeViolations(join(KIT, "plans.ts"), form), form).toHaveLength(1);
    }
    // the writers may reach validate and invoke in any form, never batch
    expect(writeViolations(join(KIT, "useActionForm.ts"), "const { invoke } = client;")).toEqual(
      [],
    );
    expect(writeViolations(join(KIT, "actionCore.ts"), 'client["validate"](a);')).toEqual([]);
    expect(writeViolations(join(KIT, "actionCore.ts"), "const { batch } = client;")).toHaveLength(
      1,
    );
    expect(writeViolations(join(KIT, "actionCore.ts"), 'client["batch"](a);')).toHaveLength(1);
    // the form model's own validate is not the client's
    expect(writeViolations(join(BROWSER, "x.ts"), "const { validate: check } = form;")).toEqual([]);
    expect(writeViolations(join(BROWSER, "x.ts"), "form.validate();")).toEqual([]);
    expect(writeViolations(join(BROWSER, "x.ts"), "const { invoke } = form;")).toHaveLength(1);
  });

  it("a verb named by a declaration, an object literal or a string is not a reach", () => {
    const quiet = [
      "interface C { invoke(a: string): void; validate: () => void }",
      "const o = { invoke: 1, batch() {} };",
      'const label = "invoke";',
      "const x = rows[i];",
      "// client.invoke(a)\nconst y = 1;",
    ];
    for (const form of quiet)
      expect(writeViolations(join(BROWSER, "x.ts"), form), form).toEqual([]);
  });

  it("a planted write or storage call in the browser or the kit is found (negative controls)", () => {
    for (const call of ["client.validate(a)", "c.invoke(a, b)", "client.batch(a)"]) {
      expect(writeViolations(join(BROWSER, "x.ts"), call), call).toHaveLength(1);
      expect(writeViolations(join(KIT, "plans.ts"), call), call).toHaveLength(1);
      expect(
        writeViolations(join(KIT, "useActionForm.ts"), call.replace("batch", "validate")),
      ).toEqual([]);
      expect(writeViolations(join(KIT, "actionCore.ts"), call.replace("batch", "invoke"))).toEqual(
        [],
      );
    }
    expect(writeViolations(join(KIT, "useActionForm.ts"), "client.batch(a)")).toHaveLength(1);
    expect(writeViolations(join(BROWSER, "x.ts"), "localStorage.getItem(a)")).toHaveLength(1);
    expect(writeViolations(join(KIT, "x.ts"), "document.cookie")).toHaveLength(1);
  });

  it("a forbidden kit edge is found (negative controls)", () => {
    const f = join(KIT, "x.ts");
    for (const bad of [
      "../areas/EntityPanel",
      "../browser/planner",
      "../console/Shell",
      "../shell/ArrasApp",
      "../route",
      "../lib/graph",
      "../lib/impact",
      "../components/ui",
    ])
      expect(kitViolations(f, `import { a } from "${bad}";`), bad).toHaveLength(1);
    expect(
      kitViolations(
        f,
        'import { a } from "../api/gql";\nimport { b } from "../lib/inputs";\nimport { c } from "./effects";',
      ),
    ).toEqual([]);
    expect(libToKitViolations(join(SRC, "lib/x.ts"), 'import { a } from "../kit";')).toHaveLength(
      1,
    );
    expect(libToKitViolations(join(SRC, "lib/x.ts"), 'import { a } from "./format";')).toEqual([]);
    // browser/ and areas/ may import the kit
    expect(browserViolations(join(BROWSER, "x.ts"), 'import { a } from "../kit";')).toEqual([]);
    expect(inboundViolations(join(SRC, "areas/x.ts"), 'import { a } from "../kit";')).toEqual([]);
  });

  it("an aliased, absolute or package-style import is resolved, so it is no way around a rule", () => {
    const k = join(KIT, "x.ts");
    const b = join(BROWSER, "x.ts");
    for (const bad of [
      "@/areas/GraphArea",
      "~/areas/GraphArea",
      "src/areas/GraphArea",
      `${SRC}/areas/GraphArea`,
      "arras-ui/shell",
      "arras-ui",
    ]) {
      expect(kitViolations(k, `import { a } from "${bad}";`), `kit ${bad}`).toHaveLength(1);
      expect(browserViolations(b, `import { a } from "${bad}";`), `browser ${bad}`).toHaveLength(1);
    }
    // the same spellings of what is allowed stay allowed, and third-party packages are not edges
    expect(kitViolations(k, 'import { a } from "@/api/gql";')).toEqual([]);
    expect(browserViolations(b, 'import { a } from "arras-ui/browser";')).toEqual([]);
    expect(
      kitViolations(k, 'import { a } from "react";\nimport { b } from "@tanstack/react-query";'),
    ).toEqual([]);
    expect(libToKitViolations(join(SRC, "lib/x.ts"), 'import { a } from "@/kit";')).toHaveLength(1);
    expect(inboundViolations(join(SRC, "areas/x.ts"), 'import("arras-ui/browser");')).toHaveLength(
      1,
    );
    expect(inboundViolations(join(SRC, "areas/x.ts"), 'import { a } from "@/shell";')).toHaveLength(
      1,
    );
  });

  it("a forbidden edge is found (negative controls)", () => {
    const f = join(BROWSER, "x.ts");
    expect(browserViolations(f, 'import { a } from "../areas/GraphArea";')).toHaveLength(1);
    expect(browserViolations(f, 'import { a } from "../ArrasConsole";')).toHaveLength(1);
    expect(browserViolations(f, 'import { a } from "../shell/ArrasApp";')).toHaveLength(1);
    expect(browserViolations(f, 'import { a } from "../lib/graph";')).toHaveLength(1);
    expect(
      browserViolations(f, 'import { a } from "../api/client";\nimport { b } from "./meta";'),
    ).toEqual([]);
    expect(
      inboundViolations(join(SRC, "areas/x.ts"), 'import { a } from "../browser/index";'),
    ).toHaveLength(1);
    expect(
      inboundViolations(join(SRC, "ArrasConsole.tsx"), 'import { a } from "./shell";'),
    ).toHaveLength(1);
  });
});
