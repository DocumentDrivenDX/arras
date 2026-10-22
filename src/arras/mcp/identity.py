# SPDX-License-Identifier: MIT OR Apache-2.0
"""Who the process serves: the token it was launched with (CONTRACT-007, Identity).

Arras does not issue or validate a token; the backends do. The user name and groups are read
from the token's claims without checking its signature, only to label the session and attribute
changes the backends will themselves attribute from the authenticated token.
"""

from __future__ import annotations

import base64
import json
import math
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from arras.mcp.config import DEFAULT_USER_CLAIMS, Config
from arras.types import Principal

GROUP_CLAIMS = ("groups", "roles")
REFRESH_BEFORE_EXPIRY = 60.0


def claims_of(token: str) -> dict[str, Any] | None:
    """The payload of a JWT-shaped token, or `None` if it is not one."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        claims = json.loads(raw)
    except ValueError:
        return None
    return claims if isinstance(claims, dict) else None  # type: ignore[reportUnknownVariableType]


def principal_from_token(
    token: str, user_claims: tuple[str, ...] = DEFAULT_USER_CLAIMS
) -> Principal | None:
    """A `Principal` for a usable token: well formed, with a user claim; `None` otherwise."""
    claims = claims_of(token.strip())
    if claims is None:
        return None
    user = next((str(claims[c]) for c in user_claims if isinstance(claims.get(c), str)), None)
    if not user:
        return None
    groups: list[str] = []
    for c in GROUP_CLAIMS:
        v = claims.get(c)
        if isinstance(v, list):
            groups += [str(g) for g in v]  # type: ignore[reportUnknownVariableType]
    return Principal(user=user, token=token.strip(), groups=tuple(groups))


class TokenSource:
    """Yields the current principal, re-reading the token file when it changes or nears expiry,
    so the host can refresh the token without restarting the process."""

    def __init__(
        self,
        *,
        token: str | None = None,
        token_file: str | None = None,
        user_claims: tuple[str, ...] = DEFAULT_USER_CLAIMS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.token, self.token_file, self.user_claims, self.clock = (
            token,
            token_file,
            user_claims,
            clock,
        )
        self._seen: tuple[float, int] | None = None
        self._principal: Principal | None = None
        self._exp: float | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> TokenSource:
        return cls.from_config(Config.from_env(env))

    @classmethod
    def from_config(cls, config: Config) -> TokenSource:
        return cls(token=config.token, token_file=config.token_file, user_claims=config.user_claims)

    def current(self) -> Principal | None:
        """The principal now, or `None` when there is no usable token."""
        if self.token_file:
            try:
                st = Path(self.token_file).stat()
                stamp = (st.st_mtime, st.st_size)
                near_expiry = (
                    self._exp is not None and self.clock() >= self._exp - REFRESH_BEFORE_EXPIRY
                )
                if stamp != self._seen or near_expiry:
                    self._seen = stamp
                    self._load(Path(self.token_file).read_text())
            except OSError:
                self._principal, self._exp, self._seen = None, None, None
        elif self._principal is None and self.token and self._seen is None:
            self._seen = (0.0, 0)
            self._load(self.token)
        if self._exp is not None and self._exp <= self.clock():
            self._principal = None  # a token that expired after it was loaded is never sent on
        return self._principal

    def _load(self, token: str) -> None:
        self._principal = principal_from_token(token, self.user_claims)
        claims = claims_of(token.strip()) or {}
        exp = claims.get("exp")
        self._exp = float(exp) if isinstance(exp, int | float) and math.isfinite(exp) else None
        if self._exp is None and "exp" in claims:
            self._principal = None  # an exp that is not a time is not a usable token
