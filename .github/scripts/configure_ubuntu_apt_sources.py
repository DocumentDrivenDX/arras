#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright 2026 DocumentDrivenDX contributors.
# Adapted from DocumentDrivenDX/weft commit cc694344da31af76ef6b97e572d20a8347989bdd.
"""Select official HTTPS mirrors for GitHub's hosted Ubuntu apt source."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

APT_ROOT = Path("/etc/apt")
# The ubuntu24/20261021.345 runner recipe's configure-apt-sources.sh (blob
# b3f5b2b180df8eb39fcbba034f616e03a69e775c) installs this exact selector.
# Recognize that token only; never resolve or trust arbitrary mirror+file paths.
RUNNER_MIRROR_URI = "mirror+file:/etc/apt/apt-mirrors.txt"
FIELD = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):[ \t]*(.*)$")
SOURCE_ENTRY = re.compile(r"^(\s*deb(?:-src)?\s+(?:\[[^]]*\]\s+)?)(\S+)(\s+)(\S+)(.*)$")
URI_TOKEN = re.compile(r"(?<!\S)(?:https?://\S+|mirror\+file:\S+)(?=\s|$)")
OFFICIAL_URI = re.compile(
    r"^(https?)://(azure\.archive\.ubuntu\.com|archive\.ubuntu\.com|security\.ubuntu\.com)/ubuntu/?$"
)


def canonical_uri(uri: str, suites: list[str]) -> tuple[str, set[str]]:
    security_suite = bool(suites) and all(suite.endswith("-security") for suite in suites)
    if uri == RUNNER_MIRROR_URI:
        host = "security.ubuntu.com" if security_suite else "archive.ubuntu.com"
        return f"https://{host}/ubuntu", {host}
    if uri.startswith("mirror+file:"):
        raise ValueError(f"Unsupported Ubuntu mirror selector: {uri}")
    match = OFFICIAL_URI.fullmatch(uri)
    if not match:
        return uri, set()
    scheme, host = match.groups()
    if scheme == "https" and host in {"archive.ubuntu.com", "security.ubuntu.com"}:
        return uri, {host}
    host = (
        "security.ubuntu.com"
        if host == "security.ubuntu.com" or security_suite
        else "archive.ubuntu.com"
    )
    return f"https://{host}/ubuntu", {host}


def transform_deb822(text: str) -> tuple[str, set[str]]:
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    hosts: set[str] = set()
    block: list[str] = []

    def transform_block(source: list[str]) -> tuple[list[str], set[str]]:
        suites: list[str] = []
        uri_fields: list[tuple[int, int, str]] = []
        current: str | None = None
        for index, line in enumerate(source):
            content = line.rstrip("\r\n")
            if not content.strip() or content.lstrip().startswith("#"):
                current = None
                continue
            field = FIELD.match(content)
            if field:
                current = field.group(1).lower()
                if current == "suites":
                    suites.extend(field.group(2).split())
                elif current == "uris":
                    uri_fields.append((index, field.start(2), field.group(2)))
            elif content[:1].isspace() and current:
                if current == "suites":
                    suites.extend(content.split())
                elif current == "uris":
                    indent = len(content) - len(content.lstrip())
                    uri_fields.append((index, indent, content[indent:]))

        found: set[str] = set()
        for index, start, value in uri_fields:

            def replace(match: re.Match[str]) -> str:
                updated, matched = canonical_uri(match.group(0), suites)
                found.update(matched)
                return updated

            content = source[index].rstrip("\r\n")
            source[index] = (
                content[:start] + URI_TOKEN.sub(replace, value) + source[index][len(content) :]
            )
        return source, found

    for line in lines:
        if line.strip():
            block.append(line)
        else:
            transformed, found = transform_block(block)
            result.extend(transformed)
            result.append(line)
            hosts.update(found)
            block = []
    transformed, found = transform_block(block)
    result.extend(transformed)
    hosts.update(found)
    return "".join(result), hosts


def transform_list(text: str) -> tuple[str, set[str]]:
    result: list[str] = []
    hosts: set[str] = set()
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        entry = SOURCE_ENTRY.match(content) if not content.lstrip().startswith("#") else None
        if entry:
            prefix, uri, separator, suite, tail = entry.groups()
            updated, found = canonical_uri(uri, [suite])
            hosts.update(found)
            line = prefix + updated + separator + suite + tail + line[len(content) :]
        result.append(line)
    return "".join(result), hosts


def configure(root: Path = APT_ROOT) -> dict[str, object]:
    source_dir = root / "sources.list.d"
    paths = [root / "sources.list", *source_dir.glob("*.list"), *source_dir.glob("*.sources")]
    direct_hosts: set[str] = set()
    source_names: list[str] = []
    pending: list[tuple[Path, str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        original = path.read_text()
        if path.suffix == ".sources":
            updated, hosts = transform_deb822(original)
        else:
            updated, hosts = transform_list(original)
        direct_hosts.update(hosts)
        source_names.append(path.name)
        pending.append((path, original, updated))

    if not direct_hosts:
        raise ValueError("No official Ubuntu archive/security source URI was found")
    for path, original, updated in pending:
        if updated != original:
            path.write_text(updated)
    return {
        "source_files": sorted(source_names),
        "direct_https_hosts": sorted(direct_hosts),
    }


def test_mirror_mapping() -> str:
    source = (
        "Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\n"
        "Suites: noble noble-updates\nComponents: main universe\n"
        "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n\n"
        "Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\n"
        "Suites: noble-security\nComponents: main universe\n"
        "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
    )
    transformed, hosts = transform_deb822(source)
    assert hosts == {"archive.ubuntu.com", "security.ubuntu.com"}
    assert "https://archive.ubuntu.com/ubuntu" in transformed
    assert "https://security.ubuntu.com/ubuntu" in transformed
    assert "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg" in transformed
    assert transform_deb822(transformed)[0] == transformed
    return source


def test_unrelated_references() -> None:
    lookalikes, hosts = transform_deb822(
        "# mirror+file:/tmp/commented-out.list\n"
        "Types: deb\nURIs: https://archive.ubuntu.com.evil/ubuntu\n"
        "Suites: noble\nComponents: main\n"
    )
    assert "mirror+file:/tmp/commented-out.list" in lookalikes
    assert "https://archive.ubuntu.com.evil/ubuntu" in lookalikes
    assert not hosts
    direct, hosts = transform_list(
        "deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] "
        "http://azure.archive.ubuntu.com/ubuntu noble main\n"
        "deb https://azure.archive.ubuntu.com/ubuntu noble main\n"
        "deb mirror+file:/etc/apt/apt-mirrors.txt noble-security main\n"
        "deb https://packages.example.test/ubuntu noble main\n",
    )
    assert "https://archive.ubuntu.com/ubuntu noble" in direct
    assert "https://azure.archive.ubuntu.com/ubuntu" not in direct
    assert "https://security.ubuntu.com/ubuntu noble-security" in direct
    assert "https://packages.example.test/ubuntu noble" in direct
    assert hosts == {"archive.ubuntu.com", "security.ubuntu.com"}


def test_configure_layout(source: str) -> None:
    # Shape matches the official Ubuntu hosted-runner recipe: exact mirror+file
    # selector, suite-specific source, preserved Signed-By, and unrelated source.
    with tempfile.TemporaryDirectory(prefix="ubuntu-apt-layout-") as temp:
        root = Path(temp) / "etc" / "apt"
        source_dir = root / "sources.list.d"
        source_dir.mkdir(parents=True)
        (source_dir / "ubuntu.sources").write_text(source)
        third_party = source_dir / "third-party.list"
        third_party.write_text("deb https://packages.example.test/ubuntu noble main\n")
        summary = configure(root)
        updated = (source_dir / "ubuntu.sources").read_text()
        assert summary["source_files"] == ["third-party.list", "ubuntu.sources"]
        assert summary["direct_https_hosts"] == ["archive.ubuntu.com", "security.ubuntu.com"]
        assert "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg" in updated
        assert third_party.read_text() == "deb https://packages.example.test/ubuntu noble main\n"
        assert configure(root) == summary


def test_unknown_selector_is_refused_without_partial_writes() -> None:
    with tempfile.TemporaryDirectory(prefix="ubuntu-apt-unknown-") as temp:
        root = Path(temp) / "etc" / "apt"
        source_dir = root / "sources.list.d"
        source_dir.mkdir(parents=True)
        recognized = source_dir / "00-ubuntu.list"
        recognized.write_text("deb http://azure.archive.ubuntu.com/ubuntu noble main\n")
        (source_dir / "ubuntu.sources").write_text(
            "Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt.bak\n"
            "Suites: noble\nComponents: main\n"
        )
        original = recognized.read_text()
        try:
            configure(root)
        except ValueError as error:
            assert "Unsupported Ubuntu mirror selector" in str(error)
        else:
            raise AssertionError("unknown mirror selector unexpectedly qualified")
        assert recognized.read_text() == original


def self_test() -> None:
    source = test_mirror_mapping()
    test_unrelated_references()
    test_configure_layout(source)
    test_unknown_selector_is_refused_without_partial_writes()


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("Ubuntu apt source fixture checks passed")
    else:
        self_test()
        print(f"Ubuntu apt source layout: {configure()}")


if __name__ == "__main__":
    main()
