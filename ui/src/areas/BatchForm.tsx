// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useClient, useRefusals } from "../api/context";
import { ApiError } from "../api/errors";
import { useModule } from "../api/queries";
import type { BatchReceipt, ErrorBody } from "../api/types";
import { Button, Chip, ErrorPanel, Notice, Spinner } from "../components/ui";
import { keyed } from "../lib/format";
import { newKey } from "../lib/inputs";
import { ReceiptView } from "./ActionEffects";

const MAX_ITEMS = 100;

type Items = Record<string, unknown>[];

const isItemObject = (x: unknown) => x !== null && typeof x === "object" && !Array.isArray(x);

/** The pasted text as items, or why it is not a batch; both null when nothing is pasted. */
function parseItems(text: string): { items: Items | null; parseError: string | null } {
  if (!text.trim()) return { items: null, parseError: null };
  let v: unknown;
  try {
    v = JSON.parse(text);
  } catch {
    return { items: null, parseError: "That is not valid JSON." };
  }
  if (!Array.isArray(v) || !v.every(isItemObject)) {
    return { items: null, parseError: "Paste a JSON array of input objects, one per item." };
  }
  if (v.length < 1 || v.length > MAX_ITEMS) {
    return {
      items: null,
      parseError: `A batch has 1 to ${MAX_ITEMS} items; this has ${v.length}.`,
    };
  }
  return { items: v as Items, parseError: null };
}

function RefusalNotice({ refusal }: { refusal: ApiError }) {
  return (
    <Notice tone="bad" role="alert">
      {refusal.kind === "not_offered"
        ? "Not offered: this host does not offer that action to you."
        : `No access (${refusal.reason ?? "refused"}).`}{" "}
      The controls are disabled.
    </Notice>
  );
}

function ItemRefusal({ index, refusal }: { index: number; refusal: ErrorBody }) {
  return (
    <span className="text-bad" data-testid={`batch-refusal-${index}`}>
      Refused: {refusal.message}
      {refusal.failures?.map((f) => (
        <span key={f.id} className="ml-2 arras-mono">
          {f.id}: {f.reason}
        </span>
      ))}
      {keyed(refusal.violations ?? [], (v) => `${v.path}:${v.message}`).map(({ key, item: v }) => (
        <span key={key} className="ml-2 arras-mono">
          {v.path}: {v.message}
        </span>
      ))}
    </span>
  );
}

function BatchResult({ module, result }: { module: string; result: BatchReceipt }) {
  return (
    <div className="mt-3" data-testid="batch-result">
      <div className="mb-1 flex gap-2">
        <Chip tone="ok">{result.succeeded} applied</Chip>
        <Chip tone={result.failed ? "bad" : "neutral"}>{result.failed} refused</Chip>
        <Chip>{result.atomic ? "atomic" : "independent"}</Chip>
      </div>
      <ul className="m-0 list-none space-y-1 p-0">
        {result.items.map((it) => (
          <li
            key={it.index}
            data-testid={`batch-item-${it.index}`}
            className="rounded border border-line bg-surface p-2"
          >
            <span className="mr-2 font-semibold">#{it.index}</span>
            {"receipt" in it ? (
              <ReceiptView r={it.receipt} module={module} />
            ) : (
              <ItemRefusal index={it.index} refusal={it.refusal} />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function BatchOptions({
  atomic,
  stopOnError,
  busy,
  onAtomic,
  onStopOnError,
}: {
  atomic: boolean;
  stopOnError: boolean;
  busy: boolean;
  onAtomic: (v: boolean) => void;
  onStopOnError: (v: boolean) => void;
}) {
  return (
    <div className="my-2 flex flex-wrap gap-4">
      <label className="flex items-center gap-1.5">
        <input
          type="checkbox"
          checked={atomic}
          disabled={busy}
          onChange={(e) => onAtomic(e.target.checked)}
        />{" "}
        Atomic (all or nothing)
      </label>
      <label className="flex items-center gap-1.5">
        <input
          type="checkbox"
          checked={stopOnError}
          disabled={atomic || busy}
          onChange={(e) => onStopOnError(e.target.checked)}
        />{" "}
        Stop on first error
      </label>
    </div>
  );
}

function ConfirmNotice({
  count,
  action,
  atomic,
  busy,
  onRun,
  onCancel,
}: {
  count: number | undefined;
  action: string;
  atomic: boolean;
  busy: boolean;
  onRun: () => void;
  onCancel: () => void;
}) {
  return (
    <Notice tone="warn" role="alert">
      <div className="mb-2">
        Apply <strong>{count}</strong> items of <span className="arras-mono">{action}</span>,{" "}
        {atomic
          ? "atomically: if one fails none apply"
          : "independently: each succeeds or fails on its own"}
        . This changes data and cannot be undone from the console.
      </div>
      <div className="flex gap-2">
        <Button variant="primary" disabled={busy} onClick={onRun}>
          {busy ? "Applying…" : "Confirm and apply batch"}
        </Button>
        <Button onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </Notice>
  );
}

const isRefusalKind = (e: ApiError) => e.kind === "no_access" || e.kind === "not_offered";

/** US-062 batch: up to 100 items of one action from a pasted JSON array, atomic or independent. */
export function BatchForm({ module: name, action }: { module: string; action: string }) {
  const client = useClient();
  const qc = useQueryClient();
  const { module: m, meta } = useModule(name);
  const { refusals, refuse } = useRefusals();
  const [text, setText] = useState("");
  const [atomic, setAtomic] = useState(false);
  const [stopOnError, setStopOnError] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BatchReceipt | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const sending = useRef(false);
  const key = useRef<{ sig: string; key: string } | null>(null);
  const refusal = refusals[action];

  if (meta.isPending) return <Spinner />;
  if (meta.error) return <ErrorPanel error={meta.error} />;
  if (!m) return <ErrorPanel error={new ApiError(404, { message: "not found" })} />;

  const { items, parseError } = parseItems(text);

  const failed = async (e: unknown) => {
    const err = e instanceof ApiError ? e : new ApiError(0, { message: String(e) });
    if (err.kind === "no_access" || err.kind === "not_offered") refuse(action, err);
    // Any conflict: the next confirmation is a new request, so it carries a new key.
    if (err.kind === "conflict" || err.kind === "revision_conflict") key.current = null;
    if (err.kind === "revision_conflict") {
      try {
        qc.setQueryData(["meta"], await client.meta());
      } catch {
        /* the next render shows the meta error */
      }
      setConfirming(false);
    }
    setError(err);
  };

  const run = async () => {
    if (!items || sending.current) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      const sig = JSON.stringify({ items, atomic, stopOnError });
      if (key.current?.sig !== sig) key.current = { sig, key: newKey() };
      const r = await client.batch(name, action, {
        items,
        atomic,
        stop_on_error: stopOnError,
        idempotency_key: key.current.key,
        expected_revision: m.revision,
      });
      setResult(r);
      setConfirming(false);
      void qc.invalidateQueries({ queryKey: ["list"] });
      void qc.invalidateQueries({ queryKey: ["entity"] });
      void qc.invalidateQueries({ queryKey: ["audit"] });
    } catch (e) {
      await failed(e);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="max-w-[900px] p-3" data-testid="batch-form">
      <p className="mt-0 text-muted">
        Paste a JSON array: one object of inputs per item (up to {MAX_ITEMS}). A batch has no dry
        run; every item is checked as it is applied.
      </p>
      {refusal && <RefusalNotice refusal={refusal} />}
      <label htmlFor="batch-items" className="mb-0.5 mt-2 block font-medium">
        Items
      </label>
      <textarea
        id="batch-items"
        className="arras-mono w-full rounded border border-strong bg-surface p-2 text-fg"
        rows={8}
        value={text}
        spellCheck={false}
        disabled={!!refusal || busy}
        onChange={(e) => {
          setText(e.target.value);
          setConfirming(false);
          setResult(null);
        }}
        placeholder={`[{"${m.actions.find((a) => a.name === action)?.inputSpecs[0]?.name ?? "input"}": "…"}]`}
        aria-invalid={!!parseError}
      />
      {parseError && (
        <div role="alert" className="text-bad">
          {parseError}
        </div>
      )}
      {items && <div className="text-muted">{items.length} items</div>}
      <BatchOptions
        atomic={atomic}
        stopOnError={stopOnError}
        busy={busy}
        onAtomic={(v) => {
          setAtomic(v);
          setConfirming(false); // a different request: review it again
        }}
        onStopOnError={(v) => {
          setStopOnError(v);
          setConfirming(false);
        }}
      />
      {error && !isRefusalKind(error) && <ErrorPanel error={error} inputsKept />}
      {confirming ? (
        <ConfirmNotice
          count={items?.length}
          action={action}
          atomic={atomic}
          busy={busy}
          onRun={() => void run()}
          onCancel={() => setConfirming(false)}
        />
      ) : (
        <Button
          variant="primary"
          disabled={!items || !!refusal || busy}
          onClick={() => setConfirming(true)}
        >
          Review batch…
        </Button>
      )}
      {result && <BatchResult module={name} result={result} />}
    </div>
  );
}
