# SPDX-License-Identifier: MIT OR Apache-2.0
"""An independent host needs no UI module to construct the public API bindings."""

import subprocess
import sys


def test_public_api_factories_construct_without_loading_the_ui():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from arras import console, operate
from arras.testing import InMemory, example_module

world = InMemory()
world.register(example_module())
principal = world.person("viewer", "catalog", "read")
identity = lambda request: principal
policy = lambda principal: False
apps = (
    console.create_app(world.arras, principal_for_request=identity, base_path="/host/console"),
    operate.create_app(world.arras, principal_for_request=identity,
                       authorize_operator=policy, base_path="/host/operate"),
    operate.create_schema_app(world.arras, principal_for_request=identity,
                              authorize_operator=policy, base_path="/host/schema"),
)
assert all(callable(app) for app in apps)
assert not any(name == "arras.ui" or name.startswith("arras.ui.") for name in sys.modules)
world.arras.close()
""",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
