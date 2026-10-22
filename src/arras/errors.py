# SPDX-License-Identifier: MIT OR Apache-2.0
"""Errors raised by the interface (CONTRACT-001)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    path: str
    code: str
    message: str


class ArrasError(Exception):
    """Base of every error the interface raises."""


class Invalid(ArrasError):
    """A parameter or literal breaks a rule or bound; every violation is reported."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = list(violations)
        super().__init__("; ".join(f"{v.path}: {v.code}: {v.message}" for v in self.violations))


class Refused(ArrasError):
    """The principal lacks access, or its token is missing or expired."""

    REASONS = ("no_access", "token_expired")

    def __init__(self, backend: str, operation: str, reason: str = "no_access") -> None:
        self.backend = backend
        self.operation = operation
        self.reason = reason  # `token_expired`: sign in again; `no_access`: request the grant
        super().__init__(f"{backend} refused {operation}")


# The reasons a backend may be unavailable for (CONTRACT-005). Anything else is reported as `other`.
UNAVAILABLE_REASONS = frozenset(
    {"not_configured", "unreachable", "access_denied", "migration_failed", "unsupported_version"}
)


class Unavailable(ArrasError):
    """The backend cannot answer."""

    def __init__(self, backend: str, reason: str, detail: str = "") -> None:
        self.backend = backend
        self.reason = reason
        self.detail = detail
        super().__init__(f"{backend} unavailable ({reason}){': ' + detail if detail else ''}")


class Unsupported(ArrasError):
    """The query or the type's capabilities do not include the request."""

    def __init__(self, construct: str, supported: list[str]) -> None:
        self.construct = construct
        self.supported = list(supported)
        super().__init__(f"unsupported: {construct}")


class NotYetCurrent(ArrasError):
    """`at_least` was not reached within the bound."""

    def __init__(self, token: str, backend: str) -> None:
        self.token = token
        self.backend = backend
        super().__init__(f"{backend} has not reached {token}")


@dataclass(frozen=True)
class Failure:
    """A precondition that did not hold."""

    id: str
    reason: str


class PreconditionFailed(ArrasError):
    """One or more preconditions are false; every one the authority could evaluate is listed."""

    def __init__(self, failures: list[Failure]) -> None:
        self.failures = list(failures)
        super().__init__("; ".join(f"{f.id}: {f.reason}" for f in self.failures))


class Conflict(ArrasError):
    """An effect collides with existing state (CONTRACT-003)."""

    REASONS = (
        "exists",
        "deleted",
        "version",
        "duplicate_relationship",
        "idempotency_key_reused",
        "revision",
    )

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"conflict ({reason}){': ' + detail if detail else ''}")
