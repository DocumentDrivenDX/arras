# SPDX-License-Identifier: MIT OR Apache-2.0
"""Shared non-sensitive result primitives for managed Lakebase case modules."""

from __future__ import annotations

import re

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_CODE = re.compile(r"[a-z][a-z0-9_.-]{0,79}\Z")

MANAGED_CASES = (
    "LB-CUSTODY",
    "LB-SETTLEMENT",
    "LB-ACL",
    "MP-01",
    "MP-02",
    "MP-03",
    "MP-04",
    "MP-05",
    "MP-06",
)
CASE_OPERATIONS: dict[str, frozenset[str]] = {
    "LB-CUSTODY": frozenset({"read", "apply"}),
    "LB-SETTLEMENT": frozenset({"read", "apply", "fault"}),
    "LB-ACL": frozenset(
        {
            "read",
            "install",
            "configure",
            "provision_module_roles",
            "prepare_owned_access_roles",
            "grant_owned_memberships",
            "revoke_owned_memberships",
        }
    ),
    "MP-01": frozenset({"read", "apply", "feed", "refresh", "restart"}),
    "MP-02": frozenset({"read", "refresh"}),
    "MP-03": frozenset({"read", "install"}),
    "MP-04": frozenset({"read", "feed", "refresh", "restart"}),
    "MP-05": frozenset({"read", "apply", "fault"}),
    "MP-06": frozenset({"read", "install", "configure"}),
}
MODULE = "lakebase_qualification"
DOCUMENT_ID = "arras-lakebase-qualification-v1"
QUERY = "SELECT p.code, p.value FROM lakebase_qualification.Probe p ORDER BY p.code"


def allowed(inputs: object, case: str) -> None:
    authorization = inputs.authorization
    if case not in authorization.get("allowed_cases", ()):
        raise Blocked("case_not_authorized")
    if not CASE_OPERATIONS[case].issubset(set(authorization.get("allowed_operations", ()))):
        raise Blocked("required_operation_not_authorized")


def is_authorized(inputs: object, case: str) -> bool:
    try:
        allowed(inputs, case)
    except Blocked:
        return False
    return True


class Blocked(Exception):
    """A required authorized capability or independently observed fact is unavailable."""

    def __init__(self, code: str) -> None:
        self.code = code


class Failed(Exception):
    """An executed managed operation contradicted a measured postcondition."""

    def __init__(self, code: str) -> None:
        self.code = code


def digest(value: object, code: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise Blocked(code)
    return value
