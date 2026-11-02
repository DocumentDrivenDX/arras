from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "local_registry_origin", ROOT / ".github/scripts/verify_local_registry_origin.py"
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


@pytest.fixture
def assets(tmp_path: Path) -> tuple[dict[str, str], str]:
    pins: dict[str, str] = {}
    for name in module.ASSETS:
        data = (
            json.dumps(
                {
                    "schema": "arras.local-release-proof.v1",
                    "status": "qualified-before-publication",
                    "tag": module.EXPECTED_TAG,
                    "version": module.EXPECTED_VERSION,
                    "tagObjectSha": module.EXPECTED_TAG_OBJECT,
                    "releaseSourceCommit": module.EXPECTED_SOURCE,
                    "transport": "local; no Actions publication run",
                }
            ).encode()
            if name == "local-release-proof.json"
            else name.encode()
        )
        (tmp_path / name).write_bytes(data)
        pins[name] = hashlib.sha256(data).hexdigest()
    sums = "".join(f"{pins[name]}  {name}\n" for name in sorted(pins)).encode()
    (tmp_path / "SHA256SUMS").write_bytes(sums)
    return pins, hashlib.sha256(sums).hexdigest()


def test_valid_local_origin(assets: tuple[dict[str, str], str], tmp_path: Path) -> None:
    pins, sums_sha = assets
    result = module.validate(
        tmp_path,
        module.EXPECTED_TAG,
        module.EXPECTED_SOURCE,
        module.EXPECTED_TAG_OBJECT,
        asset_pins=pins,
        sums_sha256=sums_sha,
    )
    assert result["origin"] == "local-release-proof"
    assert result["assets"] == pins
    assert result["wheel_sha256"] == pins["arras-0.6.5-py3-none-any.whl"]
    assert result["sums_sha256"] == sums_sha


@pytest.mark.parametrize(
    "identity",
    [
        ("v0.6.4", module.EXPECTED_SOURCE, module.EXPECTED_TAG_OBJECT),
        (module.EXPECTED_TAG, "0" * 40, module.EXPECTED_TAG_OBJECT),
        (module.EXPECTED_TAG, module.EXPECTED_SOURCE, "0" * 40),
    ],
)
def test_wrong_identity_refuses(
    assets: tuple[dict[str, str], str], tmp_path: Path, identity: tuple[str, str, str]
) -> None:
    pins, sums_sha = assets
    with pytest.raises(ValueError):
        module.validate(tmp_path, *identity, asset_pins=pins, sums_sha256=sums_sha)


def test_tampered_asset_refuses(assets: tuple[dict[str, str], str], tmp_path: Path) -> None:
    pins, sums_sha = assets
    (tmp_path / next(iter(pins))).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="asset bytes"):
        module.validate(
            tmp_path,
            module.EXPECTED_TAG,
            module.EXPECTED_SOURCE,
            module.EXPECTED_TAG_OBJECT,
            asset_pins=pins,
            sums_sha256=sums_sha,
        )


def test_extra_asset_refuses(assets: tuple[dict[str, str], str], tmp_path: Path) -> None:
    pins, sums_sha = assets
    (tmp_path / "extra").write_text("x")
    with pytest.raises(ValueError, match="exactly"):
        module.validate(
            tmp_path,
            module.EXPECTED_TAG,
            module.EXPECTED_SOURCE,
            module.EXPECTED_TAG_OBJECT,
            asset_pins=pins,
            sums_sha256=sums_sha,
        )


@pytest.mark.parametrize(
    "field", ["schema", "status", "transport", "version", "releaseSourceCommit"]
)
def test_invalid_proof_refuses(
    assets: tuple[dict[str, str], str], tmp_path: Path, field: str
) -> None:
    pins, _ = assets
    proof_path = tmp_path / "local-release-proof.json"
    proof = json.loads(proof_path.read_text())
    proof[field] = "invalid"
    proof_path.write_text(json.dumps(proof))
    pins[proof_path.name] = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("".join(f"{pins[name]}  {name}\n" for name in sorted(pins)))
    with pytest.raises(ValueError, match="proof"):
        module.validate(
            tmp_path,
            module.EXPECTED_TAG,
            module.EXPECTED_SOURCE,
            module.EXPECTED_TAG_OBJECT,
            asset_pins=pins,
            sums_sha256=hashlib.sha256(sums.read_bytes()).hexdigest(),
        )


@pytest.mark.parametrize("change", ["sums", "missing", "symlink", "duplicate"])
def test_input_boundary_refuses(
    assets: tuple[dict[str, str], str], tmp_path: Path, change: str
) -> None:
    pins, sums_sha = assets
    name = next(iter(pins))
    if change == "sums":
        sums = tmp_path / "SHA256SUMS"
        sums.write_text("\n".join(reversed(sums.read_text().splitlines())) + "\n")
    elif change == "missing":
        (tmp_path / name).unlink()
    elif change == "symlink":
        (tmp_path / name).unlink()
        (tmp_path / name).symlink_to(tmp_path / "local-release-proof.json")
    else:
        sums = tmp_path / "SHA256SUMS"
        sums.write_text(sums.read_text() + sums.read_text().splitlines()[0] + "\n")
        sums_sha = hashlib.sha256(sums.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        module.validate(
            tmp_path,
            module.EXPECTED_TAG,
            module.EXPECTED_SOURCE,
            module.EXPECTED_TAG_OBJECT,
            asset_pins=pins,
            sums_sha256=sums_sha,
        )


def test_cli_defaults_refuse_fixture_bytes(
    assets: tuple[dict[str, str], str], tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="SHA256SUMS bytes"):
        module.validate(
            tmp_path, module.EXPECTED_TAG, module.EXPECTED_SOURCE, module.EXPECTED_TAG_OBJECT
        )
