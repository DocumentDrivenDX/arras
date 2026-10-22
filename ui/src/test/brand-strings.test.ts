// SPDX-License-Identifier: MIT OR Apache-2.0
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

// SD-013, Branding (FR-73): no user-visible string names the product; the only place is the default in
// lib/brand.tsx. A literal "Arras" is allowed in comments, identifiers (ArrasApp, arras-brand,
// package names) and developer-facing `throw new Error(...)` only.
const SRC = join(import.meta.dirname, "..");
const ALLOWED_FILE = "lib/brand.tsx";

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    if (e.isDirectory()) return e.name === "test" || e.name === "integration" ? [] : sources(p);
    return /\.tsx?$/.test(e.name) ? [p] : [];
  });
}

const NAME = /arras/i;
// Identifiers that carry the lowercase name and are not words a person reads: the brand meta tag, the
// package, the export file and graph format ids, the catalog id prefix and the sandbox headers.
const IDENTIFIERS = [
  "arras-brand",
  "arras-ui",
  "arras-schema-catalog",
  "arras.graph",
  "arras:",
  "x-arras-",
];
// The library's own CSS classes and custom properties (`arras-root`, `--arras-color-text`, ...) are styling hooks, not words a person reads.
const CSS_CLASS = /(?<![\w-])(?:--|\.)?arras-(?!brand\b|ui\b|schema-catalog\b)[a-z][\w-]*/g;
const D = "$"; // builds template placeholders in the fixtures below without a literal one

/**
 * The text of a literal a person could read. A literal that is one identifier-shaped token (no
 * whitespace once its quotes, backticks and `${` `}` are off) and holds an allowed identifier is not
 * words; the same identifier inside a sentence (`"Saved as arras.graph"`, `"arras: the app"`) is.
 */
const visibleText = (text: string): string => {
  const inner = text.replace(/^["'`]|["'`]$|\$\{|\}/g, "").trim();
  return !/\s/.test(inner) && IDENTIFIERS.some((id) => inner.includes(id)) ? "" : text;
};

/**
 * A literal that only a developer sees: the direct string argument of `new Error(...)` (a plain string or a
 * template literal that is itself the argument), or the module specifier of an import, export or `import()`.
 */
function developerFacing(node: ts.Node): boolean {
  const p = node.parent;
  if (!p) return false;
  if (ts.isNewExpression(p) && p.expression.getText() === "Error") return p.arguments?.[0] === node;
  if (ts.isTemplateExpression(p) || ts.isTemplateSpan(p)) return templateIsErrorArgument(p);
  if (ts.isImportDeclaration(p) || ts.isExportDeclaration(p)) return p.moduleSpecifier === node;
  if (ts.isLiteralTypeNode(p)) return ts.isImportTypeNode(p.parent);
  return (
    ts.isCallExpression(p) &&
    p.expression.kind === ts.SyntaxKind.ImportKeyword &&
    p.arguments[0] === node
  );
}

/** Whether a template literal's part belongs to a template that is the first argument of `new Error`. */
function templateIsErrorArgument(part: ts.Node): boolean {
  const tpl = ts.isTemplateSpan(part) ? part.parent : part;
  const call = tpl.parent;
  return (
    ts.isNewExpression(call) && call.expression.getText() === "Error" && call.arguments?.[0] === tpl
  );
}

const TEXT_KINDS = new Set([
  ts.SyntaxKind.JsxText,
  ts.SyntaxKind.StringLiteral,
  ts.SyntaxKind.NoSubstitutionTemplateLiteral,
  ts.SyntaxKind.TemplateHead,
  ts.SyntaxKind.TemplateMiddle,
  ts.SyntaxKind.TemplateTail,
]);

/**
 * Every place a product-name literal can be seen by a person, found with the TypeScript parser: JSX text,
 * string literals and template parts. Comments and identifiers are not such nodes, so they pass; a literal
 * cannot be hidden from it by its surroundings (an apostrophe, a `{expr}` before it, indentation).
 */
function offences(file: string, text: string): string[] {
  const kind = file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  const hits: string[] = [];
  const visit = (node: ts.Node): void => {
    if (
      TEXT_KINDS.has(node.kind) &&
      NAME.test(visibleText(node.getText(sf)).replace(CSS_CLASS, "")) &&
      !developerFacing(node)
    ) {
      const { line } = sf.getLineAndCharacterOfPosition(node.getStart(sf));
      hits.push(`${file}:${line + 1}: ${node.getText(sf).trim().slice(0, 80)}`);
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return hits;
}

/**
 * The `<title>` of an HTML entry page: the default a served page replaces. It may be the brand's
 * default name and nothing else, so the product name has no second spelling a person can read.
 */
function titleOffences(file: string, html: string, brandName: string): string[] {
  return [...html.matchAll(/<title>([\s\S]*?)<\/title>/gi)]
    .map((m) => (m[1] ?? "").trim())
    .filter((t) => NAME.test(t) && t !== brandName)
    .map((t) => `${file}: <title>${t}</title> is not the default brand name`);
}

const defaultBrandName = (): string => {
  const text = readFileSync(join(SRC, ALLOWED_FILE), "utf8");
  const name = /DEFAULT_BRAND[^=]*=\s*\{\s*name:\s*"([^"]+)"/.exec(text)?.[1];
  if (!name) throw new Error("the default brand name was not found in lib/brand.tsx");
  return name;
};

describe("no hard-coded product name in a user-visible string (FR-73)", () => {
  it("every source outside lib/brand.tsx is clean", () => {
    const files = sources(SRC).filter((f) => relative(SRC, f) !== ALLOWED_FILE);
    expect(files.length).toBeGreaterThan(50);
    const found = files.flatMap((f) => offences(relative(SRC, f), readFileSync(f, "utf8")));
    expect(found).toEqual([]);
  });

  it("negative control: a planted literal is found in each place it can appear", () => {
    expect(offences("a.tsx", "const x = <h1>Arras console</h1>;")).toHaveLength(1);
    expect(offences("a.tsx", 'const x = <div aria-label="Arras">y</div>;')).toHaveLength(1);
    expect(offences("a.tsx", "const t = `About Arras`;")).toHaveLength(1);
    expect(offences("a.tsx", "<p>\n  This is Arras\n</p>")).toHaveLength(1);
    expect(offences("a.tsx", "const t = 'Arras';")).toHaveLength(1);
  });

  it("negative control: the literal this guard replaced, and text a line pattern misses", () => {
    const audit =
      "const x = <p><strong>No change history.</strong> This module's record store keeps no journal that Arras</p>;";
    expect(offences("a.tsx", audit)).toHaveLength(1);
    expect(offences("a.tsx", "const x = <p>{user}, welcome to Arras</p>;")).toHaveLength(1);
    expect(offences("a.tsx", "const x = <p>Hi {name} at Arras</p>;")).toHaveLength(1);
    expect(offences("a.tsx", "const x = <p>It's Arras</p>;")).toHaveLength(1);
    expect(
      offences("a.tsx", "const x = (\n  <p>\n    {count} rows in Arras\n  </p>\n);"),
    ).toHaveLength(1);
    expect(offences("a.tsx", "const x = <span>ArrasOps</span>;")).toHaveLength(1);
    expect(offences("a.tsx", `const t = \`${D}{n} rows in Arras\`;`)).toHaveLength(1);
    expect(offences("a.tsx", `const t = \`x ${D}{n} y Arras\`;`)).toHaveLength(1);
  });

  it("is not satisfied by identifiers, comments or developer errors", () => {
    expect(offences("a.tsx", "// Arras\nconst ArrasApp = 1; /* Arras */")).toEqual([]);
    expect(offences("a.tsx", 'import { ArrasClient } from "./client";')).toEqual([]);
    expect(offences("a.ts", 'throw new Error("Arras needs a provider");')).toEqual([]);
    expect(offences("a.ts", `throw new Error(\`Arras needs ${D}{x} a provider\`);`)).toEqual([]);
    expect(offences("a.ts", 'export * from "./ArrasThing";')).toEqual([]);
    expect(offences("a.ts", 'const m = "arras-brand";')).toEqual([]);
    expect(offences("a.ts", 'import("./Arras");')).toEqual([]);
    expect(offences("a.ts", 'type T = import("./Arras").X;')).toEqual([]);
  });

  it("negative control: the name in any case, and a literal beside a developer error, is found", () => {
    expect(offences("a.tsx", "const x = <h1>arras console</h1>;")).toHaveLength(1);
    expect(offences("a.tsx", "const x = <h1>ARRAS</h1>;")).toHaveLength(1);
    expect(offences("a.tsx", 'const t = "arras console";')).toHaveLength(1);
    expect(offences("a.tsx", "const x = <p>arras-brand and Arras</p>;")).toHaveLength(1);
    // JSX text that has a `new Error` sibling is not the error's argument.
    expect(offences("a.tsx", "const x = <p>{new Error('x') && 1}Arras console</p>;")).toHaveLength(
      1,
    );
    // A literal beside the argument, not the argument.
    expect(offences("a.ts", 'new Error("fine", { cause: "Arras console" });')).toHaveLength(1);
    expect(offences("a.ts", `new Error(\`fine ${D}{f("Arras console")}\`);`)).toHaveLength(1);
    expect(offences("a.ts", 'const e = new Error("x"); const s = "Arras console";')).toHaveLength(
      1,
    );
    expect(offences("a.ts", `new Error(\`Arras ${D}{x} console\`);`)).toEqual([]);
    expect(offences("a.ts", `const s = \`Arras ${D}{x}\`;`)).toHaveLength(1);
  });
});

describe("an identifier is not a way to hide the name in a sentence", () => {
  it("negative control: an allowed identifier beside words is found", () => {
    expect(offences("a.tsx", 'const t = "arras: the app";')).toHaveLength(1);
    expect(offences("a.tsx", 'const t = "Saved as arras.graph";')).toHaveLength(1);
    expect(offences("a.tsx", "const x = <p>arras.graph is the format</p>;")).toHaveLength(1);
    expect(offences("a.tsx", 'const t = "Open arras-ui now";')).toHaveLength(1);
    expect(offences("a.ts", `const t = \`welcome to arras: ${D}{x}\`;`)).toHaveLength(1);
    expect(offences("a.ts", 'const t = "x-arras-sandbox is set";')).toHaveLength(1);
  });

  it("an identifier alone in its literal is still allowed", () => {
    expect(offences("a.ts", 'const f = "arras.graph";')).toEqual([]);
    expect(offences("a.ts", 'const f = "arras:catalog";')).toEqual([]);
    expect(offences("a.ts", `const f = \`arras:${D}{k}\`;`)).toEqual([]);
    expect(offences("a.ts", 'const h = "x-arras-sandbox";')).toEqual([]);
    expect(offences("a.ts", 'const m = "arras-brand";')).toEqual([]);
  });
});

describe("the HTML entry pages (FR-73)", () => {
  const PAGES = ["index.html", "embed.html"];

  it("hold no title but the default brand name", () => {
    const name = defaultBrandName();
    for (const page of PAGES)
      expect(titleOffences(page, readFileSync(join(SRC, "..", page), "utf8"), name)).toEqual([]);
  });

  it("negative control: any other spelling of the name in a title is found", () => {
    expect(titleOffences("a.html", "<title>Arras console</title>", "Arras")).toHaveLength(1);
    expect(titleOffences("a.html", "<title>ARRAS</title>", "Arras")).toHaveLength(1);
    expect(titleOffences("a.html", "<title>\n  Arras ops\n</title>", "Arras")).toHaveLength(1);
    expect(titleOffences("a.html", "<title>Arras</title>", "Atlas")).toHaveLength(1);
    expect(titleOffences("a.html", "<title>Arras</title>", "Arras")).toEqual([]);
    expect(titleOffences("a.html", "<title>Atlas</title>", "Arras")).toEqual([]);
  });
});
