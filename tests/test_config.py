# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The MCP process's configuration (CONTRACT-007): one schema, one reader, no value in a message."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

import arras.mcp.config as config_module
from arras.mcp.backends import build_backends
from arras.mcp.config import DEFAULT_USER_CLAIMS, KEYS, NAMES, Config, ConfigError
from arras.model import Placement

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_ambient_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default config directory is relative to the working directory: keep it empty here."""
    monkeypatch.chdir(tmp_path)


def files(tmp_path: Path, **named: str) -> dict[str, str]:
    """Write `<name>.toml` under tmp_path/cfg and return the environment pointing at it."""
    d = tmp_path / "cfg"
    d.mkdir(exist_ok=True)
    for name, text in named.items():
        (d / f"{name}.toml").write_text(text)
    return {"ARRAS_CONFIG_DIR": str(d)}


def test_nothing_set_is_the_defaults_and_no_backend() -> None:
    c = Config.from_env({})
    assert c.endpoints == {} and c.token is None and c.token_file is None
    assert (c.log_level, c.dev_sandbox, c.dev_user) == ("INFO", False, "alice")
    assert c.user_claims == ("preferred_username", "email", "sub")


def test_ops_keys_are_read_and_a_blank_one_is_unset() -> None:
    c = Config.from_env(
        {
            "ARRAS_BACKEND_PRIMARY_ENDPOINT": "primary.example",
            "ARRAS_BACKEND_MIRROR_ENDPOINT": "  ",
            "ARRAS_TOKEN_FILE": "/run/token",
        }
    )
    assert c.endpoints == {"primary": "primary.example"} and c.token_file == "/run/token"


def test_an_endpoint_key_names_the_backend_the_host_calls_it() -> None:
    c = Config.from_env(
        {
            "ARRAS_BACKEND_LAKE_2_ENDPOINT": "a.example",
            "ARRAS_BACKEND_WAREHOUSE_ENDPOINT": "b.example",
        }
    )
    assert c.endpoints == {"lake_2": "a.example", "warehouse": "b.example"}


def test_a_misspelled_arras_key_is_refused_not_ignored() -> None:
    keys = ("ARRAS_TRUSS_ENDPOINT", "ARRAS_BACKEND_ENDPOINT", "ARRAS_BACKEND_x_ENDPOINT")
    for key in (*keys, "ARRAS_PLACEMENT", "ARRAS_PLACEMENT_CATALOG"):  # placement is files only
        with pytest.raises(ConfigError) as e:
            Config.from_env({key: "v.example"})
        assert e.value.problems == [f"{key}: not an Arras key"]
        assert "v.example" not in str(e.value)


def test_dev_keys_override_their_defaults() -> None:
    c = Config.from_env({"ARRAS_LOG_LEVEL": "debug", "ARRAS_USER_CLAIM": "sub,email"})
    assert c.log_level == "DEBUG" and c.user_claims == ("sub", "email")


def test_every_problem_is_reported_by_key_and_never_by_value() -> None:
    secret = "tok-SECRET-value"
    with pytest.raises(ConfigError) as e:
        Config.from_env(
            {
                "ARRAS_LOG_LEVEL": "loud",
                "ARRAS_BACKEND_ENDPOINT": "typo.example",  # a misspelled key is not silent
                "ARRAS_TOKEN": secret,
                "ARRAS_TOKEN_FILE": "/run/token",
            }
        )
    keys = sorted(p.split(":")[0] for p in e.value.problems)
    assert keys == ["ARRAS_BACKEND_ENDPOINT", "ARRAS_LOG_LEVEL", "ARRAS_TOKEN"]
    assert secret not in str(e.value) and "typo.example" not in str(e.value)


def test_the_administrators_keys_are_not_this_processs_and_not_an_error() -> None:
    c = Config.from_env(
        {
            "ARRAS_ADMIN_TOKEN": "x",
            "ARRAS_ADMIN_USER": "root",
            "ARRAS_REQUIRE_WEFT": "1",
            "ARRAS_REQUIRE_UMF": "1",
        }
    )
    assert c == Config()


def test_user_claims_are_trimmed_and_an_empty_list_is_the_default() -> None:
    assert Config.from_env({"ARRAS_USER_CLAIM": "email, sub"}).user_claims == ("email", "sub")
    assert Config.from_env({"ARRAS_USER_CLAIM": ","}).user_claims == DEFAULT_USER_CLAIMS


def test_other_environment_variables_are_not_ours_to_judge() -> None:
    assert Config.from_env({"PATH": "/bin", "DATABRICKS_HOST": "h"}).endpoints == {}


def test_the_token_is_never_shown() -> None:
    assert "SECRET" not in repr(Config(token="SECRET"))


def test_a_configured_handle_without_an_adapter_is_named_not_pretended() -> None:
    config = Config.from_env({"ARRAS_BACKEND_PRIMARY_ENDPOINT": "primary.example"})
    backends, unbuilt = build_backends(config)
    assert backends == {} and list(unbuilt) == ["primary"]
    assert "primary.example" not in unbuilt["primary"]
    assert build_backends(Config()) == ({}, {})


def test_a_postgresql_handle_builds_a_truss_backend_named_by_its_key() -> None:
    pytest.importorskip("truss")
    from arras.adapters.truss import TrussBackend

    config = Config.from_env(
        {
            "ARRAS_BACKEND_PRIMARY_ENDPOINT": "postgresql://db.example:5432/h",
            "ARRAS_BACKEND_OTHER_ENDPOINT": "somewhere-else",
        }
    )
    backends, unbuilt = build_backends(config)
    assert list(backends) == ["primary"] and list(unbuilt) == ["other"]
    backend = backends["primary"]
    assert isinstance(backend, TrussBackend) and backend.name == "primary"
    # the process holds no installing connection: it cannot migrate (CONTRACT-007)
    status = backend.status()
    assert (status.available, status.reason) == (False, "not_configured")


def test_a_postgresql_handle_that_is_not_an_endpoint_names_its_key_and_never_its_value() -> None:
    pytest.importorskip("truss")
    config = Config.from_env(
        {"ARRAS_BACKEND_PRIMARY_ENDPOINT": "postgresql://bob:hunter2@db.example/h"}
    )
    with pytest.raises(ConfigError) as e:
        build_backends(config)
    assert e.value.problems and "ARRAS_BACKEND_PRIMARY_ENDPOINT" in e.value.problems[0]
    assert "hunter2" not in str(e.value) and "bob" not in str(e.value)


def test_a_missing_extra_leaves_the_handle_unbuilt_and_says_which_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arras.adapters.truss as truss_adapter

    def absent() -> str:
        raise ImportError("truss-toolkit 0.0.48 is not installed")

    monkeypatch.setattr(truss_adapter, "require_toolkit", absent)
    config = Config.from_env({"ARRAS_BACKEND_PRIMARY_ENDPOINT": "postgresql://db.example/h"})
    backends, unbuilt = build_backends(config)
    assert backends == {} and "arras[truss]" in unbuilt["primary"]


def test_scrubbing_removes_every_libpq_variable_and_only_those() -> None:
    env = {
        "PGSERVICE": "svc",
        "PGOPTIONS": "-c role=bob",
        "PGHOST": "elsewhere",
        "PGPASSWORD": "pw-SECRET",
        "ARRAS_TOKEN": "t",
        "PATH": "/bin",
        "PYTHONPATH": "/x",
    }
    removed = config_module.scrub_ambient_connection_environment(env)
    assert removed == ["PGHOST", "PGOPTIONS", "PGPASSWORD", "PGSERVICE"]
    assert env == {"ARRAS_TOKEN": "t", "PATH": "/bin", "PYTHONPATH": "/x"}


def test_default_file_is_layer_three(tmp_path: Path) -> None:
    env = files(tmp_path, default='log_level = "warning"\ndev_user = "pat"\n')
    c = Config.from_env(env)
    assert (c.log_level, c.dev_user, c.env) == ("WARNING", "pat", None)
    assert c.sources == (str(tmp_path / "cfg" / "default.toml"),)
    assert "env=none" in c.startup_line() and "default.toml" in c.startup_line()


def test_environment_file_overrides_the_default_key_by_key(tmp_path: Path) -> None:
    env = files(
        tmp_path,
        default=(
            'log_level = "WARNING"\ndev_user = "pat"\n[placement]\nrecord = "a"\n'
            'replicas = ["b"]\n[modules.catalog]\nrecord = "a"\n'
        ),
        staging='log_level = "DEBUG"\n[placement]\nreplicas = ["c"]\n[modules.billing]\nrecord = "c"\n',
    )
    c = Config.from_env(
        {**env, "ARRAS_ENV": "staging", **{f"ARRAS_BACKEND_{n}_ENDPOINT": "e" for n in "ABC"}}
    )
    assert (c.log_level, c.dev_user, c.env) == ("DEBUG", "pat", "staging")  # key by key
    assert c.default_placement == Placement("a", ("c",))  # tables merge, a list replaces
    assert c.placements == {"catalog": Placement("a"), "billing": Placement("c")}
    assert [Path(x).name for x in c.sources] == ["default.toml", "staging.toml"]


def test_ops_values_override_the_files(tmp_path: Path) -> None:
    ops = tmp_path / "ops.toml"
    ops.write_text(
        '[backends.a]\nendpoint = "from-file.example"\n[backends.b]\nendpoint = "b.example"\n'
    )
    env = files(tmp_path, default='log_level = "WARNING"\ndev_sandbox = false\n')
    c = Config.from_env(
        {
            **env,
            "ARRAS_OPS_FILE": str(ops),
            "ARRAS_BACKEND_A_ENDPOINT": "from-env.example",
            "ARRAS_LOG_LEVEL": "error",  # an incident override of a dev key
            "ARRAS_DEV_SANDBOX": "1",
        }
    )
    assert c.endpoints == {"a": "from-env.example", "b": "b.example"}  # env wins, file fills in
    assert (c.log_level, c.dev_sandbox) == ("ERROR", True)
    assert str(ops) in c.sources


def test_a_committed_file_may_not_carry_an_ops_key(tmp_path: Path) -> None:
    text = (
        'endpoint = "SECRET-one"\nARRAS_TOKEN = "SECRET-two"\n'
        '[placement]\nrecord = "a"\ntoken = "SECRET-three"\n[backends.a]\nendpoint = "SECRET-four"\n'
    )
    env = files(tmp_path, default=text)
    with pytest.raises(ConfigError) as e:
        Config.from_env(env)
    path = str(tmp_path / "cfg" / "default.toml")
    assert sorted(e.value.problems) == sorted(
        f"{path}: {k}: an ops key; ops values never live in a committed file"
        for k in ("endpoint", "ARRAS_TOKEN", "placement.token", "backends")
    )
    assert "SECRET" not in str(e.value)


def test_placement_comes_from_the_files(tmp_path: Path) -> None:
    env = files(
        tmp_path,
        default=(
            '[placement]\nrecord = "primary"\nreplicas = ["mirror"]\n'
            '[modules.catalog]\nrecord = "primary"\nreplicas = ["mirror", "cold"]\n'
            '[modules.catalog.providers]\n"catalog.ImportFromX" = "upstream"\n'
        ),
    )
    ends = {f"ARRAS_BACKEND_{n}_ENDPOINT": "e" for n in ("PRIMARY", "MIRROR", "COLD", "UPSTREAM")}
    c = Config.from_env({**env, **ends})
    assert c.default_placement == Placement("primary", ("mirror",))
    assert c.placements == {
        "catalog": Placement("primary", ("mirror", "cold"), {"catalog.ImportFromX": "upstream"})
    }
    with pytest.raises(
        ConfigError
    ) as e:  # a backend without an endpoint names the table, not a value
        Config.from_env({**env, "ARRAS_BACKEND_PRIMARY_ENDPOINT": "secret.example"})
    keys = sorted(p.split(":")[0] for p in e.value.problems)
    assert keys == ["[modules.catalog]"] * 3 + ["[placement]"]
    assert "secret.example" not in str(e.value)
    sandbox = Config.from_env({**env, "ARRAS_DEV_SANDBOX": "1"})  # the sandbox needs no endpoint
    assert sandbox.dev_sandbox and sandbox.endpoints == {}


def test_a_malformed_placement_table_is_named_by_file_and_key(tmp_path: Path) -> None:
    env = files(
        tmp_path,
        default='[modules.catalog]\nreplicas = ["Mirror-SECRET"]\n[placement]\nrecord = 3\n',
    )
    with pytest.raises(ConfigError) as e:
        Config.from_env(env)
    assert [p.split(": ")[1] for p in e.value.problems] == [
        "modules.catalog.replicas",
        "placement.record",
    ]
    assert "SECRET" not in str(e.value)
    env = files(tmp_path, default='[modules.catalog]\nreplicas = ["a"]\n')
    with pytest.raises(ConfigError) as e:
        Config.from_env(env)
    assert [p.split(": ")[1] for p in e.value.problems] == ["[modules.catalog].record"]


def test_unknown_file_keys_are_refused_by_name(tmp_path: Path) -> None:
    env = files(tmp_path, default='colour = "SECRET"\n[placement]\nrecord = "a"\nsparkle = 1\n')
    with pytest.raises(ConfigError) as e:
        Config.from_env(env)
    path = str(tmp_path / "cfg" / "default.toml")
    assert e.value.problems == [
        f"{path}: colour: unknown key",
        f"{path}: placement.sparkle: unknown key",
    ]
    assert "SECRET" not in str(e.value)


def test_the_ops_file_carries_endpoints_only(tmp_path: Path) -> None:
    ops = tmp_path / "ops.toml"
    ops.write_text('log_level = "DEBUG"\n[backends.a]\nendpoint = "x.example"\nlevel = "SECRET"\n')
    with pytest.raises(ConfigError) as e:
        Config.from_env({"ARRAS_OPS_FILE": str(ops)})
    assert e.value.problems == [
        f"{ops}: log_level: the ops file carries [backends.<name>] endpoint only",
        f"{ops}: backends.a.level: the ops file carries endpoint only",
    ]
    assert "SECRET" not in str(e.value)


def test_a_missing_named_environment_file_is_an_error(tmp_path: Path) -> None:
    env = files(tmp_path)  # no default.toml is fine; a named environment's file must exist
    assert Config.from_env(env).sources == ()
    with pytest.raises(ConfigError) as e:
        Config.from_env({**env, "ARRAS_ENV": "prod"})
    assert e.value.problems == [f"{tmp_path / 'cfg' / 'prod.toml'}: file does not exist"]
    with pytest.raises(ConfigError) as e:
        Config.from_env({"ARRAS_ENV": "../prod"})
    assert e.value.problems == ["ARRAS_ENV: a name [a-z][a-z0-9_-]*"]
    with pytest.raises(ConfigError) as e:
        Config.from_env({"ARRAS_OPS_FILE": str(tmp_path / "nope.toml")})
    assert "ARRAS_OPS_FILE" in e.value.problems[0] and "does not exist" in e.value.problems[0]


def test_a_file_that_is_not_toml_is_named_with_its_line_and_no_content(tmp_path: Path) -> None:
    env = files(tmp_path, default='log_level = "INFO"\nsecret-thing = = SECRET\n')
    with pytest.raises(ConfigError) as e:
        Config.from_env(env)
    assert e.value.problems == [f"{tmp_path / 'cfg' / 'default.toml'}: not valid TOML at line 2"]


def test_the_committed_default_file_matches_the_schema() -> None:
    c = Config.from_env({"ARRAS_CONFIG_DIR": str(ROOT / "config")})
    assert c.sources == (str(ROOT / "config" / "default.toml"),)
    dev = {k.name: k.default for k in KEYS if k.owner == "dev"}
    assert c.log_level == dev["ARRAS_LOG_LEVEL"] and c.dev_user == dev["ARRAS_DEV_USER"]
    assert c.user_claims == tuple(str(dev["ARRAS_USER_CLAIM"]).split(","))
    assert c.dev_sandbox is False and c.endpoints == {} and c.placements == {}
    # the example shows every table and is a valid file for the environment `example`
    ex = Config.from_env(
        {
            "ARRAS_CONFIG_DIR": str(ROOT / "config"),
            "ARRAS_ENV": "example",
            **{
                f"ARRAS_BACKEND_{n}_ENDPOINT": "e"
                for n in ("PRIMARY", "MIRROR", "BULK", "UPSTREAM")
            },
        }
    )
    assert ex.default_placement is not None and "catalog" in ex.placements
    assert config_module.NAMED_KEYS and not any("PLACEMENT" in n for n in config_module.NAMED_KEYS)
    # no ops value is committed: every key of the committed files is a dev key
    for name in ("default", "example"):
        text = (ROOT / "config" / f"{name}.toml").read_text()
        assert not re.search(r"^\s*(endpoint|token|ARRAS_)", text, flags=re.M | re.I)


def test_the_example_file_lists_exactly_the_schema() -> None:
    text = (ROOT / ".env.example").read_text()
    listed = re.findall(r"^([A-Z_]+)=", text, flags=re.M)
    assert sorted(listed) == sorted(NAMES) and len(listed) == len(set(listed))
    for k in KEYS:
        if k.owner == "dev":
            assert f"{k.name}={k.default}" in text  # a dev key carries its default
        else:
            assert f"{k.name}=\n" in text  # an ops key carries none: nothing real is committed


def test_a_bad_configuration_ends_the_process_with_the_key_on_stderr_only() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "arras.mcp"],
        env={"ARRAS_LOG_LEVEL": "loud", "ARRAS_TOKEN": "tok-SECRET", "PATH": ""},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 2 and done.stdout == ""
    assert "ARRAS_LOG_LEVEL" in done.stderr and "tok-SECRET" not in done.stderr


def test_a_handle_that_is_not_an_endpoint_ends_the_process_naming_the_key_only() -> None:
    pytest.importorskip("truss")
    done = subprocess.run(
        [sys.executable, "-m", "arras.mcp"],
        env={
            "ARRAS_BACKEND_PRIMARY_ENDPOINT": "postgresql://bob:hunter2@db.example/h",
            "PATH": "",
        },
        input="",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 2 and done.stdout == ""
    assert "ARRAS_BACKEND_PRIMARY_ENDPOINT" in done.stderr and "hunter2" not in done.stderr


def test_ambient_libpq_variables_do_not_reach_the_persons_connection() -> None:
    """The process clears PG* before it connects: PGSERVICE (which no connection keyword can switch
    off), PGOPTIONS and PGHOST name nothing the person's call uses."""
    pytest.importorskip("truss")
    done = subprocess.run(
        [sys.executable, "-m", "arras.mcp"],
        env={
            "ARRAS_BACKEND_PRIMARY_ENDPOINT": "postgresql:///h?host=/nonexistent-dir",
            "ARRAS_TOKEN": "tok-SECRET",
            "PGSERVICE": "no-such-service",
            "PGOPTIONS": "-c role=intruder",
            "PGHOST": "intruder.example",
            "PGPASSWORD": "pw-SECRET",
            "PATH": "",
        },
        input=(
            '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"describe","arguments":{}}}\n'
        ),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0
    for secret in ("intruder", "no-such-service", "pw-SECRET", "tok-SECRET"):
        assert secret not in done.stderr and secret not in done.stdout


def test_a_handle_with_no_adapter_starts_the_process_degraded_and_says_so_on_stderr() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "arras.mcp"],
        env={"ARRAS_BACKEND_PRIMARY_ENDPOINT": "primary.example", "PATH": ""},
        input="",  # the host closes stdin: the server ends cleanly
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0 and done.stdout == ""
    assert "backend primary has an endpoint" in done.stderr and "primary.example" not in done.stderr


def test_custom_prefix_aliases_normalize_once_and_custom_values_win(tmp_path: Path) -> None:
    env = files(tmp_path, default='dev_user = "file-user"\n')
    env.update(
        {
            "TENANT_ENV": "",
            "TENANT_DEV_USER": "custom-user",
            "ARRAS_DEV_USER": "canonical-user",
            "TENANT_TOKEN": "secret",
        }
    )
    selected = __import__("arras.distribution", fromlist=["DistributionConfig"]).DistributionConfig(
        env_prefix="TENANT"
    )
    c = Config.from_env(env, distribution=selected)
    assert c.dev_user == "custom-user" and c.token == "secret"
    assert c.distribution.env_prefix == "TENANT"


def test_alias_credentials_conflict_even_when_custom_value_would_win() -> None:
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(env_prefix="TENANT")
    with pytest.raises(ConfigError) as e:
        Config.from_env({"TENANT_TOKEN": "one", "ARRAS_TOKEN": "two"}, distribution=selected)
    assert "TENANT_TOKEN" in str(e.value) and "ARRAS_TOKEN" in str(e.value)
    assert "one" not in str(e.value) and "two" not in str(e.value)


def test_any_token_and_token_file_alias_pair_is_refused() -> None:
    from arras.distribution import DistributionConfig

    with pytest.raises(ConfigError):
        Config.from_env(
            {"ARRAS_TOKEN": "secret", "TENANT_TOKEN_FILE": "/run/secret"},
            distribution=DistributionConfig(env_prefix="TENANT"),
        )


def test_unknown_keys_in_custom_namespace_fail_but_other_namespaces_are_untouched() -> None:
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(env_prefix="TENANT")
    with pytest.raises(ConfigError, match="TENANT_MISSPELLED"):
        Config.from_env({"TENANT_MISSPELLED": "hidden"}, distribution=selected)
    assert Config.from_env({"OTHER_MISSPELLED": "ignored"}, distribution=selected) == Config(
        distribution=selected
    )


def test_committed_distribution_can_set_brand_but_not_bootstrap_prefix(tmp_path: Path) -> None:
    from arras.distribution import DistributionConfig

    env = files(
        tmp_path,
        default='[distribution]\nmcp_server_name = "Acme"\nmcp_tool_prefix = "acme"\n[distribution.brand]\nname = "Acme"\n',
    )
    selected = DistributionConfig(env_prefix="TENANT")
    c = Config.from_env(env, distribution=selected)
    assert c.distribution.mcp_server_name == "Acme"
    assert c.distribution.brand.name == "Acme"
    assert c.distribution.env_prefix == "TENANT"
    env = files(tmp_path, default='[distribution]\nenv_prefix = "BAD"\n')
    with pytest.raises(ConfigError, match="env_prefix"):
        Config.from_env(env, distribution=selected)


def test_arras_prefixed_custom_environment_names_are_not_mistaken_for_canonical() -> None:
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(env_prefix="ARRAS_CUSTOM")
    c = Config.from_env({"ARRAS_CUSTOM_TOKEN": "secret"}, distribution=selected)
    assert c.token == "secret"


def test_blank_custom_alias_falls_back_to_canonical_value() -> None:
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(env_prefix="TENANT")
    c = Config.from_env(
        {"TENANT_DEV_USER": "  ", "ARRAS_DEV_USER": "canonical"}, distribution=selected
    )
    assert c.dev_user == "canonical"


def test_blank_credential_alias_does_not_hide_nonblank_credential() -> None:
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(env_prefix="TENANT")
    c = Config.from_env({"TENANT_TOKEN": " ", "ARRAS_TOKEN": "secret"}, distribution=selected)
    assert c.token == "secret"


def test_custom_blank_fallback_is_independent_of_environment_mapping_order() -> None:
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(env_prefix="TENANT")
    for env in (
        {"TENANT_TOKEN": " ", "ARRAS_TOKEN": "usable"},
        {"ARRAS_TOKEN": "usable", "TENANT_TOKEN": " "},
    ):
        assert Config.from_env(env, distribution=selected).token == "usable"


def test_distribution_tables_merge_brand_fields_across_environment_layers(tmp_path: Path) -> None:
    env = files(
        tmp_path,
        default='[distribution]\nmcp_server_name = "Default"\n[distribution.brand]\nname = "Default Brand"\ntagline = "base"\n',
        prod='[distribution.brand]\ntitle = "Production"\n',
    )
    env["ARRAS_ENV"] = "prod"
    config = Config.from_env(env)
    assert config.distribution.mcp_server_name == "Default"
    assert config.distribution.brand.name == "Default Brand"
    assert config.distribution.brand.tagline == "base"
    assert config.distribution.brand.title == "Production"


def test_invalid_distribution_file_values_name_the_field_without_echoing_value(
    tmp_path: Path,
) -> None:
    secret = "bad-secret-prefix"
    env = files(tmp_path, default=f'[distribution]\nmcp_tool_prefix = "{secret}"\n')
    with pytest.raises(ConfigError) as e:
        Config.from_env(env)
    assert "distribution.mcp_tool_prefix" in str(e.value)
    assert secret not in str(e.value)


def test_distribution_telemetry_names_merge_by_field_and_reject_invalid_values(
    tmp_path: Path,
) -> None:
    env = files(
        tmp_path,
        default="""[distribution.telemetry]
attribute_namespace = "example.attrs"
log_prefix = "example.logs"
""",
        local="""[distribution.telemetry]
event_prefix = "example.events"
""",
    )
    config = Config.from_env({**env, "ARRAS_ENV": "local"})
    assert config.distribution.telemetry.service_name is None
    assert config.distribution.telemetry.attribute_namespace == "example.attrs"
    assert config.distribution.telemetry.log_prefix == "example.logs"
    assert config.distribution.telemetry.event_prefix == "example.events"

    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    invalid = files(
        bad_root,
        default="""[distribution.telemetry]
attribute_namespace = "Example.attrs"
""",
    )
    with pytest.raises(ConfigError) as error:
        Config.from_env(invalid)
    assert error.value.problems == ["distribution.telemetry.attribute_namespace: invalid value"]


def test_alias_values_that_differ_warn_by_name_and_the_custom_value_is_used() -> None:
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(env_prefix="EXAMPLE")
    c = Config.from_env(
        {"EXAMPLE_DEV_USER": "alice", "ARRAS_DEV_USER": "bob-sentinel"}, distribution=selected
    )
    assert c.dev_user == "alice"
    assert c.warnings == (
        "EXAMPLE_DEV_USER and ARRAS_DEV_USER are both set to different values; "
        "EXAMPLE_DEV_USER is used",
    )
    assert "bob-sentinel" not in " ".join(c.warnings) and "alice" not in " ".join(c.warnings)


def test_equal_blank_and_single_aliases_do_not_warn() -> None:
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(env_prefix="EXAMPLE")
    for env in (
        {"EXAMPLE_DEV_USER": "alice", "ARRAS_DEV_USER": " alice "},  # equal once trimmed
        {"EXAMPLE_DEV_USER": " ", "ARRAS_DEV_USER": "bob"},  # a blank alias is unset
        {"EXAMPLE_DEV_USER": "alice"},
        {"ARRAS_DEV_USER": "bob"},
    ):
        assert Config.from_env(env, distribution=selected).warnings == ()
    assert Config.from_env({"ARRAS_DEV_USER": "bob"}).warnings == ()  # one namespace


def test_alias_warnings_are_bounded_and_never_carry_secret_looking_values() -> None:
    from arras.distribution import DistributionConfig
    from arras.mcp.config import MAX_WARNINGS

    selected = DistributionConfig(env_prefix="EXAMPLE")
    env = {
        f"{p}_BACKEND_{n}_ENDPOINT": f"{p.lower()}-secret-{n}.example"
        for n in "ABCDEFGHIJKLM"
        for p in ("EXAMPLE", "ARRAS")
    }
    c = Config.from_env(env, distribution=selected)
    assert len(c.warnings) == MAX_WARNINGS + 1
    assert c.warnings[-1] == f"and {13 - MAX_WARNINGS} more alias conflicts"
    assert "secret" not in " ".join(c.warnings)
