// SPDX-License-Identifier: MIT OR Apache-2.0
// Compile and render an isolated consumer of the same tarball the Python wheel carries. This uses
// only the just-built package and the exact dependencies already installed for the UI workspace.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const ui = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(ui, "..");
const npmDir = resolve(repo, "src/arras/ui/npm");
const tarball = process.argv[2]
  ? resolve(process.argv[2])
  : join(
      npmDir,
      `documentdrivendx-arras-ui-${/^version\s*=\s*"([^"]+)"/m.exec(readFileSync(join(repo, "pyproject.toml"), "utf8"))?.[1]}.tgz`,
    );
const manifestPath = process.argv[3]
  ? resolve(process.argv[3])
  : process.argv[2]
    ? null
    : join(repo, "src/arras/public-api.json");
assert.ok(
  manifestPath,
  "pass the public-api.json carried beside an explicit tarball so artifact checks use the same wheel cohort",
);
const catalog = JSON.parse(readFileSync(manifestPath, "utf8"));
const sourceModules = join(ui, "node_modules");
const temp = mkdtempSync(join(tmpdir(), "arras-packed-consumer-"));
const nodeModules = join(temp, "node_modules");

function installLocalPackage(name, source) {
  const target = join(nodeModules, name);
  mkdirSync(dirname(target), { recursive: true });
  symlinkSync(realpathSync(join(sourceModules, source)), target, "dir");
}

try {
  assert.ok(readFileSync(tarball).length > 0, `missing package tarball: ${tarball}`);
  mkdirSync(join(nodeModules, "@documentdrivendx"), { recursive: true });
  mkdirSync(join(nodeModules, "@documentdrivendx", "arras-ui"), { recursive: true });
  execFileSync("tar", [
    "-xzf",
    tarball,
    "-C",
    join(nodeModules, "@documentdrivendx", "arras-ui"),
    "--strip-components=1",
  ]);

  const packageRoot = join(nodeModules, "@documentdrivendx", "arras-ui");
  const peerManifest = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
  assert.equal(peerManifest.name, catalog.distribution.npm.name);

  function packedExportInventory(exports) {
    return Object.fromEntries(
      Object.entries(exports).map(([subpath, target]) => {
        if (typeof target === "string") {
          const kind = subpath === "./styles.css" ? "style" : "metadata";
          return [subpath, { [kind]: target.replace(/^\.\//, "") }];
        }
        return [
          subpath,
          {
            ...(target.import ? { runtime: target.import.replace(/^\.\//, "") } : {}),
            ...(target.types ? { types: target.types.replace(/^\.\//, "") } : {}),
          },
        ];
      }),
    );
  }
  const packedPeers = Object.fromEntries(
    Object.entries(peerManifest.peerDependencies ?? {}).map(([name, version]) => [
      name,
      {
        version,
        optional: peerManifest.peerDependenciesMeta?.[name]?.optional === true,
      },
    ]),
  );
  assert.deepEqual(packedExportInventory(peerManifest.exports), catalog.distribution.npm.exports);
  assert.deepEqual(packedPeers, catalog.distribution.npm.peer_dependencies);

  function declarationExports(file) {
    const program = ts.createProgram([file], {
      module: ts.ModuleKind.ESNext,
      moduleResolution: ts.ModuleResolutionKind.Bundler,
      skipLibCheck: true,
    });
    const source = program.getSourceFile(file);
    assert.ok(source, `TypeScript could not load packed declaration ${file}`);
    const checker = program.getTypeChecker();
    const module = checker.getSymbolAtLocation(source);
    assert.ok(module, `No declaration module symbol in ${file}`);
    return checker
      .getExportsOfModule(module)
      .filter((symbol) => {
        const resolved =
          symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
        return (resolved.flags & ts.SymbolFlags.Type) !== 0;
      })
      .map((symbol) => symbol.getName())
      .sort();
  }

  // npm's packed manifest leaves these as host dependencies. Link the exact versions the workspace
  // built against instead of reaching a registry or creating an additional React runtime.
  for (const name of [
    "react",
    "react-dom",
    "scheduler",
    "@types/react",
    "@types/react-dom",
    "csstype",
    "typescript",
    "@tanstack/react-query",
    "@tanstack/query-core",
    "@documentdrivendx/umf-schema-browser",
  ]) {
    installLocalPackage(name, name);
  }

  const packedRuntime = {};
  for (const subpath of Object.keys(catalog.ui.npm_runtime_exports)) {
    const exportEntry = peerManifest.exports[subpath];
    assert.ok(
      exportEntry && typeof exportEntry === "object" && exportEntry.import,
      `missing packed runtime export ${subpath}`,
    );
    const module = await import(pathToFileURL(resolve(packageRoot, exportEntry.import)).href);
    packedRuntime[subpath] = Object.keys(module).sort();
  }
  assert.deepEqual(packedRuntime, catalog.ui.npm_runtime_exports);

  const packedTypes = {};
  for (const subpath of Object.keys(catalog.ui.npm_type_exports)) {
    const exportEntry = peerManifest.exports[subpath];
    assert.ok(
      exportEntry && typeof exportEntry === "object" && exportEntry.types,
      `missing packed type export ${subpath}`,
    );
    packedTypes[subpath] = declarationExports(resolve(packageRoot, exportEntry.types));
  }
  assert.deepEqual(packedTypes, catalog.ui.npm_type_exports);

  const fixture = join(temp, "consumer.tsx");
  writeFileSync(
    fixture,
    `import {
  DesignSystemProvider,
  ROLE_TOKENS,
  defaultDesignSystem,
  useDesignSystem,
  type ButtonProps,
  type ButtonVariant,
  type DesignSystem,
  type FieldChrome,
  type MarkProps,
  type NoticeProps,
  type NoticeTone,
  type RoleToken,
  type SelectOption,
  type SelectProps,
  type TextAreaProps,
  type TextFieldProps,
} from "@documentdrivendx/arras-ui";
import { GraphBrowser, type GraphBrowserProps } from "@documentdrivendx/arras-ui/browser";
import { ArrasApp, type ArrasAppProps } from "@documentdrivendx/arras-ui/shell";
import type { ComponentType } from "react";

const role: RoleToken = ROLE_TOKENS[0];
const variant: ButtonVariant = "secondary";
const option: SelectOption = { value: "v", label: "Value" };
const props: ButtonProps = { variant };
const field: FieldChrome = { label: "Name" };
const mark: MarkProps = { label: "Arras" };
const notice: NoticeProps = { tone: "info" satisfies NoticeTone };
const select: SelectProps = { options: [option] };
const area: TextAreaProps = field;
const text: TextFieldProps = field;
const system: DesignSystem = defaultDesignSystem;
const allTypes: [ButtonProps, FieldChrome, MarkProps, NoticeProps, SelectProps, TextAreaProps, TextFieldProps] =
  [props, field, mark, notice, select, area, text];
const browserProps: GraphBrowserProps = { singleKeys: false };
const shellProps: ArrasAppProps = { defaultMode: "user" };
const button: ComponentType<ButtonProps> = system.Button;
void [role, allTypes, browserProps, shellProps, button];

export function Consumer({
  HostButton,
}: {
  HostButton: ComponentType<ButtonProps>;
}) {
  function BrowserProbe() {
    const ds = useDesignSystem();
    return <ds.Button variant="secondary" data-testid="browser-probe">Shared</ds.Button>;
  }

  return (
    <DesignSystemProvider designSystem={{ Button: HostButton }}>
      <GraphBrowser palette={() => <BrowserProbe />} singleKeys={false} />
    </DesignSystemProvider>
  );
}
`,
  );
  writeFileSync(
    join(temp, "tsconfig.json"),
    JSON.stringify({
      compilerOptions: {
        target: "ES2022",
        module: "NodeNext",
        moduleResolution: "NodeNext",
        jsx: "react-jsx",
        strict: true,
        skipLibCheck: true,
        noEmit: true,
      },
      files: ["consumer.tsx"],
    }),
  );
  execFileSync(
    join(nodeModules, "typescript/bin/tsc"),
    ["--project", join(temp, "tsconfig.json")],
    {
      cwd: temp,
      stdio: "inherit",
    },
  );

  const runtime = join(temp, "runtime-consumer.mjs");
  writeFileSync(
    runtime,
    `import assert from "node:assert/strict";
import * as React from "react";
import { renderToString } from "react-dom/server";
import {
  DesignSystemProvider,
  ROLE_TOKENS,
  defaultDesignSystem,
  useDesignSystem,
} from "@documentdrivendx/arras-ui";
import { GraphBrowser } from "@documentdrivendx/arras-ui/browser";
import { ArrasApp } from "@documentdrivendx/arras-ui/shell";

assert.equal(typeof DesignSystemProvider, "function");
assert.equal(typeof GraphBrowser, "function");
assert.equal(typeof ArrasApp, "function");
assert.equal(ROLE_TOKENS.length, 18);
assert.ok(defaultDesignSystem.Button);

const HostButton = ({ children, variant }) =>
  React.createElement("button", { "data-host-button": variant }, children);
function SharedProbe() {
  const ds = useDesignSystem();
  return React.createElement(
    React.Fragment,
    null,
    React.createElement(ds.Button, { variant: "secondary" }, "Shared"),
    React.createElement(ds.TextField, { label: "Default field" }),
  );
}
function DefaultProbe() {
  const ds = useDesignSystem();
  return React.createElement(ds.Button, null, "Built in");
}
globalThis.window = { location: { hash: "" }, history: { state: {} } };
const defaultHtml = renderToString(React.createElement(DefaultProbe));
assert.match(defaultHtml, /arras-btn--primary/);
const html = renderToString(
  React.createElement(
    DesignSystemProvider,
    { designSystem: { Button: HostButton } },
    React.createElement(GraphBrowser, {
      singleKeys: false,
      palette: () => React.createElement(SharedProbe),
    }),
  ),
);
assert.match(html, /data-host-button="secondary"/);
assert.match(html, />Shared<\\/button>/);
assert.match(html, /arras-field__input/);
process.stdout.write("Packed consumer passed through package exports\\n");
`,
  );

  // The library build must keep one shared context chunk reachable from all three package entries.
  // This guards against a future entry-specific bundle duplicating the context singleton.
  const dist = join(nodeModules, "@documentdrivendx", "arras-ui", "dist");
  const entryFiles = ["index.js", "browser.js", "shell.js"];
  const jsFiles = new Set(readdirSync(dist).filter((name) => name.endsWith(".js")));
  const contents = new Map(
    [...jsFiles].map((name) => [name, readFileSync(join(dist, name), "utf8")]),
  );
  const sharedContext = [...contents].find(
    ([, text]) => text.includes('"arras-btn"') && text.includes("createContext as"),
  )?.[0];
  assert.ok(sharedContext, "packed output has a recognizable shared design-system/context chunk");
  function reaches(entry, wanted, seen = new Set()) {
    if (entry === wanted) return true;
    if (seen.has(entry)) return false;
    seen.add(entry);
    const source = contents.get(entry);
    if (!source) return false;
    const refs = source.matchAll(/(?:from\s*|import\s*)["']\.\/([^"']+\.js)["']/g);
    for (const [, child] of refs) if (reaches(child, wanted, seen)) return true;
    return false;
  }
  for (const entry of entryFiles)
    assert.ok(
      reaches(entry, sharedContext),
      `${entry} reaches shared context chunk ${sharedContext}`,
    );

  execFileSync(process.execPath, [runtime], { cwd: temp, stdio: "inherit" });
  const sourceManifest = JSON.parse(readFileSync(join(ui, "package.json"), "utf8"));
  assert.deepEqual(
    peerManifest.peerDependencies && Object.keys(peerManifest.peerDependencies).sort(),
    ["@axe-core/playwright", "@playwright/test", "react", "react-dom"],
  );
  for (const name of ["@axe-core/playwright", "@playwright/test"]) {
    assert.equal(peerManifest.peerDependenciesMeta?.[name]?.optional, true);
    assert.equal(peerManifest.peerDependencies[name], sourceManifest.peerDependencies[name]);
  }
  assert.ok(existsSync(join(packageRoot, "support/qualify-downstream-theme.mjs")));
  assert.ok(existsSync(join(packageRoot, "support/QUALIFICATION.md")));
  assert.equal(peerManifest.bin?.["arras-ui-qualify"], "./support/qualify-downstream-theme.mjs");
  assert.equal(peerManifest.peerDependencies.react, sourceManifest.dependencies.react);
  assert.equal(
    peerManifest.peerDependencies["react-dom"],
    sourceManifest.dependencies["react-dom"],
  );
  assert.equal(
    realpathSync(join(nodeModules, "react")),
    realpathSync(join(sourceModules, "react")),
  );
  assert.equal(
    realpathSync(join(nodeModules, "react-dom")),
    realpathSync(join(sourceModules, "react-dom")),
  );
} finally {
  rmSync(temp, { recursive: true, force: true });
}
