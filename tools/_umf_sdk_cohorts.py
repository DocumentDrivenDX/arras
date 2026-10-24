# SPDX-License-Identifier: MIT OR Apache-2.0
"""Closed selector for verified UMF SDK release cohorts."""

from __future__ import annotations

import email.message
import re
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DIRECT = re.compile(r"^umf-core\s*@\s*(https://[^;\s]+)\s*;\s*(.+)$", re.IGNORECASE)
_ATOM = re.compile(r"^\s*(extra|sys_platform|platform_machine)\s*==\s*(['\"])([a-z0-9_.-]+)\2\s*$")
_PLATFORMS = frozenset({"linux", "darwin"})
_MACHINES = frozenset({"x86_64", "arm64"})


@dataclass(frozen=True, slots=True)
class SDKCohort:
    """One immutable published SDK artifact and its exact extra marker."""

    cohort_id: str
    distribution_version: str
    document_version: str
    platform: str
    machine: str
    filename: str
    url: str
    sha256: str
    supports_single_set: bool = False


@dataclass(frozen=True, slots=True)
class _Declaration:
    url: str
    sha256: str
    platform: str
    machine: str
    universal: bool


# The historical pure wheel is retained as a closed record. Platform-specific records are
# added only after their published bytes have been independently verified.
KNOWN_COHORTS: tuple[SDKCohort, ...] = (
    SDKCohort(
        "umf-core-0.10.0-py3-none-any",
        "0.10.0",
        "0.10.0",
        "any",
        "any",
        "umf_core-0.10.0-py3-none-any.whl",
        "https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.4/"
        "umf_core-0.10.0-py3-none-any.whl",
        "49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9",
    ),
    SDKCohort(
        "umf-core-0.10.1-cp311-abi3-linux_x86_64",
        "0.10.1",
        "0.10.0",
        "linux",
        "x86_64",
        "umf_core-0.10.1-cp311-abi3-linux_x86_64.whl",
        "https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.6/"
        "umf_core-0.10.1-cp311-abi3-linux_x86_64.whl",
        "3512e56730d1dab59d803b20301aea3ac8f6896b0dab452f767f4c3575b9ff4c",
        supports_single_set=True,
    ),
    SDKCohort(
        "umf-core-0.10.1-cp311-abi3-macosx_11_0_arm64",
        "0.10.1",
        "0.10.0",
        "darwin",
        "arm64",
        "umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
        "https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.6/"
        "umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
        "49459bb2dbc37ac9b62b269e9664bac1483439c7d4c79f0b07855e9c8546c823",
        supports_single_set=True,
    ),
)


def _parse_marker_atoms(expression: str, expected: frozenset[str]) -> dict[str, str]:
    atoms = re.split(r"\s+and\s+", expression, flags=re.IGNORECASE)
    if len(atoms) != len(expected):
        raise ValueError("UMF SDK platform marker is incomplete")
    markers: dict[str, str] = {}
    for atom in atoms:
        atom_match = _ATOM.fullmatch(atom)
        if atom_match is None:
            raise ValueError("UMF SDK marker atom is not supported")
        key, _quote, value = atom_match.groups()
        if key not in expected or key in markers:
            raise ValueError("UMF SDK marker is duplicated or unsupported")
        markers[key] = value
    if frozenset(markers) != expected:
        raise ValueError("UMF SDK platform marker is incomplete")
    return markers


def _marker_scope(marker_text: str) -> tuple[str, str, bool]:
    """Accept the prior flat form and Hatchling's exact grouped serialization."""
    if marker_text in ("extra == 'umf'", 'extra == "umf"'):
        return "any", "any", True
    grouped = re.fullmatch(
        r"""\(\s*(.*?)\s*\)\s+and\s+(extra\s*==\s*(['"])umf\3)""",
        marker_text,
    )
    if grouped is not None:
        extra_match = _ATOM.fullmatch(grouped.group(2))
        if extra_match is None or extra_match.group(1) != "extra" or extra_match.group(3) != "umf":
            raise ValueError("UMF SDK declaration is outside the public extra")
        markers = _parse_marker_atoms(
            grouped.group(1), frozenset({"sys_platform", "platform_machine"})
        )
    else:
        markers = _parse_marker_atoms(
            marker_text, frozenset({"extra", "sys_platform", "platform_machine"})
        )
        if markers["extra"] != "umf":
            raise ValueError("UMF SDK declaration is outside the public extra")
    return markers["sys_platform"], markers["platform_machine"], False


def _declarations(metadata: email.message.Message) -> tuple[_Declaration, ...]:
    lines = metadata.get_all("Requires-Dist", [])
    relevant: list[str] = []
    for line in lines:
        name = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if name is not None and re.sub(r"[-_.]+", "-", name.group(1)).lower() == "umf-core":
            relevant.append(line.strip())
    if not relevant:
        raise ValueError("UMF extra has no SDK declaration")
    parsed: list[_Declaration] = []
    for line in relevant:
        match = _DIRECT.fullmatch(line)
        if match is None:
            raise ValueError("UMF SDK declaration is not a closed direct reference")
        url, marker_text = match.groups()
        parts = urllib.parse.urlsplit(url)
        fragment = parts.fragment
        if (
            parts.scheme != "https"
            or parts.hostname != "github.com"
            or parts.username is not None
            or parts.password is not None
            or parts.port is not None
            or parts.query
            or not fragment.startswith("sha256=")
            or not _SHA.fullmatch(fragment.removeprefix("sha256="))
        ):
            raise ValueError("UMF SDK direct reference is not allowlisted")
        url_without_fragment = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "", "")
        )
        platform, machine, universal = _marker_scope(marker_text)
        if not universal and (platform not in _PLATFORMS or machine not in _MACHINES):
            raise ValueError("UMF SDK platform marker is unsupported")
        filename = PurePosixPath(parts.path).name
        if not filename.startswith("umf_core-") or not filename.endswith(".whl"):
            raise ValueError("UMF SDK wheel filename is invalid")
        parsed.append(
            _Declaration(
                url_without_fragment, fragment.removeprefix("sha256="), platform, machine, universal
            )
        )
    if len({(row.url, row.sha256, row.platform, row.machine) for row in parsed}) != len(parsed):
        raise ValueError("UMF SDK declaration is duplicated")
    return tuple(parsed)


def _matches(row: _Declaration, platform: str, machine: str) -> bool:
    return row.universal or (row.platform == platform and row.machine == machine)


def single_set_capability(
    metadata: email.message.Message, registry: Sequence[SDKCohort] = KNOWN_COHORTS
) -> bool:
    """Return the wheel's action capability only when every pin is known and agrees."""
    declarations = _declarations(metadata)
    capabilities: list[bool] = []
    for declaration in declarations:
        matches = [
            row
            for row in registry
            if (row.url, row.sha256, row.platform, row.machine, row.platform == "any")
            == (
                declaration.url,
                declaration.sha256,
                declaration.platform,
                declaration.machine,
                declaration.universal,
            )
        ]
        if len(matches) != 1:
            raise ValueError("UMF SDK declaration is not a unique verified cohort")
        capabilities.append(matches[0].supports_single_set)
    if len(set(capabilities)) != 1:
        raise ValueError("UMF SDK declarations disagree on action capability")
    return capabilities[0]


def select_sdk_cohort(
    metadata: email.message.Message,
    *,
    platform: str,
    machine: str,
    registry: Sequence[SDKCohort] = KNOWN_COHORTS,
) -> SDKCohort:
    """Validate every declared pin, reject overlap, and select exactly one host artifact."""
    platform = platform.lower()
    machine = machine.lower()
    if platform not in _PLATFORMS or machine not in _MACHINES:
        raise ValueError("host platform is unsupported")
    declarations = _declarations(metadata)
    if len(registry) == 0:
        raise ValueError("SDK cohort registry is empty")
    known = {
        (row.url, row.sha256, row.platform, row.machine, row.platform == "any") for row in registry
    }
    if any(
        (row.url, row.sha256, row.platform, row.machine, row.universal) not in known
        for row in declarations
    ):
        raise ValueError("UMF SDK declaration is not a verified cohort")
    supported_hosts = {(os, arch) for os in _PLATFORMS for arch in _MACHINES}
    for index, row in enumerate(declarations):
        row_hosts = {host for host in supported_hosts if _matches(row, *host)}
        for other in declarations[index + 1 :]:
            other_hosts = {host for host in supported_hosts if _matches(other, *host)}
            if row_hosts & other_hosts:
                raise ValueError("UMF SDK declarations overlap")
    selected = [row for row in declarations if _matches(row, platform, machine)]
    if len(selected) != 1:
        raise ValueError("UMF SDK declaration is missing or ambiguous for this host")
    declaration = selected[0]
    cohorts = [
        row
        for row in registry
        if row.url == declaration.url
        and row.sha256 == declaration.sha256
        and row.platform == declaration.platform
        and row.machine == declaration.machine
    ]
    if len(cohorts) != 1:
        raise ValueError("verified SDK cohort is ambiguous")
    return cohorts[0]
