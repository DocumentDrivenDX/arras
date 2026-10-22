// SPDX-License-Identifier: MIT OR Apache-2.0
// The headless form model of an action (SD-013 D2): values, built inputs, errors by field, validate,
// confirm, receipt, one idempotency key per input signature (cleared on a conflict), and the one
// revision-conflict rule (reload the module through `reloadModule`, rebuild, apply nothing). It reads
// no cache, route or console meta: a surface injects the module, the client, `onApplied` and
// `reloadModule`, and adapts what comes back. A refusal is returned, never decided.
import { useEffect, useMemo, useRef, useState } from "react";
import type { ApiError } from "../api/errors";
import type { Receipt, Revision, Validation } from "../api/types";
import { buildInputs, type FieldValue, newKey, violationsByField } from "../lib/inputs";
import { toApiError } from "./actionCore";
import type { ActionFormArgs, ActionFormModel, Checked } from "./types";

type ServerViolations = { sig: string; list: Validation["violations"] } | null;

const statusOf = (receipt: Receipt | null, stale: boolean): ActionFormModel["status"] => {
  if (receipt) return "applied";
  return stale ? "stale" : "preview";
};

export function useActionForm(args: ActionFormArgs): ActionFormModel {
  const { module: m, action, prefill, client } = args;
  const info = m?.actions.find((a) => a.name === action);
  const [builtRev, setBuiltRev] = useState<Revision | null>(null);
  const [values, setValues] = useState<Record<string, FieldValue>>(prefill ?? {});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [checked, setChecked] = useState<Checked | null>(null);
  const [validating, setValidating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [serverViolations, setServerViolations] = useState<ServerViolations>(null);
  const [failures, setFailures] = useState<{ id: string; reason: string }[]>([]);
  const [conflict, setConflict] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const seq = useRef(0);
  const sending = useRef(false);
  const keyRef = useRef<{ sig: string; key: string } | null>(null);

  // The form is built from the revision seen when it opened.
  useEffect(() => {
    if (m && builtRev === null) setBuiltRev(m.revision);
  }, [m, builtRev]);

  const specs = info?.inputSpecs ?? [];
  const built = useMemo(() => buildInputs(specs, values), [specs, values]);
  const sig = JSON.stringify(built.inputs);
  const hasClientErrors = Object.keys(built.errors).length > 0;
  const fresh = checked && checked.sig === sig ? checked.result : null;
  const stale = checked !== null && checked.sig !== sig;
  const refused = error?.kind === "no_access" || error?.kind === "not_offered" ? error : null;
  const refusal = args.refusal ?? refused;
  const locked = !!args.refusal || submitting || !!receipt;
  const revision: Revision = builtRev ?? m?.revision ?? {};
  const moduleName = m?.name ?? "";

  const violations = useMemo(
    () =>
      violationsByField([
        ...(fresh?.violations ?? []),
        ...(serverViolations?.sig === sig ? serverViolations.list : []),
      ]),
    [fresh, serverViolations, sig],
  );

  const noteError = (e: unknown): ApiError => {
    const err = toApiError(e);
    if (err.kind === "no_access" || err.kind === "not_offered") {
      args.onRefused?.(err);
    }
    return err;
  };

  const rebuild = async () => {
    // The registry changed: reload the module, rebuild the form from it and apply nothing.
    try {
      const next = await args.reloadModule();
      setBuiltRev(next ? next.revision : null);
    } catch (e) {
      setError(noteError(e));
    }
    setChecked(null);
    setServerViolations(null);
    setFailures([]);
    keyRef.current = null;
    setConflict(true);
    setEpoch((n) => n + 1);
  };

  const failWith = async (err: ApiError) => {
    if (err.kind === "revision_conflict") await rebuild();
    else setError(err);
  };

  const validate = async (): Promise<Validation | null> => {
    if (hasClientErrors) {
      setTouched(Object.fromEntries(specs.map((s) => [s.name, true])));
      return null;
    }
    if (checked?.sig === sig) return checked.result;
    const mine = ++seq.current;
    setValidating(true);
    setError(null);
    try {
      const result = await client.validate(moduleName, action, {
        inputs: built.inputs,
        expected_revision: revision,
      });
      if (mine !== seq.current) return null; // a newer validate superseded this one
      setChecked({ sig, result });
      setFailures(result.failures);
      return result;
    } catch (e) {
      if (mine !== seq.current) return null;
      await failWith(noteError(e));
      return null;
    } finally {
      if (mine === seq.current) setValidating(false);
    }
  };

  // Refused at invoke although validate passed (the data moved on): show why at its place and
  // ask for a fresh review before another confirmation. Nothing was applied.
  const refusedAtInvoke = (err: ApiError) => {
    if (err.kind === "invalid") setServerViolations({ sig, list: err.violations });
    else setFailures(err.failures);
    if (err.violations.length === 0 && err.failures.length === 0) setError(err);
    setChecked(null);
  };

  const invokeFailed = async (err: ApiError) => {
    if (err.kind === "invalid" || err.kind === "precondition") {
      refusedAtInvoke(err);
      return;
    }
    if (err.kind === "conflict") keyRef.current = null;
    await failWith(err);
  };

  const confirm = async () => {
    if (sending.current || !fresh?.ok) return; // one change per click: a double click is ignored
    sending.current = true;
    setSubmitting(true);
    setError(null);
    try {
      if (keyRef.current?.sig !== sig) keyRef.current = { sig, key: newKey() };
      const r = await client.invoke(moduleName, action, {
        inputs: built.inputs,
        idempotency_key: keyRef.current.key,
        expected_revision: revision,
      });
      setReceipt(r);
      args.onApplied(r);
    } catch (e) {
      await invokeFailed(noteError(e));
    } finally {
      sending.current = false;
      setSubmitting(false);
    }
  };

  const onBlur = (field: string) => {
    setTouched((t) => ({ ...t, [field]: true }));
    if (!locked) void validate();
  };

  const onChange = (field: string, v: string) => {
    setValues((x) => ({ ...x, [field]: v }));
    setServerViolations(null);
  };

  const reset = () => {
    setValues(prefill ?? {});
    setTouched({});
    setChecked(null);
    setReceipt(null);
    setError(null);
    setFailures([]);
    setServerViolations(null);
    setConflict(false);
    keyRef.current = null;
  };

  // Back to the form after an apply with the inputs kept: the next apply is a new change, so a new key.
  const editAgain = () => {
    setReceipt(null);
    setChecked(null);
    setError(null);
    setFailures([]);
    setServerViolations(null);
    keyRef.current = null;
  };

  return {
    info,
    specs,
    revision,
    values,
    touched,
    built,
    violations,
    failures,
    checked,
    fresh,
    stale,
    validating,
    submitting,
    receipt,
    error,
    refusal,
    conflict,
    epoch,
    locked,
    canConfirm: !!fresh?.ok && !hasClientErrors && !locked && !validating,
    effects: checked?.result.effects ?? [],
    status: statusOf(receipt, stale),
    valid: !!checked?.result.ok,
    validate,
    confirm,
    onChange,
    onBlur,
    reset,
    editAgain,
  };
}
