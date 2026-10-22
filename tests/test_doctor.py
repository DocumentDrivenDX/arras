# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from arras.doctor import DoctorRequest, check, main


class DoctorTests(unittest.TestCase):
    def test_request_is_immutable_and_duplicate_keys_fail(self) -> None:
        source = {"arras": "0.5.0"}
        request = DoctorRequest(expected_packages=source)
        source["arras"] = "secret"
        self.assertEqual(request.expected_packages["arras"], "0.5.0")
        with tempfile.TemporaryDirectory() as directory:
            request_path = Path(directory) / "request.json"
            request_path.write_text(
                '{"schema_version":1,"env_names":[],"env_names":[]}', encoding="utf-8"
            )
            with patch("sys.stdout") as output:
                self.assertEqual(main(["--request", str(request_path)]), 2)
            rendered = "".join(call.args[0] for call in output.write.call_args_list)
            self.assertIn('"request_invalid"', rendered)

    def test_semantically_invalid_distribution_is_typed_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(
                '{"schema_version":1,"distribution":{"brand":{"logo":"secret-mark"}}}',
                encoding="utf-8",
            )
            with patch("sys.stdout") as output:
                self.assertEqual(main(["--request", str(path)]), 1)
            rendered = "".join(call.args[0] for call in output.write.call_args_list)
            self.assertIn('"distribution_invalid"', rendered)
            self.assertNotIn("secret-mark", rendered)

    def test_optional_telemetry_service_name_accepts_explicit_null(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(
                '{"schema_version":1,"distribution":{"telemetry":{"service_name":null}}}',
                encoding="utf-8",
            )
            catalog_path = Path(__file__).parents[1] / "src" / "arras" / "public-api.json"
            npm = json.loads(catalog_path.read_text(encoding="utf-8"))["distribution"]["npm"]
            with patch(
                "arras.doctor._npm_package",
                return_value=("0" * 64, {"name": npm["name"], "version": npm["version"]}),
            ):
                with patch("sys.stdout") as output:
                    self.assertEqual(main(["--request", str(path)]), 0)
            rendered = "".join(call.args[0] for call in output.write.call_args_list)
            self.assertNotIn('"request_invalid"', rendered)

    def test_missing_npm_package_reports_exit_three(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text('{"schema_version":1}', encoding="utf-8")
            with patch("arras.doctor._npm_package", return_value=(None, None)):
                with patch("sys.stdout") as output:
                    self.assertEqual(main(["--request", str(path)]), 3)
            rendered = "".join(call.args[0] for call in output.write.call_args_list)
            self.assertIn('"package_missing"', rendered)

    def test_malformed_distribution_shape_remains_request_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(
                '{"schema_version":1,"distribution":{"brand":{"unknown":"secret"}}}',
                encoding="utf-8",
            )
            with patch("sys.stdout") as output:
                self.assertEqual(main(["--request", str(path)]), 2)
            rendered = "".join(call.args[0] for call in output.write.call_args_list)
            self.assertIn('"request_invalid"', rendered)
            self.assertNotIn("secret", rendered)

    def test_invalid_committed_distribution_has_its_stable_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.toml"
            path.write_text('[distribution.brand]\nlogo = "unsafe"\n', encoding="utf-8")
            report = check(DoctorRequest(config_files=(path,)))
        self.assertTrue(any(row.code == "distribution_invalid" for row in report.diagnostics))

    def test_direct_request_rejects_mutable_or_wrong_collection_shapes(self) -> None:
        with self.assertRaises(ValueError):
            DoctorRequest(required_python_exports=cast(Any, {"arras": "Arras"}))
        with self.assertRaises(ValueError):
            DoctorRequest(env_names=cast(Any, (1,)))
        with self.assertRaises(ValueError):
            DoctorRequest(module_profile=cast(Any, 123))

    def test_catalog_and_declared_requests(self) -> None:
        report = check(DoctorRequest(required_python_exports={"arras": ("Arras",)}))
        self.assertEqual(report.schema_version, 1)
        self.assertFalse(any(row.code == "python_export_missing" for row in report.diagnostics))
        missing = check(DoctorRequest(required_python_exports={"missing.module": ()}))
        self.assertTrue(any(row.code == "python_export_missing" for row in missing.diagnostics))

    def test_environment_checks_names_only(self) -> None:
        report = check(DoctorRequest(env_names=("ARRAS_TOKEN", "ARRAS_TOKEN_FILE")))
        self.assertTrue(
            any(row.code == "credential_sources_possible" for row in report.diagnostics)
        )
        self.assertNotIn("ARRAS_TOKEN", json.dumps(report.to_dict()))

    def test_selected_namespace_accepts_dynamic_backend_and_ignored_aliases(self) -> None:
        from arras.distribution import DistributionConfig

        selected = DistributionConfig(env_prefix="TENANT")
        report = check(
            DoctorRequest(
                distribution=selected,
                env_names=("TENANT_BACKEND_CATALOG_ENDPOINT", "TENANT_ADMIN_KEY"),
            )
        )
        self.assertFalse(any(row.code == "env_name_unknown" for row in report.diagnostics))

    def test_unavailable_pin_and_profile_are_unsupported(self) -> None:
        report = check(
            DoctorRequest(
                expected_packages={"arras": ">=1"},
                module_documents=(Path("/missing"),),
                module_profile="custom-validator",
            )
        )
        codes = {row.code for row in report.diagnostics}
        self.assertIn("capability_unsupported", codes)
        self.assertFalse(report.complete)

    def test_manifest_must_match_carried_ui_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = b"<!doctype html>"
            (root / "index.html").write_bytes(body)
            manifest = {
                "format": "arras.ui.assets",
                "version": 1,
                "kind": "page",
                "package": {"name": "wrong-package", "version": "0.5.0"},
                "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
                "schema_browser": {"name": "schema", "version": "1", "integrity": "sha512-test"},
                "entry": {"html": "index.html"},
                "files": {
                    "index.html": {
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "size": len(body),
                        "mime": "text/html",
                    }
                },
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = check(DoctorRequest(asset_manifest=manifest_path))
        self.assertTrue(any(row.code == "asset_invalid" for row in report.diagnostics))

    def test_npm_archive_name_must_match_catalog(self) -> None:
        with patch(
            "arras.doctor._npm_package", return_value=("0" * 64, {"name": "wrong", "version": "1"})
        ):
            report = check()
        self.assertTrue(any(row.code == "package_mismatch" for row in report.diagnostics))

    def test_report_observation_is_deeply_immutable(self) -> None:
        report = check()
        contracts = report.observed["contracts"]
        with self.assertRaises(TypeError):
            cast(Any, contracts)["CONTRACT-001"] = 99

    def test_legacy_document_requires_explicit_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "module.json"
            path.write_text("{}", encoding="utf-8")
            report = check(DoctorRequest(module_documents=(path,)))
        self.assertTrue(any(row.code == "module_profile_unsupported" for row in report.diagnostics))

    def test_help_precedes_request_and_unknown_args_are_redacted_json(self) -> None:
        with patch("arras.doctor._read_regular", side_effect=AssertionError("read")):
            self.assertEqual(main(["--help"]), 0)
        with patch("sys.stdout") as output:
            status = main(["--bad-secret-sentinel"])
        self.assertEqual(status, 2)
        rendered = "".join(call.args[0] for call in output.write.call_args_list)
        self.assertIn('"request_invalid"', rendered)
        self.assertNotIn("secret-sentinel", rendered)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO support is unavailable")
    def test_fifo_request_is_rejected_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            os.mkfifo(path)
            with patch("sys.stdout") as output:
                self.assertEqual(main(["--request", str(path)]), 2)
            rendered = "".join(call.args[0] for call in output.write.call_args_list)
        self.assertIn('"request_invalid"', rendered)


if __name__ == "__main__":
    unittest.main()
