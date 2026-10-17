#!/usr/bin/env bash
# Assemble the static dashboard into site/ (Vercel's outputDirectory). Needs only a POSIX shell: the data is the
# committed snapshot in deploy/snapshot/ (python -m hourproof site export), the code is web/ unchanged.
set -euo pipefail
cd "$(dirname "$0")/.."
for f in overview week carbon; do
  test -s "deploy/snapshot/$f.json" || { echo "missing deploy/snapshot/$f.json: run python -m hourproof site export" >&2; exit 1; }
done
rm -rf site
mkdir -p site/static site/api
cp web/index.html site/index.html
cp web/app.js web/carbon.js web/styles.css site/static/
cp deploy/snapshot/overview.json deploy/snapshot/week.json deploy/snapshot/carbon.json site/api/
echo "site/ built: $(find site -type f | wc -l) files"
