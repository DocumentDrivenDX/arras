# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Release readiness of the Truss adapter: the documents describe what was built.

The governed documents state the present design only: no migration tool of Arras's own, no
vendored DDL, no embedded Postgres 16, no journal-row receipts. The release gates the publish on
the Truss-marked suite and keeps the Truss extra in its sync, so the adapter stays strictly typed
and the base wheel stays free of Truss.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs/helix"

# The plan, the traceability matrix and the spikes record what was found or decided on the way;
# every other governed document and the README describe the design as it stands.
EXEMPT = ("02-design/spikes/", "04-build/", "03-test/traceability.md")
STALE = re.compile(
    r"alembic|vendored|embedded postgres|postgres(ql)? 16|history schema|apply_group"
    r"|import_batch(?!ed_in_transaction|es\b)"
    r"|(?<!no )migration history|administrative principal[^.|]*\bmigrations?\b",
    re.IGNORECASE,
)


def release_job(release: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",
        release,
    )
    assert match is not None, name
    return match.group(1)


def _governed() -> list[Path]:
    found = [p for p in DOCS.rglob("*.md") if not any(x in p.as_posix() for x in EXEMPT)]
    return [*found, ROOT / "README.md"]


def test_no_governed_document_describes_a_design_that_is_gone() -> None:
    hits = [
        f"{p.relative_to(ROOT)}:{n}: {line.strip()[:80]}"
        for p in _governed()
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if STALE.search(line)
    ]
    assert hits == []


def test_the_requirements_note_is_generic_and_states_the_pinned_release() -> None:
    note = (DOCS / "02-design/truss-requirements.md").read_text()
    assert "arras" not in note.lower()
    assert "0.1.0.dev38" not in note
    assert "truss-toolkit==0.0.48" in note
    for ask in ("R19", "R20", "R21", "R22"):
        assert re.search(rf"^\| {ask} \|", note, re.MULTILINE), ask


def test_the_readme_states_the_host_prerequisites() -> None:
    readme = (ROOT / "README.md").read_text()
    for needle in ("ConnectionSource", "PostgreSQL 18.6", "Unsupported"):
        assert needle in readme, needle
    assert "Not built, because they wait on Truss" not in readme
    assert re.search(
        r"Truss 0\.0\.45 prepared a module in embedded V8 .*? without a Bun or Node process\.",
        readme,
    )
    assert "deploy-time job" in readme


def test_no_bun_is_named_or_passed_anywhere() -> None:
    """Truss 0.0.48 prepares a module in process: no adapter call is given a Bun path."""
    adapter = ROOT / "src/arras/adapters/truss"
    users = sorted(p.name for p in adapter.glob("*.py") if "bun" in p.read_text().lower())
    assert users == []
    contract = (DOCS / "02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md").read_text()
    assert "no Bun, no Node and an empty `PATH`" in contract
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "setup-bun" not in ci and "bun-version" not in ci


def test_release_assets_are_gated_and_registry_publishing_is_opt_in() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text()
    truss, build, umf_admission = (
        release_job(release, name) for name in ("truss", "build", "umf-admission")
    )
    github, assemble, public_download, pypi, npm = (
        release_job(release, name)
        for name in (
            "github-release",
            "assemble-evidence",
            "downloaded-release",
            "publish-pypi",
            "publish-npm",
        )
    )
    assert "uv sync --locked --extra truss --group truss-test" in truss
    assert "pytest -m truss" in truss and 'ARRAS_REQUIRE_TRUSS: "1"' in truss
    assert "uv sync --locked --extra truss" in build
    assert (
        "uv run --no-sync ruff check ." in build
        and "uv run --no-sync pyright" in build
        and "uv run --no-sync pytest -q" in build
    )
    assert "assert importlib.util.find_spec('truss') is None" in build
    assert re.search(r"(?m)^    needs: check$", truss)
    assert re.search(r"(?m)^    needs: \[check, truss\]$", build)

    # GitHub asset creation has only required gates. Both registry jobs follow that release and
    # remain skipped unless their separate repository opt-in is exactly true.
    assert re.search(
        r"(?m)^    needs: \[check, truss, build, umf-admission, umf-actions, ui-qualification, installed-native, assemble-evidence\]$",
        github,
    )
    assert re.search(
        r"(?m)^    needs: \[check, build, umf-admission, umf-actions, installed-native, ui-qualification\]$",
        assemble,
    )
    assert (
        re.search(r"(?m)^    needs: \[check, build\]$", umf_admission)
        and "--qualification-phase release-build" in umf_admission
        and "name: umf-admission-qualification" in umf_admission
    )
    assert "name: release-build-inputs" in build
    assert "--build-bundle release-build-inputs" in assemble
    assert "--native-receipt native-qualification/artifacts/native-verification.json" in assemble
    assert (
        "--ui-receipt ui-qualification/tests/downstream/evidence/linux/qualification-linux.json"
        in assemble
    )
    assert (
        "--consumer-receipt ui-qualification/artifacts/extension-host-fresh-dependencies.json"
        in assemble
    )
    assert "sums_sha256:" in assemble and "sha256sum release-assets/SHA256SUMS" in assemble
    assert "name: release-assets" in assemble
    assert re.search(
        r"(?m)^    needs: \[check, build, assemble-evidence, github-release, installed-downstream\]$",
        public_download,
    )
    assert "curl --disable --fail --silent --show-error --location" in public_download
    assert "--proto '=https' --proto-redir '=https'" in public_download
    assert "GH_TOKEN" not in public_download and "gh release download" not in public_download
    assert "verify_public_release_assets.py plan" in public_download
    assert "verify_public_release_assets.py verify" in public_download
    assert re.search(r"(?m)^    if: vars\.ARRAS_PUBLISH_PYPI == 'true'$", pypi)
    assert re.search(r"(?m)^    if: vars\.ARRAS_PUBLISH_NPM == 'true'$", npm)
    assert "needs: [github-release, installed-downstream, downloaded-release]" in pypi
    assert "needs: [github-release, installed-downstream, downloaded-release]" in npm
    assert "secrets.NPM_TOKEN" not in github and "pypa/gh-action-pypi-publish" not in github

    # The checksum covers each release member. PyPI stages only wheel/sdist into its publisher
    # directory; npm publishes the already-extracted wheel payload instead of rebuilding it.
    assert (
        "sha256sum *.whl *.tar.gz *.tgz distribution-verification.json doctor-installed.json > SHA256SUMS"
        in build
    )
    assert "sha256sum -c SHA256SUMS" in github and "sha256sum -c SHA256SUMS" in npm
    assert "cp release-assets/*.whl release-assets/*.tar.gz dist/" in pypi
    assert "npm publish ./release-assets/*.tgz --access public --provenance" in npm
    assert "gh release create" in github and "release-assets/*" in github
    assert "pip install arras" not in github
    assert 'ARRAS_REQUIRE_WEFT: "1"' in build
    assert 'python-version: "3.11"' in build
    assert (
        'WEFT_VERSION: "0.4.51"' in build
        and "WEFT_SUMS_SHA256: 62c9d8082eb2f446446d7b94ff7ef7f48769e3cd836e5641c2951069302a6c75"
        in build
    )
    assert 'uv pip install --python "$GITHUB_WORKSPACE/.venv/bin/python" "$wheel"' in build
    assert (
        "tools/verify_doctor.py --wheel dist/arras-*.whl --output-json artifacts/doctor-installed.json"
        in build
    )
    assert "setup-bun" not in release


def test_github_release_rechecks_the_tag_and_uses_tagged_notes() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text()
    github = release_job(release, "github-release")
    notes = " ".join((ROOT / "docs/helix/05-deploy/release-notes.md").read_text().lower().split())
    assert "ref: ${{ needs.check.outputs.driver_sha }}" in github
    assert "ref: ${{ needs.check.outputs.source_sha }}" in github
    assert "--notes-file release-notes.md" in github
    assert "source/docs/helix/05-deploy/release-notes.md" in github
    assert "release_target.py recheck" in github
    assert "--generate-notes" in github and "--verify-tag" in github
    assert github.index("release_target.py recheck") < github.index("gh release create")
    assert "Build provenance" in github
    assert "ARRAS_DRIVER_SHA" in github and "ARRAS_TARGET_SOURCE_SHA" in github
    assert "registry access has not been established" in notes
    assert "pip install arras" not in github.lower()


def test_release_requires_ui_and_public_downstream_qualification() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text()
    ui_release = release_job(release, "ui-qualification")
    downstream = release_job(release, "installed-downstream")
    public_download = release_job(release, "downloaded-release")
    assembled = release_job(release, "assemble-evidence")
    assert (
        "needs: [check, truss, build, umf-admission, umf-actions, ui-qualification, installed-native, assemble-evidence]"
        in release_job(release, "github-release")
    )
    for required in (
        "npm audit --audit-level=high --omit=dev",
        "npm run check:umf -- --download",
        "npm run check && npm run typecheck && npm test && npm run build && npm run test:integration",
        "npm run check:umf -- --dist dist",
        "npm run build:lib",
        "npm run check:externals",
        "npm run e2e -- --project=chromium --project=schema-admin --project=browser",
        "npm run qualify:downstream -- ../release-assets/${{ needs.build.outputs.wheel_name }}",
        "tools/check_public_content.py",
        "tools/verify_extension_host.py",
        "hashlib.sha256(wheel.read_bytes()).hexdigest()",
        "name: exact-tag-ui-qualification",
        "tests/downstream/evidence/linux",
    ):
        assert required in ui_release
    assert "npx --no-install playwright install-deps chromium" in ui_release
    assert "npx --no-install playwright install chromium" in ui_release
    browser_line = next(line for line in ui_release.splitlines() if "npm run e2e --" in line)
    assert all(project in browser_line for project in ("chromium", "schema-admin", "browser"))
    assert (
        "visual" not in browser_line and "Visual screenshot baselines are macOS-specific" in release
    )
    assert 'python-version: "3.11"' in ui_release
    assert "needs: [check, build, github-release]" in downstream
    assert "uses: ./.github/workflows/downstream.yml" in downstream
    assert "needs.build.outputs.wheel_sha256" in downstream
    assert "examples/extension_host/tests/test_installed.py" in downstream
    assert "name: release-build-inputs" in ui_release
    assert "../release-assets/${{ needs.build.outputs.wheel_name }}" in ui_release
    for required in (
        ".github/scripts/verify_public_release_assets.py plan",
        ".github/scripts/verify_public_release_assets.py verify",
        "tools/verify_distribution.py",
        "tools/verify_doctor.py",
        "tools/verify_extension_host.py",
        "npm run qualify:downstream -- ../public-release-assets/${{ needs.build.outputs.wheel_name }}",
        "name: public-release-qualification",
        "public-input-verification.json",
    ):
        assert required in public_download
    assert public_download.index("verify_public_release_assets.py verify") < public_download.index(
        "tools/verify_distribution.py"
    )
    assert (
        public_download.index("tools/verify_distribution.py")
        < public_download.index("tools/verify_doctor.py")
        < public_download.index("tools/verify_extension_host.py")
        < public_download.index("npm run qualify:downstream -- ../public-release-assets/")
    )
    assert "continue-on-error" not in public_download
    assert "if: always()" in public_download
    assert (
        "needs: [check, build, umf-admission, umf-actions, installed-native, ui-qualification]"
        in assembled
    )
    assert "--qualification-phase public-download" in public_download
    assert "public-umf-admission-installed.json" in public_download
    assert "name: release-assets" in assembled
    assert "name: public-release-qualification" in public_download
    assert "needs: [github-release, installed-downstream, downloaded-release]" in release_job(
        release, "publish-pypi"
    )
    assert "needs: [github-release, installed-downstream, downloaded-release]" in release_job(
        release, "publish-npm"
    )


def test_the_requirements_note_names_the_corpus_limits_the_harness_pins() -> None:
    from truss_harness import TrussHarness

    text = (DOCS / "02-design/truss-requirements.md").read_text()
    selected_start = text.index("## Selected public cohort")
    selected_end = text.find("\n## ", selected_start + 1)
    assert selected_end != -1
    selected = text[selected_start:selected_end]
    limits_paragraph = next(
        " ".join(paragraph.split())
        for paragraph in selected.split("\n\n")
        if "corpus cases end at documented limits" in " ".join(paragraph.split())
    )
    words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    stated = re.search(r"(\w+) corpus cases end at documented limits", limits_paragraph)
    assert stated is not None
    count = stated.group(1).lower()
    assert (words.index(count) + 1 if count in words else int(count)) == len(TrussHarness.LIMITS)
    named = set(re.findall(r"`([a-z]+\.[a-z0-9.-]+)`", limits_paragraph))
    assert named == set(TrussHarness.LIMITS)
    assert "72 provider" in selected and "64 passed" in selected
    assert "seven reader-only corpus cases were inapplicable" in selected

    historical_start = text.index("## Historical state — release v0.0.45")
    historical_end = text.index("## Truss's response,", historical_start)
    historical = text[historical_start:historical_end]
    assert "63 cases pass, nine end at documented limits" in historical


def test_release_playwright_apt_setup_is_prevalidated_bounded_and_effective() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text()
    assert release.count("apt-config shell ARRAS_MAIN Dir::Etc::main/f") == 2
    assert release.count("Binary::apt-get::Acquire {") == 2
    ui_release = release_job(release, "ui-qualification")
    setup_start = ui_release.index("name: Configure bounded Ubuntu apt access for Playwright")
    browser_install = ui_release.index("npx --no-install playwright install chromium", setup_start)
    browser_launch = ui_release.index("const browser = await chromium.launch", browser_install)
    existing_e2e = ui_release.index("npm run e2e --", browser_launch)
    setup = ui_release[setup_start:existing_e2e]
    ordered = (
        "configure_ubuntu_apt_sources.py --self-test",
        "sudo python ../.github/scripts/configure_ubuntu_apt_sources.py --apply",
        "apt-config shell ARRAS_MAIN Dir::Etc::main/f",
        "ARRAS_MAIN='/etc/apt/apt.conf'",
        'sudo test -e "$apt_main_path"',
        'sudo tee -a "$apt_main_path"',
        "Acquire {",
        'Retries "2";',
        'http::Timeout "20";',
        'https::Timeout "20";',
        "Binary::apt-get::Acquire {",
        "apt-config shell ARRAS_RETRIES Acquire::Retries ARRAS_HTTP_TIMEOUT Acquire::http::Timeout ARRAS_HTTPS_TIMEOUT Acquire::https::Timeout",
        "ARRAS_APTGET_RETRIES Binary::apt-get::Acquire::Retries",
        "expected_apt_config=",
        'if [ "$apt_config" != "$expected_apt_config" ]; then',
        "timeout --signal=TERM --kill-after=30s 5m sudo apt-get update",
        "timeout --signal=TERM --kill-after=30s 15m npx --no-install playwright install-deps chromium",
        "timeout --signal=TERM --kill-after=30s 15m npx --no-install playwright install chromium",
        "timeout --signal=TERM --kill-after=10s 60s node --input-type=module",
    )
    positions = [setup.index(item) for item in ordered]
    assert positions == sorted(positions)
    assert 'if sudo test -e "$apt_main_path" || sudo test -L "$apt_main_path"; then' in setup
    assert 'if ! sudo test -f "$apt_main_path" || sudo test -L "$apt_main_path"; then' in setup
    assert "npx playwright install --with-deps chromium" not in setup
    assert "npm ci" in ui_release and "npm ci" not in setup
    assert "const browser = await chromium.launch({ headless: true })" in setup
    assert "await browser.close()" in setup


def test_release_requires_exact_installed_native_qualification_and_evidence() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text()
    native = release_job(release, "installed-native")
    github_release = release_job(release, "github-release")
    assert "needs: [check, build]" in native
    assert (
        "needs: [check, truss, build, umf-admission, umf-actions, ui-qualification, installed-native, assemble-evidence]"
        in github_release
    )
    assert "timeout-minutes: 60" in native
    assert 'python-version: "3.11"' in native
    assert "uv sync" not in native and "uv run" not in native
    assert "name: python-distributions" in native
    assert "tests/downstream/native-cohorts/linux-x86_64.json" in native
    assert "tests/downstream/native-cohorts/linux-x86_64.find-links.html" in native
    assert "tools/_native_cohort_binding.py" not in native
    for required in (
        ".github/scripts/bind_native_cohort.py",
        '--expected-version "${{ needs.check.outputs.version }}"',
        '--expected-sha256 "${{ needs.build.outputs.wheel_sha256 }}"',
        "--output-json artifacts/native-cohort.bound.json",
        "--receipt-json artifacts/native-cohort-binding.json",
        "python tools/verify_native.py",
        "--cohort artifacts/native-cohort.bound.json",
        '--python "$(command -v python)"',
        "> artifacts/native-verifier.stdout.log",
        "2> artifacts/native-verifier.stderr.log",
        ".github/scripts/ensure_native_receipt_failure.py",
        '--exit-code "$status"',
        "if: always()",
        "name: installed-native-qualification",
        "artifacts/native-verification.json",
        "artifacts/native-verifier.stdout.log",
        "artifacts/native-verifier.stderr.log",
    ):
        assert required in native
