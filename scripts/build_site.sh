#!/usr/bin/env bash
# Assemble the static dashboard into site/ (Vercel's outputDirectory): the React build of frontend/ plus the committed
# snapshot of the verified run (python -m hourproof site export) as the /api files. Install first, with the pinned npm:
#   cd frontend && npx --yes npm@11.20.0 ci
set -euo pipefail
cd "$(dirname "$0")/.."
SNAPSHOT=(overview week carbon log)
for f in "${SNAPSHOT[@]}"; do
  test -s "deploy/snapshot/$f.json" || { echo "missing deploy/snapshot/$f.json: run python -m hourproof site export" >&2; exit 1; }
done
test -d frontend/node_modules || { echo "frontend/node_modules missing: cd frontend && npx --yes npm@11.20.0 ci" >&2; exit 1; }
echo "building with node $(node -v)"
(cd frontend && npm run build)
rm -rf site
mkdir -p site/api
cp -R frontend/dist/. site/
for f in "${SNAPSHOT[@]}"; do cp "deploy/snapshot/$f.json" site/api/; done
echo "site/ built: $(find site -type f | wc -l) files"
