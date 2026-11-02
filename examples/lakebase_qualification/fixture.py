# SPDX-License-Identifier: MIT OR Apache-2.0
"""Inert placeholder for a separately authorized owner-supplied fixture."""


def _unavailable() -> None:
    raise RuntimeError("owner-authorized Lakebase fixture has not been supplied")


def build_sources(_target: object) -> object:
    _unavailable()


def observe_provider() -> object:
    _unavailable()


def observe_native() -> object:
    _unavailable()


def cleanup_owned() -> object:
    _unavailable()
