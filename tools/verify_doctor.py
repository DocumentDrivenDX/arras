#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Qualify the offline compatibility doctor from an installed Arras wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/extension_host"
THEME = ROOT / "tests/downstream/theme-package"
SENTINEL = "doctor-secret-sentinel-never-report"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run(argv: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def report_from(
    result: subprocess.CompletedProcess[str], expected_status: int, label: str
) -> dict[str, Any]:
    assert result.returncode == expected_status, (
        f"{label}: expected exit {expected_status}, got {result.returncode}; "
        f"stdout={result.stdout[:700]!r}; stderr={result.stderr[:240]!r}"
    )
    if SENTINEL in result.stdout or SENTINEL in result.stderr:
        raise AssertionError(f"{label}: secret sentinel appeared in process output")
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"{label}: expected exactly one JSON report line"
    value = json.loads(lines[0])
    assert isinstance(value, dict) and type(value.get("ok")) is bool
    return value


def codes(report: dict[str, Any]) -> set[str]:
    return {row["code"] for row in report.get("diagnostics", [])}


def assert_case(
    python: Path,
    request_path: Path,
    cwd: Path,
    env: dict[str, str],
    label: str,
    *,
    status: int,
    code: str | None,
) -> dict[str, Any]:
    result = run(
        [str(python), "-I", "-m", "arras.doctor", "--request", str(request_path)], cwd=cwd, env=env
    )
    report = report_from(result, status, label)
    if code is not None:
        assert code in codes(report), f"{label}: expected {code}, got {sorted(codes(report))}"
    return report


def extract_page_manifest(wheel: Path, output: Path) -> Path:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        manifest_name = "arras/ui/static/asset-manifest.json"
        assert manifest_name in names, "selected wheel has no page asset manifest"
        manifest = json.loads(archive.read(manifest_name))
        root = output / "page-assets"
        root.mkdir(parents=True)
        selected = {manifest_name}
        for name in manifest["files"]:
            candidate = f"arras/ui/static/{name}"
            assert candidate in names, f"page asset is absent from the wheel: {name}"
            selected.add(candidate)
        for name in selected:
            relative = Path(name).relative_to("arras/ui/static")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    return root / "asset-manifest.json"


def make_theme_fixture(output: Path, ui_version: str, contracts: dict[str, int]) -> Path:
    output.mkdir(parents=True)
    package = json.loads((THEME / "package.json").read_text(encoding="utf-8"))
    files: dict[str, dict[str, str | int]] = {}
    for filename, mime in (("theme.css", "text/css"), ("favicon.svg", "image/svg+xml")):
        body = (THEME / "src" / filename).read_bytes()
        (output / filename).write_bytes(body)
        files[filename] = {
            "sha256": hashlib.sha256(body).hexdigest(),
            "size": len(body),
            "mime": mime,
        }
    manifest = {
        "format": "arras.ui.assets",
        "version": 1,
        "kind": "theme",
        "package": {"name": package["name"], "version": package["version"]},
        "contracts": contracts,
        "ui_versions": [ui_version],
        "entry": {"stylesheet": "theme.css", "favicon": "favicon.svg"},
        "files": files,
    }
    path = output / "theme-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def tripwire_script(request_json: Path, secret_file: Path, output: Path) -> Path:
    path = output / "tripwire.py"
    path.write_text(
        """from __future__ import annotations
import builtins, dataclasses, importlib, io, json, os, socket, subprocess, sys, urllib.request
from pathlib import Path
from arras import Arras
from arras.branding import Brand
from arras.distribution import DistributionConfig, TelemetryNames
from arras.doctor import DoctorRequest, check

request_data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
secret_path = str(Path(sys.argv[2]).resolve())
report_path = Path(sys.argv[3])
sentinel = "doctor-secret-sentinel-never-report"
events = []
def trip(name):
    events.append(name)
    raise AssertionError("forbidden doctor side effect: " + name)

original_open = builtins.open
original_io_open = io.open
original_os_open = os.open
def path_text(value):
    try: return str(Path(os.fspath(value)).resolve())
    except (TypeError, ValueError, OSError): return ""
def guarded_open(path, *args, **kwargs):
    if path_text(path) == secret_path: trip("secret-file-read")
    return original_open(path, *args, **kwargs)
def guarded_io_open(path, *args, **kwargs):
    if path_text(path) == secret_path: trip("secret-file-read")
    return original_io_open(path, *args, **kwargs)
def guarded_os_open(path, *args, **kwargs):
    if path_text(path) == secret_path: trip("secret-file-read")
    return original_os_open(path, *args, **kwargs)
builtins.open = guarded_open
io.open = guarded_io_open
os.open = guarded_os_open

class DeniedEnvironment(dict):
    def __getitem__(self, key): trip("environment-read:" + str(key))
    def get(self, key, default=None): trip("environment-read:" + str(key))
    def __iter__(self): trip("environment-iteration")
    def items(self): trip("environment-iteration")
    def values(self): trip("environment-iteration")
    def keys(self): trip("environment-iteration")
os.environ = DeniedEnvironment()

def denied(name):
    return lambda *args, **kwargs: trip(name)
socket.socket.connect = denied("network")
socket.socket.connect_ex = denied("network")
socket.create_connection = denied("network")
socket.getaddrinfo = denied("network")
urllib.request.urlopen = denied("network")
subprocess.Popen = denied("subprocess")
subprocess.run = denied("subprocess")
subprocess.call = denied("subprocess")
os.system = denied("subprocess")
Arras.register = denied("registration")

original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.startswith(("arras.adapters", "arras.fakes", "extension_host", "doctor_plugin_sentinel")):
        trip("forbidden-import:" + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import

distribution = request_data["distribution"]
brand = Brand(**distribution["brand"])
selected = DistributionConfig(
    brand=brand,
    mcp_server_name=distribution["mcp_server_name"],
    mcp_tool_prefix=distribution["mcp_tool_prefix"],
    env_prefix=distribution["env_prefix"],
    telemetry=TelemetryNames(**distribution["telemetry"]),
)
request = DoctorRequest(
    expected_packages=request_data["expected_packages"],
    expected_contracts=request_data["expected_contracts"],
    required_python_exports={k: tuple(v) for k, v in request_data["required_python_exports"].items()},
    required_npm_exports={k: tuple(v) for k, v in request_data["required_npm_exports"].items()},
    required_role_tokens=tuple(request_data["required_role_tokens"]),
    distribution=selected,
    env_names=tuple(request_data["env_names"]),
    config_files=tuple(Path(p) for p in request_data["config_files"]),
    asset_manifest=Path(request_data["asset_manifest"]),
    theme_manifest=Path(request_data["theme_manifest"]),
    module_documents=tuple(Path(p) for p in request_data["module_documents"]),
    module_profile=request_data["module_profile"],
)
positive = check(request)
invalid_config_request = dataclasses.replace(request, config_files=(Path(sys.argv[4]),))
invalid_config = check(invalid_config_request)
unsupported_request = DoctorRequest(
    module_documents=(Path(request_data["module_documents"][0]),),
    module_profile="doctor_plugin_sentinel",
)
unsupported = check(unsupported_request)
assert positive.ok and positive.complete
assert any(row.code == "config_invalid" for row in invalid_config.diagnostics)
assert any(row.code == "capability_unsupported" for row in unsupported.diagnostics)
assert not events, "forbidden operations attempted: " + ",".join(events)
rendered = json.dumps({"positive": positive.to_dict(), "invalid_config": invalid_config.to_dict(), "unsupported": unsupported.to_dict()})
assert sentinel not in rendered
assert not any(name.startswith(("arras.adapters", "arras.fakes", "extension_host")) for name in sys.modules)
report_path.write_text(json.dumps({"tripwires": "passed", "positive": positive.to_dict(), "invalid_config": invalid_config.to_dict(), "unsupported": unsupported.to_dict()}, indent=2) + "\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    del request_json
    return path


def launcher_probe_script(path: Path, config_dir: Path) -> Path:
    code = """from __future__ import annotations
import contextlib, io, json, os, sys, types
from arras.branding import Brand
from arras.distribution import DistributionConfig
from arras.mcp import launch
from arras.devhost import main as devhost_main

selected = DistributionConfig(
    brand=Brand(name="Tenant Catalog"),
    mcp_server_name="Tenant Catalog MCP",
    mcp_tool_prefix="tenant",
    env_prefix="TENANT",
)
def invoke(call):
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            call()
    except SystemExit as exc:
        return exc.code, out.getvalue(), err.getvalue()
    return None, out.getvalue(), err.getvalue()

code, out, err = invoke(lambda: launch(["--help"], distribution=selected))
assert code == 0 and "usage: arras.mcp" in out and "Tenant Catalog MCP stdio server" in out
code, out, err = invoke(lambda: launch(["--token", "argument-sentinel"], distribution=selected))
assert code == 2 and err == "Tenant Catalog: only --help is supported\\n"
assert "argument-sentinel" not in out + err
code, out, err = invoke(lambda: launch([], distribution=selected))
assert code == 2 and "Tenant Catalog: configuration: ARRAS_TOKEN: conflicting aliases" in err
assert "ARRAS_TOKEN" in err and "TENANT_TOKEN" in err
assert "launcher-secret-sentinel" not in out + err
code, out, err = invoke(lambda: devhost_main(["--help"], distribution=selected))
assert code == 0 and "Tenant Catalog development host" in out
assert "python -m arras.devhost" in out
code, out, err = invoke(lambda: devhost_main(["--token"], distribution=selected))
assert code == 2 and "unrecognized arguments: --token" in err

import arras.devhost as devhost
events = []
class FakeBox:
    def close(self):
        events.append("closed")
def fake_build(*args, **kwargs):
    events.append("build")
    return FakeBox()
def fake_app(box, **kwargs):
    events.append(("app", kwargs.get("distribution") is selected))
    return object()
def fake_run(app, **kwargs):
    events.append(("server", kwargs))
devhost.build = fake_build
devhost.DevHost = fake_app
sys.modules["uvicorn"] = types.SimpleNamespace(run=fake_run)
code, out, err = invoke(lambda: devhost_main([], distribution=selected))
assert code is None and "Tenant Catalog development host at http://127.0.0.1:8000" in out
assert events == ["build", ("app", True), ("server", {"host": "127.0.0.1", "port": 8000, "log_level": "info"}), "closed"]
assert "psycopg" not in sys.modules and "truss" not in sys.modules

with open(sys.argv[2], "w", encoding="utf-8") as stream:
    json.dump({
        "custom_mcp_help": "passed",
        "custom_mcp_unsupported_args": "passed",
        "alias_conflict_refused": "passed",
        "custom_devhost_help": "passed",
        "custom_devhost_unsupported_args": "passed",
        "custom_devhost_startup_forwarding": "passed",
        "effective_telemetry_names": "observed through public launch factory",
        "native_and_server_work": "mocked or not imported",
    }, stream)
"""
    path.write_text(code, encoding="utf-8")
    return path


def installed_launcher_probe(ctx: dict[str, Any]) -> dict[str, Any]:
    config_dir = ctx["temp"] / "empty-config"
    config_dir.mkdir()
    secret = "launcher-secret-sentinel"
    report_path = ctx["temp"] / "launcher-report.json"
    script = launcher_probe_script(ctx["temp"] / "installed-launcher-probe.py", config_dir)
    env = {
        **ctx["env"],
        "ARRAS_CONFIG_DIR": str(config_dir),
        "ARRAS_TOKEN": secret,
        "TENANT_TOKEN": secret + "-conflict",
    }
    result = run(
        [str(ctx["python"]), "-I", str(script), str(config_dir), str(report_path)],
        cwd=ctx["host"],
        env=env,
    )
    assert result.returncode == 0, f"installed launcher probe failed: {result.stderr[:500]}"
    assert secret not in result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["custom_mcp_help"] == "passed"
    assert report["custom_mcp_unsupported_args"] == "passed"
    assert report["alias_conflict_refused"] == "passed"
    assert report["custom_devhost_help"] == "passed"
    assert report["custom_devhost_unsupported_args"] == "passed"
    assert report["custom_devhost_startup_forwarding"] == "passed"
    return report


def telemetry_probe_script(path: Path, report: Path) -> Path:
    path.write_text(
        """from __future__ import annotations
import asyncio, json, logging, sys, threading
import io
from contextlib import AbstractContextManager
from importlib import metadata
from pathlib import Path
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from arras.distribution import DistributionConfig, TelemetryNames
from arras.telemetry import TelemetryContext, dropped
from arras.mcp import McpServer
from arras.mcp import launch
from arras.ui import create_app
from extension_host.app import compose, run
from extension_host.configuration import settings

sentinel = "telemetry-secret-sentinel-never-report"
global_before = trace.get_tracer_provider()
records = []
class Capture(logging.Handler):
    def emit(self, record): records.append(record)
capture = Capture()
root = logging.getLogger()
old_level = root.level
root.setLevel(logging.DEBUG)
root.addHandler(capture)

def receiver(name):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter

def mark(exporter):
    return (len(exporter.get_finished_spans()), len(records))

def require_phase(label, exporter, before, expected_prefix, service_name):
    spans = exporter.get_finished_spans()[before[0]:]
    logs = records[before[1]:]
    assert spans, label + ": no newly exported spans"
    assert all(span.resource.attributes.get("service.name") == service_name for span in spans), label + ": wrong service Resource"
    assert any(span.name == expected_prefix + ".query" for span in spans), label + ": expected query event span absent"
    assert any(expected_prefix + ".module" in span.attributes for span in spans), label + ": expected attribute namespace absent"
    operation_records = [record for record in logs if record.name == expected_prefix + ".telemetry" and record.getMessage().startswith(expected_prefix + ".query ")]
    assert operation_records, label + ": expected structured query event log absent"
    assert all(getattr(record, "arras_event", None) == "arras.query" for record in operation_records), label + ": canonical event identity changed"
    assert all("module" in getattr(record, "arras_attrs", {}) for record in operation_records), label + ": structured event attributes absent"
    assert all(sentinel not in repr((span.name, span.attributes, span.events)) for span in spans), label + ": secret in span"
    assert all(sentinel not in record.getMessage() and sentinel not in repr(record.__dict__) for record in logs), label + ": secret in log"
    return {"spans": len(spans), "events": len(operation_records), "logs": sum(record.name == expected_prefix + ".telemetry" for record in logs), "service_name": service_name}

factory_values = []
def factory(names):
    factory_values.append(names)
    return TelemetryContext(names)
sys.stdin = io.StringIO("")
launch(argv=[], telemetry_factory=factory)
assert len(factory_values) == 1
assert factory_values[0] == TelemetryNames(attribute_namespace="extension_host", log_prefix="extension_host", event_prefix="extension_host")
assert "psycopg" not in sys.modules and "truss" not in sys.modules

provider_a, exporter_a = receiver("extension-alpha")
provider_b, exporter_b = receiver("extension-beta")
names_a = TelemetryNames(service_name="extension-alpha", attribute_namespace="alpha", log_prefix="alpha", event_prefix="alpha")
names_b = TelemetryNames(service_name="extension-beta", attribute_namespace="beta", log_prefix="beta", event_prefix="beta")
context_a = TelemetryContext(names_a, tracer_provider=provider_a)
context_b = TelemetryContext(names_b, tracer_provider=provider_b)
distribution_a = DistributionConfig(telemetry=names_a)
distribution_b = DistributionConfig(telemetry=names_b)

def own_library(context, barrier=None):
    with context.activate():
        if barrier is not None:
            barrier.wait(timeout=10)
        return run(settings("seed.json"))

async def concurrent_direct_calls():
    barrier = threading.Barrier(2)
    return await asyncio.gather(asyncio.to_thread(own_library, context_a, barrier), asyncio.to_thread(own_library, context_b, barrier))

direct_a = mark(exporter_a)
direct_b = mark(exporter_b)
results = asyncio.run(concurrent_direct_calls())
assert all(result["imported"] == 1 for result in results)
direct_phase_a = require_phase("direct alpha", exporter_a, direct_a, "alpha", "extension-alpha")
direct_phase_b = require_phase("direct beta", exporter_b, direct_b, "beta", "extension-beta")
default_context = TelemetryContext()
default_result = own_library(default_context)
assert default_result["imported"] == 1

world, _, _ = compose(settings("seed.json"))
reader = world.person("mcp_reader", "notes", "read")
server = McpServer(world.arras, lambda: reader, distribution=distribution_b, telemetry_context=context_b)
frame = {"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{"name":"query", "arguments":{"module":"notes", "sql":"SELECT e.* FROM notes.Entry e ORDER BY e.code LIMIT 10"}}}
before_mcp = mark(exporter_b)
response = server.handle(frame)
assert response and "result" in response and response["result"].get("isError") is not True
mcp_phase = require_phase("mcp frame", exporter_b, before_mcp, "beta", "extension-beta")

world_ui, _, _ = compose(settings("seed.json"))
ui_reader = world_ui.person("ui_reader", "notes", "read")
app = create_app(world_ui.arras, principal_for_request=lambda request: ui_reader, authorize_operator=lambda principal: True, public_origin="https://host.invalid", distribution=distribution_a, telemetry_context=context_a)
async def asgi_query():
    body = json.dumps({"module":"notes", "sql":"SELECT e.* FROM notes.Entry e ORDER BY e.code LIMIT 10"}).encode()
    messages = []
    delivered = False
    async def receive():
        nonlocal delivered
        if delivered:
            return {"type":"http.disconnect"}
        delivered = True
        return {"type":"http.request", "body":body, "more_body":False}
    async def send(message): messages.append(message)
    scope = {"type":"http", "method":"POST", "path":"/api/operate/query", "root_path":"", "query_string":b"", "headers":[(b"host",b"host.invalid"),(b"content-type",b"application/json"),(b"origin",b"https://host.invalid")]}
    await app(scope, receive, send)
    assert next(item["status"] for item in messages if item["type"] == "http.response.start") == 200
async def asgi_console():
    body = json.dumps({"query":"{ entryList { items { key } } }"}).encode()
    messages = []
    delivered = False
    async def receive():
        nonlocal delivered
        if delivered:
            return {"type":"http.disconnect"}
        delivered = True
        return {"type":"http.request", "body":body, "more_body":False}
    async def send(message): messages.append(message)
    scope = {"type":"http", "method":"POST", "path":"/api/console/graphql/notes", "root_path":"", "query_string":b"", "headers":[(b"host",b"host.invalid"),(b"content-type",b"application/json"),(b"origin",b"https://host.invalid")]}
    await app(scope, receive, send)
    assert next(item["status"] for item in messages if item["type"] == "http.response.start") == 200
before_operate = mark(exporter_a)
asyncio.run(asgi_query())
operate_phase = require_phase("ASGI operate", exporter_a, before_operate, "alpha", "extension-alpha")
before_console = mark(exporter_a)
asyncio.run(asgi_console())
console_phase = require_phase("ASGI console", exporter_a, before_console, "alpha", "extension-alpha")

with context_a.activate():
    run(settings("seed.json"))
    try:
        with context_b.activate():
            run(settings("seed.json"))
            raise RuntimeError("nested reset control")
    except RuntimeError:
        pass
    nested_a = mark(exporter_a)
    nested_b = mark(exporter_b)
    run(settings("seed.json"))
    nested_restore_phase = require_phase("nested ambient restoration", exporter_a, nested_a, "alpha", "extension-alpha")
    assert len(exporter_b.get_finished_spans()) == nested_b[0], "nested context leaked after reset"

class SwitchingProvider:
    resource = provider_a.resource
    def get_tracer(self, *args, **kwargs):
        tracer = provider_a.get_tracer(*args, **kwargs)
        class SwitchingTracer:
            def start_as_current_span(self, *args, **kwargs):
                manager = tracer.start_as_current_span(*args, **kwargs)
                class SwitchingSpan(AbstractContextManager):
                    def __enter__(self):
                        span = manager.__enter__()
                        self.inner = context_b.activate()
                        self.inner.__enter__()
                        return span
                    def __exit__(self, *args):
                        try:
                            return manager.__exit__(*args)
                        finally:
                            self.inner.__exit__(None, None, None)
                return SwitchingSpan()
        return SwitchingTracer()

switching_context = TelemetryContext(names_a, tracer_provider=SwitchingProvider())
before_switch_a = len(exporter_a.get_finished_spans())
before_switch_b = len(exporter_b.get_finished_spans())
before_switch = mark(exporter_a)
with switching_context.activate():
    own_library(switching_context)
switch_spans = exporter_a.get_finished_spans()[before_switch_a:]
assert switch_spans and any(span.name.startswith("alpha.") for span in switch_spans), "operation lost entry context snapshot"
assert len(exporter_b.get_finished_spans()) == before_switch_b, "nested active context misrouted operation snapshot"
snapshot_phase = require_phase("finish-time entry snapshot", exporter_a, before_switch, "alpha", "extension-alpha")
switch_logs = records[before_switch[1]:]
assert any(record.name == "alpha.telemetry" and record.getMessage().startswith("alpha.query ") for record in switch_logs), "finish-time snapshot lost alpha log route"
assert all(record.name != "beta.telemetry" and not record.getMessage().startswith("beta.") for record in switch_logs), "finish-time snapshot leaked to beta context"

class FailingProcessor(SpanProcessor):
    def on_start(self, span, parent_context=None): pass
    def on_end(self, span): raise RuntimeError(sentinel)
    def shutdown(self): pass
    def force_flush(self, timeout_millis=30000): return True

provider_fault = TracerProvider(resource=Resource.create({"service.name":"extension-alpha"}))
provider_fault.add_span_processor(FailingProcessor())
fault_context = TelemetryContext(names_a, tracer_provider=provider_fault)
before_fault = dropped()
before_fault_spans = len(exporter_a.get_finished_spans())
before_fault_logs = len(records)
global_tracer_calls = []
original_get_tracer = trace.get_tracer
def counted_get_tracer(*args, **kwargs):
    global_tracer_calls.append(args)
    return original_get_tracer(*args, **kwargs)
trace.get_tracer = counted_get_tracer
fault_result = own_library(fault_context)
trace.get_tracer = original_get_tracer
assert fault_result["imported"] == 1 and dropped() > before_fault
assert global_tracer_calls == [], "explicit provider failure attempted global tracer fallback"
fault_phase = {"spans": len(exporter_a.get_finished_spans()) - before_fault_spans, "events": sum(record.name == "alpha.telemetry" and getattr(record, "arras_event", None) is not None for record in records[before_fault_logs:]), "logs": sum(record.name == "alpha.telemetry" for record in records[before_fault_logs:]), "service_name": "extension-alpha"}

class FailingLogger(logging.Handler):
    def emit(self, record): raise RuntimeError(sentinel)
logger_fault = logging.getLogger("alpha.telemetry")
failing_logger = FailingLogger()
logger_fault.addHandler(failing_logger)
before_fault = dropped()
global_tracer_calls.clear()
trace.get_tracer = counted_get_tracer
logger_result = own_library(context_a)
trace.get_tracer = original_get_tracer
logger_fault.removeHandler(failing_logger)
assert logger_result["imported"] == 1 and dropped() > before_fault
assert global_tracer_calls == [], "explicit provider logger failure attempted global tracer fallback"
fault_phase = {"spans": len(exporter_a.get_finished_spans()) - before_fault_spans, "events": sum(record.name == "alpha.telemetry" and getattr(record, "arras_event", None) is not None for record in records[before_fault_logs:]), "logs": sum(record.name == "alpha.telemetry" for record in records[before_fault_logs:]), "service_name": "extension-alpha"}

bad = TelemetryContext(names_a, tracer_provider=type("BrokenProvider", (), {"resource": provider_a.resource, "get_tracer": lambda *a, **k: (_ for _ in ()).throw(RuntimeError(sentinel))})())
before_dropped = dropped()
global_tracer_calls.clear()
trace.get_tracer = counted_get_tracer
with bad.activate():
    unaffected = run(settings("seed.json"))
trace.get_tracer = original_get_tracer
assert unaffected["imported"] == 1 and dropped() > before_dropped
assert global_tracer_calls == [], "explicit provider acquisition failure attempted global tracer fallback"
try:
    TelemetryContext(TelemetryNames(service_name="wrong"), tracer_provider=provider_a)
except ValueError:
    mismatch = True
else:
    mismatch = False
assert mismatch

world_secret, _, _ = compose(settings("seed.json"))
secret_reader = world_secret.person("secret_reader", "notes", "read")
try:
    with context_a.activate():
        world_secret.arras.session(secret_reader).query("notes", "SELECT " + sentinel)
except Exception:
    pass
else:
    raise AssertionError("invalid query sentinel should be refused")

spans_a = exporter_a.get_finished_spans()
spans_b = exporter_b.get_finished_spans()
assert spans_a and spans_b
assert all(span.resource.attributes.get("service.name") == "extension-alpha" for span in spans_a)
assert all(span.resource.attributes.get("service.name") == "extension-beta" for span in spans_b)
assert any(span.name == "alpha.query" and "alpha.module" in span.attributes for span in spans_a)
assert any(span.name == "beta.query" and "beta.module" in span.attributes for span in spans_b)
assert all("arras.module" not in span.attributes for span in (*spans_a, *spans_b))
assert any("error.type" in span.attributes for span in (*spans_a, *spans_b))
assert all("alpha.error.type" not in span.attributes and "beta.error.type" not in span.attributes for span in (*spans_a, *spans_b))
assert any("alpha.telemetry" in record.name and record.getMessage().startswith("alpha.") for record in records)
assert any("beta.telemetry" in record.name and record.getMessage().startswith("beta.") for record in records)
assert any(record.name == "arras.telemetry" and record.getMessage().startswith("arras.") for record in records)
assert all(sentinel not in repr((span.name, span.attributes, span.events)) for span in (*spans_a, *spans_b))
assert all(sentinel not in record.getMessage() and sentinel not in repr(record.__dict__) for record in records)
assert trace.get_tracer_provider() is global_before
root.removeHandler(capture)
root.setLevel(old_level)
report = {"status":"passed", "telemetry_probes":{"status":"passed", "phases":{"direct":{"spans":direct_phase_a["spans"]+direct_phase_b["spans"],"events":direct_phase_a["events"]+direct_phase_b["events"],"logs":direct_phase_a["logs"]+direct_phase_b["logs"],"service_name":"extension-alpha+extension-beta"},"mcp_frame":mcp_phase,"worker_backed_asgi_console":console_phase,"worker_backed_asgi_operate":operate_phase,"concurrent_nested":{"spans":direct_phase_a["spans"]+direct_phase_b["spans"],"events":direct_phase_a["events"]+direct_phase_b["events"],"logs":direct_phase_a["logs"]+direct_phase_b["logs"],"service_name":"extension-alpha+extension-beta"},"nested_ambient_restoration":nested_restore_phase,"finish_time_snapshot":snapshot_phase,"provider_fault_isolation":fault_phase}}, "public_direct_library":"passed", "public_mcp_frame":"passed", "public_worker_backed_asgi":"passed", "sdk_resource_names":["extension-alpha","extension-beta"], "concurrent_and_nested_contexts":"passed", "default_deny_and_failure_isolation":"passed", "launcher_effective_names":{"attribute_namespace":factory_values[0].attribute_namespace,"log_prefix":factory_values[0].log_prefix,"event_prefix":factory_values[0].event_prefix}, "global_provider_unchanged":True, "versions":{"opentelemetry-api":metadata.version("opentelemetry-api"),"opentelemetry-sdk":metadata.version("opentelemetry-sdk")}}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    return path


def installed_telemetry_probe(ctx: dict[str, Any]) -> dict[str, Any]:
    report_path = ctx["temp"] / "telemetry-report.json"
    script = telemetry_probe_script(ctx["temp"] / "installed-telemetry-probe.py", report_path)
    env = {**ctx["env"], "ARRAS_CONFIG_DIR": str(ctx["config_resource"].parent)}
    for name in (
        "ARRAS_TOKEN",
        "ARRAS_TOKEN_FILE",
        "EXTENSION_HOST_TOKEN",
        "EXTENSION_HOST_TOKEN_FILE",
    ):
        env.pop(name, None)
    result = run(
        [str(ctx["python"]), "-I", str(script), str(report_path)], cwd=ctx["host"], env=env
    )
    assert result.returncode == 0, f"installed telemetry probe failed: {result.stderr[:800]}"
    script_text = script.read_text(encoding="utf-8")
    no_op_handler = """async def successful_noop(scope, receive, send):
    await send({"type":"http.response.start", "status":200, "headers":[]})
    await send({"type":"http.response.body", "body":b"{}"})

"""
    controls = (
        (
            "MCP successful no-op",
            "response = server.handle(frame)",
            'response = {"jsonrpc":"2.0","id":1,"result":{"content":[]}}',
            None,
            "mcp frame",
        ),
        (
            "ASGI successful no-op",
            "await app(scope, receive, send)",
            "await successful_noop(scope, receive, send)",
            "async def asgi_query():",
            "ASGI operate",
        ),
    )
    for label, needle, replacement, insertion, expected_failure in controls:
        assert needle in script_text, f"missing {label} mutation anchor"
        mutated = ctx["temp"] / (label.lower().replace(" ", "-") + ".py")
        mutation = script_text.replace(needle, replacement)
        if insertion is not None:
            assert insertion in mutation, f"missing {label} helper insertion point"
            mutation = mutation.replace(insertion, no_op_handler + insertion, 1)
        mutated.write_text(mutation, encoding="utf-8")
        control = run(
            [str(ctx["python"]), "-I", str(mutated), str(report_path)], cwd=ctx["host"], env=env
        )
        assert control.returncode != 0, f"{label} false-pass control unexpectedly succeeded"
        assert expected_failure in control.stderr, (
            f"{label} failed for an unrelated reason: {control.stderr[-500:]}"
        )
    locator = ctx["temp"] / "telemetry-origin.py"
    locator.write_text(
        "import importlib.util; print(importlib.util.find_spec('arras.telemetry').origin)\n",
        encoding="utf-8",
    )
    origin = run([str(ctx["python"]), "-I", str(locator)], cwd=ctx["host"], env=env)
    assert origin.returncode == 0, (
        f"installed telemetry origin lookup failed: {origin.stderr[:300]}"
    )
    telemetry_path = Path(origin.stdout.strip())
    original_telemetry = telemetry_path.read_text(encoding="utf-8")
    snapshot_anchor = "_finish(op, span, failure, time.perf_counter() - started, selected)"
    assert original_telemetry.count(snapshot_anchor) == 1, (
        "installed finish-time snapshot mutation anchor changed"
    )
    try:
        telemetry_path.write_text(
            original_telemetry.replace(
                snapshot_anchor, snapshot_anchor.replace("selected)", "_active.get())")
            ),
            encoding="utf-8",
        )
        control = run(
            [str(ctx["python"]), "-I", str(script), str(report_path)], cwd=ctx["host"], env=env
        )
        assert control.returncode != 0, (
            "finish-time active-context misrouting false-pass control unexpectedly succeeded"
        )
        assert "finish-time entry snapshot" in control.stderr, (
            f"snapshot control failed for an unrelated reason: {control.stderr[-500:]}"
        )
    finally:
        telemetry_path.write_text(original_telemetry, encoding="utf-8")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.update(report.pop("telemetry_probes"))
    report["false_pass_controls"] = [
        "MCP successful empty result",
        "ASGI successful HTTP 200 empty body",
        "finish-time ambient-context misrouting",
    ]
    assert report["global_provider_unchanged"] is True
    report["generated_probe_sha256"] = digest(script)
    return report


def isolated_venv(temp: Path, wheel: Path) -> dict[str, Any]:
    venv = temp / "venv"
    host = temp / "consumer"
    home = temp / "home"
    host.mkdir()
    home.mkdir()
    subprocess.run(["uv", "venv", str(venv)], cwd=host, check=True, capture_output=True, text=True)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "TMPDIR": str(temp),
        "PIP_CONFIG_FILE": os.devnull,
        "UV_CACHE_DIR": str(temp / "uv-cache"),
        "PYTHONPATH": str(ROOT / "src"),
    }
    example_dist = temp / "example-dist"
    example_dist.mkdir()
    subprocess.run(
        ["uv", "build", "--out-dir", str(example_dist)],
        cwd=EXAMPLE,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    example_wheels = list(example_dist.glob("*.whl"))
    assert len(example_wheels) == 1, "expected one built extension-host example wheel"
    install = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--default-index",
            "https://pypi.org/simple",
            "opentelemetry-sdk>=1.27,<2",
            str(wheel),
            str(example_wheels[0]),
        ],
        cwd=host,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    pyvenv = (venv / "pyvenv.cfg").read_text(encoding="utf-8")
    assert "include-system-site-packages = false" in pyvenv.lower()
    return {
        "venv": venv.resolve(),
        "host": host,
        "home": home,
        "python": python,
        "env": env,
        "example_wheel": example_wheels[0],
        "install": install,
    }


def save_request(temp: Path, value: object, name: str = "doctor-request.json") -> Path:
    path = temp / name
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def package_context(wheel: Path, temp: Path, context: dict[str, Any]) -> dict[str, Any]:
    page_manifest = extract_page_manifest(wheel, temp)
    page_value = json.loads(page_manifest.read_text(encoding="utf-8"))
    theme_manifest = make_theme_fixture(
        temp / "theme", page_value["package"]["version"], page_value["contracts"]
    )
    probe = temp / "resource.py"
    probe.write_text(
        "\n".join(
            [
                "from importlib import resources",
                "import json",
                "import pathlib",
                "root = resources.files('extension_host')",
                "module = pathlib.Path(str(root.joinpath('resources','module.umf.json'))).resolve()",
                "config = pathlib.Path(str(root.joinpath('config','default.toml'))).resolve()",
                "print(json.dumps({'module':str(module),'config':str(config)}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = run(
        [str(context["python"]), "-I", str(probe)], cwd=context["host"], env=context["env"]
    )
    assert result.returncode == 0, result.stderr[:300]
    installed_resources = json.loads(result.stdout)
    module_doc = Path(installed_resources["module"]).resolve(strict=True)
    config = Path(installed_resources["config"]).resolve(strict=True)
    for label, resource in (("module", module_doc), ("ADR-019 config", config)):
        assert resource.is_relative_to(context["venv"]) and not resource.is_relative_to(ROOT), (
            f"{label} resource resolved outside isolated install: {resource}; venv={context['venv']}"
        )
    with zipfile.ZipFile(wheel) as archive:
        catalog = json.loads(archive.read("arras/public-api.json"))
        npm_members = [name for name in archive.namelist() if name.endswith(".tgz")]
        assert len(npm_members) == 1, "wheel must carry exactly one npm tarball"
        npm_sha256 = hashlib.sha256(archive.read(npm_members[0])).hexdigest()
    request = json.loads((EXAMPLE / "doctor-request.json").read_text(encoding="utf-8"))
    request["required_npm_exports"]["."] += ["ArrasConsoleProps", "ProviderProps"]
    request["required_npm_exports"]["./browser"] = ["GraphBrowser", "GraphBrowserProps"]
    request["required_npm_exports"]["./shell"] = ["ArrasApp", "ArrasAppProps"]
    request["expected_packages"] = {
        "arras": catalog["distribution"]["version"],
        "@documentdrivendx/arras-ui": catalog["distribution"]["npm"]["version"],
    }
    request["required_role_tokens"] = catalog["ui"]["role_tokens"]
    request["env_names"] = [
        "EXTENSION_HOST_TOKEN",
        "EXTENSION_HOST_TOKEN_FILE",
        "EXTENSION_HOST_LOG_LEVEL",
    ]
    request["config_files"] = [str(config)]
    request["asset_manifest"] = str(page_manifest)
    request["theme_manifest"] = str(theme_manifest)
    request["module_documents"] = [str(module_doc)]
    request["module_profile"] = "legacy-arras"
    request["distribution"] = {
        "brand": {"name": "Extension Host Example", "logo": "theme"},
        "mcp_server_name": "Extension Host Example MCP",
        "mcp_tool_prefix": "ext_host",
        "env_prefix": "EXTENSION_HOST",
        "telemetry": {
            "attribute_namespace": "extension_host",
            "log_prefix": "extension_host",
            "event_prefix": "extension_host",
        },
    }
    request_path = save_request(temp, request)
    secret_file = temp / "ambient-token.txt"
    secret_file.write_text(SENTINEL, encoding="utf-8")
    env = {
        **context["env"],
        "ARRAS_TOKEN": SENTINEL,
        "ARRAS_TOKEN_FILE": str(secret_file),
        "EXTENSION_HOST_TOKEN": SENTINEL,
        "EXTENSION_HOST_TOKEN_FILE": str(secret_file),
    }
    invalid_config = temp / "invalid.toml"
    invalid_config.write_text(
        f'[distribution]\nops_token_file = "{secret_file}"\n', encoding="utf-8"
    )
    return {
        **context,
        "page_manifest": page_manifest,
        "theme_manifest": theme_manifest,
        "config": config,
        "request": request,
        "request_path": request_path,
        "secret_file": secret_file,
        "env": env,
        "invalid_config": invalid_config,
        "module_doc": module_doc,
        "config_resource": config,
        "catalog": catalog,
        "npm_sha256": npm_sha256,
    }


def run_matrix(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    request = ctx["request"]
    mutations: list[tuple[str, dict[str, Any], int, str]] = []

    def add(label: str, mutate: Any, status: int, code: str) -> None:
        value = json.loads(json.dumps(request))
        mutate(value)
        mutations.append((label, value, status, code))

    add(
        "package pin", lambda r: r["expected_packages"].update(arras="9.9.9"), 1, "package_mismatch"
    )
    add(
        "contract pin",
        lambda r: r["expected_contracts"].update(
            {"CONTRACT-004": r["expected_contracts"]["CONTRACT-004"] + 1}
        ),
        1,
        "contract_mismatch",
    )
    add(
        "Python export",
        lambda r: r["required_python_exports"]["arras"].append("NotAnArrasExport"),
        1,
        "python_export_missing",
    )
    add(
        "npm export",
        lambda r: r["required_npm_exports"]["."].append("NotAnNpmExport"),
        1,
        "npm_export_missing",
    )
    add(
        "role token",
        lambda r: r["required_role_tokens"].append("--arras-color-missing"),
        1,
        "role_token_missing",
    )
    add(
        "unsupported range pin",
        lambda r: r["expected_packages"].update(arras=">=0.5"),
        3,
        "capability_unsupported",
    )
    add(
        "environment key name",
        lambda r: r["env_names"].append("TENANT_SECRET_SENTINEL_NAME"),
        1,
        "env_name_unknown",
    )
    add(
        "committed config key",
        lambda r: r.update(config_files=[str(ctx["invalid_config"])]),
        1,
        "config_invalid",
    )
    wrong_theme = json.loads(ctx["theme_manifest"].read_text(encoding="utf-8"))
    wrong_theme["ui_versions"] = ["0.4.0"]
    wrong_theme_path = ctx["temp"] / "theme/theme-manifest-wrong-version.json"
    wrong_theme_path.write_text(json.dumps(wrong_theme), encoding="utf-8")
    add(
        "theme cohort",
        lambda r: r.update(theme_manifest=str(wrong_theme_path)),
        1,
        "theme_incompatible",
    )
    invalid_module = ctx["temp"] / "invalid-module.json"
    invalid_module.write_text("{}", encoding="utf-8")
    add(
        "legacy module document",
        lambda r: r.update(module_documents=[str(invalid_module)]),
        1,
        "module_invalid",
    )
    add(
        "unsupported official UMF profile",
        lambda r: r.update(module_profile="official-umf"),
        3,
        "capability_unsupported",
    )
    add(
        "missing module profile",
        lambda r: r.update(module_profile=None),
        3,
        "module_profile_unsupported",
    )
    add(
        "Brand semantic validation",
        lambda r: r["distribution"]["brand"].update(logo="not-a-supported-logo"),
        1,
        "distribution_invalid",
    )
    python, host, env = ctx["python"], ctx["host"], ctx["env"]
    base = [str(python), "-I", "-m", "arras.doctor", "--request"]
    cases = []
    for index, (label, value, status, expected) in enumerate(mutations):
        report = assert_case(
            python,
            save_request(ctx["temp"], value, f"case-{index}.json"),
            host,
            env,
            label,
            status=status,
            code=expected,
        )
        cases.append({"name": label, "status": status, "codes": sorted(codes(report))})
    malformed = save_request(ctx["temp"], {"schema_version": 1}, "malformed.json")
    malformed.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    report = report_from(run(base + [str(malformed)], cwd=host, env=env), 2, "duplicate JSON keys")
    assert "request_invalid" in codes(report)
    cases.append({"name": "duplicate request keys", "status": 2, "codes": sorted(codes(report))})
    return cases


def run_tail(ctx: dict[str, Any], wheel: Path, output: Path, cases: list[dict[str, Any]]) -> None:
    python, host, env = ctx["python"], ctx["host"], ctx["env"]
    unknown = run(
        [str(python), "-I", "-m", "arras.doctor", "--doctor-secret-sentinel"], cwd=host, env=env
    )
    report = report_from(unknown, 2, "unknown CLI option")
    assert "request_invalid" in codes(report)
    cases.append(
        {"name": "unknown CLI option redaction", "status": 2, "codes": sorted(codes(report))}
    )
    missing = ctx["temp"] / "missing-request"
    help_result = run(
        [str(python), "-I", "-m", "arras.doctor", "--help", "--request", str(missing)],
        cwd=host,
        env=env,
    )
    assert (
        help_result.returncode == 0
        and "usage:" in help_result.stdout.lower()
        and not missing.exists()
    )
    cases.append({"name": "help before request access", "status": 0, "codes": []})

    tripwire_output = ctx["temp"] / "tripwire-report.json"
    script = tripwire_script(ctx["request_path"], ctx["secret_file"], ctx["temp"])
    result = run(
        [
            str(python),
            "-I",
            str(script),
            str(ctx["request_path"]),
            str(ctx["secret_file"]),
            str(tripwire_output),
            str(ctx["invalid_config"]),
        ],
        cwd=host,
        env=env,
    )
    assert result.returncode == 0, f"tripwire control failed: {result.stderr[:300]}"
    tripwire_data = json.loads(tripwire_output.read_text(encoding="utf-8"))
    assert tripwire_data["tripwires"] == "passed"
    cases.append(
        {
            "name": "environment/file/network/subprocess/registration/import tripwires",
            "status": 0,
            "codes": [],
        }
    )
    launcher_data = installed_launcher_probe(ctx)
    cases.append(
        {
            "name": "installed public launcher Brand/help/startup/alias probes",
            "status": 0,
            "codes": [],
        }
    )
    telemetry_data = installed_telemetry_probe(ctx)
    cases.append(
        {
            "name": "installed SDK resources, direct/MCP/worker-backed ASGI, launcher names",
            "status": 0,
            "codes": [],
        }
    )

    probe = ctx["temp"] / "origin.py"
    probe.write_text(
        "\n".join(
            [
                "import importlib.metadata, importlib.resources, json, pathlib, sys, arras, arras.doctor",
                "print(json.dumps({'python':sys.version.split()[0],'arras_origin':str(pathlib.Path(arras.__file__).resolve()),"
                "'doctor_origin':str(pathlib.Path(arras.doctor.__file__).resolve()),"
                "'catalog_origin':str(pathlib.Path(importlib.resources.files('arras').joinpath('public-api.json')).resolve()),"
                "'metadata_version':importlib.metadata.version('arras'),'example_host_origin':str(pathlib.Path(importlib.resources.files('extension_host').joinpath('__init__.py')).resolve()),"
                "'example_config_origin':str(pathlib.Path(importlib.resources.files('extension_host').joinpath('config','default.toml')).resolve()),"
                "'versions':{name:importlib.metadata.version(name) for name in ('arras','example-extension-host','graphql-core','opentelemetry-api','opentelemetry-sdk')},'sys_path':sys.path}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    origin_result = run([str(python), "-I", str(probe)], cwd=host, env=env)
    assert origin_result.returncode == 0, origin_result.stderr[:300]
    origin = json.loads(origin_result.stdout)
    for key in (
        "arras_origin",
        "doctor_origin",
        "catalog_origin",
        "example_host_origin",
        "example_config_origin",
    ):
        assert not Path(origin[key]).is_relative_to(ROOT), f"{key} resolved into source checkout"
    assert Path(origin["arras_origin"]).is_relative_to(ctx["venv"].resolve())
    assert Path(origin["example_host_origin"]).is_relative_to(ctx["venv"].resolve())
    assert origin["metadata_version"] == ctx["catalog"]["distribution"]["version"]
    pth_files = list(ctx["venv"].rglob("*.pth"))
    assert all(
        str(ROOT) not in item.read_text(encoding="utf-8", errors="ignore") for item in pth_files
    )
    receipt = {
        "schema": "arras.ui.doctor-installed-qualification.v1",
        "status": "passed",
        "verifier_source_sha256": digest(Path(__file__).resolve()),
        "generated_probe_sha256": telemetry_data["generated_probe_sha256"],
        "platform": {
            "os": sys.platform,
            "architecture": __import__("platform").machine(),
            "release": __import__("platform").release(),
        },
        "wheel": {
            "filename": wheel.name,
            "sha256": digest(wheel),
            "version": ctx["catalog"]["distribution"]["version"],
        },
        "npm_sha256": ctx["npm_sha256"],
        "qualification_command": "uv run --no-sync python tools/verify_doctor.py --wheel <wheel> --output-json <receipt>",
        "python": origin["python"],
        "installed_origin": {
            key: origin[key]
            for key in (
                "arras_origin",
                "doctor_origin",
                "catalog_origin",
                "example_host_origin",
                "example_config_origin",
            )
        },
        "cwd_outside_source": str(host),
        "source_path_injected_but_isolated": str(ROOT / "src"),
        "python_path": origin["sys_path"],
        "source_referencing_pth_files": 0,
        "dependency_install": "uv pip install from https://pypi.org/simple in a new venv without system site packages",
        "cases": cases,
        "tripwire_report": tripwire_data,
        "launcher_probes": launcher_data,
        "telemetry_probes": telemetry_data,
        "limitations": [
            "Static catalog/manifests and legacy-Arras document parsing do not establish official UMF validity, rendered accessibility, backend registration, native semantics, or publication.",
            "This receipt qualifies only the recorded wheel and Python/platform cohort.",
            "Results do not transfer to another artifact or dependency cohort; repeat qualification when those inputs change.",
        ],
        "versions": {
            "uv": subprocess.run(
                ["uv", "--version"], check=True, capture_output=True, text=True
            ).stdout.strip(),
            "python_distributions": origin["versions"],
            "extension_host_wheel": {
                "filename": ctx["example_wheel"].name,
                "sha256": digest(ctx["example_wheel"]),
            },
            "theme_assets": "CSS/favicon fixture from tests/downstream/theme-package",
            "telemetry_sdk": telemetry_data["versions"],
        },
    }
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument(
        "--output-json", type=Path, default=ROOT / "tests/downstream/evidence/doctor-installed.json"
    )
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    output = args.output_json.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arras-doctor-installed-") as temporary:
        temp = Path(temporary)
        context = {**isolated_venv(temp, wheel), "temp": temp}
        context = package_context(wheel, temp, context)
        positive = run_positive(context)
        cases = [positive]
        cases.extend(run_matrix(context))
        run_tail(context, wheel, output, cases)
    print(
        f"Installed doctor qualification passed: {len(cases)} cases; wheel sha256 {digest(wheel)}"
    )
    print(f"Receipt: {output}")
    return 0


def run_positive(context: dict[str, Any]) -> dict[str, Any]:
    command = [
        str(context["python"]),
        "-I",
        "-m",
        "arras.doctor",
        "--request",
        str(context["request_path"]),
    ]
    result = run(command, cwd=context["host"], env=context["env"])
    report = report_from(result, 0, "positive CLI")
    assert report["ok"] and report["complete"]
    assert report["observed"].get("provenance") == "installed metadata and package resource agree"
    assert (
        report["observed"].get("theme_manifest", {}).get("provenance")
        == "validated selected manifest"
    )
    assert (
        report["observed"].get("asset_manifest", {}).get("provenance")
        == "validated selected manifest"
    )
    assert report["observed"].get("module_documents", [{}])[0].get("profile") == "legacy-arras"
    assert "credential_sources_possible" in codes(report)
    return {
        "name": "positive installed wheel with page/theme/config/Brand/env/module inputs",
        "status": 0,
        "codes": sorted(codes(report)),
    }


if __name__ == "__main__":
    raise SystemExit(main())
