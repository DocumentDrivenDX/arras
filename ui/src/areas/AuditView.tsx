// SPDX-License-Identifier: MIT OR Apache-2.0
import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import type { ArrasClient } from "../api/client";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import { useModule } from "../api/queries";
import type { ChangesQuery, ModuleInfo } from "../api/types";
import { Empty, ErrorPanel, Spinner } from "../components/ui";
import {
  type AuditForm,
  type AuditMode,
  buildQuery,
  FilterForm,
  ModeTabs,
  NoHistory,
  Pager,
  ProviderSelect,
} from "./AuditParts";
import { ChangesTable, HistoryChip, LoadsTable } from "./AuditTables";
import {
  type AuditAddress,
  addressOf,
  auditKey,
  formOf,
  modeOf,
  queryOf,
  type WriteAudit,
  withDates,
} from "./auditAddress";

export interface AuditViewProps {
  module: string;
  /** Open on one entity's history. */
  entity?: { type: string; key: string } | null;
  /** Open on the receipt of one change group. */
  group?: string;
  /** Open filtered to an action and to a time range (ISO 8601 instants). */
  action?: string;
  since?: string;
  until?: string;
  /** Open on the import loads. */
  loads?: boolean;
  /** Told each change of what the page is: a submitted form as a push, a date being typed as a replace. */
  onAddress?: WriteAudit;
  /** Told when the group the address names has no changes. */
  onEmptyGroup?: (group: string) => void;
}

const journalsOf = (m: ModuleInfo | undefined): string[] =>
  m ? [m.record, ...new Set(Object.values(m.providers).filter((p) => p !== m.record))] : [];

const chosenProvider = (chosen: string | null, journals: string[], m: ModuleInfo | undefined) =>
  chosen && journals.includes(chosen) && chosen !== m?.record ? chosen : undefined;

async function fetchAudit(
  client: ArrasClient,
  {
    name,
    provider,
    mode,
    applied,
    after,
  }: {
    name: string;
    provider: string | undefined;
    mode: AuditMode;
    applied: { q: ChangesQuery } | null;
    after: string | undefined;
  },
) {
  // Filters travel in the POST body, never the URL (CONTRACT-009).
  if (mode === "loads") {
    const loads = await client.loads({
      module: name,
      ...(provider ? { provider } : {}),
      limit: 50,
      after,
    });
    return { loads };
  }
  if (!applied) throw new Error("no filter applied");
  return { changes: await client.changes({ ...applied.q, limit: 50, after }) };
}

interface PagerState {
  page: number;
  setPage: (n: number) => void;
  cursors: (string | undefined)[];
  setCursors: (c: (string | undefined)[]) => void;
}

/** The answer to the filter in force: its state, the changes or loads, and the pager. */
function AuditResults({
  module: name,
  mode,
  asked,
  result,
  pager: { page, setPage, cursors, setCursors },
}: {
  module: string;
  mode: AuditMode;
  asked: boolean;
  result: UseQueryResult<Awaited<ReturnType<typeof fetchAudit>>>;
  pager: PagerState;
}) {
  const err = result.error;
  const unsupported = err instanceof ApiError && err.kind === "unsupported";
  const pg = result.data?.changes ?? result.data?.loads;
  return (
    <>
      {!asked && mode === "receipt" && <Empty title="Enter a group id to open a receipt" />}
      {asked && result.isPending && <Spinner />}
      {unsupported && <NoHistory module={name} />}
      {err && !unsupported && <ErrorPanel error={err} onRetry={() => void result.refetch()} />}

      {result.data?.changes && <ChangesTable module={name} rows={result.data.changes.items} />}
      {result.data?.loads && <LoadsTable loads={result.data.loads.items} />}

      {pg && (
        <Pager
          page={page}
          nextCursor={pg.nextCursor}
          asOf={pg.freshness?.asOf}
          onNewer={() => setPage(page - 1)}
          onOlder={() => {
            if (!pg.nextCursor) return;
            setCursors([...cursors.slice(0, page + 1), pg.nextCursor]);
            setPage(page + 1);
          }}
        />
      )}
    </>
  );
}

/** US-063: an entity's history, a module's changes by person, action and time, a receipt by group, and import loads. */
export function AuditView({
  module: name,
  entity,
  group,
  action,
  since,
  until,
  loads,
  onAddress,
  onEmptyGroup,
}: AuditViewProps) {
  const client = useClient();
  const { module: m } = useModule(name);
  const address: AuditAddress = {
    type: entity?.type,
    key: entity?.key,
    group,
    action,
    since,
    until,
    loads,
  };
  const addressKey = auditKey(address);
  const [mode, setMode] = useState<AuditMode>(() => modeOf(address));
  const [form, setForm] = useState<AuditForm>(() => formOf(address));
  const [applied, setApplied] = useState<{ q: ChangesQuery } | null>(() => ({
    q: queryOf(name, address),
  }));
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [keyError, setKeyError] = useState(false);
  const [page, setPage] = useState(0);
  // The address the page holds: what it started from or last wrote. A different one is a navigation
  // from outside (Back, a link) and is adopted; the one the page wrote comes back equal.
  const [held, setHeld] = useState(addressKey);
  const [seen, setSeen] = useState(addressKey);
  // The group came from the address, not from a form the person submitted.
  const [fromAddress, setFromAddress] = useState(true);
  if (seen !== addressKey) {
    setSeen(addressKey);
    if (addressKey !== held) {
      setHeld(addressKey);
      setMode(modeOf(address));
      setForm(formOf(address));
      setApplied({ q: queryOf(name, address) });
      setCursors([undefined]);
      setPage(0);
      setKeyError(false);
      setFromAddress(true);
    }
  }
  const write = (a: AuditAddress, replace: boolean) => {
    setHeld(auditKey(a));
    onAddress?.(a, { replace });
  };
  // One journal per provider (CONTRACT-001): the record store, then each backend that runs an action of the module.
  const record = m?.record ?? "";
  const journals = journalsOf(m);
  const [chosen, setChosen] = useState<string | null>(null);
  const provider = chosenProvider(chosen, journals, m);

  const restart = (next: { q: ChangesQuery } | null) => {
    setApplied(next);
    setCursors([undefined]);
    setPage(0);
  };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    setKeyError(false);
    const q = buildQuery(name, provider, mode, form);
    if (q === "needs_type") setKeyError(true);
    else if (q) {
      restart({ q });
      setFromAddress(false);
      write(addressOf(mode, q), false);
    }
  };

  const changeMode = (k: AuditMode) => {
    setMode(k);
    setFromAddress(false);
    const q = { module: name, ...(provider ? { provider } : {}) };
    restart(k === "receipt" ? null : { q });
    if (k !== "receipt") write(addressOf(k, q), false);
  };

  // A date being typed rewrites the current entry; the filter in force changes when the form is submitted.
  const typeDate = (next: AuditForm) => {
    setForm(next);
    write(withDates(addressOf(mode, applied?.q), next), true);
  };

  // The entity filter in force: History of one entity, shown as a chip that clears it.
  const history = mode === "changes" && applied?.q.type && applied.q.key ? applied.q : null;
  const clearHistory = () => {
    const { type: _t, key: _k, ...rest } = applied?.q ?? { module: name };
    setForm({ ...form, type: "", key: "" });
    restart({ q: rest });
    write(addressOf("changes", rest), false);
  };

  const changeProvider = (value: string) => {
    setChosen(value);
    // the filter in force follows the journal, from its first page
    restart(
      applied ? { q: { ...applied.q, provider: value === record ? undefined : value } } : applied,
    );
  };

  const after = cursors[page];
  const result = useQuery({
    queryKey: ["audit", name, provider ?? null, mode, applied, after],
    enabled: !!applied,
    retry: false,
    queryFn: () => fetchAudit(client, { name, provider, mode, applied, after }),
  });

  const emptyGroup =
    fromAddress && mode === "receipt" && result.data?.changes?.items.length === 0
      ? applied?.q.group
      : undefined;
  useEffect(() => {
    if (emptyGroup) onEmptyGroup?.(emptyGroup);
  }, [emptyGroup, onEmptyGroup]);

  return (
    <div className="p-3" data-testid="audit">
      <ModeTabs mode={mode} onMode={changeMode} />

      {history?.type && history.key && (
        <HistoryChip
          module={name}
          type={history.type}
          entityKey={history.key}
          onClear={clearHistory}
        />
      )}

      {journals.length > 1 && (
        <ProviderSelect
          journals={journals}
          value={provider ?? record}
          record={record}
          onChange={changeProvider}
        />
      )}

      {mode !== "loads" && (
        <FilterForm
          mode={mode}
          onSubmit={submit}
          form={form}
          setForm={setForm}
          onDate={typeDate}
          m={m}
          keyError={keyError}
        />
      )}

      <div className="mb-2 text-[12px] text-muted" data-testid="committed-only">
        The trail shows committed changes only: a refused attempt or a validate-only run is not
        recorded, and no input values are shown. Newest first.
      </div>

      <AuditResults
        module={name}
        mode={mode}
        asked={!!applied}
        result={result}
        pager={{ page, setPage, cursors, setCursors }}
      />
    </div>
  );
}
