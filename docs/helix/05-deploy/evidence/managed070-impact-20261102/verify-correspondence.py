"""Compare released artifacts and managed-path source; make no service calls."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

BASELINE = "11be778eae8050fd5b2e8b446479e8bea081778a"
CANDIDATE = "f9f04c42ae0c989d34907e00a63ca95c3cb2fcdf"
WHEELS = (
    "29139ac729e00639a8b07366ed8c64d69936bceb525d9b85bb562946f115a9b2",
    "b20f2b0c8a8f54b86abfca886dc555bb16faedd277c1e132c3c58dfc7aa17ad6",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-wheel", type=Path, required=True)
    parser.add_argument("--candidate-wheel", type=Path, required=True)
    parser.add_argument("--baseline-install", type=Path, required=True)
    parser.add_argument("--baseline-dependencies", type=Path, required=True)
    parser.add_argument("--candidate-native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def dependency_archives(report, native):
    current = {
        row["distribution"].lower().replace("_", "-"): row["sha256"]
        for row in native["pip_artifacts"]
    }
    matched = {}
    for row in report["install"]:
        name = row["metadata"]["name"].lower().replace("_", "-")
        if name in {"arras", "pip", "setuptools", "wheel"}:
            continue
        digest = row["download_info"]["archive_info"]["hashes"]["sha256"]
        assert current[name] == digest, name
        matched[name] = digest
    assert {"weft-sql", "psycopg-binary", "mini-racer"}.issubset(matched)
    return matched


def main():
    args = arguments()
    root = Path(__file__).resolve().parents[5]

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(root), *arguments])

    for path, expected in zip((args.baseline_wheel, args.candidate_wheel), WHEELS, strict=True):
        assert sha(path.read_bytes()) == expected, "release wheel identity differs"
    with zipfile.ZipFile(args.baseline_wheel) as old, zipfile.ZipFile(args.candidate_wheel) as new:
        names = sorted(
            n for n in old.namelist() if n.startswith("arras/adapters/") and not n.endswith("/")
        )
        assert names == sorted(
            n for n in new.namelist() if n.startswith("arras/adapters/") and not n.endswith("/")
        )
        assert names
        members = {}
        for name in names:
            assert old.read(name) == new.read(name), name
            members[name] = sha(new.read(name))

    def selected_paths(commit):
        names = (
            git("ls-tree", "-r", "--name-only", commit, "src/arras/adapters", "tools")
            .decode()
            .splitlines()
        )
        return sorted(
            n
            for n in names
            if n.startswith(("src/arras/adapters/", "tools/_lakebase"))
            or n == "tools/verify_lakebase_acceptance.py"
        )

    paths = selected_paths(BASELINE)
    assert paths == selected_paths(CANDIDATE)
    source = {}
    for name in paths:
        before = git("show", f"{BASELINE}:{name}")
        after = git("show", f"{CANDIDATE}:{name}")
        assert before == after, name
        source[name] = sha(after)

    installed = json.loads(args.baseline_install.read_text())
    native = json.loads(args.candidate_native.read_text())
    archives = dependency_archives(json.loads(args.baseline_dependencies.read_text()), native)
    assert installed["status"] == "verified" and native["status"] == "passed"
    assert installed["artifacts"]["arras"]["wheel_sha256"] == WHEELS[0]
    assert native["inputs"]["arras_wheel"]["sha256"] == WHEELS[1]
    versions = {}
    for name, version in installed["versions"].items():
        if name in {"arras", "pip", "setuptools", "wheel"}:
            continue
        assert native["all_installed_distributions"][name] == version, name
        versions[name] = version
    truss = installed["artifacts"]["truss-toolkit"]["wheel_sha256"]
    assert any(
        x["distribution"] == "truss-toolkit" and x["sha256"] == truss
        for x in native["pip_artifacts"]
    )
    baseline_receipt = (
        root / "docs/helix/05-deploy/evidence/embedding064-20261029/full-managed.safe.json"
    )
    managed = json.loads(baseline_receipt.read_text())
    assert managed["status"] == "passed" and len(managed["cases"]) == 12
    assert all(case["status"] == "passed" for case in managed["cases"])
    result = {
        "schema": "arras.managed-qualification-correspondence/1",
        "status": "passed",
        "baseline_source": BASELINE,
        "candidate_source": CANDIDATE,
        "baseline_wheel_sha256": WHEELS[0],
        "candidate_wheel_sha256": WHEELS[1],
        "identical_adapter_members": members,
        "identical_managed_source_files": source,
        "unchanged_runtime_versions": versions,
        "identical_dependency_archives": archives,
        "baseline_dependency_report_sha256": sha(args.baseline_dependencies.read_bytes()),
        "truss_archive_sha256": truss,
        "baseline_managed_receipt_sha256": sha(baseline_receipt.read_bytes()),
        "baseline_install_receipt_sha256": sha(args.baseline_install.read_bytes()),
        "candidate_native_receipt_sha256": sha(args.candidate_native.read_bytes()),
        "historical_cases": managed["cases"],
        "fresh_lakebase_execution": False,
        "scope": "Historical managed execution; applicability to the unchanged legacy Truss profile established by correspondence review plus existing 0.7.0 regression evidence. No new target or memory-action managed support.",
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": "passed",
                "identical_adapter_files": len(members),
                "identical_managed_source_files": len(source),
                "unchanged_runtime_versions": len(versions),
            }
        )
    )


if __name__ == "__main__":
    main()
