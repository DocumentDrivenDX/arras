// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ApiError } from "../api/errors";
import { shortName } from "../api/gql";
import type { ActionInfo, Failure, ModuleInfo, Receipt, Revision, Validation } from "../api/types";
import { ViewInExplore } from "../components/ExploreLink";
import { Button, Chip, ErrorPanel, Notice } from "../components/ui";
import { changedIds } from "../kit";
import { keyed } from "../lib/format";
import { EffectList, ReceiptView } from "./ActionEffects";

type Refusal = ApiError;

const SECTION_LABEL = "text-[11px] font-semibold uppercase tracking-wide text-muted";

function RefusalNotice({ refusal }: { refusal: Refusal }) {
  const notOffered = refusal.kind === "not_offered";
  return (
    <div className="mb-3">
      <Notice tone="bad" role="alert">
        <strong>{notOffered ? "Not offered." : "No access."}</strong>{" "}
        {notOffered
          ? "This host does not offer that action to you."
          : `The provider refused you (${refusal.reason ?? "no_access"}), so this action cannot be run as you.`}{" "}
        The controls are disabled.
      </Notice>
    </div>
  );
}

function ConflictNotice({ revision }: { revision: Revision }) {
  return (
    <div className="mb-3">
      <Notice tone="warn" role="alert">
        <strong>The module changed while this form was open.</strong> It was reloaded (revision{" "}
        <span className="arras-mono">{JSON.stringify(revision)}</span>) and the form rebuilt.
        Nothing was applied; review and confirm again.
      </Notice>
    </div>
  );
}

const isRefusalKind = (error: ApiError) =>
  error.kind === "no_access" || error.kind === "not_offered";

export function FormNotices({
  conflict,
  revision,
  refusal,
  error,
}: {
  conflict: boolean;
  revision: Revision;
  refusal: Refusal | null;
  error: ApiError | null;
}) {
  return (
    <>
      {conflict && <ConflictNotice revision={revision} />}
      {refusal && <RefusalNotice refusal={refusal} />}
      {error && !isRefusalKind(error) && <ErrorPanel error={error} inputsKept />}
    </>
  );
}

export function GeneralViolations({ messages }: { messages: string[] }) {
  if (messages.length === 0) return null;
  return (
    <div className="mb-3" data-testid="violations-general">
      <Notice tone="bad" role="alert">
        {keyed(messages, (g) => g).map(({ key, item: g }) => (
          <div key={key}>{g}</div>
        ))}
      </Notice>
    </div>
  );
}

const preconditionMark = (failed: boolean, ok: boolean | undefined) => {
  if (failed) return "✗";
  return ok ? "✓" : "·";
};

export function PreconditionList({
  info,
  failures,
  ok,
}: {
  info: ActionInfo;
  failures: Failure[];
  ok: boolean | undefined;
}) {
  return (
    <div className="mb-3">
      <div className={`mb-1 ${SECTION_LABEL}`}>Preconditions</div>
      <ul className="m-0 list-none p-0">
        {info.preconditions.map((p) => {
          const failed = failures.find((f) => f.id === p.id);
          return (
            <li
              key={p.id}
              className={failed ? "text-bad" : "text-muted"}
              data-testid={`precondition-${p.id}`}
            >
              {preconditionMark(!!failed, ok)} <span className="arras-mono">{p.id}</span>:{" "}
              {failed ? failed.reason : p.reason}
            </li>
          );
        })}
        {info.preconditions.length === 0 && <li className="text-muted">none</li>}
        {failures
          .filter((f) => !info.preconditions.some((p) => p.id === f.id))
          .map((f) => (
            <li key={f.id} className="text-bad" data-testid={`precondition-${f.id}`}>
              ✗ <span className="arras-mono">{f.id}</span>: {f.reason}
            </li>
          ))}
      </ul>
    </div>
  );
}

function ValidationChips({
  fresh,
  stale,
  validating,
}: {
  fresh: Validation | null;
  stale: boolean;
  validating: boolean;
}) {
  return (
    <div className="mb-1 flex items-center gap-2">
      <span className={SECTION_LABEL}>Effects</span>
      {validating && <Chip tone="accent">validating…</Chip>}
      {stale && !validating && <Chip tone="warn">inputs changed; validate again</Chip>}
      {fresh && <Chip tone={fresh.ok ? "ok" : "bad"}>{fresh.ok ? "valid" : "not valid"}</Chip>}
    </div>
  );
}

function ValidationBody({
  fresh,
  stale,
  module,
}: {
  fresh: Validation;
  stale: boolean;
  module?: string;
}) {
  return (
    <>
      {fresh.replay && <ReceiptView r={{ ...fresh.replay, replayed: true }} module={module} />}
      {fresh.effects.length > 0 && (
        <div className={stale ? "opacity-50" : ""}>
          <EffectList effects={fresh.effects} />
        </div>
      )}
      {!fresh.ok && (
        <div className="mt-1 text-bad" data-testid="not-valid">
          The inputs are not valid; fix the fields above. No invoke is offered.
        </div>
      )}
    </>
  );
}

export function EffectsPreview({
  fresh,
  stale,
  validating,
  module,
}: {
  fresh: Validation | null;
  stale: boolean;
  validating: boolean;
  module?: string;
}) {
  return (
    <div className="mb-3" aria-live="polite">
      <ValidationChips fresh={fresh} stale={stale} validating={validating} />
      {fresh && <ValidationBody fresh={fresh} stale={stale} module={module} />}
      {!fresh && !validating && (
        <div className="text-muted">
          Validate to see what this would change. Nothing is applied by validating.
        </div>
      )}
    </div>
  );
}

const deletedOf = (checked: Validation | null): string[] =>
  (checked?.effects ?? []).flatMap((e) =>
    e.kind === "delete" ? [`${e.ref.type}:${e.ref.key}`] : [],
  );

/** View in Explore for what the apply changed: its first entity that still exists. */
function ReceiptExploreLink({
  receipt,
  module,
  deleted,
}: {
  receipt: Receipt;
  module: string;
  deleted: string[];
}) {
  const ref = receipt.refs.find((x) => !deleted.includes(`${x.type}:${x.key}`));
  if (!ref) return null;
  return (
    <ViewInExplore
      target={{ entity: { module, type: ref.type, key: ref.key } }}
      label={`${shortName(ref.type)} ${ref.key}`}
    />
  );
}

export function ReceiptSection({
  receipt,
  receiptRef,
  module: m,
  info,
  checked,
  onViewInGraph,
  onReset,
  onEdit,
}: {
  receipt: Receipt;
  receiptRef: React.RefObject<HTMLDivElement | null>;
  module: ModuleInfo;
  info: ActionInfo;
  checked: Validation | null;
  onViewInGraph?: (change: { label: string; ids: string[] }) => void;
  onReset: () => void;
  /** Back to the form with the inputs kept, to change them and apply again. */
  onEdit?: () => void;
}) {
  return (
    <>
      <section
        ref={receiptRef}
        tabIndex={-1}
        aria-label="Receipt"
        className="outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <ReceiptView r={receipt} module={m.name} deleted={deletedOf(checked)} />
      </section>
      <div className="mt-3 flex flex-wrap gap-2">
        {onViewInGraph && (
          <Button
            variant="primary"
            onClick={() =>
              onViewInGraph({
                label: receipt.group ? `group ${receipt.group}` : shortName(info.name),
                ids: changedIds(m, checked?.effects ?? [], receipt),
              })
            }
          >
            View in graph
          </Button>
        )}
        <ReceiptExploreLink receipt={receipt} module={m.name} deleted={deletedOf(checked)} />
        {onEdit && <Button onClick={onEdit}>Edit and apply again</Button>}
        <Button onClick={onReset}>Run again</Button>
      </div>
    </>
  );
}

export function ConfirmBar({
  locked,
  validating,
  refused,
  fresh,
  canConfirm,
  stale,
  submitting,
  revision,
  onConfirm,
}: {
  locked: boolean;
  validating: boolean;
  refused: boolean;
  fresh: Validation | null;
  canConfirm: boolean;
  stale: boolean;
  submitting: boolean;
  revision: Revision;
  onConfirm: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
      <Button type="submit" disabled={locked || validating} data-testid="validate">
        Review changes
      </Button>
      {!refused && (
        <Button
          variant={fresh?.effects.some((e) => e.kind === "delete") ? "danger" : "primary"}
          disabled={!canConfirm || stale}
          onClick={onConfirm}
          data-testid="confirm"
        >
          {submitting ? "Applying…" : "Confirm and apply"}
        </Button>
      )}
      <span className="text-[12px] text-muted">
        Applies as you, once. Revision{" "}
        <span className="arras-mono">{JSON.stringify(revision)}</span>
      </span>
    </div>
  );
}
