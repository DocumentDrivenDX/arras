# SPDX-License-Identifier: MIT OR Apache-2.0
"""The explicitly opted-in memory provider's source-bound generated SET path."""

from __future__ import annotations

import copy
import hashlib
import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any, Literal, cast

from arras._action_types import AdmittedSet, PreparedSetModule
from arras.actions import KEY_VALUE, Plan, Ref, Update
from arras.errors import Conflict, Invalid, Refused, Unsupported, Violation
from arras.fakes_state import Entity, State
from arras.model import ModuleInfo
from arras.results import ImportResult, Load, Receipt, Rejection, Validation
from arras.types import Principal

_PROFILE = "arras-umf-set/1"
_TOKEN_PREFIX = "arras-set-"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class DeclaredActions:
    """Methods mixed into MemoryStore; semantic admission stays in the official UMF bridge."""

    name: str
    action_profile: str | None
    action_source_owners: dict[str, str]
    access: Any
    clock: Callable[[], datetime]
    state: State
    modules: dict[str, ModuleInfo]
    documents: dict[str, bytes]
    _action_lock: Any

    def gate(
        self,
        principal: Principal,
        module: str | None,
        mode: Literal["read", "write", "journal", "schema"] | None,
        op: str,
    ) -> None: ...

    def _apply_group(
        self, work: State, principal: Principal, plans: Sequence[Plan], mod: ModuleInfo
    ) -> list[Receipt]: ...

    def _import_entity(
        self,
        work: State,
        mod: ModuleInfo,
        r: Mapping[str, object],
        load_id: str,
        by: str,
        now: datetime,
        found: Any = None,
    ) -> tuple[int, int, list[Rejection]]: ...

    def _prepared(self, module_name: str) -> PreparedSetModule:
        source = self.documents.get(module_name)
        if source is None:
            raise Unsupported("declared action source", ["register the official source first"])
        try:
            from arras._umf_actions import prepare
        except ModuleNotFoundError as exc:
            if exc.name == "arras._umf_actions":
                raise Unsupported(
                    "official UMF action runtime", ["install the optional engine"]
                ) from None
            raise
        prepared = prepare(source)
        digest = hashlib.sha256(source).hexdigest()
        if prepared.source != source or prepared.sha256 != digest:
            raise Unsupported("declared action source", ["the prepared source is not current"])
        if prepared.module.metadata_profile != _PROFILE:
            raise Unsupported("declared action source", [_PROFILE])
        held = self.modules.get(module_name)
        if held is None or held.metadata_profile != _PROFILE:
            raise Unsupported("declared action module", ["the current module is not registered"])
        if held.actions != prepared.module.actions or held.name != prepared.module.name:
            raise Unsupported("declared action module", ["the current module differs from source"])
        return prepared

    def apply_declared_action(
        self, principal: Principal, module_name: str, raw_request: Mapping[str, object]
    ) -> Receipt | Validation:
        """Re-admit the exact request and publish SET state+replay+position in one pointer swap."""
        with self._action_lock:
            self.gate(principal, module_name, "write", "execute")
            self.gate(principal, module_name, "read", "execute")
            if self.action_profile != _PROFILE:
                raise Unsupported("declared action provider", [_PROFILE])
            if self.action_source_owners.get(module_name) is None:
                raise Refused(self.name, "execute")
            prepared = self._prepared(module_name)
            from arras._action_transport import request_kind

            kind, action_id, _ = request_kind(raw_request)
            if action_id != prepared.action_id:
                raise Invalid([Violation("action", "unknown_action", "not the registered action")])
            action_runtime = _action_runtime()
            admitted = action_runtime.materialize(prepared, raw_request)
            if not isinstance(admitted, AdmittedSet):
                raise TypeError("the official action bridge returned an invalid SET admission")
            self._check_admitted_set(prepared, admitted)
            state_entity = self._entity_for_admitted(prepared, admitted.ref)
            current_values = self._complete_values(prepared, state_entity.props)
            new_values = dict(current_values)
            for binding in prepared.bindings:
                new_values[binding.field_id] = admitted.set_values[binding.field_id]
            action_runtime.validate_candidate(prepared, new_values)
            if kind == "validate":
                if admitted.ref not in self.state.entities:
                    raise Invalid([Violation("entity", "not_found", "the target does not exist")])
                return Validation(True, (), (), (), None, None)
            request_key = raw_request.get("idempotency_key")
            if request_key is not None and (type(request_key) is not str or not request_key):
                raise Invalid([Violation("idempotency_key", "type", "a nonempty string or null")])
            return self._commit_declared_set(
                principal, prepared, admitted, state_entity, request_key
            )

    def import_declared_records(
        self,
        principal: Principal,
        module_name: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
        initiated_by: str,
    ) -> ImportResult:
        """Import only records admitted against the current official source, atomically."""
        from arras._umf_actions import admit_record

        with self._action_lock:
            self.gate(principal, module_name, "write", "import_records")
            if principal.user not in self.access.admins:
                raise Refused(self.name, "import_records")
            if initiated_by != principal.user:
                raise Invalid(
                    [Violation("initiated_by", "attribution", "a load is the caller's own")]
                )
            if type(records) not in (list, tuple) or len(records) != 1:
                raise Unsupported("declared action import", ["one exact seed record is supported"])
            prepared = self._prepared(module_name)
            if any("type" not in row for row in records):
                raise Unsupported("declared action import", ["relationship rows are not supported"])

            admitted_rows: list[Mapping[str, object]] = []
            for row in records:
                admitted = admit_record(prepared, row)
                expected_type = prepared.module.entity_types[0].name
                expected_properties = {
                    prepared.key_property,
                    *(item.property for item in prepared.bindings),
                }
                if (
                    admitted.ref.type != expected_type
                    or type(admitted.ref.key) is not str
                    or not KEY_VALUE.fullmatch(admitted.ref.key)
                    or set(admitted.properties) != expected_properties
                    or any(type(value) is not str for value in admitted.properties.values())
                ):
                    raise Unsupported("declared action import", ["one admitted string record"])
                normalized: dict[str, object] = {
                    "type": prepared.record_id,
                    "key": admitted.ref.key,
                    "properties": dict(admitted.properties),
                }
                admitted_rows.append(normalized)

            # Admission and current source/grant checks are complete before consulting the clock.
            now = self.clock()
            work = copy.deepcopy(self.state)
            created = skipped = 0
            for row in admitted_rows:
                made, existing, refusals = self._import_entity(
                    work, prepared.module, row, load_id, initiated_by, now
                )
                created += made
                skipped += existing
                if refusals:
                    raise Invalid(
                        [Violation("record", "admission", "the admitted record was rejected")]
                    )
            work.loads.append(Load(load_id, initiated_by, now, module_name, created, skipped, 0))
            if created:
                work.seq += 1
                work.at = now
            self.state = work
            return ImportResult(created, skipped, ())

    def _check_admitted_set(self, prepared: PreparedSetModule, admitted: AdmittedSet) -> None:
        types = prepared.module.entity_types
        if len(types) != 1 or admitted.ref.type != types[0].name:
            raise Unsupported("declared SET target", ["one registered record type"])
        if type(admitted.ref.key) is not str or not KEY_VALUE.fullmatch(admitted.ref.key):
            raise Unsupported("declared SET key", ["one nonempty string key component"])
        if len(prepared.bindings) != 1 or set(admitted.set_values) != {
            prepared.bindings[0].field_id
        }:
            raise Unsupported("declared SET values", ["one source-bound string field"])
        if type(admitted.inputs_digest) is not str or not _SHA256.fullmatch(admitted.inputs_digest):
            raise Unsupported("declared SET digest", ["an official SHA-256 digest"])

    def _entity_for_admitted(self, prepared: PreparedSetModule, ref: Ref) -> Entity:
        entity = self.state.entities.get(ref)
        if entity is None:
            if ref in self.state.tombstones:
                raise Conflict("deleted", str(ref))
            raise Invalid([Violation("entity", "not_found", "the target does not exist")])
        type_info = prepared.module.entity_types[0]
        allowed = {prepared.key_property, *(item.property for item in prepared.bindings)}
        if (
            type_info.key != prepared.key_property
            or {item.name for item in type_info.properties} != allowed
            or set(entity.props) != allowed
            or entity.props.get(prepared.key_property) != ref.key
        ):
            raise Unsupported("declared SET record", ["the one-key, one-string-field profile"])
        return entity

    @staticmethod
    def _complete_values(
        prepared: PreparedSetModule, properties: Mapping[str, object]
    ) -> dict[str, object]:
        values: dict[str, object] = {prepared.key_field_id: properties[prepared.key_property]}
        for binding in prepared.bindings:
            values[binding.field_id] = properties[binding.property]
        return values

    def _commit_declared_set(
        self,
        principal: Principal,
        prepared: PreparedSetModule,
        admitted: AdmittedSet,
        entity: Entity,
        request_key: str | None,
    ) -> Receipt:
        replay_identity = (
            _PROFILE,
            prepared.module_id,
            prepared.source_revision,
            principal.user,
            request_key or "",
        )
        held = self.state.declared_replays.get(replay_identity) if request_key else None
        if held is not None:
            if held[0] != admitted.inputs_digest:
                raise Conflict("idempotency_key_reused", "the key was used with other inputs")
            return replace(cast(Receipt, held[1]), replayed=True)

        binding = prepared.bindings[0]
        new_value = admitted.set_values[binding.field_id]
        existing_value = entity.props.get(binding.property)
        work: State = copy.deepcopy(self.state)
        if existing_value == new_value:
            receipt = Receipt(
                prepared.action_id,
                (),
                0,
                0,
                0,
                0,
                0,
                self._new_declared_token(work),
            )
        else:
            ref = admitted.ref
            plan = Plan(
                prepared.action_id,
                (),
                (Update(ref, {binding.property: new_value}),),
                inputs_digest=admitted.inputs_digest,
            )
            receipt = self._apply_group(work, principal, (plan,), prepared.module)[0]
            receipt = replace(receipt, token=self._new_declared_token(work))
        work.declared_tokens[receipt.token] = (
            prepared.module_id,
            prepared.source_revision,
            work.seq,
        )
        if request_key:
            work.declared_replays[replay_identity] = (admitted.inputs_digest, receipt)
        self.state = work
        return receipt

    @staticmethod
    def _new_declared_token(state: Any) -> str:
        token = _TOKEN_PREFIX + secrets.token_urlsafe(24)
        while token in state.declared_tokens:
            token = _TOKEN_PREFIX + secrets.token_urlsafe(24)
        return token

    def reached_declared(self, principal: Principal, token: str) -> bool:
        """Resolve issued canonical tokens only after current module read authorization."""
        with self._action_lock:
            self.gate(principal, None, None, "reached")
            current = [
                name for name, module in self.modules.items() if module.metadata_profile == _PROFILE
            ]
            if len(current) > 1:
                raise Unsupported("declared action store", ["one canonical module"])
            if current:
                module = current[0]
                self.gate(principal, module, "read", "reached")
            else:
                return False
            if type(token) is not str or not token.startswith(_TOKEN_PREFIX):
                return False
            scope = self.state.declared_tokens.get(token)
            if scope is None:
                return False
            token_module, source_revision, sequence = scope
            if token_module != module:
                return False
            raw = self.documents.get(module)
            if raw is None or source_revision != _source_revision(raw):
                return False
            return self.state.seq >= sequence


def _action_runtime() -> Any:
    try:
        from arras import _umf_actions
    except ModuleNotFoundError as exc:
        if exc.name != "arras._umf_actions":
            raise
        raise Unsupported("official UMF action runtime", ["install the optional engine"]) from None
    return _umf_actions


def _source_revision(source: bytes) -> str:
    return f"sha256:{hashlib.sha256(source).hexdigest()}"
