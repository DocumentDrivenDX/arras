// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useId, useRef, useState } from "react";
import { useRefusals, useSchemaApi } from "../api/context";
import { ApiError, describeError } from "../api/errors";
import { SCHEMA_CATALOG_KEY, useSchemaCatalog } from "../api/queries";
import type {
  RegistryResult,
  SchemaChange,
  SchemaChangeElement,
  SchemaChangeKind,
  SchemaPlan,
} from "../api/types";
import { Button, Chip, ErrorPanel, Notice, Spinner } from "../components/ui";
import { keyed } from "../lib/format";
import { entryId } from "./umfBrowser";

/** Held in `useRefusals` once the backend has refused the viewer's schema grant: the view stays disabled. */
export const SCHEMA_REFUSAL = "schema";
/** A refusal belongs to the module it was for: a host's `authorize_schema` may refuse one module and not another. */
const refusalKey = (module: string) => `${SCHEMA_REFUSAL}:${module}`;

const ELEMENTS: { element: SchemaChangeElement; title: string }[] = [
  { element: "type", title: "Types" },
  { element: "property", title: "Properties" },
  { element: "relationship", title: "Relationships" },
  { element: "action", title: "Actions" },
];
const KIND_TONE: Record<SchemaChangeKind, "ok" | "warn" | "bad"> = {
  added: "ok",
  changed: "warn",
  retired: "bad",
};

interface Chosen {
  name: string;
  text: string;
}

/** The plan's changes grouped by element, in the order a person reads a module. */
export function groupChanges(
  changes: SchemaChange[],
): { element: SchemaChangeElement; title: string; changes: SchemaChange[] }[] {
  return ELEMENTS.map((g) => ({
    ...g,
    changes: changes.filter((c) => c.element === g.element),
  })).filter((g) => g.changes.length > 0);
}

function Changes({ plan }: { plan: SchemaPlan }) {
  const groups = groupChanges(plan.changes);
  if (groups.length === 0) return null;
  return (
    <div className="space-y-2" data-testid="plan-changes">
      {groups.map((g) => (
        <section key={g.element} aria-label={g.title} data-testid={`plan-${g.element}`}>
          <h4 className="m-0 mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
            {g.title} ({g.changes.length})
          </h4>
          <ul className="m-0 list-none space-y-1 p-0">
            {g.changes.map((c) => (
              <li
                key={`${c.kind}:${c.name}`}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded border border-line bg-surface px-2 py-1"
              >
                <Chip tone={KIND_TONE[c.kind]}>{c.kind}</Chip>
                <span className="arras-mono font-medium">{c.name}</span>
                {c.detail && <span className="text-muted">{c.detail}</span>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Violations({ items }: { items: { path: string; code: string; message: string }[] }) {
  return (
    <ul className="m-0 list-none space-y-1 p-0" data-testid="plan-violations">
      {keyed(items, (v) => `${v.code}:${v.path}:${v.message}`).map(({ key, item: v }) => (
        <li key={key} className="rounded border border-bad/40 bg-badsoft px-2 py-1">
          <span className="arras-mono font-semibold text-bad">{v.code}</span>
          {v.path && (
            <>
              {" "}
              <span className="arras-mono text-muted">{v.path}</span>
            </>
          )}
          <div>{v.message}</div>
        </li>
      ))}
    </ul>
  );
}

/** The module's registered document as the schema catalog holds it, to read the plan against. */
function Current({ module }: { module: string }) {
  const catalog = useSchemaCatalog();
  const entry = catalog.data?.entries.find((e) => e.id === entryId(module));
  let body: ReactNode;
  if (catalog.isPending) body = <Spinner label="Loading the registered document" />;
  else if (catalog.error)
    body = <ErrorPanel error={catalog.error} onRetry={() => void catalog.refetch()} />;
  else if (!entry)
    body = (
      <div className="text-muted">No registered document for {module} is readable for you.</div>
    );
  else if (entry.schemaFormat !== "umf")
    body = (
      <div className="text-muted">
        The catalog shows only a note for {module}: its document is too large to show.
      </div>
    );
  else
    body = (
      <textarea
        readOnly
        wrap="off"
        rows={Math.min(24, entry.text.split("\n").length)}
        value={entry.text}
        aria-label={`Registered document of ${module}`}
        className="arras-mono block w-full resize-y whitespace-pre rounded border border-line bg-surface p-2 text-[11px]"
        data-testid="current-document"
      />
    );
  return (
    <section aria-label="Currently registered" data-testid="current-registered" className="min-w-0">
      <h4 className="m-0 mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
        Currently registered: <span className="arras-mono normal-case">{module}</span>
      </h4>
      {body}
    </section>
  );
}

type Busy = "validate" | "apply" | null;

/**
 * The state of one import: the chosen file (in memory only), its plan, the result of applying it, and the request in
 * flight. A late answer to an older request is dropped: only the newest request's answer is shown. */
function useSchemaImport(module: string) {
  const api = useSchemaApi();
  const qc = useQueryClient();
  const { refusals, refuse } = useRefusals();
  const [file, setFile] = useState<Chosen | null>(null);
  const [readError, setReadError] = useState<string | null>(null);
  const [plan, setPlan] = useState<SchemaPlan | null>(null);
  const [applied, setApplied] = useState<RegistryResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const seq = useRef(0);

  const reset = () => {
    seq.current++;
    setPlan(null);
    setApplied(null);
    setError(null);
    setBusy(null);
  };

  function failed(e: unknown) {
    const err =
      e instanceof ApiError
        ? e
        : new ApiError(0, { type: "Network", message: e instanceof Error ? e.message : String(e) });
    if (err.status === 403 && err.type === "Refused")
      refuse(refusalKey(plan?.module ?? module), err);
    setError(err);
  }

  /** Run one request as the newest: its answer is used only if no newer request or reset came after it. */
  async function track<T>(
    kind: Exclude<Busy, null>,
    work: () => Promise<T>,
    onDone: (v: T) => unknown,
  ) {
    const mine = ++seq.current;
    setError(null);
    setBusy(kind);
    try {
      const v = await work();
      if (mine === seq.current) await onDone(v);
    } catch (e) {
      if (mine === seq.current) failed(e);
    } finally {
      if (mine === seq.current) setBusy(null);
    }
  }

  async function choose(f: File | undefined) {
    reset();
    setReadError(null);
    setFile(null);
    if (!f) return;
    try {
      setFile({ name: f.name, text: await f.text() });
    } catch {
      setReadError(`${f.name} could not be read.`);
    }
  }

  const validate = () => {
    if (!file) return;
    setPlan(null);
    setApplied(null);
    void track("validate", () => api.validate(file.text), setPlan);
  };

  const apply = () => {
    if (!(file && plan)) return;
    void track(
      "apply",
      () => api.register(file.text, plan.revision),
      async (r) => {
        setApplied(r);
        await Promise.all([
          qc.invalidateQueries({ queryKey: ["meta"] }),
          qc.invalidateQueries({ queryKey: SCHEMA_CATALOG_KEY }),
        ]);
      },
    );
  };

  const refusal = refusals[refusalKey(plan?.module ?? module)];
  return { file, readError, plan, applied, error, busy, refusal, choose, validate, apply };
}

/** What went wrong with a validate or an apply, in the surface's own terms (a 403 is shown as a refusal instead). */
function Problem({
  error,
  disabled,
  busy,
  onValidate,
}: {
  error: ApiError;
  disabled: boolean;
  busy: boolean;
  onValidate: () => void;
}) {
  if (error.kind === "revision_conflict" || error.kind === "conflict") {
    return (
      <Notice tone="warn" role="alert">
        <div data-testid="schema-conflict">
          <strong>The record store has moved on since this plan</strong> (conflict on the revision).
          Nothing was applied. Validate again to see what the document would change now.
          <Button className="ml-2" onClick={onValidate} disabled={disabled || busy}>
            Validate again
          </Button>
        </div>
      </Notice>
    );
  }
  if (error.kind === "unsupported") {
    return (
      <Notice role="alert">
        <div data-testid="schema-unsupported">
          <strong>Import is not offered for this module.</strong> Its record store cannot check a
          registration without applying it ({error.message}).
        </div>
      </Notice>
    );
  }
  if (error.status === 413) {
    return (
      <Notice tone="bad" role="alert">
        <strong>The document is too large.</strong> A document over 1 MiB is refused; nothing was
        sent for registration.
      </Notice>
    );
  }
  if (error.kind === "invalid") {
    return (
      <Notice tone="bad" role="alert">
        <div data-testid="schema-invalid">
          <strong>The document was refused</strong>
          {error.violations.length === 0 && <>: {error.message}</>}
          {error.violations.length > 0 && (
            <div className="mt-1">
              <Violations items={error.violations} />
            </div>
          )}
        </div>
      </Notice>
    );
  }
  return <ErrorPanel error={error} />;
}

function Applied({ result }: { result: RegistryResult }) {
  return (
    <Notice tone="ok" role="status">
      <div data-testid="schema-applied">
        <strong>
          {result.changed ? "Registered" : "Nothing changed in"}{" "}
          <span className="arras-mono">{result.module}</span>.
        </strong>{" "}
        {result.changed ? "New revision" : "Revision"}:{" "}
        <span className="arras-mono">{JSON.stringify(result.revision)}</span>. The schema views are
        refreshed.
      </div>
    </Notice>
  );
}

function PlanBody({ plan, module }: { plan: SchemaPlan; module: string }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold arras-mono">{plan.module}</span>
        <Chip tone={plan.ok ? "ok" : "bad"}>
          {plan.ok ? "can be registered" : "cannot be registered"}
        </Chip>
        <Chip title="The module's revision this plan was computed against; Apply registers only if it still holds">
          revision: <span className="arras-mono">{JSON.stringify(plan.revision)}</span>
        </Chip>
      </div>
      {plan.module !== module && (
        <Notice tone="warn">
          This document is for <span className="arras-mono">{plan.module}</span>, not{" "}
          <span className="arras-mono">{module}</span>, the module in view.
        </Notice>
      )}
      {!plan.ok && <Violations items={plan.violations} />}
      {plan.ok && !plan.changed && (
        <Notice tone="ok">
          <span data-testid="plan-unchanged">
            Nothing would change: this document is equal in meaning to the one registered. Apply is
            not offered.
          </span>
        </Notice>
      )}
      <Changes plan={plan} />
      {plan.report.length > 0 && (
        <ul className="m-0 list-none p-0 text-[12px] text-muted" aria-label="Backend report">
          {keyed(plan.report, (r) => r).map(({ key, item: r }) => (
            <li key={key}>{r}</li>
          ))}
        </ul>
      )}
    </>
  );
}

function PlanPane({ plan, module }: { plan: SchemaPlan | null; module: string }) {
  return (
    <section aria-label="Plan" data-testid="plan" className="min-w-0 space-y-2">
      <h4 className="m-0 text-[11px] font-semibold uppercase tracking-wide text-muted">Plan</h4>
      {plan ? (
        <PlanBody plan={plan} module={module} />
      ) : (
        <div className="text-muted">
          Choose Validate to see what this document would change. Nothing is applied by validating.
        </div>
      )}
    </section>
  );
}

/**
 * OPR-12, OPR-13: choose a UMF document (a file, read in this browser and kept in memory only), validate it
 * (a plan: what it would add, change or retire, and every refusal), and apply it as the viewer with the plan's
 * revision. Whether the viewer may is the backend's answer (the `schema` grant) and the host's
 * `authorize_schema`: a 403 is shown with its reason and disables the controls for this view, never replaced
 * by a decision of the console (OPR-07). Nothing is stored, and the document travels only in request bodies.
 */
export function SchemaImport({ module }: { module: string }) {
  const inputId = useId();
  const { file, readError, plan, applied, error, busy, refusal, choose, validate, apply } =
    useSchemaImport(module);
  const disabled = !!refusal;
  const canApply = !disabled && !busy && !!plan && plan.ok && plan.changed && !applied;

  return (
    <div className="flex flex-col gap-3" data-testid="schema-import">
      <Notice>
        <strong>Import a UMF document.</strong> The file is read in this browser and sent only to
        the schema surface, as you. <em>Validate</em> shows what it would change and applies
        nothing; <em>Apply</em> registers it as a new revision, attributed to you. The backend
        decides whether you may.
      </Notice>
      {refusal && (
        <Notice tone="bad" role="alert">
          <div data-testid="schema-refused">
            <strong>{describeError(refusal).title}.</strong> {describeError(refusal).detail} Import
            and Apply are disabled in this view.
          </div>
        </Notice>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={inputId} className="text-[12px] font-medium">
          UMF document
        </label>
        <input
          id={inputId}
          type="file"
          accept=".json,application/json"
          disabled={disabled}
          className="max-w-full text-[12px]"
          onChange={(e) => void choose(e.target.files?.[0])}
        />
        <Button
          onClick={validate}
          disabled={disabled || !file || !!busy}
          aria-busy={busy === "validate"}
        >
          Validate
        </Button>
        <Button
          variant="primary"
          onClick={apply}
          disabled={!canApply}
          aria-busy={busy === "apply"}
          data-testid="apply"
        >
          Apply
        </Button>
        {file && (
          <span className="text-[12px] text-muted" data-testid="chosen-file">
            {file.name}
          </span>
        )}
      </div>
      {readError && (
        <Notice tone="bad" role="alert">
          {readError}
        </Notice>
      )}
      <div aria-live="polite" className="flex flex-col gap-3">
        {busy === "validate" && <Spinner label="Validating" />}
        {busy === "apply" && <Spinner label="Applying" />}
        {error && error.status !== 403 && (
          <Problem error={error} disabled={disabled} busy={!!busy} onValidate={validate} />
        )}
        {applied && <Applied result={applied} />}
      </div>
      {(plan || file) && (
        <div className="grid items-start gap-3 min-[900px]:grid-cols-2">
          <PlanPane plan={plan} module={module} />
          <Current module={plan?.module ?? module} />
        </div>
      )}
    </div>
  );
}
