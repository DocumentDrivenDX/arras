# SPDX-License-Identifier: MIT OR Apache-2.0
"""Prepare the existing managed required-STRING authored-Key page profile.

Weft compiles the unchanged Statement. Ashlar owns the source/publication binding;
UMF owns the strict parameter/output models and original EngineRead. Preparation
does not authorize SQL, construct a read policy or establish replica visibility.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from arras.errors import Unavailable, Unsupported
from arras.types import Statement


@dataclass(frozen=True, repr=False)
class PreparedPage:
    entry: Any
    parameters: Any
    request_json: str
    program_json: str


def _owners() -> tuple[Callable[..., Any], Callable[..., Any]]:
    import ashlar_host.managed_current_weft_binding as binding  # type: ignore[import-not-found]
    from umf_access.engine_catalog import EngineRead  # pyright: ignore[reportMissingImports, reportUnknownVariableType]

    # Optional owner packages are absent from the base install. Runtime installed
    # qualification must bind their exact distribution/source identities.
    return cast(Callable[..., Any], cast(Any, binding).managed_current_sdk_pages_request), cast(
        Callable[..., Any], cast(Any, EngineRead).from_original
    )


def prepare_managed_page(
    name: str,
    statement: Statement,
    *,
    source_bundle: dict[str, Any],
    weft_inputs: dict[str, Any],
    compiler: Any,
    parameters_type: Any,
    result_type: Any,
    page_size: int,
) -> PreparedPage:
    """Compile only; a separate person-scoped held AshlarTarget executes the entry.

    source_bundle and weft_inputs are original retained owner inputs, not a
    binding inferred from Arras ModuleInfo or display names. No profile repin or
    candidate-to-qualified substitution occurs here.
    """
    if type(page_size) is not int or not 1 <= page_size <= 999:
        raise Unsupported("Ashlar page size", ["1..999"])
    if any(type(value) is not str for value in statement.params.values()):
        raise Unsupported("Ashlar page parameters", ["required STRING parameters"])
    try:
        build, from_original = _owners()
    except ImportError:
        raise Unavailable(name, "unsupported_version", "Ashlar page APIs unavailable") from None
    try:
        values = dict(statement.params)
        parameters = parameters_type.model_validate(values)
        if parameters.model_dump(mode="python") != values:
            raise ValueError("parameter model changed original values")
        request = build(
            copy.deepcopy(source_bundle),
            copy.deepcopy(weft_inputs),
            statement.sql,
            {key: {"family": "string", "value": value} for key, value in values.items()},
        )
        envelope = {
            "version": "weft.engine-page/0.1",
            "compiler": "ashlar-spark4-pages",
            "request": request,
            "pageSize": page_size,
        }
        raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(raw.encode("utf-8")) > 1_048_576:
            raise ValueError("request exceeds owner page profile")
        program = compiler.compile_engine_page_json(raw)
        if type(program) is not str or not 0 < len(program.encode("utf-8")) <= 1_048_576:
            raise ValueError("bounded original engine program required")
        entry = from_original(program, parameters=parameters_type, result=result_type)
        admitted = entry.artifact()
        if any(admitted.get(key) != value for key, value in envelope.items()):
            raise ValueError("compiled original request correspondence differs")
        return PreparedPage(entry, parameters, raw, program)
    except Exception:
        # Source/binding/model/compiler errors can contain private source and
        # values. Do not guess a Weft refusal category from exception prose.
        raise Unavailable(name, "unreachable", "Ashlar page preparation failed") from None
