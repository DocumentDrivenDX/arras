#!/usr/bin/env bash
# Build the documentation microsite into ./site, stamped with VERSION (default "dev").
#   scripts/build_site.sh 0.8.2
# Needs `uv sync --group docs` and a built static host (`cd ui && npm ci && npm run build:static`).
set -euo pipefail
cd "$(dirname "$0")/.."
version="${1:-dev}"
cp CHANGELOG.md docs/site/changelog.md
rm -rf docs/site/demo
(cd ui && node scripts/stage-static.mjs ../docs/site/demo ../examples/catalog/catalog.umf.json \
  ../examples/catalog/catalog.graph.json --title "Arras demo: software catalog")
# Stamp the version into the pages for the build only; restore the placeholders afterwards.
backup="$(mktemp -d)"
cp docs/site/index.md docs/site/quickstart.md "$backup/"
trap 'cp "$backup"/*.md docs/site/; rm -rf "$backup"' EXIT
for page in docs/site/index.md docs/site/quickstart.md; do
  python3 - "$page" "$version" <<'PY'
import sys
path, version = sys.argv[1:]
text = open(path, encoding="utf-8").read().replace("@VERSION@", version)
open(path, "w", encoding="utf-8").write(text)
PY
done
ARRAS_VERSION="$version" uv run --no-sync mkdocs build --strict
