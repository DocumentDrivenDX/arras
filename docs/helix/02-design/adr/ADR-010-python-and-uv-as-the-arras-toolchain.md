---
ddx:
  id: ADR-010
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-04
  authoring:
    home: repo
  links:
    - id: ADR-006
      kind: informed_by
---

# ADR-010: Python 3.11 with uv as the toolchain for Arras

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-04 | Accepted | Erik LaBianca (architecture lead) | [ADR-006](ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md), [`concerns.md`](../../01-frame/concerns.md) | High |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | The kickoff fixed Python as the language of Arras (the interface to an ontology, a Python library embedded in the praxis Databricks app) and set nothing else. The toolchain (package manager, linter, type checker, test runner) needs a recorded choice. Arras and anything runnable beside it need reproducible, isolated environments that a reviewer can stand up in one command. |
| Current State | The repo is a uv project (uv is Astral's Python package and project manager): `pyproject.toml`, a committed `uv.lock`, `uv run`. The HELIX library's `python-uv` concern prescribes Python 3.12+ (Arras uses 3.11, see Decision), uv, `ruff` (linter and formatter), `pyright` (type checker), `pytest` (test runner), `hatchling` (build backend), and `pyproject.toml` as the only project metadata. **Databricks Apps supports uv natively** ([Manage dependencies for a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/dependencies), read 19 Sep 2026): if `requirements.txt` is absent and both `pyproject.toml` and `uv.lock` are present, the app is installed with `uv sync` from the lock file; `requires-python` selects the interpreter; uv-based apps ship no pre-installed libraries. If `requirements.txt` exists it takes precedence and the app is installed with pip on Python 3.11. |
| Requirements | One command to create an environment and run anything (`uv sync`, `uv run`). Byte-reproducible dependency resolution across machines (a committed lockfile). Isolation per implementation, so a benchmark or tool cannot pollute the library. A pinned interpreter per project. Static checks that run without configuration. Deployable to Databricks Apps as-is: the same `pyproject.toml` and `uv.lock` the developer commits are what the platform installs. |
| Decision Drivers | Operator direction, 19 Sep 2026: record uv by ADR and give each implementation an isolated uv environment. The library concern already exists, so adopting it costs nothing. The host, praxis (an agent-harness app on Databricks Apps), requires Python 3.11 or later (`requires-python = ">=3.11"`), and Arras embeds in it, so 3.11 is the interpreter. `pgserver`, a PostgreSQL bundled in a wheel and used for local development and tests, ships wheels through CPython 3.12, so it runs on 3.11. |

## Decision

We will use **Python 3.11 managed by uv** for Arras and every runnable artifact in this repository: one `pyproject.toml`, one committed `uv.lock`, one `.python-version` and one `.venv` per implementation directory, with `ruff` for lint and format, `pyright` for types, `pytest` for tests and `hatchling` as the build backend.

**Key Points**: Each implementation is its own uv project. Nothing is installed globally, and a project that depends on another declares it as a path dependency in `[tool.uv.sources]` | `uv.lock` is committed. `uv sync` reproduces the environment exactly | The interpreter is pinned per project in `.python-version` and declared in `requires-python`, which Databricks Apps honours for uv-based apps. Arras and its spikes pin `3.11` to match the host | `ruff check`, `ruff format --check` and `pyright` must pass before a change lands; they are configured in `pyproject.toml` and need no other files | **No `requirements.txt`, ever, in an app directory.** On Databricks Apps its presence overrides `pyproject.toml`, switches installation to pip and the interpreter to Python 3.11, and drops the lockfile. The uv path also provides no pre-installed libraries, so every runtime dependency (the base install declares no `psycopg`: `psycopg` and `truss-toolkit[native,query]` are the optional extra `truss`, and Arras has no migration tool of its own) is declared in `[project.dependencies]` or, for the `truss` extra, in `[project.optional-dependencies]`; `[dependency-groups].dev` holds only tooling

**The Truss extra.** `truss-toolkit[native,query]==0.0.45` is the optional extra `truss`, never a base or `dev` dependency, so the base install needs no psycopg and no Bun. None of the toolkit, Weft and `pgserver-pg18` is on PyPI: `[tool.uv] find-links` names one committed flat page, `tools/find-links/index.html`, whose anchors point at the three releases' download URLs on the DocumentDrivenDX release pages (Truss v0.0.45: the wheel (the release has an sdist, which the page does not list); Weft v0.4.49: five wheels; pgserver pg18.6-pgv0.8.6-r2: twelve wheels, of which the nine for Python 3.11 to 3.13 are locked), each with a `#sha256=` fragment copied from that release's `SHA256SUMS` (the page records each SUMS file's own digest in a comment). `uv.lock` therefore records a `hash` for every truss-toolkit and weft-sql file, with the page as a relative path, `tests/test_truss_toolkit.py` asserts it, and `uv sync --locked --extra truss` verifies each wheel it installs against the lock, in the `check` and release jobs alike. What this verifies is the release's own `SHA256SUMS` as read when the page was written, not an independent signature. `uv sync --extra truss` is the development command: strict pyright needs the adapter's imports, so the `check` and release jobs sync it. The local PostgreSQL for the Truss tests is the separate group `truss-test` (`truss-toolkit[local]`, `pgserver-pg18`: Linux x86_64 and aarch64 and macOS 14 arm64 only, wheels without an sdist, so the group does not sync on macOS x86_64, Windows or musl), and tests that need it carry the `truss` marker, which `addopts = "-m 'not truss'"` leaves out of a default run. The test job's Weft parser is `weft-sql` 0.4.49, the version Truss pins, so the memory adapter and Truss compile with one parser. Adapters live in the `adapters` module group (`arras.adapters.<engine>`), which imports only the foundation, domain and contract groups; only a binding or the dev host may import it, and no module outside it loads `truss`, `psycopg` or `weft` at run time (`tests/test_modules.py`). Arras itself publishes to PyPI as `arras`, but PyPI does not carry the Truss wheels, so a host that installs `arras[truss]` vendors the pinned wheels or passes the find-links page (CONTRACT-005, Runtime).

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| `pip` + `venv` + hand-maintained `requirements.txt` | Ships with Python; what Databricks' own reference apps use; the pip path on Databricks Apps comes with 20 pre-installed libraries | No lockfile, so two machines resolve differently; no interpreter management; pins the app to Python 3.11 on Databricks Apps; the file drifts from `pyproject.toml` | Rejected: not reproducible, and it removes the interpreter choice |
| Poetry | Lockfile and `pyproject.toml`-native | Slower resolver, its own non-standard `[tool.poetry]` table, no interpreter management | Rejected: a second tool for the same job |
| conda / mamba | Manages non-Python binaries | Heavy, its own package index, does not fit a pure-Python service on a managed runtime | Rejected: wrong shape |
| One shared environment for every project | Fewer directories | A benchmark dependency can leak into production, and the projects' upgrade cycles couple | Rejected: isolation is the requirement |
| **uv, one project per implementation** | Lockfile, interpreter pinning, path dependencies between projects, fast resolution, already the repo's convention, matches the HELIX `python-uv` concern, and is the Databricks Apps-native path (`pyproject.toml` + `uv.lock` → `uv sync`, `requires-python` honoured) | Contributors need uv installed; no pre-installed libraries on the platform, so the dependency list must be complete | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | A reviewer runs `uv sync && uv run pytest` in any implementation directory and gets the same result the author did. The ontology package is consumed by the benchmark as a path dependency, so the model and the schema it generates cannot diverge. Lint, format and type checks are one command each and need no CI configuration to be meaningful. The committed `pyproject.toml` and `uv.lock` are the deployment artifact for Databricks Apps; nothing is translated at deploy time. |
| Negative | Two lockfiles to keep current instead of one. The 3.11 pin follows the host and must move with it. |
| Neutral | The repository's other tooling is unaffected. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A stray `requirements.txt` lands in an app directory and silently switches the app to pip and Python 3.11 | M | M | A repo check rejects `requirements.txt` under any Arras app directory; the deploy checklist repeats it |
| A runtime dependency is missing because the pip path's pre-installed libraries masked it in local testing | L | M | Local development also runs from `uv sync` with no global packages; `databricks apps run-local` uses the same uv environment |
| The host's `requires-python` and Arras's diverge | L | M | Arras declares `>=3.11`, no upper bound for the library; other projects pin `3.11` |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| Arras syncs and passes tests from a clean checkout with `uv sync && uv run pytest` | A reviewer cannot reproduce a result |
| No `requirements.txt` appears under any Arras app directory | One is committed |
| The praxis app deploys with Arras installed from `pyproject.toml` + `uv.lock` on the declared interpreter | The platform installs with pip, or refuses the declared `requires-python` |


## Concern Impact

- **Concern selection**: Confirms the `python-uv` library concern in [`concerns.md`](../../01-frame/concerns.md) and fills the `language-runtime` slot by ADR.
- **Practice override**: The library concern says Python 3.12+; Arras uses 3.11 to match its host. Recorded as an override with this ADR as record store. The `databricks-apps` concern's dependency practice is refined: `pyproject.toml` + `uv.lock`, never `requirements.txt`.

## References

- [`concerns.md`](../../01-frame/concerns.md): the `python-uv` row
- `pyproject.toml` and `uv.lock`: the project's own uv metadata and lock
- [ADR-006](ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md): the embedded library this toolchain builds
- [Manage dependencies for a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/dependencies): `requirements.txt` precedence, `pyproject.toml` + `uv.lock` → `uv sync`, `requires-python`, no pre-installed libraries on the uv path (read 19 Sep 2026)
- [Configure Databricks app execution with app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime): `command` and `env`; default command `python <first .py>` when absent
- [uv documentation](https://docs.astral.sh/uv/): lockfiles, `.python-version`, `[tool.uv.sources]`
