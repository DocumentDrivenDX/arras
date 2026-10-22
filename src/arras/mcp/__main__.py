# SPDX-License-Identifier: MIT OR Apache-2.0
"""`python -m arras.mcp`: the only Arras code that reads the environment (CONTRACT-005, 007).

The configuration is `arras.mcp.config`: identity from `ARRAS_TOKEN_FILE` (re-read when it
changes or nears expiry) or `ARRAS_TOKEN`, backend handles from `ARRAS_BACKEND_<NAME>_ENDPOINT`
or the ops file, everything dev-owned (placement included) from the committed `config/*.toml`.
A handle that is a PostgreSQL URI is a Truss backend (`arras.mcp.backends`); a handle no adapter
reads leaves the server degraded: `describe` says so and every other tool answers `unavailable`.
The libpq environment (`PG*`) is cleared before the first connection. `ARRAS_DEV_SANDBOX=1`
serves the fake sandbox instead, for trying a client against it. A configuration that cannot be used ends the process with status 2
and each offending key on stderr, never its value. Diagnostics go to stderr; stdout carries
protocol frames only. One startup line on stderr names the environment and the files read.

The process is disposable: SIGTERM and SIGINT finish the frame in flight, stop reading and exit with
status 0. It holds no state a restart needs, so a kill at any other moment loses nothing either.
"""

from __future__ import annotations

import logging
import signal
import sys
from collections.abc import Iterator
from types import FrameType

from arras.core import Arras
from arras.mcp import McpServer, TokenSource, serve
from arras.mcp.backends import build_backends
from arras.mcp.config import Config, ConfigError, scrub_ambient_connection_environment

log = logging.getLogger("arras.mcp")


class _Stop(BaseException):
    """Raised by the signal handler only while the loop waits for a frame."""


class _Frames:
    """Stdin lines, ending when a stop signal arrives. A signal during the blocking read ends it
    at once; a signal while a frame is being handled is noted and takes effect between frames."""

    def __init__(self, stream: object) -> None:
        self._stream = stream
        self.stopping = False
        self._waiting = False

    def request_stop(self, signum: int, frame: FrameType | None) -> None:
        self.stopping = True
        if self._waiting:
            raise _Stop

    def __iter__(self) -> Iterator[str]:
        try:
            while not self.stopping:
                self._waiting = True
                try:
                    line: str = self._stream.readline()  # type: ignore[attr-defined]
                finally:
                    self._waiting = False
                if not line:
                    return
                yield line
        except _Stop:
            return


def main() -> None:
    try:
        config = Config.from_env()
    except ConfigError as e:
        for problem in e.problems:
            print(f"arras.mcp: configuration: {problem}", file=sys.stderr)
        raise SystemExit(2) from None
    config.configure_logging(sys.stderr)
    print(config.startup_line(), file=sys.stderr, flush=True)
    if config.dev_sandbox:
        from arras.sandbox import Sandbox

        box = Sandbox().seed()
        server = McpServer(box.arras, lambda: box.principal(config.dev_user))
    else:
        scrub_ambient_connection_environment()
        try:
            backends, unbuilt = build_backends(config)
        except ConfigError as e:
            for problem in e.problems:
                print(f"arras.mcp: configuration: {problem}", file=sys.stderr)
            raise SystemExit(2) from None
        for name, reason in unbuilt.items():
            log.warning("backend %s has an endpoint but no adapter was built: %s", name, reason)
        tokens = TokenSource.from_config(config)
        server = McpServer(
            Arras.start(
                backends,
                expected=tuple(config.endpoints),
                placement=config.placements,
                default_placement=config.default_placement,
            ),
            tokens.current,
        )
    out, sys.stdout = sys.stdout, sys.stderr  # a stray print cannot corrupt the frames
    frames = _Frames(sys.stdin)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, frames.request_stop)
    serve(frames, out, server)
    out.flush()


if __name__ == "__main__":
    main()
