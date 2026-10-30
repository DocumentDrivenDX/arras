# SPDX-License-Identifier: MIT OR Apache-2.0
"""`arras`: one command for the module entry points.

    arras doctor [options]    python -m arras.doctor
    arras devhost [options]   python -m arras.devhost
    arras mcp [options]       python -m arras.mcp
    arras --version

Each subcommand hands the rest of the command line to the module's own `main`, so the options,
output and exit status are those of the module. The module entry points are unchanged. A
distribution that rebrands a launcher keeps calling `arras.devhost.main(distribution=...)` and
`arras.mcp.launch(distribution=...)`; this command always runs the unbranded launchers.
"""

from __future__ import annotations

import sys
from importlib import metadata

SUBCOMMANDS = ("doctor", "devhost", "mcp")

_USAGE = """\
usage: arras [-h] [--version] {doctor,devhost,mcp} ...

commands:
  doctor    check the installation (python -m arras.doctor)
  devhost   serve the console over fake data on loopback (python -m arras.devhost)
  mcp       run the MCP stdio server (python -m arras.mcp)

Run `arras <command> --help` for the options of a command.
"""


def _version() -> str:
    try:
        return metadata.version("arras")
    except metadata.PackageNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        out = sys.stdout if args else sys.stderr
        out.write(_USAGE)
        return 0 if args else 2
    command, rest = args[0], args[1:]
    if command in ("-V", "--version"):
        sys.stdout.write(f"arras {_version()}\n")
        return 0
    if command == "doctor":
        from arras import doctor

        return doctor.main(rest)
    if command == "devhost":
        from arras import devhost

        devhost.main(rest)
        return 0
    if command == "mcp":
        from arras import mcp

        mcp.launch(rest)
        return 0
    sys.stderr.write(f"arras: unknown command {command!r}\n{_USAGE}")
    return 2


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    run()
