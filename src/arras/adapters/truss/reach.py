# SPDX-License-Identifier: MIT OR Apache-2.0
"""`reached` of the Truss adapter (CONTRACT-001, CONTRACT-004, plan TR-10): has the store reached a token.

One read-only call as the person, asking Truss's `reached_in_transaction` (it never waits: the answer
is one read of evidence in the person's own transaction). A token is opaque and is never inspected
here, and `consumer_id` is never passed (that compares a replica's published progress, a separate
plan). The typed results map as follows, and `False` is only ever Truss's own `included=False`:

- `ReceiptIncluded` gives its `included`.
- `invalid_token` is `Invalid`, and so is a token over Truss's 16,384 character bound (Truss answers
  that one `resource` before any SQL; a `resource` the backend gives for a token inside the bound is
  `Unavailable`, as is the evidence bound).
- `authorization` (a person who is a member of nothing, or whose role was revoked) is `Refused`.
- every other reason (`epoch_profile`, `retention`, `observation_integrity`, `invalid_consumer`, `not_yet`) is
  `Unavailable`, never `False`: a token that cannot be told is not a token the store has not reached.
  Another installation's token is one of these (`epoch_profile`), not `Invalid`.

The error text never carries the token.
"""

from __future__ import annotations

from typing import Any

from arras.adapters.truss.connection import Connections
from arras.adapters.truss.registry import kind_of
from arras.errors import Invalid, Refused, Unavailable, Violation
from arras.types import Principal

TOKEN_BOUND = 16_384  # Truss's `maximum_token_bytes`, counted in characters by Truss


class Visibility:
    def __init__(self, name: str, connections: Connections) -> None:
        self.name = name
        self.connections = connections

    def reached(self, principal: Principal, token: str) -> bool:
        with self.connections.read(principal, "reached") as call:
            out: Any = call.unwrap(call.assembly.reached_in_transaction(call.tx, token))
        kind = kind_of(out)
        if kind == "ReceiptIncluded" and isinstance(out.included, bool):
            return out.included
        if kind != "ReceiptVisibilityUnavailable":
            raise Unavailable(self.name, "unreachable", "truss gave an unrecognized answer")
        reason = str(out.reason)
        malformed = Violation("token", "malformed", "not a token this backend issued")
        if reason == "invalid_token":
            raise Invalid([malformed])
        if reason == "resource":
            if len(token) > TOKEN_BOUND:
                raise Invalid([malformed])
            raise Unavailable(self.name, "resource", "truss resource")
        if reason == "authorization":
            raise Refused(self.name, "reached", "no_access")
        raise Unavailable(self.name, "unreachable", f"truss {reason}")
