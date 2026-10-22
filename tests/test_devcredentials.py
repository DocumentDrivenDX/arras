# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic

from __future__ import annotations

import json
import multiprocessing
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from arras.devcredentials import FileCredentialSource


def _create_in_process(path: Path, role: str, results: Any) -> None:
    results.put((role, FileCredentialSource(path)(role, create=True)))


def test_file_source_creates_stable_owner_only_credentials(tmp_path: Path) -> None:
    source = FileCredentialSource(tmp_path / "credentials.json")
    token = source("arrasdev_alice", create=True)

    assert token == source("arrasdev_alice", create=False)
    assert stat.S_IMODE(source.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(source.lock_path.stat().st_mode) == 0o600
    assert source.path.stat().st_uid == os.geteuid()
    assert json.loads(source.path.read_text()) == {
        "version": 1,
        "credentials": {"arrasdev_alice": token},
    }


def test_lookup_of_missing_credential_does_not_create_store_or_parent(tmp_path: Path) -> None:
    path = tmp_path / "not-created" / "credentials.json"
    source = FileCredentialSource(path)

    with pytest.raises(ValueError, match="missing"):
        source("arrasdev_alice", create=False)

    assert not path.parent.exists() and not source.lock_path.exists()


def test_unsafe_or_malformed_store_is_refused_without_replacement(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    source = FileCredentialSource(path)
    path.write_text('{"version":1,"credentials":{"arrasdev_alice":"one","arrasdev_alice":"two"}}')
    path.chmod(0o600)
    original = path.read_bytes()

    with pytest.raises(ValueError, match="unsafe, malformed"):
        source("arrasdev_bob", create=True)

    assert path.read_bytes() == original


def test_credential_store_symlink_is_refused_without_following_it(tmp_path: Path) -> None:
    secret_target = tmp_path / "target.json"
    secret_target.write_text("{}")
    secret_target.chmod(0o600)
    path = tmp_path / "credentials.json"
    path.symlink_to(secret_target)

    with pytest.raises(ValueError, match="unsafe"):
        FileCredentialSource(path)("arrasdev_alice", create=True)

    assert secret_target.read_text() == "{}"


def test_concurrent_creation_keeps_one_token_per_role(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"

    def get_token(_: int) -> str:
        return FileCredentialSource(path)("arrasdev_alice", create=True)

    with ThreadPoolExecutor(8) as pool:
        tokens = list(pool.map(get_token, range(24)))

    assert len(set(tokens)) == 1
    assert json.loads(path.read_text()) == {
        "version": 1,
        "credentials": {"arrasdev_alice": tokens[0]},
    }


def test_cross_process_creation_keeps_all_roles_and_one_token_per_role(
    tmp_path: Path,
) -> None:
    path = tmp_path / "credentials.json"
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    requests = [
        ("arrasdev_alice", 2),
        ("arrasdev_bob", 2),
    ]
    processes = [
        context.Process(target=_create_in_process, args=(path, role, results))
        for role, count in requests
        for _ in range(count)
    ]
    for process in processes:
        process.start()
    created = [results.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        assert process.exitcode == 0

    alice_tokens = [token for role, token in created if role == "arrasdev_alice"]
    bob_tokens = [token for role, token in created if role == "arrasdev_bob"]
    assert len(set(alice_tokens)) == len(set(bob_tokens)) == 1
    stored = json.loads(path.read_text())
    assert set(stored["credentials"]) == {"arrasdev_alice", "arrasdev_bob"}
    assert stored["credentials"]["arrasdev_alice"] == alice_tokens[0]
    assert stored["credentials"]["arrasdev_bob"] == bob_tokens[0]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_unknown_store_version_is_refused_without_replacement(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text('{"version":2,"credentials":{}}')
    path.chmod(0o600)
    original = path.read_bytes()

    with pytest.raises(ValueError, match="unsafe, malformed"):
        FileCredentialSource(path)("arrasdev_alice", create=True)

    assert path.read_bytes() == original
