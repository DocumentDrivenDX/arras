"""Build the exact pip command for an isolated, hash-verified cohort install."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


def command(
    python: Path,
    arras_wheel: Path,
    cohort: dict[str, Any],
    wheel_paths: dict[str, Path],
    report_path: Path,
    *,
    public_index: str,
    canonical_name: Callable[[str], str],
) -> list[str]:
    toolkit = next(
        wheel
        for wheel in cohort["native_wheels"]
        if canonical_name(wheel["distribution"]) == "truss-toolkit"
    )
    toolkit_url = wheel_paths[toolkit["filename"]].resolve().as_uri()
    requirements = [str(arras_wheel), f"truss-toolkit[native,query,local] @ {toolkit_url}"]
    requirements.extend(
        str(wheel_paths[wheel["filename"]])
        for wheel in cohort["native_wheels"]
        if wheel is not toolkit
    )
    return [
        str(python),
        "-m",
        "pip",
        "install",
        "--isolated",
        "--no-cache-dir",
        "--disable-pip-version-check",
        "--only-binary=:all:",
        "--index-url",
        public_index,
        "--report",
        str(report_path),
        *requirements,
    ]
