# SPDX-License-Identifier: MIT OR Apache-2.0
"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_dev_truss_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The dev host reads a persistent server's URL from the environment and from
    `~/.arras/truss-dev.env`: a developer's own, which no test may attach to. Every test sees
    neither, so a test of `main(["--truss"])` is the throwaway unless it sets one."""
    from arras import devhost

    monkeypatch.delenv(devhost.TRUSS_URL_VARIABLE, raising=False)
    nowhere: Path = tmp_path_factory.getbasetemp() / "no-truss-dev.env"
    monkeypatch.setattr(devhost, "TRUSS_URL_FILE", nowhere)
