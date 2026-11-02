# SPDX-License-Identifier: MIT OR Apache-2.0
"""The MCP process's configuration (CONTRACT-007, Configuration): one typed object, built once.

Config has three layers, split by who owns each key (twelve-factor), highest precedence first:

1. Ops-injected, never committed: environment variables and one optional ops file named by
   `ARRAS_OPS_FILE`. They carry the backends' endpoints (`ARRAS_BACKEND_<NAME>_ENDPOINT`, or
   `[backends.<name>] endpoint` in the ops file; the environment wins), the person's token, and the
   keys that select the files.
2. A committed per-environment file `<config_dir>/<env>.toml`, `env` from `ARRAS_ENV`: dev-owned,
   non-secret values.
3. The committed defaults `<config_dir>/default.toml`.

Layer 2 overrides layer 3 key by key and tables merge. Placement (where each module lives) is a
dev-owned fact and lives in these files only. An operator may still override a dev key by its
environment variable at deploy time, as an incident measure. A committed file that carries an ops
key is refused, so the repository could be opened at any moment without leaking a handle.

The library takes everything as parameters (CONTRACT-005); only this process reads files and the
environment, and it reads them here and nowhere else. A key that cannot be used stops the process at
start naming the file and key and never a value. An unknown `ARRAS_` variable stops it too, so a
misspelled endpoint is not a silent `not_configured`. The token is the person's own (ADR-017) and no
backend credential lives in this object. The process also clears the libpq environment (`PG*`)
before it connects (`scrub_ambient_connection_environment`), so a host, a role or a service file
that happens to be set in the deploy environment cannot reach the person's connection.
"""

from __future__ import annotations

import logging
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, cast

from arras.branding import Brand
from arras.distribution import DistributionConfig
from arras.model import Placement
from arras.names import BACKEND_NAME

DEFAULT_USER_CLAIMS = ("preferred_username", "email", "sub")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
DEFAULT_CONFIG_DIR = "config"
MAX_WARNINGS = 8

Owner = Literal["ops", "dev"]


@dataclass(frozen=True)
class Key:
    name: str
    owner: Owner
    what: str
    default: str | None = None  # a dev key's default; an ops key has none


# The environment's schema: the contract between whoever deploys the process and whoever develops it.
KEYS: tuple[Key, ...] = (
    Key(
        "ARRAS_ENV",
        "ops",
        "Names the per-environment file `<config_dir>/<env>.toml`; unset: none",
    ),
    Key("ARRAS_CONFIG_DIR", "ops", "Directory of the committed files (default `config`)"),
    Key(
        "ARRAS_OPS_FILE",
        "ops",
        "Mounted TOML file of `[backends.<name>] endpoint`, outside the repo",
    ),
    Key("ARRAS_TOKEN_FILE", "ops", "File holding the person's token, re-read when it changes"),
    Key("ARRAS_TOKEN", "ops", "The person's token, when there is no file to re-read"),
    Key(
        "ARRAS_USER_CLAIM",
        "dev",
        "Token claims naming the user, in order",
        ",".join(DEFAULT_USER_CLAIMS),
    ),
    Key("ARRAS_LOG_LEVEL", "dev", "Level of the diagnostics written to stderr", "INFO"),
    Key("ARRAS_DEV_SANDBOX", "dev", "1 serves the fake sandbox instead of backends", "0"),
    Key("ARRAS_DEV_USER", "dev", "The sandbox person", "alice"),
)
NAMES = frozenset(k.name for k in KEYS)
# A key that carries a name, in any number: a backend's endpoint.
ENDPOINT_KEY = re.compile(r"ARRAS_BACKEND_([A-Z][A-Z0-9_]{0,40})_ENDPOINT")
NAMED_KEYS = ("ARRAS_BACKEND_<NAME>_ENDPOINT: the handle of the backend the host calls <name>",)
# The administrator's keys belong to another process (CONTRACT-007), and the required-parser flags
# belong to the test runner (CI turns a skipped optional-engine check into a failure with them):
# present, never read, never an error.
IGNORED_PREFIXES = ("ARRAS_ADMIN_", "ARRAS_REQUIRE_WEFT", "ARRAS_REQUIRE_UMF")

# The keys of a committed file (layers 2 and 3). Anything else is an ops key or unknown.
FILE_KEYS = frozenset(
    {"log_level", "user_claims", "dev_sandbox", "dev_user", "placement", "modules", "distribution"}
)
PLACEMENT_FILE_KEYS = frozenset({"record", "replicas", "providers"})
# Spellings of what only ops may hold: refused in a committed file by name.
OPS_FILE_KEYS = frozenset(
    {"endpoint", "endpoints", "token", "token_file", "backends", "env", "config_dir", "ops_file"}
)
_ENV_NAME = re.compile(r"[a-z][a-z0-9_-]{0,40}")
_BACKEND_NAME = BACKEND_NAME


class ConfigError(Exception):
    """The configuration cannot be used. `problems` name files and keys and reasons, never values."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class Config:
    endpoints: Mapping[str, str] = field(default_factory=dict[str, str])
    """The handle of each backend, by the name the host gave it."""
    placements: Mapping[str, Placement] = field(default_factory=dict[str, Placement])
    """Where each named module lives."""
    default_placement: Placement | None = None
    token_file: str | None = None
    token: str | None = field(default=None, repr=False)  # the person's own, never shown
    user_claims: tuple[str, ...] = DEFAULT_USER_CLAIMS
    log_level: str = "INFO"
    dev_sandbox: bool = False
    dev_user: str = "alice"
    env: str | None = None
    """The environment named by `ARRAS_ENV`, when there is one."""
    config_dir: str = DEFAULT_CONFIG_DIR
    sources: tuple[str, ...] = ()
    distribution: DistributionConfig = field(default_factory=DistributionConfig)
    warnings: tuple[str, ...] = ()
    """What the environment did that a deployer may not intend (never a value): at most
    `MAX_WARNINGS` lines, such as a custom-prefix key shadowing a different `ARRAS_` value."""
    """The files actually read, lowest precedence first (for the startup diagnostic)."""

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, *, distribution: DistributionConfig | None = None
    ) -> Config:
        """Build the configuration from the environment and the files it points at, or raise
        `ConfigError` naming every file and key that cannot be used."""
        selected = distribution or DistributionConfig()
        problems: list[str] = []
        warnings: list[str] = []
        env = _normalize_environment(
            os.environ if env is None else env, selected.env_prefix, problems, warnings
        )

        def get(key: str) -> str | None:
            value = env.get(key, "").strip()
            return value or None

        env_name = get("ARRAS_ENV")
        if env_name and not _ENV_NAME.fullmatch(env_name):
            problems.append("ARRAS_ENV: a name [a-z][a-z0-9_-]*")
            env_name = None
        config_dir = get("ARRAS_CONFIG_DIR") or DEFAULT_CONFIG_DIR

        merged, origin, sources = _load_committed(config_dir, env_name, problems)

        # Layer 1: ops-injected.
        file_endpoints: dict[str, str] = {}
        ops_path = get("ARRAS_OPS_FILE")
        if ops_path:
            data = _read_toml(Path(ops_path), True, problems, key="ARRAS_OPS_FILE")
            if data is not None:
                sources.append(ops_path)
                file_endpoints = _check_ops_file(ops_path, data, problems)
        endpoints = {
            **file_endpoints,
            **{
                m.group(1).lower(): v
                for k in sorted(env)
                if (m := ENDPOINT_KEY.fullmatch(k)) and (v := get(k))
            },
        }

        dev = {k.name: k.default for k in KEYS if k.owner == "dev"}
        level = str(get("ARRAS_LOG_LEVEL") or merged.get("log_level") or dev["ARRAS_LOG_LEVEL"])
        level = level.upper()
        if level not in LOG_LEVELS:
            problems.append(
                f"ARRAS_LOG_LEVEL: one of {', '.join(LOG_LEVELS)} (also the log_level of a file)"
            )
        raw_sandbox = get("ARRAS_DEV_SANDBOX")
        sandbox = (
            raw_sandbox == "1"
            if raw_sandbox in ("0", "1")
            else bool(merged.get("dev_sandbox", False))
        )
        if raw_sandbox not in (None, "0", "1"):
            problems.append("ARRAS_DEV_SANDBOX: 0 or 1")
        effective_distribution = validate_distribution(
            merged.get("distribution"), selected, problems
        )
        default, placements = _placements(merged, origin, endpoints, sandbox, problems)

        claims_env = get("ARRAS_USER_CLAIM")
        if claims_env is not None:
            claims = tuple(c.strip() for c in claims_env.split(",") if c.strip())
        else:
            claims = tuple(merged.get("user_claims", ()))
        if problems:
            raise ConfigError(problems)
        return cls(
            endpoints=endpoints,
            placements=placements,
            default_placement=default,
            token_file=get("ARRAS_TOKEN_FILE"),
            token=get("ARRAS_TOKEN"),
            user_claims=claims or DEFAULT_USER_CLAIMS,
            log_level=level,
            dev_sandbox=sandbox,
            dev_user=get("ARRAS_DEV_USER") or str(merged.get("dev_user") or dev["ARRAS_DEV_USER"]),
            env=env_name,
            config_dir=config_dir,
            sources=tuple(sources),
            distribution=effective_distribution,
            warnings=_bounded(warnings),
        )

    def startup_line(self) -> str:
        """One line for stderr: which environment and which files, never a value."""
        files = ", ".join(self.sources) or "none"
        label = self.diagnostic_prefix(self.distribution)
        return f"{label}: env={self.env or 'none'} files={files}"

    @staticmethod
    def diagnostic_prefix(distribution: DistributionConfig | None) -> str:
        """A printable one-line human label; default diagnostics keep their established prefix."""
        selected = distribution or DistributionConfig()
        if selected.brand == Brand():
            return "arras.mcp"
        safe = " ".join(
            "".join(char if char.isprintable() else " " for char in selected.brand.name).split()
        )
        return safe or "Arras"

    def configure_logging(self, stream: object) -> None:
        """Diagnostics go to `stream` (stderr): stdout carries protocol frames and nothing else."""
        logging.basicConfig(
            stream=stream,  # type: ignore[arg-type]
            level=self.log_level,
            format="%(levelname)s %(name)s: %(message)s",
        )


def _load_committed(
    config_dir: str, env_name: str | None, problems: list[str]
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """Layers 3 then 2: committed, dev-owned. A missing default file is fine; a named
    environment's file must exist."""
    merged: dict[str, Any] = {}
    origin: dict[str, str] = {}
    sources: list[str] = []
    layers = [(Path(config_dir) / "default.toml", False)]
    if env_name:
        layers.append((Path(config_dir) / f"{env_name}.toml", True))
    for path, required in layers:
        data = _read_toml(path, required, problems)
        if data is None:
            continue
        sources.append(str(path))
        if validate_committed(str(path), data, problems):
            merge_committed(merged, data, origin, str(path))
    return merged, origin, sources


def _placements(
    merged: Mapping[str, Any],
    origin: Mapping[str, str],
    endpoints: Mapping[str, str],
    sandbox: bool,
    problems: list[str],
) -> tuple[Placement | None, dict[str, Placement]]:
    """The default placement and each module's, from the merged files. Outside the sandbox every
    backend a placement names must have an endpoint."""
    default = None
    if "placement" in merged:
        default = _placement(
            "[placement]", origin.get("placement", ""), merged["placement"], problems
        )
    placements = {
        module: _placement(
            f"[modules.{module}]", origin.get(f"modules.{module}", ""), table, problems
        )
        for module, table in sorted(dict(merged.get("modules", {})).items())
    }
    if not sandbox:
        keyed = [(f"[modules.{m}]", p) for m, p in placements.items()]
        for k, placed in [*keyed, ("[placement]", default)]:
            for n in _backends_of(placed):
                if n not in endpoints:
                    problems.append(f"{k}: names backend {n!r}, which has no endpoint")
    return default, placements


def _backends_of(placed: Placement | None) -> list[str]:
    """Every backend a placement names: its readers and its providers."""
    if placed is None:
        return []
    return [n for n in (*placed.readers, *placed.providers.values()) if n]


def _parse_committed_document(raw: bytes) -> dict[str, Any]:
    """Parse one already-bounded UTF-8 committed document without performing file I/O."""
    return tomllib.loads(raw.decode("utf-8"))


def _read_toml(
    path: Path, required: bool, problems: list[str], key: str | None = None
) -> dict[str, Any] | None:
    """The file's table, or None when it is absent and may be, or unusable (then a problem names
    the file and, for a parse error, the line, never any content)."""
    label = f"{key} ({path})" if key else str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if required:
            problems.append(f"{label}: file does not exist")
        return None
    except UnicodeDecodeError:
        problems.append(f"{label}: not UTF-8 text")
        return None
    except OSError:
        problems.append(f"{label}: cannot be read")
        return None
    try:
        return _parse_committed_document(text.encode("utf-8"))
    except tomllib.TOMLDecodeError as e:
        line = re.search(r"line (\d+)", str(e))
        problems.append(f"{label}: not valid TOML" + (f" at line {line.group(1)}" if line else ""))
        return None


def _unknown(path: str, dotted: str, name: str) -> str:
    """An ops key in a committed file, or one nobody owns: named, never valued."""
    if name.lower() in OPS_FILE_KEYS or name.upper().startswith("ARRAS_"):
        return f"{path}: {dotted}: an ops key; ops values never live in a committed file"
    return f"{path}: {dotted}: unknown key"


def _bounded(warnings: list[str]) -> tuple[str, ...]:
    """At most `MAX_WARNINGS` lines; the rest are counted, not listed."""
    if len(warnings) <= MAX_WARNINGS:
        return tuple(warnings)
    return (*warnings[:MAX_WARNINGS], f"and {len(warnings) - MAX_WARNINGS} more alias conflicts")


def _normalize_environment(
    raw_env: Mapping[str, str],
    prefix: str,
    problems: list[str],
    warnings: list[str] | None = None,
) -> dict[str, str]:
    """Normalize known canonical and selected-prefix aliases, retaining safe diagnostics.

    A key set under the selected prefix and under `ARRAS_` to different nonblank values is
    reported as a warning naming both variables and which one is used, never a value. The
    credential keys are the exception: they refuse (below)."""
    canonical_values: dict[str, list[tuple[str, str]]] = {}
    normalized: dict[str, str] = {}
    for original, raw_value in raw_env.items():
        if prefix != "ARRAS" and original.startswith(prefix + "_"):
            suffix, custom = original[len(prefix) + 1 :], True
        elif original.startswith("ARRAS_"):
            suffix, custom = original[6:], False
        else:
            continue
        canonical = "ARRAS_" + suffix
        known = canonical in NAMES or ENDPOINT_KEY.fullmatch(canonical) is not None
        if not known and not canonical.startswith(IGNORED_PREFIXES):
            problems.append(
                f"{original}: not an Arras key"
                if prefix == "ARRAS"
                else f"{original}: unknown environment key"
            )
            continue
        if canonical.startswith(IGNORED_PREFIXES):
            continue
        value = raw_value.strip()
        canonical_values.setdefault(canonical, []).append((original, value))
        if custom and value:
            normalized[canonical] = value
    for canonical, values in canonical_values.items():
        if canonical not in normalized:
            fallback = next((v for name, v in values if name == canonical and v), None)
            if fallback is None:
                fallback = next((v for _, v in values if v), None)
            if fallback is not None:
                normalized[canonical] = fallback
        if (
            canonical not in ("ARRAS_TOKEN", "ARRAS_TOKEN_FILE")
            and warnings is not None
            and len({value for _, value in values if value}) > 1
        ):
            used = next(name for name, value in values if value and name != canonical)
            warnings.append(
                f"{used} and {canonical} are both set to different values; {used} is used"
            )
        if (
            canonical in ("ARRAS_TOKEN", "ARRAS_TOKEN_FILE")
            and len({value for _, value in values if value}) > 1
        ):
            aliases = ", ".join(name for name, _ in values)
            problems.append(f"{canonical}: conflicting aliases ({aliases})")
    tokens = [(key, values) for key, values in canonical_values.items()]
    has_token = any(
        key == "ARRAS_TOKEN" and any(value for _, value in values) for key, values in tokens
    )
    has_file = any(
        key == "ARRAS_TOKEN_FILE" and any(value for _, value in values) for key, values in tokens
    )
    if has_token and has_file:
        token_name = next(
            (name for name, value in canonical_values.get("ARRAS_TOKEN", []) if value),
            "ARRAS_TOKEN",
        )
        problems.append(f"{token_name}: supply a token or token file, not both")
    return normalized


def _check_distribution_file(path: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, dict):
        problems.append(f"{path}: distribution: a table")
        return
    table = cast("dict[str, object]", value)
    allowed = {"mcp_server_name", "mcp_tool_prefix", "brand", "telemetry"}
    for field_name, field_value in table.items():
        if field_name not in allowed:
            problems.append(f"{path}: distribution.{field_name}: unknown or launcher-only field")
        elif field_name in {"mcp_server_name", "mcp_tool_prefix"} and not isinstance(
            field_value, str
        ):
            problems.append(f"{path}: distribution.{field_name}: a string")
        elif field_name == "brand":
            names = {"name", "title", "wordmark", "tagline", "logo"}
            brand_fields = (
                cast("dict[object, object]", field_value) if isinstance(field_value, dict) else {}
            )
            if (
                not isinstance(field_value, dict)
                or not set(brand_fields) <= names
                or not all(isinstance(v, str) for v in brand_fields.values())
            ):
                problems.append(f"{path}: distribution.brand: known string fields only")
        elif field_name == "telemetry":
            names = {"service_name", "attribute_namespace", "log_prefix", "event_prefix"}
            values = (
                cast("dict[object, object]", field_value) if isinstance(field_value, dict) else {}
            )
            if (
                not isinstance(field_value, dict)
                or not set(values) <= names
                or not all(isinstance(v, str) for v in values.values())
            ):
                problems.append(f"{path}: distribution.telemetry: known string fields only")


def validate_distribution(
    value: object, selected: DistributionConfig, problems: list[str]
) -> DistributionConfig:
    """Apply presentation overrides from committed files; env_prefix remains launcher-owned."""
    if not isinstance(value, dict):
        return selected
    table = cast("dict[str, object]", value)
    brand = selected.brand
    brand_values = table.get("brand", {})
    if isinstance(brand_values, dict):
        for field_name, field_value in cast("dict[str, object]", brand_values).items():
            try:
                brand = replace(brand, **{field_name: field_value})
            except (TypeError, ValueError):
                problems.append(f"distribution.brand.{field_name}: invalid value")
    values: dict[str, object] = {"brand": brand}
    for field_name in ("mcp_server_name", "mcp_tool_prefix"):
        if field_name not in table:
            continue
        try:
            candidate = replace(selected, **{field_name: table[field_name]})
        except (TypeError, ValueError):
            problems.append(f"distribution.{field_name}: invalid value")
        else:
            values[field_name] = getattr(candidate, field_name)
    telemetry_values = table.get("telemetry")
    if isinstance(telemetry_values, dict):
        try:
            values["telemetry"] = replace(
                selected.telemetry,
                **cast("dict[str, object]", telemetry_values),
            )
        except (TypeError, ValueError):
            for field_name in cast("dict[object, object]", telemetry_values):
                problems.append(f"distribution.telemetry.{field_name}: invalid value")
    try:
        return replace(selected, **values)
    except (TypeError, ValueError):
        problems.append("distribution: invalid settings")
        return selected


def validate_committed(path: str, data: dict[str, Any], problems: list[str]) -> bool:
    """Whether a committed file is well formed; each fault is a problem naming file and key."""
    before = len(problems)
    for key, value in data.items():
        if key not in FILE_KEYS:
            problems.append(_unknown(path, key, key))
        elif key == "log_level" and not isinstance(value, str):
            problems.append(f"{path}: log_level: a string")
        elif key == "dev_user" and not isinstance(value, str):
            problems.append(f"{path}: dev_user: a string")
        elif key == "dev_sandbox" and not isinstance(value, bool):
            problems.append(f"{path}: dev_sandbox: true or false")
        elif key == "user_claims" and not _strings(value):
            problems.append(f"{path}: user_claims: a list of strings")
        elif key == "placement":
            _check_placement(path, "placement", cast("object", value), problems)
        elif key == "modules":
            if not isinstance(value, dict):
                problems.append(f"{path}: modules: a table of module placements")
                continue
            for module, table in cast("dict[str, object]", value).items():
                _check_placement(path, f"modules.{module}", table, problems)
        elif key == "distribution":
            _check_distribution_file(path, value, problems)
    return len(problems) == before


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(c, str) for c in cast("list[object]", value))


def _provider_table(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(n, str) and _BACKEND_NAME.fullmatch(n)
        for n in cast("dict[object, object]", value).values()
    )


def _check_placement(path: str, dotted: str, table: object, problems: list[str]) -> None:
    if not isinstance(table, dict):
        problems.append(f"{path}: {dotted}: a table of record, replicas, providers")
        return
    for key, value in cast("dict[object, object]", table).items():
        where = f"{dotted}.{key}"
        if key not in PLACEMENT_FILE_KEYS:
            problems.append(_unknown(path, where, str(key)))
        elif key == "record" and not (isinstance(value, str) and _BACKEND_NAME.fullmatch(value)):
            problems.append(f"{path}: {where}: a backend name [a-z][a-z0-9_]*")
        elif key == "replicas" and not (
            _strings(value) and all(_BACKEND_NAME.fullmatch(n) for n in cast("list[str]", value))
        ):
            problems.append(f"{path}: {where}: a list of backend names [a-z][a-z0-9_]*")
        elif key == "providers" and not _provider_table(value):
            problems.append(f"{path}: {where}: a table of action name to backend name")


def _check_ops_file(path: str, data: dict[str, Any], problems: list[str]) -> dict[str, str]:
    """The ops file carries `[backends.<name>] endpoint` and nothing else."""
    found: dict[str, str] = {}
    for key, value in data.items():
        if key != "backends" or not isinstance(value, dict):
            problems.append(f"{path}: {key}: the ops file carries [backends.<name>] endpoint only")
            continue
        for name, table in value.items():  # type: ignore[reportUnknownVariableType]
            where = f"backends.{name}"
            if not _BACKEND_NAME.fullmatch(str(name)):  # type: ignore[reportUnknownArgumentType]
                problems.append(f"{path}: {where}: a backend name [a-z][a-z0-9_]*")
            elif not isinstance(table, dict):
                problems.append(f"{path}: {where}: a table with endpoint")
            else:
                for k, v in table.items():  # type: ignore[reportUnknownVariableType]
                    if k != "endpoint":
                        problems.append(f"{path}: {where}.{k}: the ops file carries endpoint only")
                    elif not isinstance(v, str):
                        problems.append(f"{path}: {where}.endpoint: a string")
                    elif v.strip():
                        found[str(name)] = v.strip()  # type: ignore[reportUnknownArgumentType]
    return found


def merge_committed(
    into: dict[str, Any], data: dict[str, Any], origin: dict[str, str], path: str
) -> None:
    """Layer `data` over `into`: scalars and lists replace, a placement table merges key by key."""
    for key, value in data.items():
        if key == "placement":
            into.setdefault("placement", {}).update(value)
            origin["placement"] = path
        elif key == "modules":
            for module, table in value.items():
                into.setdefault("modules", {}).setdefault(module, {}).update(table)
                origin[f"modules.{module}"] = path
        elif key == "distribution" and isinstance(value, dict):
            target = into.setdefault("distribution", {})
            distribution_values = cast("dict[str, Any]", value)
            for field_name, field_value in distribution_values.items():
                if field_name == "brand" and isinstance(field_value, dict):
                    target.setdefault("brand", {}).update(field_value)
                elif field_name == "telemetry" and isinstance(field_value, dict):
                    target.setdefault("telemetry", {}).update(field_value)
                else:
                    target[field_name] = field_value
        else:
            into[key] = value


def _placement(key: str, path: str, table: Mapping[str, Any], problems: list[str]) -> Placement:
    """The placement a table spells; a missing record is a problem under the table's key."""
    record = table.get("record")
    if not record:
        problems.append(f"{path}: {key}.record: required")
        return Placement("")
    replicas = tuple(table.get("replicas", ()))
    named = [record, *replicas]
    if len(set(named)) != len(named):
        problems.append(f"{path}: {key}: a reader is named twice")
    return Placement(record, replicas, dict(table.get("providers", {})))


def scrub_ambient_connection_environment(environ: dict[str, str] | None = None) -> list[str]:
    """Remove every libpq variable (`PG*`) from `environ` (the process's, by default) and return
    the names removed, never their values. The adapter passes every connection keyword it can, but
    libpq's service file (`PGSERVICE`) has no keyword that switches it off, so the process drops
    them all before its first connection and nothing ambient can name a host, a role or an option
    for the person's connection (CONTRACT-007)."""
    target = os.environ if environ is None else environ
    found = sorted(k for k in target if k.startswith("PG"))
    for key in found:
        del target[key]
    return found
