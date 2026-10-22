"""Compare selected wheel payload with files installed into the isolated venv."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


def classify_native(head: bytes, suffix: str, sys_platform: str) -> tuple[str, bool] | None:
    if head.startswith(b"\x7fELF"):
        binary_format = "ELF"
    elif head.startswith(
        (
            b"\xcf\xfa\xed\xfe",
            b"\xfe\xed\xfa\xcf",
            b"\xce\xfa\xed\xfe",
            b"\xfe\xed\xfa\xce",
            b"\xca\xfe\xba\xbe",
            b"\xbe\xba\xfe\xca",
            b"\xca\xfe\xba\xbf",
            b"\xbf\xba\xfe\xca",
        )
    ):
        binary_format = "MachO"
    elif head.startswith(b"MZ"):
        binary_format = "PE"
    elif suffix in (".so", ".dylib", ".dll", ".pyd", ".exe"):
        binary_format = "native-extension"
    else:
        return None
    suffix_native = (
        (sys_platform.startswith("linux") and suffix == ".so")
        or (sys_platform == "darwin" and suffix in (".so", ".dylib"))
        or (sys_platform == "win32" and suffix in (".dll", ".pyd", ".exe"))
    )
    runtime_native = (
        (binary_format == "ELF" and sys_platform.startswith("linux"))
        or (binary_format == "MachO" and sys_platform == "darwin")
        or (binary_format == "PE" and sys_platform == "win32")
        or suffix_native
    )
    return binary_format, runtime_native


class PayloadError(ValueError):
    """Installed files do not match the selected wheel payload."""


def payload_target(name: str, roots: dict[str, Path]) -> Path | None:
    parts = Path(name).parts
    if len(parts) >= 3 and parts[0].endswith(".data"):
        root = roots.get(parts[1])
        return root.joinpath(*parts[2:]) if root is not None else None
    return next(
        (root / name for root in (roots["purelib"], roots["platlib"]) if (root / name).is_file()),
        None,
    )


def verify_payload_parity(wheel: Path, roots: dict[str, Path]) -> dict[str, str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            members = archive.namelist()
            payload = [
                name
                for name in members
                if not name.endswith("/") and not name.endswith(".dist-info/RECORD")
            ]
            observed: dict[str, str] = {}
            for name in payload:
                target = payload_target(name, roots)
                if target is None:
                    raise PayloadError(f"installed payload omits {name} from {wheel.name}")
                installed = target.read_bytes()
                original = archive.read(name)
                expected = original
                if ".data/scripts/" in name and original.startswith(
                    (b"#!python\n", b"#!pythonw\n")
                ):
                    _, _, rest = original.partition(b"\n")
                    expected = b"#!" + str(roots["executable"]).encode() + b"\n" + rest
                if installed != expected:
                    raise PayloadError(
                        f"installed payload differs from the verified wheel member {name}"
                    )
                observed[name] = hashlib.sha256(installed).hexdigest()
            return observed
    except (OSError, zipfile.BadZipFile) as exc:
        raise PayloadError(f"cannot verify installed payload from {wheel.name}: {exc}") from exc
