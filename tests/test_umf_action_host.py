# SPDX-License-Identifier: MIT OR Apache-2.0
"""Public Arras path driven by the unchanged official generated action client."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, cast

import pytest

from arras.fakes import MemoryStore
from arras.testing import InMemory

_FIXTURE = Path(__file__).parent / "fixtures" / "umf-actions-binding"
_REQUIRED = os.environ.get("ARRAS_REQUIRE_UMF_ACTIONS") == "1"


def _memory_store(world: InMemory) -> MemoryStore:
    return cast(MemoryStore, cast(Any, world)._store)


def _candidate_symbols() -> tuple[Any, Any]:
    try:
        runtime = importlib.import_module("umf.action_runtime")
        importlib.import_module("umf.rust_codegen")
    except ModuleNotFoundError as exc:
        if _REQUIRED:
            pytest.fail(f"required candidate UMF action runtime is unavailable: {exc.name}")
        pytest.skip("candidate UMF action runtime is not installed")
    factory = getattr(runtime, "create_action_engine", None)
    if not callable(factory):
        if _REQUIRED:
            pytest.fail("candidate UMF action runtime has no packaged engine factory")
        pytest.skip("candidate UMF action runtime has no packaged engine factory")
    engine = factory()
    if not callable(getattr(engine, "generate_python_client", None)):
        if _REQUIRED:
            pytest.fail("candidate engine cannot generate the official Python client")
        pytest.skip("candidate engine cannot generate the official Python client")
    return runtime, engine


def _generate_client(engine: Any, source: bytes, package_root: Path) -> None:
    generated_raw: object = engine.generate_python_client(
        {"text": source.decode("utf-8", errors="strict"), "package": "actions_binding"}
    )
    generated = cast(dict[str, object], generated_raw) if type(generated_raw) is dict else {}
    files_raw: object = generated.get("files")
    files = cast(list[object], files_raw) if type(files_raw) is list else []
    if type(files) is not list or not files:
        pytest.fail("official client generator returned no package files")
    for item in files:
        if type(item) is not dict:
            pytest.fail("official client generator returned an invalid file entry")
        entry = cast(dict[str, object], item)
        path: object = entry.get("path")
        text: object = entry.get("text")
        if type(path) is not str or type(text) is not str:
            pytest.fail("official client generator returned an invalid file entry")
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            pytest.fail("official client generator returned an unsafe package path")
        destination = package_root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")


class _CaptureTransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def execute(self, request: Mapping[str, object]) -> Mapping[str, object]:
        snapshot = dict(request)
        self.requests.append(snapshot)
        if snapshot.get("kind") == "validate":
            return {"schema": snapshot["schema"], "valid": True}
        return {
            "schema": snapshot["schema"],
            "status": "committed",
            "created": [],
            "changed": [],
            "counts": {"created": 0, "updated": 0, "deleted": 0, "linked": 0, "unlinked": 0},
            "consistency_token": "capture-token",
        }


class _AfterPublishTransport:
    def __init__(self, target: Any, *, malformed: bool) -> None:
        self.target = target
        self.malformed = malformed
        self.calls = 0

    def execute(self, request: Mapping[str, object]) -> Mapping[str, object]:
        self.calls += 1
        self.target.execute(request)
        if self.malformed:
            return {"schema": "0" * 64}
        raise RuntimeError("simulated response loss after publication")


def _consistency_token(response: object) -> str:
    token: object = None
    if isinstance(response, Mapping):
        token = cast(Mapping[str, object], response).get("consistency_token")
    if token is None:
        token = getattr(cast(Any, response), "consistency_token", None)
    if type(token) is not str or not token:
        pytest.fail("generated client response omitted its consistency token")
    return token


def _remove_generated_client(package_path: Path) -> None:
    if str(package_path) in sys.path:
        sys.path.remove(str(package_path))
    for name in tuple(sys.modules):
        if name == "actions_binding" or name.startswith("actions_binding."):
            sys.modules.pop(name, None)


def _exercise_uncertain_responses(
    sync_actions: Any,
    sync_client: Any,
    item: Any,
    writer: Any,
    reader_session: Any,
    store: MemoryStore,
    write_outcome_unknown: Any,
) -> None:
    lost = _AfterPublishTransport(writer, malformed=False)
    lost_actions = sync_actions(sync_client(lost))
    sequence_before_loss = store.state.seq
    with pytest.raises(write_outcome_unknown):
        lost_actions.set_label(item=item, label_value="ready", idempotency_key="lost-response")
    assert lost.calls == 1
    assert store.state.seq == sequence_before_loss + 1
    rows_after_loss = reader_session.query(
        "catalog", "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10"
    ).rows
    assert len(rows_after_loss) == 1 and rows_after_loss[0]["label"] == "ready"

    malformed = _AfterPublishTransport(writer, malformed=True)
    malformed_actions = sync_actions(sync_client(malformed))
    sequence_before_malformed = store.state.seq
    with pytest.raises(write_outcome_unknown):
        malformed_actions.set_label(
            item=item, label_value="abcdefgh", idempotency_key="malformed-response"
        )
    assert malformed.calls == 1
    assert store.state.seq == sequence_before_malformed + 1
    rows_after_malformed = reader_session.query(
        "catalog", "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10"
    ).rows
    assert len(rows_after_malformed) == 1 and rows_after_malformed[0]["label"] == "abcdefgh"


def _exercise_public_world(
    sync_actions: Any,
    sync_client: Any,
    item_key: Any,
    vectors: dict[str, Any],
    digest: str,
    access_error: Any,
    write_outcome_unknown: Any,
) -> None:
    world = InMemory(action_profile="arras-umf-set/1")
    world.register((_FIXTURE / "source.json").read_bytes())
    imported = world.import_records(
        "catalog",
        [{"type": "item", "key": "item-1", "properties": {"label": "held"}}],
        load_id="candidate-action-seed",
    )
    assert imported.created == 1 and imported.skipped == 0 and not imported.rejected

    writer = world.person("writer", "catalog", "read", "write")
    reader = world.person("reader", "catalog", "read")
    store = _memory_store(world)
    reader_session = world.arras.session(reader)
    actions = sync_actions(sync_client(world.arras.session(writer)))
    key = item_key(item_id="item-1")
    rows_before_validate = reader_session.query(
        "catalog", "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10"
    ).rows
    state_before_validate = store.state
    actions.set_label_validate(item=key, label_value="ready")
    assert store.state is state_before_validate
    assert (
        reader_session.query(
            "catalog", "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10"
        ).rows
        == rows_before_validate
    )

    _exercise_uncertain_responses(
        sync_actions,
        sync_client,
        key,
        world.arras.session(writer),
        reader_session,
        store,
        write_outcome_unknown,
    )

    applied = actions.set_label(item=key, label_value="ready", idempotency_key="host-apply")
    token = _consistency_token(applied)
    first_seq = _memory_store(world).state.seq
    rows = world.arras.session(reader).query(
        "catalog",
        "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10",
        at_least=token,
    )
    assert len(rows.rows) == 1 and rows.rows[0]["label"] == "ready"

    noop = actions.set_label(item=key, label_value="ready", idempotency_key="host-noop")
    noop_token = _consistency_token(noop)
    assert _memory_store(world).state.seq == first_seq
    repeated = actions.set_label(item=key, label_value="ready", idempotency_key="host-noop")
    assert _consistency_token(repeated) == noop_token
    assert _memory_store(world).state.seq == first_seq
    noop_rows = world.arras.session(reader).query(
        "catalog",
        "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10",
        at_least=noop_token,
    )
    assert noop_rows.rows[0]["label"] == "ready"

    world.expire(writer)
    with pytest.raises(access_error) as refused:
        actions.set_label(item=key, label_value="ready", idempotency_key="expired-writer")
    assert refused.value.code == "DENIED"
    assert not isinstance(refused.value, write_outcome_unknown)
    assert _memory_store(world).state.seq == first_seq
    assert world.arras.session(writer).execute(vectors["generatedRequests"]["apply"]) == {
        "schema": digest,
        "error": {"code": "DENIED"},
    }


def test_official_generated_client_runs_the_public_inmemory_path(
    tmp_path: Path,
) -> None:
    source = (_FIXTURE / "source.json").read_bytes()
    vectors = json.loads((_FIXTURE / "vectors.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(source).hexdigest()
    assert digest == vectors["source"]["sha256"]

    _, engine = _candidate_symbols()
    _generate_client(engine, source, tmp_path)
    sys.path.insert(0, str(tmp_path))
    try:
        generated = importlib.import_module("actions_binding")
        item_key = generated.ItemKey
        sync_actions = generated.SyncActions
        sync_client = generated.SyncClient
        access_error = generated.AccessError
        write_outcome_unknown = generated.WriteOutcomeUnknown
    except (ImportError, AttributeError) as exc:
        _remove_generated_client(tmp_path)
        if _REQUIRED:
            pytest.fail(f"required generated client package is incomplete: {type(exc).__name__}")
        pytest.skip("candidate generator did not produce its synchronous client")

    try:
        capture = _CaptureTransport()
        generated_actions = sync_actions(sync_client(capture))
        item = item_key(item_id="item-1")
        generated_actions.set_label(item=item, label_value="ready", idempotency_key="fixture-key")
        generated_actions.set_label_validate(item=item, label_value="ready")
        assert capture.requests == [
            vectors["generatedRequests"]["apply"],
            vectors["generatedRequests"]["validate"],
        ]
        _exercise_public_world(
            sync_actions,
            sync_client,
            item_key,
            vectors,
            digest,
            access_error,
            write_outcome_unknown,
        )
    finally:
        _remove_generated_client(tmp_path)
