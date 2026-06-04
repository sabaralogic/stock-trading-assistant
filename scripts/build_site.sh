#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

./venv/bin/python main.py

rm -rf site
mkdir -p site

cp webapp/templates/index.html site/index.html
cp webapp/templates/stock.html site/stock.html
cp -R webapp/static site/static

touch site/.nojekyll

echo "Built static site at: $ROOT_DIR/site"
echo "To preview locally:"
echo "  cd site"
echo "  ../venv/bin/python -m http.server 8000"
